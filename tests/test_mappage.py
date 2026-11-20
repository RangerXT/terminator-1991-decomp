"""The overhead map: matrix_from_angles (0000:1C1A), matrix_apply (0000:1C33) on random
input, and map_page_update against recordings of the original at 0000:CE19 (the point in
0000:CE12 reached only in frames where the lists have just been rebuilt).

Captures: python tools/capture.py 0000:CE19 mappage --count 14 --skip 0 --ticks 700 --keys "2:right:200,210:up:150,370:left:200,580:up:100"

Each recording is also run from other camera heights, with both zooms on, and with the
"off screen" flags of the ground records set beforehand. Compared: all conventional memory
except the stack, the four bit planes and the card's registers.
"""
import ctypes
import gzip
import os
import pickle
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from test_drawlist import compare, make_game  # noqa: E402
from test_polyfill import PLANE_BYTES, planes_of  # noqa: E402

CASES = 0
MATRIX = (0x4164, 0x4188)        # the matrix and its workspace


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.map_page_update.restype = ctypes.c_int
    fails = []
    m = ctx.game()
    rng = random.Random(11)

    saved = m.ds_read(0x3CD6, 6)
    saved_matrix = m.ds_read(MATRIX[0], MATRIX[1] - MATRIX[0])
    angle_sets = [(0x17E, 0, 0), (0, 0, 0), (128, 128, 128), (511, 511, 511), (1, 2, 3)]
    angle_sets += [tuple(rng.randrange(512) for _ in range(3)) for _ in range(300)]
    for a, b, c in angle_sets:
        m.call(0x0000, 0x1C1A, ax=a, bx=b, cx=c)
        want = m.ds_read(MATRIX[0], MATRIX[1] - MATRIX[0])
        ds = ctx.ds_copy()
        lib.matrix_from_angles(ds, ctypes.c_uint16(a), ctypes.c_uint16(b), ctypes.c_uint16(c))
        CASES += 1
        if ds.raw[MATRIX[0]:MATRIX[1]] != want:
            fails.append(f'matrix_from_angles({a}, {b}, {c}): matrix differs')
            break
        # the same matrix applied to a few points
        for _ in range(12):
            x, y, z = (rng.choice([rng.randrange(-32768, 32768), rng.randrange(-3000, 3000), -32768, 32767, 0])
                       for _ in range(3))
            out = m.call(0x0000, 0x1C33, ax=x, bx=y, cx=z)
            cx_, cy_, cz_ = ctypes.c_int16(x), ctypes.c_int16(y), ctypes.c_int16(z)
            ds2 = ctypes.create_string_buffer(m.ds_read(0, 0x10000), 0x10000)
            lib.matrix_apply(ds2, ctypes.byref(cx_), ctypes.byref(cy_), ctypes.byref(cz_))
            CASES += 1
            got = (cx_.value & 0xFFFF, cy_.value & 0xFFFF, cz_.value & 0xFFFF)
            if got != (out['ax'], out['bx'], out['cx']):
                fails.append(f'matrix_apply({x}, {y}, {z}) with angles {a},{b},{c}: {got}, original '
                             f'{(out["ax"], out["bx"], out["cx"])}')
                break
        if fails:
            break
    m.ds_write(0x3CD6, saved)
    m.ds_write(MATRIX[0], saved_matrix)
    if fails:
        return fails

    def variants():
        yield 'as recorded', lambda mm: None
        yield 'both zooms on', lambda mm: (mm.ds_write(0x114D, b'\xff'), mm.ds_write(0x114F, b'\xff'))

        def flags(mm):
            n = mm.rw(mm.DATA_SEG, 0x91D8)
            for i in range(0, n, 2):
                rec = 0x2836 + 12 * i + 6
                mm.ds_write(rec, struct.pack('<H', mm.rw(mm.DATA_SEG, rec) | 8))
        yield 'off-screen flags set', flags

        def moved(mm):
            player = mm.rw(mm.DATA_SEG, 0x03A0)
            mm.ds_write(player, struct.pack('<H', 37))
            mm.ds_write(player + 4, struct.pack('<H', 990))
        yield 'player in a corner of the cell', moved

    states = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'mappage.pkl.gz'), 'rb'))
    drew = 0
    for n, st in enumerate(states):
        for label, change in variants():
            mm = capture.restore(st)
            change(mm)
            g, mem, planes = make_game(mm)
            start = planes.raw
            status = lib.map_page_update(ctypes.byref(g))
            CASES += 1
            where = f'capture {n}, {label}'
            try:
                capture.run_to_return(mm, max_instr=30_000_000)
            except Exception as e:
                fails.append(f'{where}: original: {e} (C returned {status})')
                continue
            if status != 0:
                fails.append(f'{where}: C version returned {status}')
                continue
            if compare(where, mem, planes, mm, fails):
                drew += sum(1 for i in range(PLANE_BYTES) if start[i] != planes.raw[i])
    print(f'    mappage: {len(states)} recordings; {drew} plane bytes drawn on the map page in all')
    return fails
