"""Map action priority against the executable, stopping before platform waits."""
import ctypes
import os
import sys
import struct
import random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
import dosemu

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/local_map.pkl'))
    saved = m.ds_read(0, 65536)
    ctx.lib.map_requested_action.restype = ctypes.c_uint8
    for blocked in [0, 1, 128, 255]:
        for fast in [0, 1, 128, 255]:
            for home in [0, 1, 128, 255]:
                m.ds_write(0, saved)
                for at, val in [(0x01DE, blocked), (0x5BFA, fast), (0x5BFC, home), (0xE25A, 123)]:
                    m.ds_write(at, bytes([val]))
                ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
                result = ctx.lib.map_requested_action(ds)
                # Both target points precede any RET or retrace call, so no artificial
                # return address or BIOS stub is needed for this bounded comparison.
                target = 0xCC8B if (not blocked and fast) or home else 0xCC6E
                m.cs, m.ip = dosemu.LOAD_SEG, 0xCC46
                m.step((dosemu.LOAD_SEG << 4) + target, 100)
                CASES += 1
                if m.ip != target or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                    fails.append(f'blocked={blocked}, F={fast}, H={home}: state differs')
                if result != m.ds_read(0xE25A, 1)[0]:
                    fails.append('returned action differs')
    rng = random.Random(0xD2BE)
    for i in range(256):
        m.ds_write(0, saved)
        values = [rng.randrange(65536) for _ in range(4)]
        if i == 0:
            values = [0, 65535, 65535, 65535]
        m.ds_write(0xE26A, struct.pack('<HHHH', *values))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.map_write_destination_position(ds)
        m.cs, m.ip = dosemu.LOAD_SEG, 0xD2BE
        m.step((dosemu.LOAD_SEG << 4) + 0xD2F3, 100)
        CASES += 1
        if m.ip != 0xD2F3 or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            fails.append(f'destination position {values}: state differs')
    return fails
