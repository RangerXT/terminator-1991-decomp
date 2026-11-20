"""Original shop-upgrade weapon picker: dynamic text, slot mapping, EGA/VGA selection.
Only DOS stack unwinds at 571F/574F are normalized to isolate 56B2's structured return.
Selected windows remain open; cancel restores them. No original output replay into C.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_menu import Call, Platform
from test_polyfill import planes_of
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x56B2)
    fails = []
    ids = saved[0x78DC:0x78DC+8]
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def stock(count, phase):
        m.ds_write(0x05B0, bytes(144))
        n = 0
        for j in range(count):
            name = 0x8200+j*20
            m.ds_write(name, ('WEAPON %02d'%j).encode()+bytes([0]))
            category = 1 if phase or j%3 == 0 else 2
            m.ds_write(0x05B0+j*6, struct.pack('<H4B', name, ids[j%8], 1, category, 1))
            n += category == 1
        return n
    m.wb(dosemu.LOAD_SEG+0x5776, 0x0247, bytes([0xCB]))
    m.wb(dosemu.LOAD_SEG, 0x48E6, bytes([0xC3]))
    m.wb(dosemu.LOAD_SEG, 0x571F, bytes([0x90])*3)
    observed_line = [None]
    def line_hook(uc, address, size, user):
        observed_line[0] = m.r(dosemu.UC_X86_REG_DX)&255
    at = (dosemu.LOAD_SEG<<4)+0x5703
    m.uc.hook_add(UC_HOOK_CODE, line_hook, None, at, at)
    ctx.lib.inventory_weapon_menu_text.restype = ctypes.c_uint8
    ctx.lib.inventory_weapon_menu_choice.restype = ctypes.c_uint16
    for i in range(256):
        m.ds_write(0, saved)
        stock(i%20, False)
        g, mem, planes = make_game(m)
        line = ctx.lib.inventory_weapon_menu_text(ctypes.byref(g))
        out = m.call(0, 0x56B2, dx=0, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if line != observed_line[0]:
            return ['weapon picker line count %d: %s != %s'%(i, line, observed_line[0])]
        compare('weapon picker text %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    m.wb(dosemu.LOAD_SEG, 0x574F, bytes([0xC3]))
    for i in range(256):
        m.ds_write(0, saved)
        m.ds_write(0x792B, bytes(ids[j%8] for j in range(20)))
        index = i%20
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        slot = ctx.lib.inventory_weapon_menu_choice(ds, index)
        out = m.call(0, 0x5737, si=index)
        CASES += 1
        if slot != out['bx'] or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['weapon picker slot %d'%i]
    selected = canceled = empty = 0
    for i in range(64):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        mode = i%2
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
        m.ds_write(0x5A4E, bytes([0]))
        m.ds_write(0x5BD9, bytes(0x59))
        count = stock(0 if i%8 in [0, 1] else 1+i%4, True)
        m.wb(dosemu.LOAD_SEG, 0x571F, bytes([0x90])*3)
        m.wb(dosemu.LOAD_SEG, 0x574F, bytes([0x83, 0xC4, 0x02]))
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, bytes([0xCB]))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        logs = [[], []]
        waits = [0, 0]
        choice = [None]
        target = i%max(count, 1)
        cancel = i//2%4 == 2
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
                raise RuntimeError('unexpected picker input phase %04x'%op)
            return 0
        @Call
        def callback(gp, op, a, b, user):
            logs[0].append((op, a, b, mem.raw[:0xA0000], planes.raw, screen.raw))
            return effect(0, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op)
        def hook(uc, address, size, user):
            cs = m.r(dosemu.UC_X86_REG_CS)
            ip = m.r(dosemu.UC_X86_REG_IP)
            if cs == dosemu.LOAD_SEG and ip == 0x574F:
                choice[0] = m.r(dosemu.UC_X86_REG_BX)
                return
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
        got = ctx.lib.inventory_choose_weapon(ctypes.byref(g), ctypes.byref(host), screen)
        out = m.call(0, 0x56B2, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        want = -3 if not count else -2 if cancel else choice[0]
        if got != want or waits[0] != waits[1] or len(logs[0]) != len(logs[1]):
            return ['weapon picker selection/polls %d: %s != %s'%(i, got, want)]
        stack = m.r(dosemu.UC_X86_REG_SS)<<4
        for a, b in zip(*logs):
            if a[:3] != b[:3] or a[4] != b[4] or (mode and a[5] != b[5]) or any(a[3][lo:hi] != b[3][lo:hi] for lo, hi in [(0, stack), (stack+1024, 0xA0000)]):
                return ['weapon picker input boundary %d'%i]
        if mode and screen.raw != bytes(m.vga.chunky):
            return ['weapon picker final VGA pixels %d'%i]
        compare('weapon picker full %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        selected += got >= 0
        canceled += got == -2
        empty += got == -3
    print('    weapon picker: selected=%d canceled=%d empty=%d'%(selected, canceled, empty))
    if not all([selected, canceled, empty]):
        return ['weapon picker coverage missing']
    return fails
