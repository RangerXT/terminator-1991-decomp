"""Homing panel composition checked against 0000:CB4B."""
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
    for i in range(48):
        m.ds_write(0, saved)
        player = m.rw(m.DATA_SEG, 0x03A0)
        m.ds_write(0xE1EF, bytes([255 if i % 4 else 0]))
        m.ds_write(0x11CA, bytes([1 if i % 5 == 0 else 0]))
        m.ds_write(player + 14, bytes([1 if i % 3 else 2]))
        m.ds_write(0xE26A, struct.pack('<HHHH', (i * 13) % 192, (i * 7) % 128, i * 19, i * 21))
        g, mem, planes = make_game(m)
        ctx.lib.map_draw_homing(ctypes.byref(g))
        m.call(0, 0xCB4B)
        CASES += 1
        compare(f'homing {i}', mem, planes, m, fails)
        if fails:
            break
    m.ds_write(0, saved)
    return fails
