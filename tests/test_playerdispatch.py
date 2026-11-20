"""Native playerdispatch with actual resource files; BIOS/stat/stream boundaries independent."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_vehicletransition as base
CASES = 0
def run(ctx):
    global CASES
    base.CASES = 0
    result = base.run(ctx, caller="control")
    CASES = base.CASES
    if result:
        return result
    return ordinary(ctx)

def ordinary(ctx):
    global CASES
    import ctypes, random, struct
    import dosemu
    from unicorn import UC_HOOK_CODE
    from test_drawlist import make_game, compare
    from test_blast import GameEvent, set_clock
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x255)
    fails = []
    calls = []
    m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
    at = (dosemu.LOAD_SEG<<4)+0x89A2
    def sound(uc, address, size, user):
        calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255, m.ds_read(0x80E9, 1)[0]))
    m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def events():
        buf = (GameEvent*512)()
        n = ctx.lib.game_events(buf, 512)
        return [(e.kind, e.a, e.b) for e in buf[:n]]
    for i in range(512):
        m.ds_write(0, saved)
        p = [0x04D4, 0x0508][i%2]
        word(0x03A0, p)
        m.ds_write(p+14, bytes([1 if i%3 else 2]))
        word(p+6, i*37%512)
        word(p+48, 100)
        m.ds_write(0x5BD9, bytes(0x59))
        for o in [0x5C21, 0x5C24, 0x5C26, 0x5BF8, 0x5C2B, 0x5C22, 0x5C0F, 0x5BF6]:
            m.ds_write(o, bytes([255 if rng.randrange(4) == 0 else 0]))
        m.ds_write(0x5CDA, bytes([i//8%16]))
        for o in [0x8096, 0x1155, 0x114C]:
            m.ds_write(o, bytes([255 if i//4%4 == o%4 else 0]))
        word(0x5F72, 20)
        word(0x0416, 300)
        word(p+10, [0, 1, 8, 16, 32][i%5])
        word(p+12, 10)
        word(p+30, 80)
        word(p+32, 40)
        word(p+34, 80*1024+500)
        word(p+36, (80*1024+500)>>16)
        word(p+42, 40*1024+500)
        word(p+44, 0)
        g, mem, planes = make_game(m)
        calls.clear()
        events()
        set_clock(ctx.lib, m)
        dx = ctypes.c_uint32()
        status = ctx.lib.player_control_step_dx(ctypes.byref(g), None, None, ctypes.byref(dx))
        out = m.call(0, 0x0255, es=m.DATA_SEG, max_instr=10_000_000)
        CASES += 1
        if status or events() != calls:
            return ['ordinary player control status/events %d'%i]
        if dx.value != out['dx']:
            return ['ordinary player control DX %d: %04x/%04x'%(i, dx.value, out['dx'])]
        compare('ordinary player control %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
