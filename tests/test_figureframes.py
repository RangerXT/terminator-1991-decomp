"""Standalone figure movement initialization and frame tables against DOS."""
import ctypes
import os
import random
import struct
import dosemu
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xB0A6)
    for i in range(192):
        m.ds_write(0, saved)
        count = i%32
        m.ds_write(0x119A, struct.pack('<H', count))
        for j in range(count):
            words = [rng.randrange(65536) for k in range(11)]
            words[0] = rng.choice([0, 2, 4, 8, 10, 12, 16])
            words[3] = rng.randrange(512)
            words[5] = rng.choice([0, 0, 2, 3])
            words[7] = rng.randrange(512)
            words[8] = rng.choice([0, 1, 2, 3, 255])|(rng.randrange(4)<<8)
            m.ds_write(0xB30+j*22, struct.pack('<11H', *words))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.figure_select_frames(ds)
        m.call(0, 0xB0A6)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['frames %d'%i]
    for i in range(192):
        m.ds_write(0, saved)
        m.ds_write(0xB740, bytes(rng.choice([0, 0, 1, 255]) for k in range(144)))
        m.ds_write(0xDF0, struct.pack('<6H', rng.choice([-1025, -1024, 0, 256, 2048, 2049])&65535, 0, rng.choice([-1024, 0, 256, 2048])&65535, 0, 0, 10))
        m.ds_write(0xB30, struct.pack('<11H', 2, 1, 2, 0, 0, i%4, 0, 0, 0, 0, 0))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.figure_init_movement(ds, 0xB30, 0xDF0)
        m.call(0, 0xB05E, si=0xB30, di=0xDF0)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['init movement %d'%i]
    return []
