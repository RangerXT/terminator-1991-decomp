"""mesh_face_visibility against recorded calls of the original at 11BC:159C.

Captures: python tools/capture.py 11BC:159C visibility --count 24 --skip 9 --ticks 40 --keys "2:right:12,18:up:15"
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import capture  # noqa: E402

CASES = 0
DS_END = 0xEA70


def run(ctx):
    global CASES
    lib = ctx.lib
    fails = []
    kinds = set()
    for n, (before, after, rin, rout) in enumerate(capture.replay('visibility', far=True)):
        raw = before.ds_read(0, 0x10000)
        mesh = rin['bx']
        # note which table values this capture exercises
        table = int.from_bytes(raw[mesh + 0x0A:mesh + 0x0C], 'little')
        count = int.from_bytes(raw[mesh + 2:mesh + 4], 'little')
        for t in raw[table:table + count]:
            kinds.add('test' if t == 0 else 'two-sided' if t & 0x80 else 'copy')
        ds = ctypes.create_string_buffer(raw, 0x10000)
        lib.mesh_face_visibility(ds, ctypes.c_uint16(mesh), ctypes.c_uint8(rin['ax'] & 0xFF))
        want = after.ds_read(0, DS_END)
        CASES += 1
        if ds.raw[:DS_END] != want:
            diff = [i for i in range(DS_END) if ds.raw[i] != want[i]]
            fails.append(f'capture {n}: {len(diff)} bytes differ, first at DS:{diff[0]:04X}')
    missing = {'test', 'copy', 'two-sided'} - kinds
    if missing:
        fails.append(f'captures never exercise: {sorted(missing)}')
    return fails
