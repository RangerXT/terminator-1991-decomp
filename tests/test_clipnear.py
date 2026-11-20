"""mesh_clip_near against recorded calls of the original at 0000:24EA.

Captures: python tools/capture.py 0000:24EA clipnear --count 40 --skip 5 --ticks 40 --keys "2:right:12,18:up:15"

Only some recordings have vertices behind the camera, so each one is also replayed with
randomised depths to force clipping (and the occasional divide overflow).
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import capture  # noqa: E402

CASES = 0
DS_END = 0xEA70


def compare(label, ds, want, fails):
    if ds.raw[:DS_END] != want:
        diff = [i for i in range(DS_END) if ds.raw[i] != want[i]]
        fails.append(f'{label}: {len(diff)} bytes differ, first at DS:{diff[0]:04X}')


def run(ctx):
    global CASES
    lib = ctx.lib
    fails = []
    rnd = random.Random(24)
    clipped = 0
    for n, (before, after, rin, rout) in enumerate(capture.replay('clipnear')):
        mesh = rin['bx']
        raw = before.ds_read(0, 0x10000)
        if raw[0x4B6E]:
            clipped += 1
        ds = ctypes.create_string_buffer(raw, 0x10000)
        lib.mesh_clip_near(ds, ctypes.c_uint16(mesh))
        CASES += 1
        compare(f'capture {n}', ds, after.ds_read(0, DS_END), fails)

        # forced clipping on the same mesh: new depths for every vertex
        m = before
        src = m.rw(m.DATA_SEG, 0x3CDC)
        count = m.rw(m.DATA_SEG, mesh + 4)
        for trial in range(3):
            verts = b''
            behind = 0
            for _ in range(count):
                span = rnd.choice((50, 500, 20000))
                x, y = rnd.randint(-span, span), rnd.randint(-span, span)
                z = rnd.choice((rnd.randint(-300, 300), rnd.randint(-32768, 32767), 0, -1, 1))
                behind += z < 0
                verts += struct.pack('<3h', x, y, z)
            m.ds_write(src, verts)
            m.ds_write(0x4B6E, bytes([behind & 0xFF]))
            ds = ctypes.create_string_buffer(m.ds_read(0, 0x10000), 0x10000)
            saved = m.ds_read(0, 0x10000)
            m.call(0x0000, 0x24EA, bx=mesh)
            want = m.ds_read(0, DS_END)
            m.ds_write(0, saved)                 # the routine repoints the mesh; undo for the next trial
            lib.mesh_clip_near(ds, ctypes.c_uint16(mesh))
            CASES += 1
            compare(f'capture {n} forced {trial}', ds, want, fails)
    if clipped == 0:
        fails.append('no recording has vertices behind the camera')
    return fails
