"""Cached 83A6 confirmations with native option handlers: buy/steal/cancel,
upgrades, nonmodal refusal windows and alarms. Entire-shop 82C4 exit is an explicit
boundary (test stub restores caller SP and returns); its body is not replayed into C.
"""
import ctypes, os, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_menu import Call, Platform
from test_blast import GameEvent, set_clock
from test_polyfill import planes_of
from test_imageload import ImageIO
CASES = 0
class ShopServices(ctypes.Structure):
    _fields_ = [('files', ctypes.POINTER(ImageIO)), ('menu', ctypes.POINTER(Platform)), ('text', ctypes.c_void_p), ('screen', ctypes.c_void_p)]

def run(ctx):
    global CASES
    fails = []
    exits = misses = choices = 0
    for i in range(96):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        mode = i%2
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        if mode:
            m.w(dosemu.UC_X86_REG_AX, 19)
            m._video()
        m.ds_write(0xADCF, bytes([mode]))
        m.ds_write(0x5A4E, bytes([255]))
        m.ds_write(0xC4AB, bytes([0]))
        m.ds_write(0xAE04, bytes([0]))
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        word(0x1234, 0)
        m.ds_write(0x5BD9, bytes(0x59))
        word(0x0208, 0x9000)
        word(0xA612, 2 if i//2%2 else 0)
        word(0x009D, 0)
        word(0x009F, 0)
        word(0x94E0, 0x1234)
        word(0x94E2, 0x8000)
        word(0x9A84, 192)
        pharmacy = i//8%2
        names = 0x9BE2 if pharmacy else 0x8400
        word(0x9A6E, names)
        word(0x9A88, 0x8420)
        word(0x9A70, 0x1234)
        for j in range(4):
            m.wb(0x9000, j*48, struct.pack('<8H', 0, 0, 16, 16, 10+20*j, 20, 0, 32)+bytes([255])*32)
            name = 0x8200+j*20
            definition = 0x8300+j*4
            m.ds_write(name, ('ITEM %d'%j).encode()+bytes([0]))
            word(names+j*2, name)
            word(0x8420+j*2, definition)
            id = [11, 15, 0x23, 0x26, 0xA8][(i+j)%5]
            m.ds_write(definition, bytes([id, 1, 2, 1+j]))
        m.ds_write(0x05B0, bytes(144))
        owned = 2 if i//12%2 else 0
        ids = m.ds_read(0x78DC, 8)
        for j in range(owned):
            m.ds_write(0x8800+j*20, ('OWNED %d'%j).encode()+bytes([0]))
            m.ds_write(0x05B0+j*6, struct.pack('<H4B', 0x8800+j*20, ids[j], 1, 1, 1))
        word(0x03A2, 0x05B0+owned*6)
        p = 0x04D4 if i//2%2 else 0x0508
        word(0x03A0, p)
        m.ds_write(p+50, bytes([0]))
        m.ds_write(0x115A, bytes([1]))
        m.ds_write(0x7A18, bytes([0]))
        m.ds_write(0x80E9, bytes([0]))
        m.ds_write(0x9A49, bytes([255 if i%12 == 5 and not pharmacy else 0]))
        m.ds_write(0x9A4B, bytes([0]))
        m.ds_write(0xAAA4, bytes([i//4%2]))
        word(0x117E, [0, 4, 5, 1000][i//3%4])
        word(0x116C, 0)
        word(0x03F2, 1000 if i//16%2 else 1)
        for j in range(6):
            word(0x9A4E+j*2, 0x1138+j)
            m.ds_write(0x1138+j, bytes([0]))
        word(0x1176, 0)
        word(0x03A8, 0x03AA)
        word(0x8546, 0x8600)
        m.ds_write(0x8600, bytes(range(11)))
        word(0x11C4, 65535 if i//3%2 else 0)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *([65535]*200)))
        collision = m.rw(m.DATA_SEG, 0x91B2)
        phase = (((m.rw(m.DATA_SEG, p)+8)>>4)+64+3)%9
        m.wb(collision, 0, bytes(1 if (j%192)%9 == phase else 0 for j in range(0x9000)))
        word(0x119A, 0)
        word(0x119C, 0)
        word(0x03A4, 0x0DF0)
        target = i%4
        hit = i%8 not in [0, 1]
        x = 18+20*target if hit else 0
        y = 28
        if mode and m.rw(m.DATA_SEG, 0xA612) == 2:
            x //= 2
        sp = (m.r(dosemu.UC_X86_REG_SP)-2)&65535
        word(0x9A4C, sp)
        m.wb(dosemu.LOAD_SEG, 0x82C4, bytes([0xBC, sp&255, sp>>8, 0xC3]))
        m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, bytes([0xCB]))
        calls = []
        logs = [[], []]
        waits = [0, 0]
        exited = [False]
        selected = [0]
        action = i%(2 if pharmacy else 3)
        escape = i%16 in [14, 15]
        def effect(which, write, op):
            if op == 0x02C6:
                n = waits[which]
                waits[which] += 1
                for o in [0x5BDA, 0x5BF5, 0x5C21, 0x5C29]:
                    write(o, bytes([0]))
                if escape:
                    write(0x5BDA, bytes([255]))
                elif n < action:
                    write(0x5C29, bytes([255]))
                else:
                    write(0x5BF5, bytes([255]))
            elif op == 0x1000:
                write(0x5BF5, bytes([0]))
                write(0x5BDA, bytes([0]))
            elif op == 0x1001:
                write(0x5BDA, bytes([0]))
            elif op == 0x1002:
                write(0x5BF5, bytes([0]))
            else:
                raise RuntimeError('unexpected confirmation phase %04x'%op)
            return 0
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        @Call
        def callback(gp, op, a, b, user):
            logs[0].append((op, a, b, mem.raw[:0xA0000], planes.raw, screen.raw))
            return effect(0, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op)
        def hook(uc, address, size, user):
            cs = m.r(dosemu.UC_X86_REG_CS)
            ip = m.r(dosemu.UC_X86_REG_IP)
            if cs == dosemu.LOAD_SEG and ip == 0x82C4:
                exited[0] = True
                return
            if cs == dosemu.LOAD_SEG and ip == 0x5737:
                selected[0] += 1
                return
            if cs == dosemu.LOAD_SEG and ip == 0x89A2:
                calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255, m.ds_read(0x80E9, 1)[0]))
                return
            if cs == dosemu.LOAD_SEG+0x5776 and ip == 0x02C6:
                op, a, b = 0x02C6, m.r(dosemu.UC_X86_REG_CX), 0
            elif cs == dosemu.LOAD_SEG and ip == (0x9E36 if mode else 0x4A6F) and (m.ds_read(0x5BDA, 1)[0] or m.ds_read(0x5BF5, 1)[0]):
                op, a, b = 0x1000, 0, 0
            elif cs == dosemu.LOAD_SEG and ip == (0x9F07 if mode else 0x4B3A) and m.ds_read(0x5BDA, 1)[0]:
                op, a, b = 0x1001, 0, 0
            elif cs == dosemu.LOAD_SEG and ip == 0x8449 and m.ds_read(0x5BF5, 1)[0]:
                op, a, b = 0x1002, 0, 0
            else:
                return
            logs[1].append((op, a, b, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m), bytes(m.vga.chunky)))
            effect(1, m.ds_write, op)
        m.uc.hook_add(UC_HOOK_CODE, hook)
        menu = Platform(callback, None)
        host = ShopServices(None, ctypes.pointer(menu), None, ctypes.addressof(screen))
        def events():
            buf = (GameEvent*512)()
            n = ctx.lib.game_events(buf, 512)
            return [(e.kind, e.a, e.b) for e in buf[:n]]
        events()
        set_clock(ctx.lib, m)
        got = ctx.lib.shop_confirm_item(ctypes.byref(g), x, y, ctypes.byref(host))
        m.call(0, 0x83A6, ax=x, bx=y, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        want = 2 if exited[0] else 0
        if got != want or events() != calls or waits[0] != waits[1] or len(logs[0]) != len(logs[1]):
            return ['shop confirmation status/events/polls %d got%d want%d waits%s logs%s'%(i, got, want, waits, [len(v) for v in logs])]
        stack = m.r(dosemu.UC_X86_REG_SS)<<4
        for a, b in zip(*logs):
            if a[:3] != b[:3] or a[4] != b[4] or (mode and a[5] != b[5]) or any(a[3][lo:hi] != b[3][lo:hi] for lo, hi in [(0, stack), (stack+1024, 0xA0000)]):
                return ['shop confirmation input boundary %d op%04x'%(i, a[0])]
        if mode and screen.raw != bytes(m.vga.chunky):
            return ['shop confirmation VGA pixels %d'%i]
        compare('shop confirmation %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        exits += exited[0]
        misses += not hit
        choices += selected[0]
    print('    cached shop confirms: owner exits=%d mask misses=%d nested weapon choices=%d'%(exits, misses, choices))
    if not exits or not misses or not choices:
        return ['shop confirmation coverage missing']
    return fails
