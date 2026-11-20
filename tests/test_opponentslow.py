"""B7B6 on-foot controller vs original, with explicit movie/wait/stream/camera stubs.
Attack, inventory, queries, steering, placements and scratch-register flow are native.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services
from test_blast import c_events, set_clock
from ai_helpers import prepare
from test_vehicletransition import VehicleServices
CASES = 0


def run(ctx, vehicle=False):
    global CASES
    CASES = 0
    vehicle_host = VehicleServices()
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xB7B6)
    calls = []
    fails = []
    paths = {}
    active = [None]
    collisionseg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(collisionseg, 0, 0x9000)
    barriers = bytes(j%192%9 == 0 for j in range(0x9000))
    for kind, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
        m.wb(dosemu.LOAD_SEG, off, b'\xc3')
        at = (dosemu.LOAD_SEG<<4)+off
        def event(uc, address, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&255))
        m.uc.hook_add(UC_HOOK_CODE, event, None, at, at)
    for off in [0xBFB3, 0xBF1B, 0xC1B0, 0xB94A, 0xBAB7, 0xBBF1, 0xC14C, 0xB210]:
        at = (dosemu.LOAD_SEG<<4)+off
        def watch(uc, address, size, user, off=off):
            paths[off] = paths.get(off, 0)+1
        m.uc.hook_add(UC_HOOK_CODE, watch, None, at, at)
    for seg, off, far in [(0, 0xB210, False), (0x5776, 0x02C6, True), (0, 0x3B88, False), (0, 0x7A28, False)]:
        m.wb(dosemu.LOAD_SEG+seg, off, b'\xcb' if far else b'\xc3')
        at = ((dosemu.LOAD_SEG+seg)<<4)+off
        def service(uc, address, size, user, off=off):
            arg = m.r(dosemu.UC_X86_REG_SI) if off == 0xB210 else m.r(dosemu.UC_X86_REG_CX) if off == 0x02C6 else 0
            if off == 0xB210:
                assert [m.r(reg) for reg in [dosemu.UC_X86_REG_AX, dosemu.UC_X86_REG_BX, dosemu.UC_X86_REG_CX]] == [40, 8, 0]
            active[0](off, arg)
        m.uc.hook_add(UC_HOOK_CODE, service, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    external = 0
    for i in range(1568):
        prepare(m, saved, rng, collision, barriers, i, vehicle=vehicle)
        m.ds_write(0xB69F, bytes([0 if i%2 else 200]))
        word(0x0386, 10000 if i%3 else 0)
        if i >= 1536:
            player = m.rw(m.DATA_SEG, 0x03A0)
            actor = m.rw(m.DATA_SEG, 0x04BA)
            word(actor+30, m.rw(m.DATA_SEG, player+30)+3)
            word(0x04D2, 1)
            word(0x97B8, 65535)
            m.ds_write(0x115C, b'\0')
            m.ds_write(0xDE3C, bytes([[0, 0x80, 0x81][i%3]]))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        logs = [[], []]
        errors = []
        def effect(which, read, write, service, arg):
            logs[which].append((service, arg, read(0xDB61, 1), read(0xDE3C, 2), read(0x7242, 2)))
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            return 0
        active[0] = lambda service, arg:effect(1, m.ds_read, m.ds_write, service, arg)
        @CALLBACK
        def callback(gp, service, arg, user):
            try:
                return effect(0, lambda off, n:ctypes.string_at(g.ds+off, n), lambda off, b:ctypes.memmove(g.ds+off, b, len(b)), service, arg)
            except Exception as exc:
                errors.append(repr(exc))
                return 0xFFFFFFFF
        host = Services(callback, None)
        status = ctx.lib.opponent_controller_slow(ctypes.byref(g), ctypes.byref(host), ctypes.byref(vehicle_host)) if vehicle else ctx.lib.opponent_controller_slow_on_foot(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0xB7B6, max_instr=2_000_000)
        CASES += 1
        if status or errors or c_events(ctx.lib) != calls or logs[0] != logs[1]:
            return ['slow controller status/events %d: status=%d errors=%s native=%s original=%s logs=%s'%(i, status, errors, c_events(ctx.lib), calls, logs)]
        compare('slow controller %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        external += bool(logs[0])
    ctx.lib.opponent_fire_at_companion_state.restype = ctypes.c_uint32
    for i in range(768):
        prepare(m, saved, rng, collision, barriers, i, vehicle=vehicle)
        word(0x0386, 10000 if i%2 else 0)
        ax = rng.randrange(65536)
        dx = rng.randrange(65536)
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        got = ctx.lib.opponent_fire_at_companion_state(ctypes.byref(g), ax, dx)
        out = m.call(0, 0xBFB3, ax=ax, dx=dx)
        CASES += 1
        if got != out['ax']|(out['dx']<<16) or c_events(ctx.lib) != calls:
            return ['companion attack register state %d: %08x != %08x'%(i, got, out['ax']|(out['dx']<<16))]
        compare('companion attack register state %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    print('    slow controller paths=%s; presentation service chains=%d'%({('%04X'%k):v for k, v in paths.items()}, external))
    if not external or any(not paths.get(off) for off in [0xBFB3, 0xBF1B, 0xC1B0, 0xBAB7, 0xBBF1, 0xC14C]):
        return ['missing slow-controller branches']
    return fails
