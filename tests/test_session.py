"""Session set-up (src/session.c) against the original 0000:0B12, 0B4E, 0B80, 1483, 057C,
97BF, 9845 and 97B4, from the in-game snapshot with the areas they read filled with random
bytes (levels 0..7 for 0B4E, Reese or not for 057C, random places for 97B4). Compared: all
memory but the stack.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import compare, regions  # noqa: E402

CASES = 0


def run(ctx):
    global CASES
    lib = ctx.lib
    fails = []
    rng = random.Random(0x0B12)
    for i in range(96):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        kind = i % 8
        m.ds_write(0x04D4, bytes(rng.randrange(256) for _ in range(0x100)))
        pointers = m.ds_read(0x1200, 12)                      # the far targets of 0B12's copies stay
        m.ds_write(0x11CE, bytes(rng.randrange(256) for _ in range(0x2C + 0x3C + 0xC4)))
        m.ds_write(0x1200, pointers)
        m.ds_write(0x055E, bytes(rng.randrange(256) for _ in range(4)))
        regs = {}
        g, mem, planes = make_game(m)
        if kind == 0:
            lib.session_reset(ctypes.byref(g))
            address = 0x0B12
        elif kind == 1:
            m.ds_write(0x1176, struct.pack('<H', i // 8 % 8 if i % 16 else rng.randrange(0x10000)))
            g, mem, planes = make_game(m)
            lib.session_pointers(ctypes.c_void_p(g.ds))
            address = 0x0B4E
        elif kind == 2:
            page = rng.randrange(4)
            regs = {'ax': page}
            lib.session_draw_page_wide(ctypes.c_void_p(g.ds), page)
            address = 0x0B80
        elif kind == 3:
            lib.session_row_table(ctypes.c_void_p(g.ds))
            address = 0x1483
        elif kind == 4:
            if i % 16 < 8:
                m.ds_write(0x03A0, struct.pack('<H', 0x04D4))
            g, mem, planes = make_game(m)
            lib.session_arrival_followup(ctypes.c_void_p(g.ds))
            address = 0x057C
        elif kind == 5:
            lib.session_clear_items(ctypes.c_void_p(g.ds))
            address = 0x97BF
        elif kind == 6:
            lib.session_clear_flags(ctypes.c_void_p(g.ds))
            address = 0x9845
        else:
            si, di = rng.randrange(0x0400, 0xE000), rng.randrange(0x0400, 0xE000)
            regs = {'si': si, 'di': di}
            lib.point_copy(ctypes.c_void_p(g.ds), si, di)
            address = 0x97B4
        m.call(0, address, **regs)
        CASES += 1
        compare(f'{address:04X} case {i}', mem, planes, m, regions(m), fails)
        if fails:
            return fails
    return fails
