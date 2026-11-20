"""Shot visual insertion, wrapping and repeated movement against A00C/A036."""
import ctypes
import os
import random
import struct
import dosemu
CASES = 0

def run(ctx):
    global CASES
    ctx.lib.weapon_visual_step_dx.restype = ctypes.c_uint16
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xA036)
    for slot in range(30):
        for pitch in [0, 1, 511, 32768, 65535]:
            m.ds_write(0, saved)
            m.ds_write(0xB64C, struct.pack('<H', 0xB520+10*slot))
            m.ds_write(0xB65E, struct.pack('<H', pitch))
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            for step in range(3):
                vals = [rng.randrange(65536) for _ in range(4)]
                ctx.lib.weapon_visual_insert(ds, *vals)
                m.call(0, 0xA00C, ax=vals[0], bx=vals[1], cx=vals[2], dx=vals[3])
                CASES += 1
                if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                    return ['shot insertion %d/%d/%d'%(slot, pitch, step)]
    for scenario in range(32):
        m.ds_write(0, saved)
        for j in range(30):
            heading = [65535, 32768, rng.randrange(512)][(j+scenario)%3]
            y = rng.choice([0, 1, 511, 32767, 32768, 65535])
            pitch = rng.choice([0, 1, 2, 511, 32768, 65535])
            m.ds_write(0xB520+10*j, struct.pack('<5H', rng.randrange(65536), y, rng.randrange(65536), heading, pitch))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        for step in range(16):
            incoming = rng.randrange(65536)
            result = ctx.lib.weapon_visual_step_dx(ds, incoming)
            output = m.call(0, 0xA036, dx=incoming)
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70) or result != output['dx'] or output['cx']:
                return ['shot movement %d/%d'%(scenario, step)]
    return []
