"""mesh_order_faces against the original at 0000:2D2A.

Captures: python tools/capture.py 0000:2D2A order --count 60 --skip 3 --ticks 40 --keys "2:right:12,18:up:15"

Each recording is also replayed with a forced pivot face and random hidden flags, because in
normal play the pivot face is usually visible and the routine then does nothing.
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
    lib.mesh_order_faces.restype = ctypes.c_int
    fails = []
    rnd = random.Random(2)
    reordered = 0
    for n, (before, after, rin, rout) in enumerate(capture.replay('order')):
        mesh = rin['si']
        raw = before.ds_read(0, 0x10000)
        ds = ctypes.create_string_buffer(raw, 0x10000)
        lib.mesh_order_faces(ds, ctypes.c_uint16(mesh))
        want = after.ds_read(0, DS_END)
        CASES += 1
        compare(f'capture {n}', ds, want, fails)
        if raw[mesh + 6:mesh + 8] != want[mesh + 6:mesh + 8]:
            reordered += 1

        m = before
        nfaces = struct.unpack_from('<H', raw, mesh + 2)[0]
        flags = struct.unpack_from('<H', raw, 0x40E0)[0]
        if nfaces < 2:
            continue
        for trial in range(4):
            pivot = rnd.randint(1, nfaces - 1)
            hidden = bytearray(rnd.choice((0, 0, 1)) for _ in range(nfaces))
            hidden[pivot - 1] = rnd.choice((1, 1, 1, 0))
            saved = m.ds_read(0, 0x10000)
            m.ds_write(mesh + 0x0C, struct.pack('<H', pivot))
            m.ds_write(flags, bytes(hidden))
            m.ds_write(0x00BB, b'\0')
            ds = ctypes.create_string_buffer(m.ds_read(0, 0x10000), 0x10000)
            m.call(0x0000, 0x2D2A, si=mesh)
            want = m.ds_read(0, DS_END)
            m.ds_write(0, saved)
            status = lib.mesh_order_faces(ds, ctypes.c_uint16(mesh))
            CASES += 1
            if status != 0:
                fails.append(f'capture {n} forced {trial}: C version does not handle this path')
            else:
                compare(f'capture {n} forced {trial}', ds, want, fails)
    print(f'    order recordings: {reordered} of the unmodified calls reordered their faces')
    return fails
