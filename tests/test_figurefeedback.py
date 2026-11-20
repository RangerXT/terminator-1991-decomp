"""Actual CAF feedback frames and the 5BDB family controller; native decode/draw."""
import ctypes
import os
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
    fails = []
    ctx.lib.figure_feedback_draw.restype = ctypes.c_uint16
    for i in range(33):
        m.ds_write(0, saved)
        m.ds_write(0x1234, struct.pack('<H', (i%3)*0x2000))
        source = m.rw(m.DATA_SEG, 0x7A8C+(i//3)*2)
        seg = m.rw(m.DATA_SEG, 0x91C6)
        g, mem, planes = make_game(m)
        got = ctx.lib.figure_feedback_draw(ctypes.byref(g), seg, source)
        out = m.call(0, 0xC9A5, es=seg, si=source, max_instr=50000000)
        CASES += 1
        if got != out['ax']:
            return ['feedback next frame %d'%i]
        compare('feedback frame %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(96):
        m.ds_write(0, saved)
        player = m.rw(m.DATA_SEG, 0x03A0)
        m.ds_write(player+14, bytes([i%2]))
        m.ds_write(0x11CA, bytes([(i//2)%3]))
        m.ds_write(0x1234, struct.pack('<H', (i%3)*0x2000))
        for off in [0x7A80, 0x7A82, 0x7A84]:
            m.ds_write(off, struct.pack('<H', (i//6)%5))
        # Keep selected frame valid while forcing each group's wrap.
        family = [0, 4, 7][(i//30)%3];slot = 0 if family == 0 else 2 if family == 4 else 4
        n = m.rw(m.DATA_SEG, 0x7A86+slot)
        m.ds_write(0x7A80+slot, struct.pack('<H', (i//6)%n))
        g, mem, planes = make_game(m)
        ctx.lib.figure_feedback(ctypes.byref(g), family)
        m.call(0, 0x5BDB, bx=family, max_instr=50000000)
        CASES += 1
        compare('feedback controller %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
