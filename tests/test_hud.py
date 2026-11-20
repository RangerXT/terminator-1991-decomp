"""HUD/map numeric renderer against the original, including page and alignment state."""
import ctypes
import random
import struct
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import capture

CASES = 0


def run(ctx):
    global CASES
    ctx.lib.hud_draw_number_bx.restype = ctypes.c_uint16
    fails = []
    rng = random.Random(1991)
    m = ctx.game()
    original_ds = m.ds_read(0, 65536)
    for i in range(120):
        m.ds_write(0, original_ds)
        width = 1 + i % 5
        m.ds_write(0xE172, struct.pack('<H', width))
        m.ds_write(0xE170, struct.pack('<H', (0, 65535, 1, 32768)[i % 4]))
        m.ds_write(0xE16A, bytes([i % 16]))
        m.ds_write(0x1234, struct.pack('<H', (0, 0x2000, 0x4000)[i % 3]))
        value = rng.randrange(65536)
        dest = rng.randrange(0x100, 0x1800)
        g, mem, planes = make_game(m)
        bx = ctx.lib.hud_draw_number_bx(ctypes.byref(g), value, dest)
        out = m.call(0, 0xC766, ax=value, di=dest)
        if bx != out["bx"]:
            return ["number BX %d: %04x != %04x" % (i, bx, out["bx"])]
        CASES += 1
        compare(f'number {i}', mem, planes, m, fails)
        if fails:
            break
    if not fails:
        for col, row in [(0, 0), (6, 3), (180, 120), (191, 127), (192, 128),
                         (65530, 65533), (32767, 32767)]:
            m.ds_write(0, original_ds)
            m.ds_write(0xE172, struct.pack('<H', 3))
            g, mem, planes = make_game(m)
            ctx.lib.map_draw_grid_labels(ctypes.byref(g), col, row)
            m.call(0x11BC, 0x2E46, far=True, ax=col, bx=row)
            CASES += 1
            compare(f'grid {col},{row}', mem, planes, m, fails)
    if not fails:
        for i in range(64):
            m.ds_write(0, original_ds)
            text = (b'', b'Hello World 0123', b'! ~ Az09', bytes(range(1, 256)))[i % 4]
            m.ds_write(0x8000, text + b'\0')
            m.ds_write(0xE170, struct.pack('<H', (0, 65535, 1, 32768)[i % 4]))
            m.ds_write(0xE16A, bytes([i % 16]))
            m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
            m.vga.seq[2] = i % 16
            g, mem, planes = make_game(m)
            ctx.lib.hud_draw_text(ctypes.byref(g), 0x8000, 0x1800)
            m.call(0, 0xC7ED, si=0x8000, di=0x1800)
            CASES += 1
            compare(f'text {i}', mem, planes, m, fails)
    m.ds_write(0, original_ds)
    for name, far in [('hudnumber', False), ('maplabels', True)]:
        for i, (before, after, regs, _) in enumerate(capture.replay(name, far=far)):
            g, mem, planes = make_game(before)
            if far:
                ctx.lib.map_draw_grid_labels(ctypes.byref(g), regs['ax'], regs['bx'])
            else:
                ctx.lib.hud_draw_number(ctypes.byref(g), regs['ax'], regs['di'])
            CASES += 1
            compare(f'{name} live capture {i}', mem, planes, after, fails)
    return fails
