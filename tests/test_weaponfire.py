"""Complete 6D49 and 6B54 using native spawning/damage/sights; sound is event output."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import GameEvent, set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x6D49)
    fails = []
    calls = []
    m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
    addr = (dosemu.LOAD_SEG<<4)+0x89A2
    def sound(uc, address, size, user):
        calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255, m.ds_read(0x80E9, 1)[0]))
    m.uc.hook_add(UC_HOOK_CODE, sound, None, addr, addr)
    def events():
        buf = (GameEvent*512)()
        n = ctx.lib.game_events(buf, 512)
        return [(e.kind, e.a, e.b) for e in buf[:n]]
    def word(off, v):
        m.ds_write(off, struct.pack('<H', v&65535))
    fired = spawned = charged = guided = 0
    for i in range(1536):
        m.ds_write(0, saved)
        kind = i%8
        full = (i//8)%2
        m.ds_write(0x01DE, bytes([0]))
        word(0x03A0, 0x508)
        m.ds_write(0x508, struct.pack('<5H', 0, 100, 0, 0, 0))
        m.ds_write(0x516, bytes([rng.choice([0, 1, 2])]))
        m.ds_write(0x521, bytes([rng.choice([0, 0, 8, 64])]))
        m.ds_write(0x53A, bytes([rng.randrange(10)]))
        word(0x118E, rng.choice([0, 1, 1, 2]))
        word(0x1190, 0)
        for slot in range(2):
            m.ds_write(0x570+6*slot, bytes([kind, 0, 0, rng.choice([0, 1, 2, 255]), 0, 10]))
        m.ds_write(0x11CA, bytes([rng.randrange(3)]))
        for off in [0x8096, 0x5BE8, 0x5BF5, 0x1160, 0xAA83, 0x0361, 0x0366, 0x115D, 0x5C04, 0x5C12, 0x1150]:
            m.ds_write(off, bytes([rng.choice([0, 0, 1, 255])]))
        m.ds_write(0x80E9, bytes([0]))
        m.ds_write(0x80EA, bytes([rng.choice([0, 1, 2, 4])]))
        m.ds_write(0x80EB, bytes([rng.choice([0, 1, 2, 5])]))
        word(0x04D0, rng.choice([0, 0, 0, 1, 95, 65521]))
        word(0x119A, rng.choice([0, 1]))
        word(0x119C, rng.choice([0, 1]))
        count = m.rw(m.DATA_SEG, 0x119A)
        word(0x03A4, 0xDF0+12*count)
        m.ds_write(0xB30, bytes(31*22))
        for j in range(count):
            m.ds_write(0xDF0+j*12, struct.pack('<6H', 100, 0, 300, 0x4000, j*2, 10))
        word(0x03F0, 0)
        word(0xB64E, 0)
        word(0xB64C, 0xB520)
        word(0x118A, 0)
        word(0x118C, 0)
        word(0x11A2, 159)
        word(0x11A4, 60)
        word(0x11C8, 86)
        word(0x1194, 0)
        word(0x11AA, 0)
        word(0x0418, rng.choice([0, 0x8300]))
        m.ds_write(0x8300, struct.pack('<6H', 100, 0, 500, 0, 0, 0))
        m.ds_write(0x0364, bytes([rng.choice([12, 15])]))
        word(0x11AE, 0x8700)
        word(0x11B0, 0x8700)
        word(0x8100, rng.choice([0x8700, 0x8800]))
        word(0x11A0, 0)
        m.ds_write(0x10F0, bytes(72))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *[rng.randrange(65536) for _ in range(200)]))
        word(0x1234, (i%3)*0x2000)
        incoming_dx = rng.randrange(65536)
        g, mem, planes = make_game(m)
        calls.clear()
        events()
        set_clock(ctx.lib, m)
        status = getattr(ctx.lib, 'weapon_frame' if full else 'weapon_fire')(ctypes.byref(g), incoming_dx)
        m.call(0, 0x6B54 if full else 0x6D49, dx=incoming_dx, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status:
            return ['firing status %d'%i]
        got = events()
        if got != calls:
            return ['firing events %d: %s != %s'%(i, got, calls)]
        compare('weapon %s %d'%('frame' if full else 'fire', i), mem, planes, m, fails)
        if fails:
            return fails
        fired += m.rw(m.DATA_SEG, 0x0378) != struct.unpack_from('<H', saved, 0x0378)[0]
        spawned += m.rw(m.DATA_SEG, 0x119A) > count
        charged += m.ds_read(0x0373, 1)[0] != saved[0x0373]
        guided += m.rw(m.DATA_SEG, 0x11A0) > 0
    # Persistent complete-frame sequences: real hits, removal, continuous latch and dry fire.
    for kind in [0, 1, 3, 4]:
        m.ds_write(0, saved)
        word(0x03A0, 0x508)
        word(0x118E, 1)
        word(0x1190, 0)
        word(0xB64C, 0xB520)
        m.ds_write(0x01DE, bytes([0]))
        m.ds_write(0x8096, bytes([0]))
        m.ds_write(0x508, struct.pack('<5H', 0, 100, 0, 0, 0))
        m.ds_write(0x516, bytes([1]))
        m.ds_write(0x521, bytes([0]))
        m.ds_write(0x570, bytes([kind, 0, 0, 8, 0, 3]))
        for off, val in [(0x5BE8, 1), (0x5BF5, 0), (0xAA83, 0), (0x0361, 1), (0x0366, 0), (0x1160, 0), (0x80E9, 0), (0x80EB, 0), (0x11CA, 0), (0x5C04, 0), (0x5C12, 0), (0x1150, 0)]:
            m.ds_write(off, bytes([val]))
        word(0x04D0, 0)
        word(0x11A2, 159)
        word(0x11A4, 60)
        word(0x118A, 0)
        word(0x118C, 0)
        word(0x1194, 0)
        word(0x11AA, 0)
        word(0x8100, 0x8800)
        word(0x11AE, 0x8700)
        word(0x119A, 2)
        word(0x119C, 0)
        word(0x03A4, 0xE08)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *([1]*200)))
        word(0xB64E, 1)
        for j in range(3):
            m.ds_write(0xB30+j*22, struct.pack('<11H', 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            m.ds_write(0xDF0+j*12, struct.pack('<6H', 0, 0, 100, 0x4000, j*2, 5))
        m.ds_write(0xB18E, struct.pack('<9H', 0xDF0, 0, 100, 8, 311, 8, 110, 0, 0))
        collision_seg = m.rw(m.DATA_SEG, 0x91B2)
        m.wb(collision_seg, 0, bytes(0x9000))
        g, mem, planes = make_game(m)
        for step in range(16):
            if not m.rw(m.DATA_SEG, 0x119A):
                word(0xB64E, 0)
                ctypes.c_uint16.from_address(g.ds+0xB64E).value = 0
            calls.clear()
            events()
            set_clock(ctx.lib, m)
            status = ctx.lib.weapon_frame(ctypes.byref(g), 0x4321)
            m.call(0, 0x6B54, dx=0x4321, es=m.DATA_SEG, max_instr=50000000)
            CASES += 1
            if status or events() != calls:
                return ['sequence events/status %d/%d'%(kind, step)]
            compare('firing sequence %d/%d'%(kind, step), mem, planes, m, fails)
            if fails:
                return fails
    print('    firing: fired=%d spawned=%d charged=%d projectile=%d'%(fired, spawned, charged, guided))
    if not all([fired, spawned, charged, guided]):
        return ['missing firing branch coverage']
    return fails
