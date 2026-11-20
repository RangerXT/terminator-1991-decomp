"""Planar menu pixels, original setup, shortcuts/navigation/callback boundaries."""
import ctypes, gzip, os, pickle, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu, capture
from unicorn import UC_HOOK_CODE
from test_drawlist import Game, make_game, compare, STACK_BYTES
from test_polyfill import planes_of
CASES = 0
Call = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p)
class Platform(ctypes.Structure):
    _fields_ = [('call', Call), ('user', ctypes.c_void_p)]

def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(128):
        m.ds_write(0, saved)
        word(0x9A72, 40 if i%2 else 80)
        word(0x91C0, 0x100)
        word(0x91C2, 0x9000)
        word(0x7850, [1, 2, 3, 19, 20, 21, 39][i%7])
        m.ds_write(0xADCF, bytes([0]))
        dest = 0x340+i%3*0x2000
        g, mem, planes = make_game(m)
        status = ctx.lib.menu_highlight(ctypes.byref(g), dest)
        m.call(0x5776, 0x02D5, far=True, di=dest)
        CASES += 1
        if status:
            return ['highlight status']
        compare('menu highlight %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        g, mem, planes = make_game(m)
        status = ctx.lib.menu_unhighlight(ctypes.byref(g))
        m.call(0x5776, 0x0330, far=True)
        CASES += 1
        if status:
            return ['unhighlight status']
        compare('menu unhighlight %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    caps = pickle.load(gzip.open(os.path.join(dosemu.ROOT, 'tests/captures/menu_live.pkl.gz'), 'rb'))
    for i in range(33):
        m = capture.restore(caps[0])
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        params = [m.r(m.REG_BY_NAME[n]) for n in ['si', 'ax', 'bx', 'cx', 'dx', 'di']]
        if i:
            word(0x9A72, 40 if i%2 else 80)
            word(0x1234, i%3*0x2000)
            word(0x122A, (i+1)%3)
            word(0x91C0, 0x100)
            word(0x91C2, 0x9000)
            word(0xC4C4, 0xC4C6)
            word(0xC546, 0)
            m.ds_write(0xC4AB, bytes([0]))
            m.ds_write(0x5BDA, bytes([i%2]))
            m.ds_write(0x5BF5, bytes([i//2%2]))
        saved_opcode = m.rb(dosemu.LOAD_SEG, 0x4A96, 1)
        m.wb(dosemu.LOAD_SEG, 0x4A96, bytes([0xC3]))
        g, mem, planes = make_game(m)
        logs = [[], []]
        counts = [0, 0]
        def release(which, write):
            counts[which] += 1
            if counts[which] >= 2:
                write(0x5BDA, bytes([0]))
                write(0x5BF5, bytes([0]))
        @Call
        def callback(gp, op, a, b, user):
            logs[0].append((op, a, b, mem.raw[:0xA0000], planes.raw))
            release(0, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)))
            return 0
        def hook(uc, address, size, user):
            if m.r(dosemu.UC_X86_REG_CS) == dosemu.LOAD_SEG and m.r(dosemu.UC_X86_REG_IP) == 0x4A6F and (m.ds_read(0x5BDA, 1)[0] or m.ds_read(0x5BF5, 1)[0]):
                logs[1].append((0x1000, 0, 0, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m)))
                release(1, m.ds_write)
        m.uc.hook_add(UC_HOOK_CODE, hook)
        host = Platform(callback, None)
        status = ctx.lib.menu_prepare(ctypes.byref(g), *params, ctypes.byref(host))
        m.call(0, 0x48E6, si=params[0], ax=params[1], bx=params[2], cx=params[3], dx=params[4], di=params[5], es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if status or counts[0] != counts[1] or len(logs[0]) != len(logs[1]):
            return ['prepare status/poll counts %d %s'%(i, counts)]
        stack = m.r(dosemu.UC_X86_REG_SS)<<4
        for a, b in zip(*logs):
            if a[:3] != b[:3] or a[4] != b[4] or any(a[3][lo:hi] != b[3][lo:hi] for lo, hi in [(0, stack), (stack+STACK_BYTES, 0xA0000)]):
                return ['menu prepare input boundary %d meta %s/%s card_equal=%s memory=%s'%(i, a[:3], b[:3], a[4] == b[4], [(hex(j), a[3][j], b[3][j]) for lo, hi in [(0, stack), (stack+STACK_BYTES, 0xA0000)] for j in range(lo, hi) if a[3][j] != b[3][j]][:12])]
        compare('menu prepare %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        if i == 0:
            m.wb(dosemu.LOAD_SEG, 0x4A96, saved_opcode)
            live_prepared = capture.state_of(m)
    seen = set()
    actions = 0
    for i in range(96):
        m = capture.restore(live_prepared if i < 48 else caps[0])
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        word(0x784E, i%7)
        word(0x7816, 0x8500)
        m.ds_write(0x5BD4, bytes(2))
        m.ds_write(0x5BDA, bytes([0]))
        m.ds_write(0x5BF5, bytes([0]))
        m.ds_write(0x5C21, bytes([0]))
        m.ds_write(0x5C29, bytes([0]))
        for j in range(7):
            word(0x8500+j*2, 0x0200+j)
            m.wb(dosemu.LOAD_SEG, 0x0200+j, bytes([0xC3]))
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, bytes([0xCB]))
        g, mem, planes = make_game(m)
        logs = [[], []]
        counts = [0, 0]
        released = [0, 0]
        def effect(which, write, op, a, b):
            seen.add(op)
            if op == 0x02C6:
                n = counts[which]
                counts[which] += 1
                for o in [0x5BDA, 0x5BF5, 0x5C21, 0x5C29]:
                    write(o, bytes([0]))
                if i%6 == 0 or n >= 4:
                    write(0x5BDA, bytes([255]))
                elif i%6 == 1:
                    write(0x5C21 if n < 3 else 0x5BF5, bytes([255]))
                elif i%6 == 2:
                    write(0x5C29 if n < 3 else 0x5BF5, bytes([255]))
                elif i%6 == 3:
                    write(0x5BF5, bytes([255]))
                else:
                    # Buffered ASCII is supplied by the input platform, then
                    # consumed by native 37D5/37AC and the source hotkey scan.
                    write(0x5B70, bytes([ord('j') if i%6 == 4 else ord('?')]))
                    write(0x5B6E, struct.pack('<H', 0x5B70))
                    write(0x5BD4, struct.pack('<H', 1))
                    if n >= 2:
                        write(0x5BDA, bytes([255]))
            elif op == 0x1001:
                released[which] += 1
                if released[which] >= 2:
                    write(0x5BDA, bytes([0]))
            elif op == 0x4B35:
                # A returning option handler. Its body is a boundary; this
                # deterministic input effect exits the next iteration.
                counts[which] = 4;write(0x5BF5, bytes([0]));write(0x5BD4, bytes(2))
            return 0
        @Call
        def callback(gp, op, a, b, user):
            logs[0].append((op, a, b, mem.raw[:0xA0000], planes.raw))
            return effect(0, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op, a, b)
        def hook(uc, address, size, user):
            cs = m.r(dosemu.UC_X86_REG_CS)
            ip = m.r(dosemu.UC_X86_REG_IP)
            if cs == dosemu.LOAD_SEG+0x5776 and ip == 0x02C6:
                op, a, b = 0x02C6, m.r(dosemu.UC_X86_REG_CX), 0
            elif cs == dosemu.LOAD_SEG and ip == 0x4B3A and m.ds_read(0x5BDA, 1)[0]:
                op, a, b = 0x1001, 0, 0
            elif cs == dosemu.LOAD_SEG and 0x0200 <= ip < 0x0207:
                op, a, b = 0x4B35, ip, m.rw(m.DATA_SEG, 0x784E)
            else:
                return
            logs[1].append((op, a, b, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m)))
            effect(1, m.ds_write, op, a, b)
        m.uc.hook_add(UC_HOOK_CODE, hook)
        host = Platform(callback, None)
        if i < 48:
            status = ctx.lib.menu_run(ctypes.byref(g), ctypes.byref(host))
            out = m.call(0, 0x4A96, max_instr=100_000_000)
        else:
            params = [m.r(m.REG_BY_NAME[n]) for n in ['si', 'ax', 'bx', 'cx', 'dx']]+[0x8500]
            status = ctx.lib.menu_display(ctypes.byref(g), *params, ctypes.byref(host))
            out = m.call(0, 0x48E6, si=params[0], ax=params[1], bx=params[2], cx=params[3], dx=params[4], di=params[5], max_instr=100_000_000)
        CASES += 1
        if status or counts[0] != counts[1] or released[0] != released[1] or len(logs[0]) != len(logs[1]):
            return ['navigation status/counts %d %s %s'%(i, counts, released)]
        stack = m.r(dosemu.UC_X86_REG_SS)<<4
        for a, b in zip(*logs):
            if a[:3] != b[:3] or a[4] != b[4] or any(a[3][lo:hi] != b[3][lo:hi] for lo, hi in [(0, stack), (stack+STACK_BYTES, 0xA0000)]):
                return ['menu navigation boundary %d op %04x/%04x'%(i, a[0], b[0])]
        compare('menu navigation %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        actions += sum(a[0] == 0x4B35 for a in logs[0])
    print('    menu original entry + prepared layouts, navigation returning actions=%d'%actions)
    if not actions or not {0x02C6, 0x1001, 0x4B35}.issubset(seen):
        return ['menu navigation coverage missing']
    return fails
