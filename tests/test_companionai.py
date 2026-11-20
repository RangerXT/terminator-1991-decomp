"""DB26 with native steering, selection, player-hit feedback and register outputs."""
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
    rng = random.Random(0xDB26)
    calls = []
    fails = []
    shots = [0]
    clear = blocked = 0
    collisionseg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(collisionseg, 0, 0x9000)
    barriers = bytes(j%192%9 == 0 for j in range(0x9000))
    for kind, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
        m.wb(dosemu.LOAD_SEG, off, b'\xc3')
        at = (dosemu.LOAD_SEG<<4)+off
        def event(uc, address, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&255))
        m.uc.hook_add(UC_HOOK_CODE, event, None, at, at)
    def shot(uc, address, size, user):
        shots[0] += 1
    at = (dosemu.LOAD_SEG<<4)+0xBC68
    m.uc.hook_add(UC_HOOK_CODE, shot, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(1536):
        prepare(m, saved, rng, collision, barriers, i, vehicle=vehicle)
        player = m.rw(m.DATA_SEG, 0x03A0)
        col = m.rw(m.DATA_SEG, player+30)
        row = m.rw(m.DATA_SEG, player+32)
        x = m.rw(m.DATA_SEG, player)+[0, 60, 200, 500, 1400, 1600][i%6]
        z = m.rw(m.DATA_SEG, player+4)+(i%3-1)*200
        wx = (col*1024+x)&0xFFFFFFFF
        wz = (row*1024+1024-z)&0xFFFFFFFF
        word(0x055E, wx)
        word(0x0560, wx>>16)
        word(0x0566, wz)
        word(0x0568, wz>>16)
        word(0xE3EC, x)
        word(0xE3EE, z)
        m.ds_write(0x1154, bytes([i%5 != 0]))
        m.ds_write(0x034C, bytes([i%4 == 0]))
        m.ds_write(0x034A, bytes([i%7 == 0]))
        word(0x0546, [0, 1, 10, 15][i%4])
        word(0xDECC, [0, 40000, 65535][i%3])
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.companion_ai(ctypes.byref(g), ctypes.byref(vehicle_host)) if vehicle else ctx.lib.companion_ai_on_foot(ctypes.byref(g))
        m.call(0, 0xDB26, max_instr=2_000_000)
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['companion AI status/events %d'%i]
        compare('companion AI %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        if i%5:
            clear += bool(m.ds_read(0x0349, 1)[0])
            blocked += not m.ds_read(0x0349, 1)[0]
    print('    companion AI: clear=%d blocked=%d original player-shot calls=%d'%(clear, blocked, shots[0]))
    if not all([clear, blocked, shots[0]]):
        return ['missing companion AI branches']
    return fails
