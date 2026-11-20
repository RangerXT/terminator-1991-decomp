"""Full D177/B588/B5F9 native on-foot simulation, with actual original AI updates.
Cell IO, two modal panels, movie/wait/camera hardware are explicit external services.
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
    rng = random.Random(0xD177)
    calls = []
    fails = []
    active = [None]
    steps = [0]
    encounters = [0]
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
    for off in [0xB5F9, 0xBBF1, 0xC35F]:
        at = (dosemu.LOAD_SEG<<4)+off
        def watch(uc, address, size, user, off=off):
            if off == 0xB5F9:
                steps[0] += 1
            else:
                encounters[0] += 1
        m.uc.hook_add(UC_HOOK_CODE, watch, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    total_steps = total_encounters = 0
    for i in range(48):
        prepare(m, saved, rng, collision, barriers, i, vehicle=vehicle)
        p = m.rw(m.DATA_SEG, 0x03A0)
        other = m.rw(m.DATA_SEG, 0x04BA)
        mode = (i//2)%3
        col = m.rw(m.DATA_SEG, p+30)
        row = m.rw(m.DATA_SEG, p+32)
        word(other+30, col+5)
        word(other+32, row)
        wx = (col+5)*1024+500
        wz = row*1024+500
        word(other+34, wx)
        word(other+36, wx>>16)
        word(other+42, wz)
        word(other+44, wz>>16)
        word(other, 500)
        word(other+4, 524)
        word(0x055E, wx)
        word(0x0560, wx>>16)
        word(0x0566, wz)
        word(0x0568, wz>>16)
        word(0x055A, col+5)
        word(0x055C, row)
        word(0xE3EC, 5*1024+500)
        word(0xE3EE, 524)
        word(p+10, 20)
        word(0xE272, 400)
        m.ds_write(0xE26A, struct.pack('<4H', col+1, row+1, 111, 777))
        word(other+28, 5 if mode == 2 else 200)
        word(other+26, 0)
        word(0x04D2, 200 if mode == 0 else 5)
        word(0x11C0, 100)
        word(0x1174, 0)
        word(0x11BE, i%5)
        word(0x11C2, 2000)
        for off, v in [(0x0345, 0), (0x01DE, 0), (0x034E, 255), (0xDE37, 0), (0x0348, 0), (0x1152, 0), (0x1153, 0), (0x1154, 0), (0xB69F, 200)]:
            m.ds_write(off, bytes([v]))
        m.ds_write(0x97B8, bytes(400))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.wb(collisionseg, 0, barriers)
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        logs = [[], []]
        errors = []
        steps[0] = encounters[0] = 0
        def effect(which, read, write, service, arg):
            logs[which].append((service, arg, read(0xE26A, 20), read(0x0300, 0x300), read(0xDE3C, 2)))
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
        status = ctx.lib.travel_run_native_simulation(ctypes.byref(g), ctypes.byref(host), ctypes.byref(host), ctypes.byref(vehicle_host)) if vehicle else ctx.lib.travel_run_native_world(ctypes.byref(g), ctypes.byref(host), ctypes.byref(host))
        m.call(0, 0xD177, max_instr=50_000_000)
        CASES += 1
        if status or errors or c_events(ctx.lib) != calls or logs[0] != logs[1]:
            return ['native world travel %d mode %d status/events differ %s'%(i, mode, errors)]
        compare('native world travel %d mode %d'%(i, mode), mem, planes, m, fails)
        if fails:
            return fails
        total_steps += steps[0]
        total_encounters += encounters[0]
    print('    native travel/world: original world steps=%d encounter placements=%d'%(total_steps, total_encounters))
    if total_steps < 100 or not total_encounters:
        return ['missing complete travel simulation branches']
    return fails
