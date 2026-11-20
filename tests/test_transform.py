"""object_transform_vertices against recorded calls of the original at 0000:29C4.

Captures: python tools/capture.py 0000:29C4 transform --count 16 --skip 5 --ticks 60 --keys "2:right:20,30:up:25"
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import capture  # noqa: E402

CASES = 0
DS_END = 0xEA70          # the data segment proper; above it is the stack


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.object_transform_vertices.restype = ctypes.c_int
    fails = []
    for n, (before, after, rin, rout) in enumerate(capture.replay('transform')):
        ds = ctypes.create_string_buffer(before.ds_read(0, 0x10000), 0x10000)
        status = lib.object_transform_vertices(ds, ctypes.c_uint16(rin['bx']))
        want = after.ds_read(0, DS_END)
        CASES += 1
        if status != 0:
            fails.append(f'capture {n}: C version does not handle this path')
        elif ds.raw[:DS_END] != want:
            diff = [i for i in range(DS_END) if ds.raw[i] != want[i]]
            fails.append(f'capture {n}: {len(diff)} bytes differ, first at DS:{diff[0]:04X}')
    return fails
