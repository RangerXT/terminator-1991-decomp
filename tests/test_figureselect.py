"""A840 position search and AA3B coordinate unpacking vs DOS; no replay."""
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
    rng = random.Random(0xA840)
    ctx.lib.figure_select_position.restype = ctypes.c_uint8
    for address in range(0xB740-1, 0xB740+170):
        m.ds_write(0, saved)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.figure_grid_to_world(ds, address)
        m.call(0, 0xAA3B, bx=address)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['world conversion %04x'%address]
    seen = set()
    for i in range(864):
        m.ds_write(0, saved)
        mode = i%3
        wanted = [0, 1, 255][(i//3)%3]
        pattern = i%6
        grid = bytearray([255]*144)
        if pattern == 1:
            grid[:] = bytes([wanted])*144
        elif pattern >= 2:
            for j in range(144):
                grid[j] = rng.choice([0, 1, 255, 255, 255])
        m.ds_write(0xB740, grid)
        for off, v in [(0x122E, rng.choice([-1025, -1024, -1023, 0, 255, 256, 1792, 2047, 2048, 2049])), (0x1232, rng.choice([-1025, -1024, 0, 256, 1792, 2048, 2049])), (0x9948, 0x97B8), (0x994A, 0x9948), (0x97B8, rng.randrange(65536))]:
            m.ds_write(off, struct.pack('<H', v&65535))
        m.ds_write(0xB735, bytes([(i//9)%2]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.figure_select_position(ds, mode, wanted)
        out = m.call(0, 0xA840, si=mode, bp=wanted, max_instr=5000000)
        CASES += 1
        seen.add(got)
        if got != (out['flags']&1):
            return ['search carry %d'%i]
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            diff = [j for j in range(0xEA70) if ds.raw[j] != m.ds_read(j, 1)[0]]
            return ['search %d state differs at %04x'%(i, diff[0])]
    if seen != {0, 1}:
        return ['missing success/failure coverage']
    return []
