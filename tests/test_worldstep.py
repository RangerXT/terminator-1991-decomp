"""B5F9 composition: native on-foot opponents/clock/steering/companion motion.
Only two modal panels and movie/wait/stream/camera-reset are external stubs.
Compare full memory/EGA, hardware events and input state at each external boundary.
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
    rng = random.Random(0xB5F9)
    calls = []
    fails = []
    active = [None]
    ops = {}
    companion_calls = [0]
    collisionseg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(collisionseg, 0, 0x9000)
    barriers = bytes(j%192%9 == 0 for j in range(0x9000))
    for kind, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
        m.wb(dosemu.LOAD_SEG, off, b'\xc3')
        at = (dosemu.LOAD_SEG<<4)+off
        def event(uc, address, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&255))
        m.uc.hook_add(UC_HOOK_CODE, event, None, at, at)
    external = [(0, off, False) for off in [0xB210, 0x3B88, 0x7A28, 0x57E7, 0x57D4]]+[(0x5776, 0x02C6, True)]
    for seg, off, far in external:
        m.wb(dosemu.LOAD_SEG+seg, off, b'\xcb' if far else b'\xc3')
        at = ((dosemu.LOAD_SEG+seg)<<4)+off
        def service(uc, address, size, user, off=off):
            arg = m.r(dosemu.UC_X86_REG_SI) if off == 0xB210 else m.r(dosemu.UC_X86_REG_CX) if off == 0x02C6 else 0
            active[0](off, arg)
        m.uc.hook_add(UC_HOOK_CODE, service, None, at, at)
    def watch_ai(uc, address, size, user):
        companion_calls[0] += 1
    at = (dosemu.LOAD_SEG<<4)+0xDB26
    m.uc.hook_add(UC_HOOK_CODE, watch_ai, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(1024):
        prepare(m, saved, rng, collision, barriers, i, vehicle=vehicle)
        mode = i%5
        word(0x11BE, mode)
        m.ds_write(0xB69F, bytes([200 if i%3 else 0]))
        m.ds_write(0x0345, bytes([i%5 == 0]))
        m.ds_write(0x01DE, bytes([i%7 == 0]))
        m.ds_write(0xAF52, bytes([i%3 == 0]))
        m.ds_write(0xDE37, bytes([i%6]))
        m.ds_write(0x0348, bytes([[58, 59, 60][(i//6)%3]]))
        m.ds_write(0x034E, bytes([i%3 == 0]))
        p = m.rw(m.DATA_SEG, 0x03A0)
        col = m.rw(m.DATA_SEG, p+30)+(i//3%7-3)
        row = m.rw(m.DATA_SEG, p+32)
        word(0x055A, col)
        word(0x055C, row)
        wx = col*1024+300
        wz = row*1024+700
        word(0x055E, wx)
        word(0x0560, wx>>16)
        word(0x0566, wz)
        word(0x0568, wz>>16)
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        logs = [[], []]
        errors = []
        def effect(which, read, write, service, arg):
            logs[which].append((service, arg, read(0x0300, 0x300), read(0xDE3C, 2), read(0x7242, 2)))
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
        status = ctx.lib.world_step(ctypes.byref(g), ctypes.byref(host), ctypes.byref(vehicle_host)) if vehicle else ctx.lib.world_step_on_foot(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0xB5F9, max_instr=2_000_000)
        CASES += 1
        if status or errors or c_events(ctx.lib) != calls or logs[0] != logs[1]:
            return ['world step %d status/events/boundary differ: %s'%(i, errors)]
        compare('world step %d mode %d'%(i, mode), mem, planes, m, fails)
        if fails:
            return fails
        for op, *_ in logs[0]:
            ops[op] = ops.get(op, 0)+1
    m.ds_write(0, saved)
    p = m.rw(m.DATA_SEG, 0x03A0)
    m.ds_write(p+14, b'\2')
    g, mem, planes = make_game(m)
    before = (mem.raw, planes.raw)
    if ctx.lib.world_step_on_foot(ctypes.byref(g), None) != -1 or before != (mem.raw, planes.raw):
        return ['world vehicle-target rejection']
    CASES += 1
    print('    native world-step external boundaries:', {('%04X'%k):v for k, v in ops.items()})
    print('    native DB26 calls in world composition:', companion_calls[0])
    if not companion_calls[0] or any(not ops.get(k) for k in [0x57E7, 0x57D4]):
        return ['missing world-step companion branches']
    return fails
