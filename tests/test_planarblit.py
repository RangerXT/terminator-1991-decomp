"""Raw planar copy, original five HUD pieces, wraps, aliasing and EGA state."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import capture
import dosemu

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    pieces = struct.unpack('<5H', saved[0x1216:0x1220])
    seg = struct.unpack_from('<H', saved, 0x120E)[0]
    ctx.lib.screen_blit_planar.restype = ctypes.c_int64
    for i in range(45):
        m.ds_write(0, saved)
        off = pieces[i % 5]
        m.ds_write(0x1220, struct.pack('<HH', off, seg))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.vga.gc[3] = ((i // 5) % 4) << 3
        m.vga.gc[5] = (i // 15) % 3
        g, mem, planes = make_game(m)
        result = ctx.lib.screen_blit_planar(ctypes.byref(g), seg, off + 16)
        out = m.call(0, 0x1A4D, ds=seg, si=off + 16)
        CASES += 1
        if result != out['si'] | (out['di'] << 16):
            return [f'piece {i}: SI/DI differs']
        compare(f'raw piece {i}', mem, planes, m, fails)
        if fails:
            return fails
    for i in range(144):
        m.ds_write(0, saved)
        count = 1 + i % 4
        width = [1, 2, 3, 5, 40, 41, 80, 81][(i // 4) % 8]
        rows = 1 + i % 9
        stride = [40, 41, 80][(i // 16) % 3]
        header = struct.pack('<8H', 15, count, width * 8 - 3, rows, 8, 3, 0, 0)
        m.wb(0x8200, 0x200, header)
        m.ds_write(0x1220, struct.pack('<HH', 0x200, 0x8200))
        m.ds_write(0x1228, struct.pack('<H', stride))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        source_seg = [0x8000, 0xA000, 0x8100][i % 3]
        source = [0xFFFB, 0xFFFF, 0x300][(i // 3) % 3]
        # The harness wraps a video word at AFFFF back to plane byte 0. That
        # unverified map-boundary behavior is excluded; RAM word crossing remains.
        if source_seg == 0xA000: source &= 0xFFFE
        for j in range((width + 1) * rows * count + 4):
            m.wb(source_seg, (source + j) & 65535, bytes([(j * 37 + i) & 255]))
        if source_seg == 0xA000:
            for plane in range(4):
                for j in range(1024):
                    m.vga.planes[plane][j] = (i + plane * 43 + j) & 255
        m.ds_write(0xADDC, struct.pack('<H', [0xA000, 0x8100, 0x8000][(i // 9) % 3]))
        m.vga.gc[3] = ((i // 7) % 4) << 3
        m.vga.gc[4] = i % 4
        m.vga.gc[5] = (i // 5) % 3
        g, mem, planes = make_game(m)
        result = ctx.lib.screen_blit_planar(ctypes.byref(g), source_seg, source)
        out = m.call(0, 0x1A4D, ds=source_seg, si=source)
        CASES += 1
        if result != out['si'] | (out['di'] << 16):
            return [f'raw {i}: SI/DI differs']
        compare(f'raw synthetic {i}', mem, planes, m, fails)
        if fails:
            return fails
    m.ds_write(0, saved)
    for i in range(9):
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        g, mem, planes = make_game(m)
        ctx.lib.hud_restore_background(ctypes.byref(g))
        m.call(0, 0x1B19)
        CASES += 1
        compare(f'five HUD pieces {i}', mem, planes, m, fails)
        if fails:
            return fails
    return fails
