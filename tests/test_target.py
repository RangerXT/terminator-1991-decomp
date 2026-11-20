"""track_target and approx_distance against the originals at 0000:A2D5 and 0000:5EEE.

Captures: python tools/capture.py 0000:A2D5 target --count 20 --skip 9 --ticks 30

Target collection is normally off, so each recording is also replayed with it switched on
and every kind of object flag.
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


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.track_target.restype = ctypes.c_uint8
    lib.approx_distance.restype = ctypes.c_uint16
    fails = []
    rnd = random.Random(0xA2D5)

    m = ctx.game()
    for _ in range(3000):
        a = [rnd.choice((rnd.randint(-32768, 32767), rnd.randint(-300, 300), 0, -32768, 32767)) for _ in range(4)]
        r = m.call(0x0000, 0x5EEE, ax=a[0], bx=a[1], cx=a[2], dx=a[3])
        got = lib.approx_distance(*[ctypes.c_int16(v) for v in a])
        CASES += 1
        if got != r['ax']:
            fails.append(f'approx_distance{tuple(a)}: original {r["ax"]} C {got}')

    for n, (before, after, rin, rout) in enumerate(capture.replay('target')):
        ds = ctypes.create_string_buffer(before.ds_read(0, 0x10000), 0x10000)
        al = lib.track_target(ds, ctypes.c_uint8(rin['ax'] & 0xFF))
        CASES += 1
        if ds.raw[:DS_END] != after.ds_read(0, DS_END) or al != (rout['ax'] & 0xFF):
            fails.append(f'capture {n}: differs (AL {al:02X} vs {rout["ax"] & 0xFF:02X})')

        mm = before
        for flags in (0x0020, 0x0024, 0x2000, 0x4000, 0x6001, 0x0000, 0x0003):
            saved = mm.ds_read(0, 0x10000)
            mm.ds_write(0x118E, b'\xFF')
            mm.ds_write(0x57C6, struct.pack('<H', flags))
            mm.ds_write(0xB64E, struct.pack('<H', rnd.randint(0, 5)))
            mm.ds_write(0x57C4, struct.pack('<H', rnd.choice((rnd.randint(0, 40), mm.rw(mm.DATA_SEG, 0x9A64)))))
            ds = ctypes.create_string_buffer(mm.ds_read(0, 0x10000), 0x10000)
            al_in = rnd.randint(0, 255)
            r = mm.call(0x0000, 0xA2D5, ax=al_in, bx=rin['bx'])
            want = mm.ds_read(0, DS_END)
            mm.ds_write(0, saved)
            al = lib.track_target(ds, ctypes.c_uint8(al_in))
            CASES += 1
            if ds.raw[:DS_END] != want:
                diff = [i for i in range(DS_END) if ds.raw[i] != want[i]]
                fails.append(f'capture {n} flags {flags:04X}: {len(diff)} bytes differ, first at DS:{diff[0]:04X}')
            elif al != (r['ax'] & 0xFF):
                fails.append(f'capture {n} flags {flags:04X}: AL {al:02X} vs original {r["ax"] & 0xFF:02X}')
    return fails
