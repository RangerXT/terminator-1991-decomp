"""The small routines of src/misc.c against the original 0000:4344, A075, C20B, ACE1, 9BA6,
DF00 and 9A01, called directly from the in-game snapshot with random inputs (registers, the
far pointer DS:1204, figure counts, character lists with and without the character, cell
positions). Compared: AX and the carry where the routine returns them, and all memory but
the stack, the planes and card.
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
    lib.misc_band_test.restype = ctypes.c_uint32
    lib.misc_collect_char.restype = ctypes.c_uint16
    fails = []
    rng = random.Random(0x9BA6)
    for i in range(140):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        kind = i % 7
        regs = {}
        got = want = None
        if kind == 0:
            ax = rng.randrange(0x10000)
            g, mem, planes = make_game(m)
            lib.misc_store_1204(ctypes.byref(g), ax)
            address, regs = 0x4344, {'ax': ax}
        elif kind == 1:
            record = rng.randrange(0x0400, 0xE000)
            g, mem, planes = make_game(m)
            lib.misc_mark_record(ctypes.c_void_p(g.ds), record)
            address, regs = 0xA075, {'si': record}
        elif kind == 2:
            m.ds_write(0xDE50, struct.pack('<H', rng.randrange(0x10000)))
            ax = rng.choice([rng.randrange(0x10000), m.rw(m.DATA_SEG, 0xDE50) + rng.randrange(-0x200, 0x200) & 0xFFFF])
            g, mem, planes = make_game(m)
            got = lib.misc_band_test(ctypes.c_void_p(g.ds), ax)
            address, regs = 0xC20B, {'ax': ax}
        elif kind == 3:
            m.ds_write(0x119A, struct.pack('<H', rng.choice([0, rng.randrange(1, 20)])))
            g, mem, planes = make_game(m)
            lib.misc_append_figures(ctypes.c_void_p(g.ds))
            address = 0xACE1
        elif kind == 4:
            count = rng.choice([0, rng.randrange(1, 12)])
            m.ds_write(0xADB6, bytes(rng.randrange(0x41, 0x48) for _ in range(16)))
            m.ds_write(0xADD4, struct.pack('<H', count))
            text = bytes(rng.randrange(0x41, 0x50) for _ in range(40))
            m.ds_write(0x8200, text)
            g, mem, planes = make_game(m)
            end = ctypes.c_uint16()
            got = lib.misc_collect_char(ctypes.c_void_p(g.ds), 0x8200, ctypes.byref(end))
            address, regs = 0x9BA6, {'si': 0x8200}
        elif kind == 5:
            record, ax, bx = rng.randrange(0x0B00, 0x0D00), rng.randrange(0x10000), rng.randrange(0x10000)
            g, mem, planes = make_game(m)
            lib.misc_cell_position(ctypes.c_void_p(g.ds), record, ax, bx)
            address, regs = 0xDF00, {'si': record, 'ax': ax, 'bx': bx}
        else:
            g, mem, planes = make_game(m)
            lib.misc_frame_lines_abec(ctypes.byref(g))
            address = 0x9A01
        out = m.call(0, address, **regs)
        CASES += 1
        if address == 0xC20B:
            want = out['ax'] | (m.r(dosemu.UC_X86_REG_EFLAGS) & 1) << 16
        elif address == 0x9BA6:
            want = out['ax']
            if end.value != out['si']:
                return [f'9BA6 case {i}: SI C {end.value:04X}, original {out["si"]:04X}']
        if got != want:
            return [f'{address:04X} case {i}: C {got:X}, original {want:X}']
        compare(f'{address:04X} case {i}', mem, planes, m, regions(m), fails)
        if fails:
            return fails
    return fails
