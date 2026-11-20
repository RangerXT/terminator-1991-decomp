"""Dynamic pickup menu text and source transfer ordering, then full planar panel
with real HUD asset IO. Input/retrace release is an explicit platform boundary.
"""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare as compare_full
from test_menu import Call, Platform
from test_imageload import Files, trace_dos, regions, compare, check_memory
from test_polyfill import planes_of
CASES = 0

def setup(m, i, count=20):
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    p = [0x04D4, 0x0508][i%2]
    word(0x03A0, p)
    word(p, 500)
    word(p+4, 500)
    word(p+30, 80)
    word(p+32, 40)
    m.ds_write(p+14, bytes([1]))
    m.ds_write(0xADCF, bytes([0]))
    m.ds_write(0x11CA, bytes([i%3]))
    for j in range(20):
        at = 0x0253+j*13
        name = 0x8200+j*20
        m.ds_write(name, ('ITEM %02d'%j).encode()+bytes([0]))
        m.ds_write(at, struct.pack('<5H3B', 80, 40, 500+(0 if j < count and (j+i)%4 else 300), 500, name, 10+j%5, 1, 2))
    return p

def run(ctx, controller=False, on_menu=None):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    rng = random.Random(0x531C)
    for off, far, seg in [(0x48E6, False, 0), (0x4F4B, False, 0), (0x012A, True, 0x5776)]:
        m.wb(dosemu.LOAD_SEG+seg, off, bytes([0xCB if far else 0xC3]))
    for i in range(0 if controller else 256):
        m.ds_write(0, saved)
        setup(m, i, count=i%21)
        g, mem, planes = make_game(m)
        ctx.lib.pickup_menu_text(ctypes.byref(g))
        m.call(0, 0x531C, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        compare_full('pickup dynamic menu text %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    m.wb(dosemu.LOAD_SEG, 0x53EB, bytes([0xC3]))
    stacks = appends = 0
    for i in range(0 if controller else 512):
        m.ds_write(0, saved)
        setup(m, i)
        index = i%15
        m.ds_write(0x05B0, bytes(120))
        for j in range(i%5):
            m.ds_write(0x05B0+j*6, struct.pack('<H4B', 0x8200+j*20, 10+j, 1, 2, [1, 2, 255][i%3]))
        g, mem, planes = make_game(m)
        status = ctx.lib.pickup_take_selected(ctypes.byref(g), index)
        m.call(0, 0x5397, si=index, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if status:
            return ['pickup transfer unavailable %d'%i]
        compare_full('pickup item transfer %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    # Recreate untouched routines for complete menu/action/restore/HUD comparisons.
    for i in range(24):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        setup(m, i, count=4)
        m.ds_write(0x05B0, bytes(120))
        m.ds_write(0x5BD9, bytes(0x59))
        m.ds_write(0xC4AB, bytes([0]))
        m.ds_write(0xC4C4, struct.pack('<H', 0xC4C6))
        m.ds_write(0xC546, bytes(2))
        m.ds_write(0x1234, struct.pack('<H', i%3*0x2000))
        m.ds_write(0x11CD, struct.pack('<H', i%2))
        # Four contiguous, valid non-weapon item records. All can be selected.
        for j in range(20):
            at = 0x0253+j*13
            m.ds_write(at+4, struct.pack('<H', 500 if j < 4 else 800))
            m.ds_write(at+10, bytes([10, 1, 2]))
            m.ds_write(0x8200+j*20, b'MEDKIT'+bytes([0]))
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, bytes([0xCB]))
        trace_dos(m)
        spans = regions(m)
        g, mem, planes = make_game(m)
        files = Files(m)
        logs = [[], []]
        waits = [0, 0]
        def effect(which, write, op):
            if op == 0x02C6:
                n = waits[which]
                waits[which] += 1
                for o in [0x5BDA, 0x5BF5, 0x5C21, 0x5C29]:
                    write(o, bytes([0]))
                if i%5 == 4:
                    write(0x5BDA, bytes([255]))
                elif n < i%4:
                    write(0x5C29, bytes([255]))
                else:
                    write(0x5BF5, bytes([255]))
            elif op == 0x1001:
                write(0x5BDA, bytes([0]))
            else:
                raise RuntimeError('unexpected pickup poll %04x'%op)
            return 0
        @Call
        def callback(gp, op, a, b, user):
            logs[0].append((op, a, b, mem.raw[:0xA0000], planes.raw))
            return effect(0, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op)
        def hook(uc, address, size, user):
            cs = m.r(dosemu.UC_X86_REG_CS)
            ip = m.r(dosemu.UC_X86_REG_IP)
            if cs == dosemu.LOAD_SEG+0x5776 and ip == 0x02C6:
                op, a, b = 0x02C6, m.r(dosemu.UC_X86_REG_CX), 0
            elif cs == dosemu.LOAD_SEG and ip == 0x4B3A and m.ds_read(0x5BDA, 1)[0]:
                op, a, b = 0x1001, 0, 0
            else:
                return
            logs[1].append((op, a, b, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m)))
            effect(1, m.ds_write, op)
        m.uc.hook_add(UC_HOOK_CODE, hook)
        host = Platform(callback, None)
        if controller:
            for o, v in [(0x99ED, bytes([255])), (0x5BFF, bytes([255])), (0x9A60, struct.pack('<HH', 500, 500))]:
                m.ds_write(o, v)
                ctypes.memmove(g.ds+o, v, len(v))
            status = ctx.lib.pickup_interaction_native(ctypes.byref(g), ctypes.byref(host), ctypes.byref(files.host))
            entry = 0x884B
        else:
            status = ctx.lib.pickup_inventory_panel(ctypes.byref(g), ctypes.byref(host), ctypes.byref(files.host))
            entry = 0x531C
        m.call(0, entry, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if status or waits[0] != waits[1] or len(logs[0]) != len(logs[1]):
            return ['pickup full menu status/polls %d %s'%(i, waits)]
        for a, b in zip(*logs):
            if a[:3] != b[:3] or a[4] != b[4]:
                return ['pickup menu poll input %d'%i]
            error = check_memory(a[3], b[3], spans)
            if error:
                return ['pickup menu poll state %d: %s'%(i, error)]
        if on_menu and i == 0:
            on_menu(logs[0][0], logs[1][0], m)
        if len(files.calls) != len(m.image_calls):
            return ['pickup HUD IO counts %d'%i]
        for a, b in zip(files.calls, m.image_calls):
            if a[0] != b[0]:
                return ['pickup HUD IO args %d'%i]
            error = check_memory(a[1], b[1], spans)
            if error:
                return ['pickup HUD IO state %d: %s'%(i, error)]
        compare('full pickup panel %d'%i, mem, planes, m, spans, fails)
        if fails:
            return fails
        if files.handles:
            return ['pickup HUD IO handles leaked']
    return fails
