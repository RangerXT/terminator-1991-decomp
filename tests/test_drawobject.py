"""draw_object against recorded calls of the original at 0000:2AF2: one whole object from
camera-space vertices to pixels.

Captures: python tools/capture.py 0000:2AF2 drawobject --count 60 --skip 3 --ticks 40 --keys "2:right:12,18:up:15"

Compared after each call: the data segment and all four EGA bit planes.
"""
import ctypes
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from test_polyfill import PLANE_BYTES, SCREEN_BYTES, check, planes_of  # noqa: E402

CASES = 0


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.draw_object.restype = ctypes.c_int
    fails = []
    results = {0: 0, 1: 0}
    changed_screen = 0
    for n, (before, after, rin, rout) in enumerate(capture.replay('drawobject')):
        ds = ctypes.create_string_buffer(before.ds_read(0, 0x10000), 0x10000)
        start = planes_of(before)
        planes = ctypes.create_string_buffer(start, SCREEN_BYTES)
        status = lib.draw_object(ds, planes, ctypes.c_uint16(rin['bx']), ctypes.c_uint8(before.DATA_SEG & 0xFF))
        CASES += 1
        if status not in (0, 1):
            fails.append(f'capture {n}: C version returned {status}')
            continue
        results[status] += 1
        if planes_of(after)[:PLANE_BYTES] != start[:PLANE_BYTES]:
            changed_screen += 1
        check(f'capture {n}', ds, planes, after, fails)

        # the same object pushed far to one side, to exercise the "off screen" exit
        m = before
        mesh = rin['bx']
        buf = m.rw(m.DATA_SEG, 0x3CDC)
        count = m.rw(m.DATA_SEG, mesh + 4)
        shift = 12000 if n % 2 else -12000
        verts = bytearray(m.ds_read(buf, count * 6))
        for i in range(count):
            x = struct.unpack_from('<h', verts, i * 6)[0]
            struct.pack_into('<h', verts, i * 6, max(-32768, min(32767, x + shift)))
        m.ds_write(buf, bytes(verts))
        ds = ctypes.create_string_buffer(m.ds_read(0, 0x10000), 0x10000)
        planes = ctypes.create_string_buffer(planes_of(m), SCREEN_BYTES)
        m.call(0x0000, 0x2AF2, bx=mesh)
        status = lib.draw_object(ds, planes, ctypes.c_uint16(mesh), ctypes.c_uint8(m.DATA_SEG & 0xFF))
        CASES += 1
        if status in (0, 1):
            results[status] += 1
        check(f'capture {n} pushed aside', ds, planes, m, fails)
    print(f'    drawobject cases: {results[0]} drawn, {results[1]} off screen; '
          f'{changed_screen} recordings changed the screen')
    return fails
