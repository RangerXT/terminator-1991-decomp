"""Full-height numeric HUD composition and its clear/heading helpers."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import capture

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = ctx.game()
    saved = m.ds_read(0, 65536)
    rng = random.Random(772)
    ctx.lib.heading_degrees.restype = ctypes.c_uint16
    for h in list(range(512)) + [32767, 32768, 65535]:
        out = m.call(0, 0x5998, ax=h)
        got = ctx.lib.heading_degrees(h)
        CASES += 1
        if got != out['ax']:
            fails.append(f'heading {h}: {got} vs {out["ax"]}')
    for i in range(48):
        m.ds_write(0, saved)
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.vga.gc[3] = (i % 4) << 3
        m.vga.gc[5] = (i % 3)
        m.vga.gc[4] = i % 4
        digits, dest = i % 8, 0x1800 + i
        g, mem, planes = make_game(m)
        ctx.lib.hud_clear_number(ctypes.byref(g), dest, digits)
        m.call(0x5776, 0x018A, far=True, di=dest, bx=digits)
        CASES += 1
        compare(f'clear {i}', mem, planes, m, fails)
    for i in range(72):
        m.ds_write(0, saved)
        m.ds_write(0x11CA, bytes([i % 3]))
        m.ds_write(0xE172, struct.pack('<H', 3))
        m.ds_write(0xE170, struct.pack('<H', 0 if i % 2 else 65535))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        player = m.rw(m.DATA_SEG, 0x03A0)
        for field in [0, 4, 6, 10, 30, 32]:
            value = rng.randrange(65536) if field != 6 else rng.randrange(512)
            m.ds_write(player + field, struct.pack('<H', value))
        g, mem, planes = make_game(m)
        ctx.lib.hud_draw_counters(ctypes.byref(g))
        m.call(0, 0x772B)
        CASES += 1
        compare(f'counters {i}', mem, planes, m, fails)
    m.ds_write(0, saved)
    for i in range(72):
        for off, name in [(0x73C1, 'hud_draw_speed'), (0x7428, 'hud_draw_vehicle_counter')]:
            m.ds_write(0, saved)
            player = m.rw(m.DATA_SEG, 0x03A0)
            m.ds_write(player + 14, bytes([i % 8]))
            m.ds_write(player + 10, struct.pack('<H', rng.randrange(65536)))
            m.ds_write(player + 0x30, struct.pack('<H', rng.randrange(65536)))
            m.ds_write(0x114C, bytes([(i // 8) % 2]))
            m.ds_write(0xE40F, bytes([i % 16]))
            m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
            g, mem, planes = make_game(m)
            getattr(ctx.lib, name)(ctypes.byref(g))
            m.call(0, off)
            CASES += 1
            compare(f'{name} {i}', mem, planes, m, fails)
    for i in range(96):
        m.ds_write(0, saved)
        player = m.rw(m.DATA_SEG, 0x03A0)
        m.ds_write(player + 14, bytes([(0, 1, 2, 3)[i % 4]]))
        m.ds_write(player + 6, struct.pack('<H', (i * 37) % 512))
        m.ds_write(0xAA96, bytes([(i // 4) % 2]))
        m.ds_write(0x7AC5, bytes([(i // 8) % 2]))
        m.ds_write(0x122C, struct.pack('<H', i % 3))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        if i % 5:
            for j in range(3):
                m.ds_write(0x7B3C + 4 * j, struct.pack('<HH', 212 + j, 141 + j))
        else:
            m.ds_write(0x7B3C, b'\xff' * 12)
        g, mem, planes = make_game(m)
        ctx.lib.hud_draw_compass(ctypes.byref(g))
        m.call(0, 0x4F2A)
        CASES += 1
        compare(f'compass {i}', mem, planes, m, fails)
    m.ds_write(0, saved)
    modes = set()
    for name in ['hudcounters', 'hudcounters_full']:
        for i, (before, after, regs, _) in enumerate(capture.replay(name)):
            modes.add(before.ds_read(0x11CA, 1)[0])
            g, mem, planes = make_game(before)
            ctx.lib.hud_draw_counters(ctypes.byref(g))
            CASES += 1
            compare(f'{name} live counters {i}', mem, planes, after, fails)
    print(f'    HUD counters: live camera modes {sorted(modes)}')
    return fails
