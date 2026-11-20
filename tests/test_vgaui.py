"""VGA menu text/line/window/overlay primitives vs 11BC, native chunky buffer."""
import ctypes, os, random, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    m = dosemu.Machine()
    m.load(root/'out/emu/states/ingame.pkl')
    m.w(dosemu.UC_X86_REG_AX, 19)
    m._video()
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x29CE)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        pattern = bytes((j*37+i)&255 for j in range(65536))
        m.vga.chunky[:] = pattern
        return pattern
    ctx.lib.screen_text8_vga.restype = ctx.lib.textbox_vga_base.restype = ctypes.c_uint16
    for i in range(256):
        pattern = setup(i)
        m.ds_write(0xADE4, bytes([i%2]))
        word(0xE412, i%20 if i%2 == 0 else i%150)
        word(0xE414, i%15 if i%2 == 0 else i%150)
        word(0xE41C, i%4)
        m.ds_write(0xE40F, bytes([i]))
        seg = [m.DATA_SEG, 0x9000][i%2]
        text = 0x8200
        m.wb(seg, text, bytes(rng.randrange(1, 256) for _ in range(i%25))+bytes([0]))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        got = ctx.lib.screen_text8_vga(ctypes.byref(g), screen, seg, text)
        out = m.call(0x11BC, 0x29CE, far=True, ds=seg, si=text)
        CASES += 1
        if got != out['ax'] or screen.raw != bytes(m.vga.chunky):
            return ['VGA font pixels/AX %d'%i]
        compare('VGA font %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        pattern = setup(i)
        x0 = rng.randrange(320)
        y0 = rng.randrange(200)
        x1 = rng.randrange(320)
        y1 = rng.randrange(200)
        if i%4 == 0:
            x1 = x0
        if i%4 == 1:
            y1 = y0
        word(0x122E, x0)
        word(0x1230, y0)
        m.ds_write(0xE40F, bytes([i]))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        ctx.lib.screen_vga_line_to(ctypes.c_void_p(g.ds), screen, x1, y1)
        m.call(0x11BC, 0x2A65, far=True, ax=x1, bx=y1)
        CASES += 1
        if screen.raw != bytes(m.vga.chunky):
            return ['VGA line pixels %d'%i]
        compare('VGA line %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(64):
        pattern = setup(i)
        word(0x91BC, 0x100)
        word(0x91BE, 0x9000)
        m.ds_write(0xAE04, bytes([i%3]))
        word(0xAF22, 0x140)
        word(0xAF24, 19)
        word(0xAF26, 9)
        source = 0x345+i%3*100
        width = 3+i%29
        rows = 3+i%21
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        ctx.lib.scene_vga_overlay_save(ctypes.byref(g), screen, source, width, rows)
        m.call(0x11BC, 0x2B48, far=True, si=source, ax=width, cx=rows)
        CASES += 1
        if screen.raw != bytes(m.vga.chunky):
            return ['VGA save pixels']
        compare('VGA save %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        screen[0x350] = 0x44
        m.vga.chunky[0x350] = 0x44
        ctx.lib.scene_vga_overlay_restore(ctypes.byref(g), screen)
        m.call(0x11BC, 0x2B91, far=True)
        CASES += 1
        if screen.raw != bytes(m.vga.chunky):
            return ['VGA restore pixels']
        compare('VGA restore %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        word(0x7850, 1+i%25)
        ctypes.memmove(g.ds+0x7850, struct.pack('<H', 1+i%25), 2)
        ctx.lib.menu_vga_highlight(ctypes.c_void_p(g.ds), screen, source)
        m.call(0x11BC, 0x2B1D, far=True, di=source)
        CASES += 1
        if screen.raw != bytes(m.vga.chunky):
            return ['VGA highlight pixels']
        compare('VGA highlight %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(48):
        pattern = setup(i)
        word(0x91BC, 0x100)
        word(0x91BE, 0x9000)
        m.ds_write(0xAE04, bytes([0]))
        word(0xEA36, m.DATA_SEG)
        m.ds_write(0x8200, bytes([i%16]))
        args = [0x8200, 2+i%3, 2+i%5, 10+i%8, 4+i%7]
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        si = ctx.lib.textbox_vga_base(ctypes.byref(g), screen, *args)
        out = m.call(0x11BC, 0x2C58, far=True, si=args[0], ax=args[1], bx=args[2], cx=args[3], dx=args[4])
        CASES += 1
        if si != out['si'] or screen.raw != bytes(m.vga.chunky):
            return ['VGA window pixels/SI %d'%i]
        compare('VGA window base %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
