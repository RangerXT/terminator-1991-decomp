"""Weapon source classification and numeric HUD against the DOS executable."""
import ctypes
import itertools
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    for active in [0, 1, 2, 9, 255, 256, 257, 32768, 65535]:
        for match in [False, True]:
            m.ds_write(0, saved)
            m.ds_write(0x118E, struct.pack('<H', active))
            slot = (0x11AE + ((active - 1) * 2)) & 65535
            val = struct.unpack('<H', m.ds_read(slot, 2))[0]
            m.ds_write(0x8100, struct.pack('<H', val if match else val ^ 65535))
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            ctx.lib.weapon_classify_source(ds)
            m.call(0, 0x6AFC)
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                fails.append('classification %s/%s' % (active, match))
    for i, (camera, vehicle, active, secondary, value) in enumerate(itertools.product(
            range(3), [0, 2], [0, 1, 2, 256, 257, 65535], [0, 1, 3, 257], [0, 7, 99, 127, 128, 255])):
        m.ds_write(0, saved)
        player = 0x8200
        m.ds_write(player + 14, bytes([vehicle]))
        m.ds_write(0x11CA, bytes([camera]))
        m.ds_write(0x118E, struct.pack('<HH', active, secondary))
        for selection in [active, secondary]:
            slot = ((selection - 1) & 255) * 6
            m.ds_write(0x573 + slot, bytes([value]))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        g, mem, planes = make_game(m)
        ctx.lib.weapon_draw_numbers(ctypes.byref(g), player)
        m.call(0, 0x7008, si=player)
        CASES += 1
        compare('weapon numbers %d' % i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
