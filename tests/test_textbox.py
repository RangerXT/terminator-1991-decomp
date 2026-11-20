"""Planar font, bevels, saved backgrounds and nonmodal warnings vs. the executable."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x5032)
    fails = []
    def word(off, v):
        m.ds_write(off, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, b'\x00')
        word(0x9A72, 40 if i%2 else 80)
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.ds_write(0xC4AB, b'\x00')
        word(0x1234, (i%3)*0x2000)
        word(0x122A, i%3)
        word(0x122C, (i+1)%3)
    for i in range(128):
        setup(i)
        dest = 0x80+i%3*0x2000
        width = 3+i%15
        rows = 12+i%21
        g, mem, planes = make_game(m)
        ctx.lib.scene_overlay_save(ctypes.byref(g), dest, width, rows)
        m.call(0x5776, 0x01E0, far=True, di=dest, cx=width, bx=rows, es=m.DATA_SEG)
        CASES += 1
        compare('save %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        setup(i)
        seg = [m.DATA_SEG, 0x9000][i%2]
        text = 0x8200
        raw = bytes([rng.randrange(1, 256) for _ in range(i%27)])+b'\x00'
        m.wb(seg, text, raw)
        word(0xE412, 0xA500+i%12)
        word(0xE414, i%12)
        word(0xE41C, i%3)
        g, mem, planes = make_game(m)
        ctx.lib.screen_text8(ctypes.byref(g), seg, text)
        m.call(0, 0xE0C0, ds=seg, si=text)
        CASES += 1
        compare('font %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(128):
        setup(i)
        m.ds_write(0x7758, bytes([2+i%5]))
        m.ds_write(0x775A, bytes([2+i%6]))
        word(0xC4B4, 24+i%30)
        word(0xC4B6, 8+i%14)
        g, mem, planes = make_game(m)
        ctx.lib.textbox_border(ctypes.byref(g))
        m.call(0x5776, 0x0346, far=True)
        CASES += 1
        compare('border %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        setup(i)
        word(0x0200, i%4)
        m.ds_write(0x8096, bytes([(i//4)%2]))
        m.ds_write(0x5A4E, b'\xff')
        seg = [m.DATA_SEG, 0x9000][i%2]
        word(0xEA36, seg)
        # Actual format: colour; relative x/y, NUL-terminated text; FF sentinel.
        m.wb(seg, 0x8200, bytes([i%16, 1, 1])+b'WARNING\x00'+bytes([1, 2])+b'SYSTEM 1991\x00\xff')
        x = 2+i%6
        y = 2+i%5
        width = 15+i%4
        height = 4
        g, mem, planes = make_game(m)
        status = ctx.lib.textbox_draw_nonmodal(ctypes.byref(g), 0x8200, x, y, width, height)
        m.call(0, 0x5032, si=0x8200, ax=x, bx=y, cx=width, dx=height, es=m.DATA_SEG)
        CASES += 1
        if status:
            return ['textbox rejected']
        compare('textbox %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(96):
        setup(i)
        m.ds_write(0x00B9, bytes([i%2]))
        m.ds_write(0x00BA, bytes([(i//2)%2]))
        g, mem, planes = make_game(m)
        ctx.lib.scene_warning(ctypes.byref(g))
        m.call(0, 0x093A, es=m.DATA_SEG)
        CASES += 1
        compare('warning %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(2):
        setup(i)
        word(0x0200, 0)
        m.ds_write(0x8096, b'\x00')
        m.ds_write(0x5A4E, b'\x00')
        m.ds_write(0xADCF, bytes([i]))
        g, mem, planes = make_game(m)
        before = (mem.raw, planes.raw)
        status = ctx.lib.textbox_draw_nonmodal(ctypes.byref(g), 0x0729, 6, 4, 13, 3)
        CASES += 1
        if status != -1 or before != (mem.raw, planes.raw):
            return ['unsupported textbox mutated state']
    return fails
