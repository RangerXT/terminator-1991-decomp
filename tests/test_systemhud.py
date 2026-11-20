"""System HUD bitmap frame, flash timer and zoom-key latch vs executable."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import dosemu
CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    for pressed in [0, 1, 255]:
        for latch in [0, 1, 255]:
            for zoom in [0, 1, 255]:
                m.ds_write(0, saved)
                for off, value in [(0x5C05, pressed), (0xE4FC, latch), (0x114D, zoom)]:
                    m.ds_write(off, bytes([value]))
                ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
                ctx.lib.hud_zoom_key(ds)
                m.call(0, 0xE5BD)
                CASES += 1
                if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                    fails.append('zoom latch state differs')
    image = open(os.path.join(dosemu.ROOT, 'data/common/S8X59.IMG'), 'rb').read()
    m.wb(0x8000, 0, image)
    for i in range(96):
        m.ds_write(0, saved)
        m.ds_write(0xE524, struct.pack('<HH', 0, 0x8000))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.ds_write(0x11CA, bytes([i % 3]))
        m.ds_write(0x1150, bytes([255 if i % 5 == 0 else 0]))
        m.ds_write(0x1142, bytes([255 if i % 7 == 0 else 0]))
        y = 90 if i % 3 == 2 else 60
        m.ds_write(0x11A2, struct.pack('<HH', 159 if i % 4 == 0 else (i * 7) % 300 + 8,
                                     y if i % 4 == 1 else (i * 5) % 95 + 8))
        m.ds_write(0x468D, b'\xff')
        m.wb(dosemu.LOAD_SEG, 0x1B41, b'\x04')
        m.wb(dosemu.LOAD_SEG, 0x1B42, struct.pack('<H', 40))
        g, mem, planes = make_game(m)
        ctx.lib.hud_draw_system_frame(ctypes.byref(g))
        m.call(0, 0xE66E)
        CASES += 1
        compare(f'system frame {i}', mem, planes, m, fails)
        if fails:
            return fails
    for i in range(96):
        m.ds_write(0, saved)
        count = [0, 1, 2, 255][i % 4]
        reload = [0, 1, 3, 255][(i // 4) % 4]
        state = [0, 1, 2, 255][(i // 16) % 4]
        record = 0x8200
        slot = i % 12
        m.ds_write(record, struct.pack('<BBBBHHHH', count, reload, state, 123, 8, (i % 59) + 1, 0x04E8, slot))
        m.ds_write(0xE500 + 4 * slot, struct.pack('<HH', 0, 0x8000))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        g, mem, planes = make_game(m)
        ctx.lib.hud_flash_bitmap(ctypes.byref(g), record)
        m.call(0, 0xE638, si=record)
        CASES += 1
        compare(f'flash bitmap {i}', mem, planes, m, fails)
        if fails:
            return fails
    return fails