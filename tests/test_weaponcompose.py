"""Post-firing sight composition at 6B70; firing is not part of this entry."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x6B70)
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 65535))
    for i in range(1200):
        m.ds_write(0, saved)
        word(0x03A0, 0x8200)
        m.ds_write(0x8200, struct.pack('<5H', 1000, 0, 1000, 0, 0))
        m.ds_write(0x8219, bytes([64 if i%2 else 0]))
        word(0x118E, 1)
        word(0x11AE, 0x8700)
        word(0x8100, 0x8700 if i%3 == 0 else 0x8800)
        word(0x1194, 1 if i%4 else 0)
        word(0x11AA, 0)
        word(0x041C, 0x8300)
        m.ds_write(0x8300, struct.pack('<6H', 1000+rng.choice([-30, 0, 1, 30]), 0, 1500, 0, 0, 0))
        for off in [0x5C04, 0x5C06, 0x8160, 0x0365, 0x5C12, 0x5A4F, 0x5C26, 0x5C24, 0x5C21, 0x5C29, 0x1150]:
            m.ds_write(off, bytes([rng.choice([0, 0, 1, 255])]))
        m.ds_write(0x5C0F, bytes([rng.choice([0, 1, 127, 128, 255])]))
        word(0x11A2, rng.choice([28, 29, 159, 289, 290]))
        word(0x11A4, rng.choice([18, 19, 60, 85, 86]))
        word(0x11C8, 86)
        for off in [0x5A54, 0x5A5A]:
            word(off, 100)
        for off in [0x5A5E, 0x5A60]:
            word(off, 100+rng.randrange(-20, 21))
        for off in [0x5A62, 0x5A66]:
            word(off, 1)
        for off in [0x5A64, 0x5A68]:
            word(off, rng.randrange(128))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        word(0x97B8, i%256)
        word(0x1234, i%3*0x2000)
        g, mem, planes = make_game(m)
        ctx.lib.weapon_draw_sights(ctypes.byref(g))
        m.call(0, 0x6B70)
        CASES += 1
        compare('sight composition %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for before, after, _, _ in capture.replay('weaponsights_prepared'):
        g, mem, planes = make_game(before)
        ctx.lib.weapon_draw_sights(ctypes.byref(g))
        compare('prepared gameplay sights', mem, planes, after, fails)
        CASES += 1
        if fails:
            return fails
    return fails
