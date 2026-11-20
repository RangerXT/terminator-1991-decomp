"""mesh_clip_window against recorded calls of the original at 0000:1F6A.

Captures: python tools/capture.py 0000:1F6A clip2d --count 40 --skip 5 --ticks 40 --keys "2:right:12,18:up:15"

Each recording is also replayed with randomised screen points and outcode bits, so that
every edge, the two-buffer ping-pong and the divide-overflow path are exercised.
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
    rnd = random.Random(1970)
    real_clips = 0
    for n, (before, after, rin, rout) in enumerate(capture.replay('clip2d')):
        mesh = rin['bx']
        raw = before.ds_read(0, 0x10000)
        if raw[0x4B70]:
            real_clips += 1
        ds = ctypes.create_string_buffer(raw, 0x10000)
        lib.mesh_clip_window(ds, ctypes.c_uint16(mesh))
        CASES += 1
        compare(f'capture {n}', ds, after.ds_read(0, DS_END), fails)

        m = before
        pts = m.rw(m.DATA_SEG, 0x40DE)
        count = m.rw(m.DATA_SEG, mesh + 4)
        for trial in range(4):
            data = b''
            for _ in range(count):
                span = rnd.choice((200, 600, 5000, 32767))
                x = rnd.choice((rnd.randint(-span, span), 8, 311, 7, 312))
                y = rnd.choice((rnd.randint(-span, span), 8, 110, 7, 111))
                data += struct.pack('<3h', x, y, rnd.randint(0, 3000))
            m.ds_write(pts, data)
            m.ds_write(0x4B70, bytes([rnd.choice((1, 2, 3, 4, 8, 12, 15, 5, 10, 15))]))
            m.ds_write(0x4B6E, bytes([0]))
            saved = m.ds_read(0, 0x10000)
            ds = ctypes.create_string_buffer(saved, 0x10000)
            m.call(0x0000, 0x1F6A, bx=mesh)
            want = m.ds_read(0, DS_END)
            m.ds_write(0, saved)
            lib.mesh_clip_window(ds, ctypes.c_uint16(mesh))
            CASES += 1
            compare(f'capture {n} forced {trial}', ds, want, fails)
    if real_clips == 0:
        fails.append('no recording actually needed clipping')
    return fails
