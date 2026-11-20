"""Indexed cursor save-under/restore, mask pixels, original AX and key movement.
Includes RAM-backed source screen segment, u16 offsets and zero-position sentinel.
"""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.w(dosemu.UC_X86_REG_AX, 19)
    m._video()
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x153A)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, bytes([1]))
        video = 0xA000 if i%2 else 0x9000
        word(0xADDC, video)
        word(0x1212, 0xFF80 if i%3 == 0 else 0x100)
        word(0x1214, 0x8500)
        word(0x1210, [0, 1, 320, 0xFFF0][i%4])
        m.wb(0x8500, 0, bytes([i%256])*65536)
        pattern = bytes((j*37+i)&255 for j in range(65536))
        m.wb(video, 0, pattern)
        m.vga.chunky[:] = pattern
        m.ds_write(0x7C00, bytes(rng.randrange(256) for j in range(64)))
        return pattern
    ctx.lib.screen_draw_mask16_vga.restype = ctypes.c_uint16
    for i in range(256):
        pattern = setup(i)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        x = [0, 1, 7, 15, 304, 319, 65535][i%7]
        y = [0, 1, 100, 199, 65535][i%5]
        rows = [1, 8, 16, 20][i%4]
        got = ctx.lib.screen_draw_mask16_vga(ctypes.byref(g), screen, x, y, rows, 0x7C00)
        out = m.call(0, 0x1492, ax=x, bx=y, cx=rows, si=0x7C00, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if got != out['ax'] or screen.raw != bytes(m.vga.chunky):
            return ['VGA cursor pixels/AX %d'%i]
        compare('VGA cursor %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        ctx.lib.screen_restore_mask16_vga(ctypes.byref(g), screen)
        m.call(0, 0x1517)
        CASES += 1
        if screen.raw != bytes(m.vga.chunky):
            return ['VGA cursor restore pixels %d'%i]
        compare('VGA cursor restore %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(128):
        pattern = setup(i)
        word(0x7BF6, 16)
        word(0x7C90, [0, 1, 304, 65535][i%4])
        word(0x7C92, [0, 1, 184, 65535][i//4%4])
        word(0x724C, 310)
        word(0x9A5A, 184)
        for j, o in enumerate([0x5C26, 0x5C24, 0x5C29, 0x5C21, 0x5C0F]):
            m.ds_write(o, bytes([255 if i&(1<<j) else 0]))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        status = ctx.lib.map_pointer_step_display(ctypes.byref(g), screen)
        m.call(0, 0x830F, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if status or screen.raw != bytes(m.vga.chunky):
            return ['VGA pointer movement %d'%i]
        compare('VGA pointer movement %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
