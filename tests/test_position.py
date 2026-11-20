"""Position normalization and cell rebasing against original 2F1C."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(__file__))
from test_drawlist import make_game, compare
CASES = 0
def run(ctx):
    global CASES
    fails = []
    m = ctx.game()
    saved = m.ds_read(0, 65536)
    for i in range(81):
        m.ds_write(0, saved)
        p = m.rw(m.DATA_SEG, 0x3A0)
        x, z = m.rw(m.DATA_SEG, p + 30), m.rw(m.DATA_SEG, p + 32)
        m.ds_write(p + 34, struct.pack('<I', (x + i % 3 - 1) * 1024 + i * 7))
        m.ds_write(p + 42, struct.pack('<I', (z + (i // 3) % 3 - 1) * 1024 + i * 9))
        m.ds_write(0x5A25, bytes([255 if i % 2 else 0]))
        m.ds_write(0x5EF6, bytes([i % 3]))
        g, mem, planes = make_game(m)
        ctx.lib.position_normalize(ctypes.byref(g), p)
        m.call(0, 0x2F1C, si=p)
        CASES += 1
        compare(f'position {i}', mem, planes, m, fails)
        if fails:
            break
    m.ds_write(0, saved)
    for x in range(-3, 4):
        for z in range(-3, 4):
            m.ds_write(0, saved)
            p = m.rw(m.DATA_SEG, 0x3A0)
            m.ds_write(0x53C + 30, struct.pack('<H', (m.rw(m.DATA_SEG, p + 30) + x) & 65535))
            m.ds_write(0x53C + 32, struct.pack('<H', (m.rw(m.DATA_SEG, p + 32) + z) & 65535))
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            got = ctx.lib.position_relative_actor(ds)
            out = m.call(0, 0xB660)
            CASES += 1
            if got != (out['flags'] & 1) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                fails.append(f'relative actor {x},{z}: differs')
    m.ds_write(0, saved)
    return fails
