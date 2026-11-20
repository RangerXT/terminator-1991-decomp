"""Shared HUD/map mask blitter against original 1985, including returned offsets."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import dosemu
CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    rng = random.Random(0x1985)
    m.wb(0x8000, 0, bytes(rng.randrange(256) for _ in range(65536)))
    ctx.lib.screen_blit_mask.restype = ctypes.c_uint32
    for i in range(128):
        width = (i % 81) + 1
        rows = i % 17 + 1
        stride = 40 if i % 2 else 80
        source = (65520, 0, 0x100)[i % 3]
        segment = 0xA000 if i % 7 == 0 else 0x8000
        dest = 0x1000 + i
        colour = i % 16
        m.wb(dosemu.LOAD_SEG, 0x1B41, bytes([colour]))
        m.wb(dosemu.LOAD_SEG, 0x1B42, struct.pack('<H', stride))
        m.vga.gc[5] = i % 4
        m.vga.gc[3] = ((i // 4) % 4) << 3
        m.vga.gc[4] = i % 4
        g, mem, planes = make_game(m)
        got = ctx.lib.screen_blit_mask(ctypes.byref(g), segment, source, dest, width, rows, colour, stride)
        out = m.call(0, 0x1985, ds=segment, si=source, di=dest, bx=width, cx=rows)
        CASES += 1
        if got != out['si'] | (out['di'] << 16):
            fails.append(f'mask blit {i}: returned offsets differ')
        compare(f'mask blit {i}', mem, planes, m, fails)
        if fails:
            break
    return fails
