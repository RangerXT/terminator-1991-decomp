"""font_load / font_scale (src/fontscale.c) against the original 11BC:28F8 and 11BC:2714.

Random fonts (glyph sizes 1..24 rows and pixels, random bits, 1 to 9 glyphs) scaled to
random sizes (up, down and mixed, 1..40), with random character widths; and the real
font.pck loaded by both and scaled to the sizes the game asks for (0C0C by the ratings
screen) and a few others. Compared: all memory but the stack, the planes and card. Random
inputs that overflow the last width division (a divide error the game never meets) are
left out.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402

CASES = 0


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.font_load.restype = ctypes.c_int
    fails = []
    rng = random.Random(0x2714)
    base = dosemu.Machine()
    base.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    work_seg = base.rw(base.DATA_SEG, 0x91C6)
    for i in range(160):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        src_rows, src_width = rng.randrange(1, 25), rng.randrange(1, 25)
        dst_rows, dst_width = rng.choice([rng.randrange(1, 41), src_rows * 2, max(1, src_rows // 2)]), \
            rng.choice([rng.randrange(1, 41), src_width * 2, max(1, src_width // 2)])
        count = rng.randrange(1, 10)
        glyph = src_rows * ((src_width + 7) // 8)
        si = rng.randrange(0, 0x100)
        di = si + glyph * count + rng.randrange(0, 0x40)
        m.wb(work_seg, si, bytes(rng.randrange(256) for _ in range(glyph * count)))
        m.ds_write(0xADE8, struct.pack('<H', work_seg))
        m.ds_write(0xAE00, struct.pack('<H', work_seg))
        widths = [rng.randrange(256) for _ in range(0x58)]
        extra = rng.randrange(256)
        # the last width's leftover DX enters AE02's division (no XOR DX,DX there); keep out
        # inputs where that overflows, a divide error the game never meets with its sizes
        dx = ((widths[-1] << 8) // src_width) * dst_width >> 16
        if ((dx << 16) | (extra << 8)) // src_width > 0xFFFF:
            widths[-1] = 0
        m.ds_write(0xAEC3, bytes(widths))
        m.ds_write(0xAE02, bytes([extra]))
        g, mem, planes = make_game(m)
        src, dst = src_rows | src_width << 8, dst_rows | dst_width << 8
        lib.font_scale(ctypes.byref(g), src, dst, count, si, di)
        m.call(0x11BC, 0x2714, far=True, ax=src, bx=dst, cx=count, si=si, di=di)
        CASES += 1
        compare(f'scale {i}: {src_rows}x{src_width} to {dst_rows}x{dst_width}, {count} glyphs', mem, planes, m,
                regions(m), fails)
        if fails:
            return fails
    for dst in (0x0C0C, 0x1010, 0x0808, 0x1818, 0x0A0C, 0x0E08):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        status = lib.font_load(ctypes.byref(g), ctypes.byref(files.host), 0x7A49)
        m.call(0x11BC, 0x28F8, far=True, dx=0x7A49)
        CASES += 1
        if status:
            return [f'font.pck: font_load returned {status}']
        compare('font.pck loaded', mem, planes, m, regions(m), fails)
        if fails:
            return fails
        size, si = m.rw(m.DATA_SEG, 0xADFE), m.rw(m.DATA_SEG, 0xADE6)
        lib.font_scale(ctypes.byref(g), 0x0C0C, dst, 0x46, si, size)
        m.call(0x11BC, 0x2714, far=True, ax=0x0C0C, bx=dst, cx=0x46, si=si, di=size)
        CASES += 1
        compare(f'font.pck to {dst:04X}', mem, planes, m, regions(m), fails)
        if fails:
            return fails
        # text in the scaled font (11BC:2682): random strings, places, colours and strides
        lib.font_text.restype = ctypes.c_uint16
        for j in range(12):
            text = bytes(rng.choice([rng.randrange(0x20, 0x7F), 0x20, rng.randrange(1, 256)])
                         for _ in range(rng.randrange(0, 14))) + b'\0'
            text = text.replace(b'\0', b'A', text.count(b'\0') - 1) if text.count(b'\0') > 1 else text
            m.ds_write(0x8200, text)
            m.ds_write(0x1228, struct.pack('<H', rng.choice([0x28, 0x50])))
            m.ds_write(0xE40F, bytes([rng.randrange(16)]))
            x, y = rng.randrange(0, 600), rng.randrange(0, 190)
            g, mem, planes = make_game(m)
            got = lib.font_text(ctypes.byref(g), x, y, 0x8200)
            regs = m.call(0x11BC, 0x2682, far=True, ax=x, bx=y, si=0x8200)
            CASES += 1
            if got != regs['ax']:
                return [f'text {dst:04X} {j}: x after C {got}, original {regs["ax"]}']
            compare(f'text {dst:04X} {j} at {x},{y}', mem, planes, m, regions(m), fails)
            if fails:
                return fails
    return fails
