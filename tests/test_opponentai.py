"""C21F native opponent controller and BFB3 companion attack, with real dependencies.
Sound/border hardware are events. Compare original memory, EGA, events and branches.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
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
    rng = random.Random(0xC21F)
    calls = []
    fails = []
    paths = {}
    for kind, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
        m.wb(dosemu.LOAD_SEG, off, b'\xc3')
        at = (dosemu.LOAD_SEG<<4)+off
        def event(uc, address, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&255))
        m.uc.hook_add(UC_HOOK_CODE, event, None, at, at)
    for off in [0xC397, 0xC1B0, 0xB94A, 0xBAB7, 0xC35F, 0xDC7B, 0xC14C, 0xC42F]:
        at = (dosemu.LOAD_SEG<<4)+off
        def watch(uc, address, size, user, off=off):
            paths[off] = paths.get(off, 0)+1
        m.uc.hook_add(UC_HOOK_CODE, watch, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    collisionseg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(collisionseg, 0, 0x9000)
    barriers = bytes(j%192%9 == 0 for j in range(0x9000))
    def setup(i):
        prepare(m, saved, rng, collision, barriers, i, vehicle=vehicle)
    ctx.lib.angle_between_state.restype = ctypes.c_uint32
    ctx.lib.opponent_openings_state.restype = ctypes.c_uint32
    for i in range(512):
        setup(i)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        args = [rng.randrange(-32768, 32768) for _ in range(4)]
        got = ctx.lib.angle_between_state(ds, *args)
        out = m.call(0, 0x5E62, ax=args[0]&65535, bx=args[1]&65535, cx=args[2]&65535, dx=args[3]&65535)
        CASES += 1
        if got != out['ax']|(out['dx']<<16) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['angle register state %d'%i]
        word(0xDE52, rng.randrange(-3000, 4000))
        word(0xDE54, rng.randrange(-3000, 4000))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.opponent_openings_state(ds)
        out = m.call(0, 0xB91F)
        CASES += 1
        if got != out['ax']|((out['flags']&1)<<16) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['opening register state %d'%i]
    for i in range(1536):
        setup(i)
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.opponent_controller(ctypes.byref(g), ctypes.byref(vehicle_host)) if vehicle else ctx.lib.opponent_controller_on_foot(ctypes.byref(g))
        m.call(0, 0xC21F, max_instr=2_000_000)
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['opponent controller status/events %d'%i]
        compare('opponent controller %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    companion_hits = 0
    for i in range(768):
        setup(i)
        word(0x0386, [0, 50, 1000, 65535][i%4])
        word(0x0558, 2)
        before = m.rw(m.DATA_SEG, 0x0556)
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        ctx.lib.opponent_fire_at_companion(ctypes.byref(g))
        m.call(0, 0xBFB3)
        CASES += 1
        if c_events(ctx.lib) != calls:
            return ['companion attack events %d'%i]
        compare('companion attack %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        companion_hits += m.rw(m.DATA_SEG, 0x0556) != before
    m.ds_write(0, saved)
    p = m.rw(m.DATA_SEG, 0x03A0)
    m.ds_write(p+14, b'\2')
    g, mem, planes = make_game(m)
    before = (mem.raw, planes.raw)
    if ctx.lib.opponent_controller_on_foot(ctypes.byref(g)) != -1 or before != (mem.raw, planes.raw):
        return ['vehicle target controller rejection']
    CASES += 1
    print('    controller paths=%s companion attacks with damage=%d'%({('%04X'%k):v for k, v in paths.items()}, companion_hits))
    if not companion_hits or any(not paths.get(off) for off in [0xC397, 0xC1B0, 0xBAB7, 0xC35F, 0xC14C]):
        return ['missing controller branches']
    return fails
