"""string_copy (0000:FA4B) and number_format (0000:F604) against the original.

Random strings (lengths 0 to 300, any non-zero bytes) copied between places in the data
segment; random values and the edge values 0, 1, base - 1, base, base squared and 65535 in
every base from 0 to 36, and in 40, 100, 200 and 255 (digit characters past Z). Compared:
the whole data segment (but the call's own stack) and the registers returned or kept.
"""
import ctypes
import random

import dosemu

CASES = 0


def same_outside_stack(got, m):
    """The data segment equal, except where the call itself pushed (SS:SP lies inside it)."""
    want = m.ds_read(0, 0x10000)
    stack = ((m.r(dosemu.UC_X86_REG_SS) << 4) + m.r(dosemu.UC_X86_REG_SP) - (m.DATA_SEG << 4)) & 0xFFFF
    lo, hi = max(stack - 128, 0), min(stack + 8, 0x10000)
    return got[:lo] == want[:lo] and got[hi:] == want[hi:]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.string_copy.restype = ctypes.c_uint16
    lib.string_copy.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]
    lib.number_format.restype = ctypes.c_uint16
    lib.number_format.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint8]
    m = ctx.game()
    saved = m.ds_read(0, 0x10000)
    rng = random.Random(0xFA4B)
    fails = []
    try:
        for i in range(400):
            m.ds_write(0, saved)
            length = rng.choice([0, 1, 2, 3, rng.randrange(300)])
            src, dest = rng.randrange(0x8000, 0x9000), rng.randrange(0xA000, 0xB000)
            m.ds_write(src, bytes(rng.randrange(1, 256) for _ in range(length)) + b'\0')
            ds = ctx.ds_copy()
            got = lib.string_copy(ds, dest, src)
            regs = m.call(0, 0xFA4B, si=src, di=dest, cx=0x1234)
            CASES += 1
            if got != regs['di'] or regs['si'] != src or regs['cx'] != 0x1234 or not same_outside_stack(ds.raw, m):
                fails.append(f'string_copy {i}: length {length}, DI C {got:04X} original {regs["di"]:04X}')
                break
        for base in list(range(37)) + [40, 100, 200, 255]:
            values = [0, 1, base, max(base - 1, 0), base * base, 65535] + [rng.randrange(65536) for _ in range(40)]
            for value in values:
                m.ds_write(0, saved)
                dest = rng.randrange(0xA000, 0xB000)
                ds = ctx.ds_copy()
                got = lib.number_format(ds, dest, value & 0xFFFF, base)
                regs = m.call(0, 0xF604, ax=value & 0xFFFF, bx=base | 0x5500, si=dest, cx=0x4321)
                CASES += 1
                if (got != regs['si'] or regs['ax'] != value & 0xFFFF or regs['bx'] != base | 0x5500
                        or regs['cx'] != 0x4321 or not same_outside_stack(ds.raw, m)):
                    fails.append(f'number_format: {value} in base {base}: SI C {got:04X} original {regs["si"]:04X}')
                    return fails
    finally:
        m.ds_write(0, saved)
    return fails
