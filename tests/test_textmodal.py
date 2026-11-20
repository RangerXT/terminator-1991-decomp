"""Complete planar modal 5032, with scripted input/timing but native drawing/state."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import Game, make_game, compare, STACK_BYTES
from test_polyfill import planes_of
CASES = 0
Poll = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p)
class Platform(ctypes.Structure):
    _fields_ = [('poll', Poll), ('user', ctypes.c_void_p)]

def run(ctx):
    global CASES
    fails = []
    phases = set()
    for i in range(48):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        def word(off, v):
            m.ds_write(off, struct.pack('<H', v&65535))
        word(0x0200, 0)
        m.ds_write(0x8096, b'\x00')
        m.ds_write(0x5A4E, b'\x00')
        m.ds_write(0xADCF, b'\x00')
        word(0x9A72, 40 if i%2 else 80)
        word(0x1234, i%3*0x2000)
        word(0x122A, (i+1)%3)
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.ds_write(0xC4AB, b'\x00')
        word(0x78AC, 13)
        word(0x78AE, 24)
        word(0x78B0, 0x506)
        m.ds_write(0x5BDA, bytes([i%2]))
        m.ds_write(0x5BF5, bytes([(i//2)%2]))
        # Retrace timing is a platform boundary; its rendering-free body is stubbed.
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, b'\xcb')
        g, mem, planes = make_game(m)
        mine = []
        original = []
        counts = [[0, 0, 0], [0, 0, 0]]
        def apply(which, phase, put):
            counts[which][phase] += 1
            n = counts[which][phase]
            if phase == 0:
                if i%8 == 7 and n == 1:
                    put(0x0200, struct.pack('<H', 4))
                elif n >= 2:
                    put(0x5BDA, b'\x00')
                    put(0x5BF5, b'\x00')
            elif phase == 1 and n >= 2+i%3:
                put(0x5BF5 if i%2 else 0x5BDA, b'\xff')
            elif phase == 2 and n >= 2+i%2:
                put(0x5BDA, b'\x00')
                put(0x5BF5, b'\x00')
        @Poll
        def poll(gp, phase, ticks, user):
            phases.add(phase)
            mine.append((phase, ticks, mem.raw[:0xA0000], planes.raw))
            apply(0, phase, lambda o, b:ctypes.memmove(g.ds+o, b, len(b)))
            return 0
        def hook(uc, a, size, user):
            ip = uc.reg_read(dosemu.UC_X86_REG_IP)
            cs = uc.reg_read(dosemu.UC_X86_REG_CS)
            if cs == dosemu.LOAD_SEG and ip == 0x5169:
                if not (m.ds_read(0x5BDA, 1)[0] or m.ds_read(0x5BF5, 1)[0]):
                    return
                phase, ticks = 0, 0
            elif cs == dosemu.LOAD_SEG and ip == 0x5195:
                phase, ticks = 2, 0
            elif cs == dosemu.LOAD_SEG+0x5776 and ip == 0x02C6:
                phase, ticks = 1, uc.reg_read(dosemu.UC_X86_REG_CX)
            else:
                return
            original.append((phase, ticks, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m)))
            apply(1, phase, m.ds_write)
        m.uc.hook_add(UC_HOOK_CODE, hook)
        host = Platform(poll, None)
        status = ctx.lib.textbox_draw(ctypes.byref(g), 0x0729, 6, 4, 13, 3, ctypes.byref(host))
        m.call(0, 0x5032, si=0x0729, ax=6, bx=4, cx=13, dx=3, es=m.DATA_SEG)
        CASES += 1
        if status or counts[0] != counts[1] or len(mine) != len(original):
            return ['modal service count/status %d %s'%(i, counts)]
        stack = m.r(dosemu.UC_X86_REG_SS)<<4
        for a, b in zip(mine, original):
            if a[:2] != b[:2] or a[3] != b[3] or any(a[2][lo:hi] != b[2][lo:hi] for lo, hi in [(0, stack), (stack+STACK_BYTES, 0xA0000)]):
                return ['modal service state %d phase %d'%(i, a[0])]
        compare('modal textbox %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    if phases != {0, 1, 2}:
        return ['missing modal input phase']
    for i in range(12):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0xADCF, b'\x00')
        m.ds_write(0x0200, struct.pack('<H', i%2))
        m.ds_write(0x5A4E, b'\xff')
        m.ds_write(0x8096, bytes([(i//2)%2]))
        g, mem, planes = make_game(m)
        status = ctx.lib.textbox_draw(ctypes.byref(g), 0x0729, 6, 4, 13, 3, None)
        m.call(0, 0x5032, si=0x0729, ax=6, bx=4, cx=13, dx=3, es=m.DATA_SEG)
        CASES += 1
        if status:
            return ['immediate general textbox rejected']
        compare('general immediate textbox %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    m.ds_write(0x0200, bytes(2))
    m.ds_write(0x5A4E, b'\x00')
    m.ds_write(0x8096, b'\x00')
    g, mem, planes = make_game(m)
    before = (mem.raw, planes.raw)
    if ctx.lib.textbox_draw(ctypes.byref(g), 0x0729, 6, 4, 13, 3, None) != -1 or before != (mem.raw, planes.raw):
        return ['missing input host must reject before painting']
    CASES += 1
    return fails
