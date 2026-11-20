"""draw_visible_faces (with line_to and polygon_outline) against recorded calls of the
original at 0000:482B.

Captures: python tools/capture.py 0000:482B drawfaces --count 40 --skip 5 --ticks 40 --keys "2:right:12,18:up:15"

Compared after each call: the data segment and all four EGA bit planes. Each recording is
also replayed with every face forced to "filled and outlined" so that the outline code and
all line directions are exercised whatever the recordings happen to contain.
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


def faces_of(raw, mesh):
    count = struct.unpack_from('<H', raw, mesh + 2)[0]
    face = struct.unpack_from('<H', raw, mesh + 6)[0]
    out = []
    for _ in range(count):
        out.append(face)
        face += 6 + 2 * struct.unpack_from('<H', raw, face + 4)[0]
    return out


def run(ctx):
    global CASES
    lib = ctx.lib
    fails = []
    outlined = 0
    for n, (before, after, rin, rout) in enumerate(capture.replay('drawfaces')):
        mesh = rin['bx']
        raw = before.ds_read(0, 0x10000)
        outlined += sum(1 for f in faces_of(raw, mesh) if raw[f + 2] & 2)
        ds = ctypes.create_string_buffer(raw, 0x10000)
        planes = ctypes.create_string_buffer(planes_of(before), SCREEN_BYTES)
        dx = lib.draw_visible_faces_dx(ds, planes, mesh, rin['dx'])
        if dx != rout['dx']:
            return [f'capture {n}: DX {dx:04X} vs {rout["dx"]:04X}']
        CASES += 1
        check(f'capture {n}', ds, planes, after, fails)

        # forced outlines: flags = 3 and a visible outline colour on every face
        m = before
        for k, f in enumerate(faces_of(raw, mesh)):
            m.ds_write(f + 1, bytes([(k * 5 + 1) & 15]))
            m.ds_write(f + 2, b'\x03\x00')
        ds = ctypes.create_string_buffer(m.ds_read(0, 0x10000), 0x10000)
        planes = ctypes.create_string_buffer(planes_of(m), SCREEN_BYTES)
        out = m.call(0x0000, 0x482B, bx=mesh, dx=rin['dx'])
        dx = lib.draw_visible_faces_dx(ds, planes, mesh, rin['dx'])
        if dx != out['dx']:
            return [f'outlined {n}: DX {dx:04X} vs {out["dx"]:04X}']
        CASES += 1
        check(f'capture {n} with forced outlines', ds, planes, m, fails)
    print(f'    drawfaces recordings: {outlined} outlined faces in the unmodified data')
    return fails
