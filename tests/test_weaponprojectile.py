"""Projectile allocation and creation, including count/occupancy disagreement."""
import ctypes
import os
import random
import struct
import dosemu
CASES = 0

def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xD896)
    ctx.lib.weapon_projectile_slot.restype = ctypes.c_uint16
    for mask in range(16):
        for count in [0, 1, 2, 3, 4, 5, 65535]:
            m.ds_write(0, saved)
            for j in range(4):
                m.ds_write(0x1100+18*j, struct.pack('<H', 65535 if mask&(1<<j) else 0))
            m.ds_write(0x11A0, struct.pack('<H', count))
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            got = ctx.lib.weapon_projectile_slot(ds)
            want = m.call(0, 0xDAD6)['si']
            CASES += 1
            if got != want:
                return ['slot %d/%d'%(mask, count)]
            vals = [rng.randrange(65536) for _ in range(6)]
            ctx.lib.weapon_projectile_create(ds, *vals)
            m.call(0, 0xD896, ax=vals[0], bx=vals[1], cx=vals[2], dx=vals[3], si=vals[4], bp=vals[5])
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                return ['projectile %d/%d'%(mask, count)]
    ctx.lib.weapon_projectile_turn.restype = ctypes.c_uint32
    ctx.lib.weapon_projectile_outside.restype = ctypes.c_uint8
    for heading in range(512):
        for delta in [0, 1, 7, 8, 9, 127, 128, 129, 255, 256, 383, 384, 385, 503, 504, 505, 511]:
            target = (heading+delta)&511
            got = ctx.lib.weapon_projectile_turn(heading, target)
            out = m.call(0, 0xDA2C, ax=heading, bx=target)
            want = out['ax']|((out['flags']&1)<<16)
            CASES += 1
            if got != want:
                return ['turn %d/%d: %x != %x'%(heading, target, got, want)]
    coords = [-32768, -925, -924, -923, -1, 0, 1947, 1948, 1949, 32767]
    for x in coords:
        for z in coords:
            got = ctx.lib.weapon_projectile_outside(x&65535, z&65535)
            want = m.call(0, 0xDABC, ax=x&65535, bx=z&65535)['flags']&1
            CASES += 1
            if got != want:
                return ['projectile bounds %d/%d'%(x, z)]
    return fails
