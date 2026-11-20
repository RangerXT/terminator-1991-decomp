"""Sight arithmetic, crosshair and charge/release against original instructions."""
import ctypes
import itertools
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
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x6C93)
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 65535))
    for i in range(1200):
        m.ds_write(0, saved)
        m.ds_write(0x5A4F, bytes([i % 3]))
        for off in [0x5A5E, 0x5A54, 0x5A60, 0x5A5A, 0x5A64, 0x5A62, 0x5A68, 0x5A66, 0x11A2, 0x11A4]:
            word(off, rng.randrange(65536))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.weapon_update_sight(ds)
        m.call(0, 0x6C93)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['sight arithmetic %d' % i]
    for i, (x, y, hidden) in enumerate(itertools.product([0, 8, 24, 28, 56, 159, 264, 290, 296, 319], [0, 8, 18, 24, 36, 60, 86, 98], [0, 1])):
        m.ds_write(0, saved)
        m.ds_write(0x1150, bytes([hidden]))
        word(0x1234, i%3*0x2000)
        g, mem, planes = make_game(m)
        ctx.lib.weapon_draw_crosshair(ctypes.byref(g), x, y)
        m.call(0, 0x15F4, ax=x, bx=y)
        CASES += 1
        compare('crosshair %d' % i, mem, planes, m, fails)
        if fails:
            return fails
    for i, (charge, held, height) in enumerate(itertools.product([0, 1, 90, 94, 95, 99, 100, 251, 255, 256, 32762, 32763, 65520, 65530, 65531, 65535], [0, 1, 255], [0, 1, 65535, 32768])):
        m.ds_write(0, saved)
        player = 0x8200
        word(0x03A0, player)
        m.ds_write(player, struct.pack('<5H', 123, height, 456, 500, 20))
        word(0x04D0, charge)
        word(0x118A, rng.randrange(65536))
        word(0x1234, i%3*0x2000)
        m.ds_write(0x5BF5, bytes([held]))
        g, mem, planes = make_game(m)
        ctx.lib.weapon_charge_step(ctypes.byref(g))
        m.call(0, 0x6EE0)
        CASES += 1
        compare('charge %d' % i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
