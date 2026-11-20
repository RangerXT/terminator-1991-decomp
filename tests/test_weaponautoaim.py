"""Native target selection and autoaim drawing; no service replay."""
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
    ctx.lib.weapon_target_rejected.restype = ctypes.c_uint8
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 65535))
    values = [0, 1, 5, 6, 7, 24, 32767, 32768, 65530, 65535]
    for x, y, lock in itertools.product(values, values, [0, 1, 255]):
        m.ds_write(0, saved)
        m.ds_write(0x0365, bytes([lock]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.weapon_lock_colour(ds, x, y)
        m.call(0, 0x720C, ax=x, bx=y)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['lock colour %s/%s/%s' % (x, y, lock)]
    drawn = rejected = 0
    rng = random.Random(7158)
    for i in range(600):
        m.ds_write(0, saved)
        player = 0x8200
        word(0x03A0, player)
        m.ds_write(player, struct.pack('<5H', 1000, 0, 1000, 0 if i < 150 else rng.randrange(512), 0))
        count = i % 6
        word(0x1194, count)
        word(0x11AA, i % max(count, 1))
        m.ds_write(0x5C06, bytes([i % 3]))
        m.ds_write(0x8160, bytes([(i // 3) % 3]))
        m.ds_write(0x0365, bytes([(i // 9) % 2]))
        word(0x040A, [60, 36, 37, 97, 98][(i // 27) % 5])
        word(0x1234, (i % 3) * 0x2000)
        for j in range(count):
            target = 0x8300 + 16*j
            word(0x041A + 4*j + 2, target)
            x = rng.choice([0, 1, 5, 30, -30, 300, -300])
            z = rng.choice([-100, 0, 30, 31, 32, 100, 500])
            m.ds_write(target, struct.pack('<6H', (1000+x)&65535, 0, (1000+z)&65535, 0, 0, 65535 if i%7 == 0 else 0))
        if count:
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            got = ctx.lib.weapon_target_rejected(ds, 0x041A)
            regs = m.call(0, 0x78D6, bx=0x041A)
            CASES += 1
            if got != (regs['flags'] & 1):
                return ['target predicate %d: C=%s DOS=%s' % (i, got, regs['flags'] & 1)]
        g, mem, planes = make_game(m)
        ctx.lib.weapon_draw_autoaim(ctypes.byref(g))
        m.call(0, 0x7158)
        CASES += 1
        if m.rw(m.DATA_SEG, 0x04CC) == 65535:
            rejected += 1
        else:
            drawn += 1
        compare('autoaim %d' % i, mem, planes, m, fails)
        if fails:
            return fails
    if not drawn or not rejected:
        fails.append('missing draw/reject coverage')
    return fails
