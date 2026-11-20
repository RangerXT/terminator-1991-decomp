"""Native gameplay opening and queued blasts, retaining sound/border/object host events."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import c_events, set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    calls = []
    source = m.ds_read(m.rw(m.DATA_SEG, 0x01FE), 12)
    for kind, s, o, reg in [(1, 0, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0, 0x0A4F, dosemu.UC_X86_REG_BX), (4, 0x151B, 0x02DE, dosemu.UC_X86_REG_SI)]:
        m.wb(dosemu.LOAD_SEG+s, o, bytes([0xCB if s else 0xC3]))
        addr = ((dosemu.LOAD_SEG+s)<<4)+o
        def hook(uc, a, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&(255 if kind in [1, 5] else 65535)))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    hit = steps = 0
    for i in range(256):
        m.ds_write(0, saved)
        word(0x03A0, 0x508)
        word(0x526, 100)
        word(0x528, 60)
        word(0x508, 0)
        word(0x50C, 0)
        m.ds_write(0x516, bytes([1]))
        m.ds_write(0x521, bytes([0]))
        m.ds_write(0x5A50, bytes([0]))
        m.ds_write(0x5CDC, bytes([0]))
        m.ds_write(0xB69F, bytes([1]))
        m.ds_write(0x1155, bytes([i%4]))
        word(0x854A, 2)
        word(0x119A, 0)
        word(0x119C, 0)
        word(0x116E, 0)
        word(0x1170, 0)
        word(0x020E, 0)
        m.ds_write(0x1153, bytes([0, 0]))
        word(0x5F72, 100)
        count = i%5
        word(0x97B6, count)
        word(0x96F4, 0x96F6+count*12)
        word(0x020C, (i//5)%4)
        for j in range(count):
            at = 0x96F6+j*12
            m.ds_write(at, source)
            word(at, 0 if i%2 else 2000)
            word(at+4, 0)
            word(at+10, [0, 20, 60, 150][(i//20)%4])
        if i < 192:
            m.wb(dosemu.LOAD_SEG, 0x0829, b'\xe8')
        else:
            m.wb(dosemu.LOAD_SEG, 0x0829, b'\xc3')
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        if i < 192:
            status = 0
            ctx.lib.blast_queue_step_native(ctypes.byref(g))
            m.call(0, 0x80B6)
        else:
            status = ctx.lib.gameplay_update_opening(ctypes.byref(g), None, None)
            m.call(0, 0x0809)
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['opening/blast events/status %d'%i]
        compare('native queue/opening %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        hit += any(k == 5 for k, a in calls)
        steps += m.rw(m.DATA_SEG, 0x97B6) < count
    print('    native queue/opening: %d player-feedback cases, %d queue advances'%(hit, steps))
    if not hit or not steps:
        return ['missing queued-blast integration paths']
    return fails
