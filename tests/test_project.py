"""project_vertices against recorded calls of the original at 0000:46AC.

Captures: python tools/capture.py 0000:46AC project --count 24 --skip 9 --ticks 40 --keys "2:right:12,18:up:15"

Each recording is also replayed with every vertex pushed to extreme coordinates, to exercise
the divide-overflow path, which normal gameplay hits only occasionally.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import capture  # noqa: E402
import dosemu  # noqa: E402

CASES = 0
DS_END = 0xEA70


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.project_vertices.restype = ctypes.c_int
    fails = []
    for n, (before, after, rin, rout) in enumerate(capture.replay('project')):
        ds = ctypes.create_string_buffer(before.ds_read(0, 0x10000), 0x10000)
        carry = lib.project_vertices(ds)
        want = after.ds_read(0, DS_END)
        CASES += 1
        if ds.raw[:DS_END] != want:
            diff = [i for i in range(DS_END) if ds.raw[i] != want[i]]
            fails.append(f'capture {n}: {len(diff)} bytes differ, first at DS:{diff[0]:04X}')
        elif carry != (rout['flags'] & 1):
            fails.append(f'capture {n}: carry {carry} vs original {rout["flags"] & 1}')

    # synthetic vertices on top of the last recorded state
    rnd = random.Random(46)
    m = before
    src = m.rw(m.DATA_SEG, 0x3CDC)
    end = m.rw(m.DATA_SEG, 0x4B86)
    count = (end - src) // 6
    for trial in range(60):
        verts = b''
        for _ in range(count):
            span = rnd.choice((30, 300, 3000, 32768))
            x, y = rnd.randint(-span, span - 1), rnd.randint(-span, span - 1)
            z = rnd.choice((0, 1, 5, 40, 400, 4000, 32767, -1, rnd.randint(-100, 32767)))
            verts += struct.pack('<3h', x, y, z)
        m.ds_write(src, verts)
        m.ds_write(0x114D, bytes([rnd.choice((0, 0, 0xFF))]))
        m.ds_write(0x114F, bytes([rnd.choice((0, 0, 0xFF))]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 0x10000), 0x10000)
        r = m.call(0x0000, 0x46AC)
        want = m.ds_read(0, DS_END)
        carry = lib.project_vertices(ds)
        CASES += 1
        if ds.raw[:DS_END] != want:
            diff = [i for i in range(DS_END) if ds.raw[i] != want[i]]
            fails.append(f'synthetic {trial}: {len(diff)} bytes differ, first at DS:{diff[0]:04X}')
        elif carry != (r['flags'] & 1):
            fails.append(f'synthetic {trial}: carry {carry} vs original {r["flags"] & 1}')
    return fails
