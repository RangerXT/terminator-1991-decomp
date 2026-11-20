"""640-pixel map lines, clipping wrapper and full-area viewport against original."""
import ctypes
import gzip
import os
import pickle
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import capture
import dosemu
CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/area_map.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x1343)
    for i in range(300):
        m.ds_write(0, saved)
        x, y, xx, yy = rng.randrange(640), rng.randrange(350), rng.randrange(640), rng.randrange(350)
        if i % 3 == 0:
            xx = x
        elif i % 3 == 1:
            yy = y
        m.ds_write(0x122E, struct.pack('<HH', xx, yy))
        m.ds_write(0x468C, bytes([i % 16]))
        m.vga.seq[2] = i % 16
        g, mem, planes = make_game(m)
        ctx.lib.area_line_to(ctypes.c_void_p(g.ds), planes, x, y)
        m.call(0, 0x1343, ax=x, bx=y)
        CASES += 1
        compare(f'area line {i}', mem, planes, m, fails)
        if fails:
            return fails
    for i in range(160):
        m.ds_write(0, saved)
        if i % 2:
            x = rng.randrange(-50, 700)
            xx = x
            y, yy = rng.randrange(-50, 400), rng.randrange(-50, 400)
        else:
            y = rng.randrange(-50, 400)
            yy = y
            x, xx = rng.randrange(-50, 700), rng.randrange(-50, 700)
        m.ds_write(0x122E, struct.pack('<HH', xx & 65535, yy & 65535))
        g, mem, planes = make_game(m)
        ctx.lib.area_line_clipped(ctypes.c_void_p(g.ds), planes, x & 65535, y & 65535)
        m.call(0, 0xD102, ax=x, bx=y)
        CASES += 1
        compare(f'area clipping {i}', mem, planes, m, fails)
        if fails:
            return fails
    states = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'areaviewport.pkl.gz'), 'rb'))
    for i in range(20):
        mm = capture.restore(states[0])
        if i:
            p = mm.rw(mm.DATA_SEG, 0x03A0)
            mm.ds_write(p + 34, struct.pack('<I', (i * 31 % 640) * 307))
            mm.ds_write(p + 42, struct.pack('<I', (i * 17 % 350) * 374))
        g, mem, planes = make_game(mm)
        ctx.lib.map_area_viewport(ctypes.byref(g))
        capture.run_to_return(mm)
        CASES += 1
        compare(f'area viewport {i}', mem, planes, mm, fails)
        if fails:
            return fails
    return fails