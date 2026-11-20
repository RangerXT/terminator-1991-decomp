"""Complete upgrade item path of 855A: EGA/VGA selected, cancel, no weapon.
Only ADD SP,4 at 8652 is NOPed for isolated no-weapon returns; ordinary menu/action
unwinds at 571F/574F execute unchanged. No-weapon dialog uses nonmodal source gate.
"""
import ctypes, os, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_menu import Call, Platform
from test_polyfill import planes_of
CASES = 0

def run(ctx):
    global CASES
    fails = []
    upgraded = canceled = empty = 0
    for i in range(48):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        mode = i%2
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        if mode:
            m.w(dosemu.UC_X86_REG_AX, 0x13)
            m._video()
        m.ds_write(0xADCF, bytes([mode]))
        m.ds_write(0x5A4E, bytes([255]))
        word(0x1234, 0)
        m.ds_write(0xC4AB, bytes([0]))
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.call(0, 0x5032, si=0x0E7A, ax=12, bx=8, cx=22, dx=10, es=m.DATA_SEG, max_instr=100_000_000)
        m.ds_write(0x5BD9, bytes(0x59))
        m.ds_write(0x05B0, bytes(144))
        ids = m.ds_read(0x78DC, 8)
        count = 0 if i%6 in [0, 1] else 1+i%4
        cancel = i//2%3 == 1
        target = i%max(count, 1)
        for j in range(count):
            name = 0x8200+j*20
            m.ds_write(name, ('WEAPON %02d'%j).encode()+bytes([0]))
            m.ds_write(0x05B0+j*6, struct.pack('<H4B', name, ids[j%8], 1, 1, 1))
        word(0x03A2, 0x05B0+count*6)
        definition = 0x8300
        m.ds_write(definition, bytes([0x23 if i//6%2 else 0x26, 1, 1, 10]))
        word(0x03A0, 0x04D4 if i//12%2 else 0x0508)
        m.wb(dosemu.LOAD_SEG, 0x8652, bytes([0x90])*3)
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, bytes([0xCB]))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        logs = [[], []]
        waits = [0, 0]
        def effect(which, write, op):
            if op == 0x02C6:
                n = waits[which]
                waits[which] += 1
                for o in [0x5BDA, 0x5BF5, 0x5C21, 0x5C29]:
                    write(o, bytes([0]))
                if cancel:
                    write(0x5BDA, bytes([255]))
                elif n < target:
                    write(0x5C29, bytes([255]))
                else:
                    write(0x5BF5, bytes([255]))
            elif op == 0x1001:
                write(0x5BDA, bytes([0]))
            else:
                raise RuntimeError('unexpected upgrade input %04x'%op)
            return 0
        @Call
        def callback(gp, op, a, b, user):
            logs[0].append((op, a, b, mem.raw[:0xA0000], planes.raw, screen.raw))
            return effect(0, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op)
        def hook(uc, address, size, user):
            cs = m.r(dosemu.UC_X86_REG_CS)
            ip = m.r(dosemu.UC_X86_REG_IP)
            if cs == dosemu.LOAD_SEG+0x5776 and ip == 0x02C6:
                op, a, b = 0x02C6, m.r(dosemu.UC_X86_REG_CX), 0
            elif cs == dosemu.LOAD_SEG and ip == (0x9F07 if mode else 0x4B3A) and m.ds_read(0x5BDA, 1)[0]:
                op, a, b = 0x1001, 0, 0
            else:
                return
            logs[1].append((op, a, b, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m), bytes(m.vga.chunky)))
            effect(1, m.ds_write, op)
        m.uc.hook_add(UC_HOOK_CODE, hook)
        host = Platform(callback, None)
        got = ctx.lib.shop_add_item(ctypes.byref(g), definition, 0x1138, ctypes.byref(host), None, screen)
        m.call(0, 0x855A, si=definition, di=0x1138, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        want = 4 if not count else 3 if cancel else 2
        if got != want or waits[0] != waits[1] or len(logs[0]) != len(logs[1]):
            return ['shop upgrade result/polls %d: %s != %s'%(i, got, want)]
        stack = m.r(dosemu.UC_X86_REG_SS)<<4
        for a, b in zip(*logs):
            if a[:3] != b[:3] or a[4] != b[4] or (mode and a[5] != b[5]) or any(a[3][lo:hi] != b[3][lo:hi] for lo, hi in [(0, stack), (stack+1024, 0xA0000)]):
                return ['shop upgrade input boundary %d'%i]
        if mode and screen.raw != bytes(m.vga.chunky):
            return ['shop upgrade VGA pixels %d'%i]
        compare('shop upgrade full %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        upgraded += got == 2
        canceled += got == 3
        empty += got == 4
    print('    shop upgrades: upgraded=%d canceled=%d no-weapon=%d'%(upgraded, canceled, empty))
    if not all([upgraded, canceled, empty]):
        return ['shop upgrade coverage missing']
    return fails
