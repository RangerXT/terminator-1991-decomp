"""Line/needle BX consumed by the guarded vehicle-exit combat path."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    ctx.lib.line_to_bx.restype = ctx.lib.hud_compass_needle_bx.restype = ctypes.c_uint16
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x0F32)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(1024):
        m.ds_write(0, saved)
        x0 = rng.randrange(320)
        x1 = rng.randrange(320)
        y0 = rng.randrange(200)
        y1 = rng.randrange(200)
        if i%4 == 0:
            x1 = x0
        if i%4 == 1:
            y1 = y0
        if i%16 == 0:
            x0 = x1 = [8, 311][i//16%2]
        if i%16 == 1:
            y0 = y1 = [8, 110][i//16%2]
        word(0x122E, x0)
        word(0x1230, y0)
        word(0x1234, i%3*0x2000)
        g, mem, planes = make_game(m)
        bx = ctx.lib.line_to_bx(ctypes.c_void_p(g.ds), planes, x1, y1)
        out = m.call(0, 0x0F32, ax=x1, bx=y1)
        CASES += 1
        if bx != out['bx']:
            return ['line BX %d %s: %04x != %04x'%(i, (x0, y0, x1, y1), bx, out['bx'])]
        compare('line state %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(1024):
        m.ds_write(0, saved)
        heading = i%512
        word(0x122C, i%3)
        word(0x1234, i%3*0x2000)
        m.ds_write(0x7AC5, bytes([i//512]))
        history = 0x7B3C
        word(history+i%3*4, 65535 if i%4 == 0 else 212+(i%31)-15)
        word(history+i%3*4+2, 143+(i%29)-14)
        g, mem, planes = make_game(m)
        bx = ctx.lib.hud_compass_needle_bx(ctypes.byref(g), history, heading, 14)
        out = m.call(0x11BC, 0x1A01, far=True, di=history, bx=heading, ax=14)
        CASES += 1
        if bx != out['bx']:
            return ['needle BX %d: %04x != %04x'%(i, bx, out['bx'])]
        compare('needle state %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
