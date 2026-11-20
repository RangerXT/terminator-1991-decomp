"""Original player collision: cached positions, nine cells, rotated object bitmaps,
rollback/normalization, vehicle sounds, and native fast-travel push-out.
Synthetic maps exercise boundary branches; installed game tables remain source inputs.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services
from test_blast import c_events
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    rng = random.Random(0x1FCC)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    mapseg = m.rw(m.DATA_SEG, 0x91B2)
    calls = []
    m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
    at = (dosemu.LOAD_SEG<<4)+0x89A2
    def sound(uc, address, size, user):
        calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255))
    m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)
    ctx.lib.player_collision_test.restype = ctypes.c_uint8
    blocked = clear = rolled = 0
    for i in range(1536):
        m.ds_write(0, saved)
        p = [0x04D4, 0x0508][i%2]
        word(0x03A0, p)
        m.ds_write(p+14, bytes([1 if i%3 else 2]))
        m.ds_write(0x8683, bytes([i//3%2]))
        x, z = [512, 496, 520, 560, 480, 528, 511, 513][i%8], [512, 480, 527, 560, 495, 513, 496][i%7]
        word(p, x)
        word(p+4, z)
        word(p+30, 80)
        word(p+32, 40)
        word(p+34, 80*1024+x)
        word(p+36, (80*1024+x)>>16)
        word(p+42, 40*1024+1024-z)
        word(p+44, 0)
        for j, o in enumerate([34, 36, 42, 44]):
            word(0x911E+2*j, m.rw(m.DATA_SEG, p+o))
        word(0x9126, rng.randrange(65536))
        if i < 64:
            word(0x9120, 65535)
            m.ds_write(0x8683, bytes([0]))
        elif i < 128:
            m.ds_write(0x8683, bytes([0]))
        else:
            word(0x911E, m.rw(m.DATA_SEG, p+34)-1)
        m.wb(mapseg, 0, bytes(65536))
        word(0x91B0, 0x9000)
        m.wb(0x9000, 0, bytes(4096))
        word(0x8FEC, 0x0100)
        # Offset word -> header at +2; width/height are source's inclusive bounds.
        m.wb(0x9000, 0x0100, struct.pack('<7H', 0, 0, 0, 4, 4, 8, 8)+bytes([0, 255, 128, 85, 170, 1][i%6])*32)
        for j in range(8):
            m.ds_write(0x8B3A+12*j, struct.pack('<6H', 512, 0, 512, j%4, 0, 0))
        gridx = ((x+8)>>4)+64
        gridz = ((z+8)>>4)+64
        center = (0x9000-192*gridz+gridx)&65535
        if i%13:
            slot = (i%9)*2
            delta = struct.unpack('<h', m.ds_read(0x865D+slot, 2))[0]
            cell = 128 if i%5 == 0 else 1+i%8
            m.wb(mapseg, (center+delta)&65535, bytes([cell]))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        got = ctx.lib.player_collision_test(ctypes.byref(g), p)
        out = m.call(0x11BC, 0x1FCC, far=True, bx=p, max_instr=10_000_000)
        CASES += 1
        if got != (out['flags']&1) or c_events(ctx.lib) != calls:
            return ['player collision flags/events %d'%i]
        compare('player collision %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        blocked += bool(got)
        clear += not got
        rolled += bool(got) and not m.ds_read(0x8683, 1)[0]
    # Native D265 adapter, with cell loading and the 057C follow-up as boundaries.
    active = [None]
    for off in [0x3B88, 0x057C]:
        m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
        at = (dosemu.LOAD_SEG<<4)+off
        def hook(uc, address, size, user, off=off):
            active[0](off)
        m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
    for i in range(64):
        m.ds_write(0, saved)
        p = [0x04D4, 0x0508][i%2]
        word(0x03A0, p)
        m.ds_write(p+14, bytes([1]))
        word(p+6, (i*37)%512)
        word(0x11BE, 2 if i%3 else 0)
        m.wb(mapseg, 0, bytes([128])*65536)
        g, mem, planes = make_game(m)
        logs = [[], []]
        nloads = [0, 0]
        def side(which, read, write, op, clear_map):
            logs[which].append((op, read(p, 52), read(0x8683, 1), read(0x911E, 12)))
            if op == 0x3B88:
                nloads[which] += 1
                if nloads[which] >= 1+i%4:
                    clear_map()
            return 0
        active[0] = lambda op:side(1, m.ds_read, m.ds_write, op, lambda:m.wb(mapseg, 0, bytes(65536)))
        @CALLBACK
        def callback(gp, op, arg, user):
            if op not in [0x3B88, 0x057C] or arg:
                return 0xFFFFFFFF
            return side(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op, lambda:ctypes.memset(g.mem+(mapseg<<4), 0, 65536))
        host = Services(callback, None)
        c_events(ctx.lib)
        calls.clear()
        status = ctx.lib.travel_clear_arrival_native(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0xD265, max_instr=10_000_000)
        CASES += 1
        if status or logs[0] != logs[1] or c_events(ctx.lib) != calls:
            return ['native collision arrival state/events %d'%i]
        compare('native arrival collision %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    print('    player collision: clear=%d blocked=%d rolled-back=%d; 64 arrival chains'%(clear, blocked, rolled))
    if not all([clear, blocked, rolled]):
        return ['collision coverage missing']
    return fails
