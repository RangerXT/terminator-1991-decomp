"""Map pixel sampling and spawn-candidate grid vs original, no replay."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xA480)
    fails = []
    ctx.lib.figure_map_sample.restype = ctypes.c_uint16
    for i in range(192):
        m.ds_write(0, saved)
        for off in [0x114D, 0x114F]:
            m.ds_write(off, bytes([rng.randrange(2)]))
        x = rng.randrange(-1500, 2500)&65535
        z = rng.randrange(-1500, 2500)&65535
        m.vga.gc[5] = 0
        for p in range(4):
            m.vga.planes[p][0x6000:0x8000] = bytes([rng.randrange(256)])*8192
        g, mem, planes = make_game(m)
        got = ctx.lib.figure_map_sample(ctypes.byref(g), x, z)
        out = m.call(0, 0x5CFA, ax=x, bx=z)
        CASES += 1
        if got != out['ax']:
            return ['map sample AX %d'%i]
        compare('map sample %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(36):
        m.ds_write(0, saved)
        m.ds_write(0xB73E, struct.pack('<H', i%9))
        m.ds_write(0xB82A, struct.pack('<H', 65535))
        m.ds_write(0x114D, bytes([0]))
        m.ds_write(0x114F, bytes([0]))
        m.vga.gc[5] = 0
        for p in range(4):
            m.vga.planes[p][0x6000:0x8000] = bytes([255 if i%3 == 1 and p == 0 else 0])*8192
        g, mem, planes = make_game(m)
        full = i >= 18
        getattr(ctx.lib, 'figure_spawn_grid' if full else 'figure_spawn_grid_block')(ctypes.byref(g))
        m.call(0, 0xA46F if full else 0xA480, max_instr=50000000)
        CASES += 1
        compare('spawn grid %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
