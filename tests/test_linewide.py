"""line_to_wide (src/line.c) against the original 640-wide line 0000:1201.

From the in-game snapshot: random lines on the 640x200 screen (80 bytes a row), sloped in
all four octants, vertical and horizontal ones (0000:1090 / 1106), ones on the edges of the
view window that those two leave out, lines inside one byte, random colours (DS:468C),
pages and plane masks. Compared: the registers BX and DX afterwards, all memory but the
stack, the planes and card.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import compare, regions  # noqa: E402

CASES = 0


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.line_to_wide_registers.restype = ctypes.c_uint32
    fails = []
    rng = random.Random(0x1201)
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    spans = regions(m)
    view = m.ds_read(0x03F4, 8)

    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 0xFFFF))

    for i in range(1200):
        x0, x1, y0, y1 = rng.randrange(640), rng.randrange(640), rng.randrange(200), rng.randrange(200)
        kind = i % 8
        if kind == 0:
            x1 = x0
        elif kind == 1:
            y1 = y0
        elif kind == 2:
            x1 = (x0 & ~7) + rng.randrange(8)
            y1 = y0
        elif kind == 3:
            x1 = x0 + rng.randrange(-3, 4)
        m.ds_write(0x03F4, view)
        if i % 16 == 4:          # on the left / right edge of the view window
            x0 = x1 = struct.unpack('<H', view[rng.choice([0, 4]):][:2])[0]
        if i % 16 == 5:          # on the top / bottom edge
            y0 = y1 = struct.unpack('<H', view[rng.choice([2, 6]):][:2])[0]
        x1, x0 = max(0, min(639, x1)), max(0, min(639, x0))
        word(0x122E, x0)
        word(0x1230, y0)
        word(0x1234, rng.choice([0, 0x4000, 0x8000]))
        m.ds_write(0x468C, bytes([rng.randrange(16)]))
        m.vga.seq[2] = rng.choice([0x0F, 0x0F, rng.randrange(16)])
        g, mem, planes = make_game(m)
        got = lib.line_to_wide_registers(ctypes.c_void_p(g.ds), planes, x1, y1)
        out = m.call(0, 0x1201, ax=x1, bx=y1)
        CASES += 1
        want = out['bx'] | out['dx'] << 16
        if got != want:
            return [f'line {i} {(x0, y0, x1, y1)}: BX/DX C {got:08X}, original {want:08X}']
        compare(f'line {i} {(x0, y0, x1, y1)}', mem, planes, m, spans, fails)
        if fails:
            return fails
    return fails
