"""build_ground_list against the original at 0000:3D62-3D80 (inside update_visible_cells):
the ground meshes around the player become the ground draw list.

Captures: python tools/capture.py 0000:3D62 ground --count 24 --skip 0 --ticks 260 --keys "2:right:40,50:up:30,90:left:60,160:up:40,210:right:30"

Variants: the player moved to 12 other cells of the loaded window, and the list area
pre-filled with other bytes (the last word of each record is never written, yet takes part
in the duplicate test). Compared: all conventional memory except the stack.
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
import dosemu  # noqa: E402
from test_drawlist import compare, make_game  # noqa: E402

CASES = 0
END = 0x3D81


def run_original(m):
    until = (dosemu.LOAD_SEG << 4) + END
    uc = m.uc
    uc.reg_write(dosemu.UC_X86_REG_EFLAGS, uc.reg_read(dosemu.UC_X86_REG_EFLAGS) & ~dosemu.IF_ & 0xFFFF)
    m.pending = None
    for _ in range(60):
        m.step(until, 1_000_000)
        if m.pending is not None:
            m._apply_pending()
            if m.blocked:
                raise RuntimeError(m.blocked)
            continue
        if (m.cs << 4) + m.ip == until:
            return
    raise RuntimeError('did not reach the end of the ground list builder')


def variants():
    yield 'as recorded', lambda m: None
    rng = random.Random(7)

    def scribble(m):
        m.ds_write(0x2836, bytes(rng.randrange(256) for _ in range(12 * 230)))
    yield 'list area scribbled', scribble
    for k in range(12):
        def move(m, k=k):
            player = m.rw(m.DATA_SEG, 0x03A0)
            col0, row0 = m.rw(m.DATA_SEG, 0x7272), m.rw(m.DATA_SEG, 0x7274)
            m.ds_write(player + 0x1E, struct.pack('<H', col0 + 1 + (k * 7) % 22))
            m.ds_write(player + 0x20, struct.pack('<H', row0 + 1 + (k * 5 + 3) % 22))
        yield f'player moved {k}', move


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.build_ground_list.restype = None
    fails = []
    states = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'ground.pkl.gz'), 'rb'))
    sizes = []
    for n, st in enumerate(states):
        for label, change in variants():
            m = capture.restore(st)
            change(m)
            g, mem, planes = make_game(m)
            lib.build_ground_list(ctypes.byref(g))
            CASES += 1
            where = f'capture {n}, {label}'
            try:
                run_original(m)
            except Exception as e:
                fails.append(f'{where}: original: {e}')
                continue
            if compare(where, mem, planes, m, fails):
                sizes.append(m.rw(m.DATA_SEG, 0x91D8))
    if sizes:
        print(f'    ground: list sizes {min(sizes)}..{max(sizes)}, {sum(sizes)} records in all')
    return fails
