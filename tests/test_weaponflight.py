"""Charged and guided flight vs executable; native movement/collision/blasts/figures."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import c_events, set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    seg = m.rw(m.DATA_SEG, 0x91B2)
    rng = random.Random(0x6F99)
    calls = []
    fails = []
    for kind, s, o, reg in [(1, 0, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0, 0x0A4F, dosemu.UC_X86_REG_BX), (4, 0x151B, 0x02DE, dosemu.UC_X86_REG_SI)]:
        m.wb(dosemu.LOAD_SEG+s, o, bytes([0xCB if s else 0xC3]))
        addr = ((dosemu.LOAD_SEG+s)<<4)+o
        def hook(uc, address, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&(255 if kind in [1, 5] else 65535)))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
    def word(off, v):
        m.ds_write(off, struct.pack('<H', v&65535))
    def prepare(i):
        m.ds_write(0, saved)
        m.ds_write(0x01DE, bytes([0]))
        m.ds_write(0x11CA, bytes([0 if i%2 else 2]))
        m.wb(seg, 0, bytes([1 if i%3 == 0 else 0])*0x9000)
        word(0x03A0, 0x508)
        m.ds_write(0x508, struct.pack('<5H', 0, 100, 0, 0, 0))
        word(0x119A, 1)
        word(0x119C, 0)
        word(0xB64E, 0)
        word(0x50AC, 0)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *([1]*200)))
        word(0x118E, 1)
        m.ds_write(0x575, bytes([5]))
        word(0xB64C, 0xB520)
        m.ds_write(0x115D, bytes([0]))
        m.ds_write(0x0366, bytes([i%2]))
        m.ds_write(0x1160, bytes([1]))
        word(0x11A0, 0)
        m.ds_write(0x10F0, bytes(72))
    def check(label, g, mem, planes):
        if c_events(ctx.lib) != calls:
            return ['event mismatch '+label]
        compare(label, mem, planes, m, fails)
        return fails
    expired = collided = travelled = 0
    for i in range(288):
        prepare(i)
        active = i%6 != 0
        m.ds_write(0x0373, bytes([255 if active else 0]))
        life = [0, 1, 2, 5, 22, 23][(i//6)%6]
        m.ds_write(0x367, struct.pack('<6H', rng.randrange(-800, 1800)&65535, rng.randrange(100), rng.randrange(-800, 1800)&65535, rng.randrange(512), rng.choice([0, 10, 100, 255]), life))
        # Include the weapon-switched-to-guidance case; its inactive target words need CX/DX.
        if i >= 216:
            m.ds_write(0x115D, bytes([1]))
            m.ds_write(0x0364, bytes([15]))
            word(0x0418, 0)
        cx = rng.randrange(65536)
        dx = rng.randrange(65536)
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.weapon_charge_projectile_step(ctypes.byref(g), cx, dx)
        m.call(0, 0x6F99, cx=cx, dx=dx, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status:
            return ['charged flight status %d'%i]
        error = check('charged flight %d'%i, g, mem, planes)
        if error:
            return error
        expired += active and life == 1
        collided += active and life != 1 and not m.ds_read(0x373, 1)[0]
        travelled += active and bool(m.ds_read(0x373, 1)[0])
    impacts = moved = outside = 0
    for i in range(288):
        prepare(i)
        count = i%5
        word(0x11A0, count)
        for j in range(count):
            x = rng.choice([-925, -924, 0, 1000, 1948, 1949])
            z = rng.choice([-925, 0, 1000, 1949])
            mode = (i+j)%3
            heading = rng.randrange(512)
            target = 0x8300+j*12
            m.ds_write(target, struct.pack('<6H', 100, 0, 100, 0x2000 if i%2 else 0, 0, 0))
            m.ds_write(0x10F0+j*18, struct.pack('<9H', x&65535, 0, z&65535, heading, mode, target, 100, 100, 65535))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.weapon_guided_projectiles_step(ctypes.byref(g))
        m.call(0, 0xD8D2, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status:
            return ['guided status %d'%i]
        error = check('guided flight %d'%i, g, mem, planes)
        if error:
            return error
        impacts += bool(calls)
        moved += m.rw(m.DATA_SEG, 0x11A0) > 0
        outside += m.rw(m.DATA_SEG, 0x11A0) < count and not calls
    for serial, camera in [(1, 0), (0, 1)]:
        prepare(1)
        m.ds_write(0x01DE, bytes([serial]))
        m.ds_write(0x11CA, bytes([camera]))
        g, mem, planes = make_game(m)
        before = mem.raw
        screen = planes.raw
        if ctx.lib.weapon_guided_projectiles_step(ctypes.byref(g)) != -1 or mem.raw != before or planes.raw != screen:
            return ['flight rejection not atomic']
        CASES += 1
    print('    charged: expired=%d collision=%d travelling=%d; guided: impacts=%d active=%d out-of-bounds=%d'%(expired, collided, travelled, impacts, moved, outside))
    if not all([expired, collided, travelled, impacts, moved, outside]):
        return ['missing flight coverage']
    return fails
