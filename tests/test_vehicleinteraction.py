"""Vehicle proximity/entry bookkeeping vs original. Transition body is a boundary
here; test_vehicleentry composes its real native resources separately.
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
    rng = random.Random(0x400E)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        p = [0x04D4, 0x0508][i%2]
        word(0x03A0, p)
        m.ds_write(0x01DE, bytes([0]))
        word(0x1200, 0)
        word(0x1202, 0x9000)
        word(0x1206, 0x9000)
        word(0x1204, (i%14)*14)
        word(0x04C6, i%14)
        m.wb(0x9000, 0, bytes(rng.randrange(256) for j in range(256)))
        return p
    ctx.lib.vehicle_find_parked.restype = ctypes.c_uint8
    matches = 0
    for i in range(512):
        p = setup(i)
        word(p, rng.randrange(1024))
        word(p+4, rng.randrange(1024))
        word(p+6, rng.randrange(65536))
        word(p+48, rng.randrange(65536))
        m.ds_write(p+14, bytes([2|((i%2)*8)]))
        g, mem, planes = make_game(m)
        status = ctx.lib.vehicle_park(ctypes.byref(g), p)
        m.call(0, 0x434E, bx=p, es=m.DATA_SEG)
        CASES += 1
        if status:
            return ['park status']
        compare('vehicle park %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(512):
        p = setup(i)
        count = i%14
        word(0x1204, count*14)
        for j in range(count):
            cell = (m.ds_read(p+30, 1)[0]|(m.ds_read(p+32, 1)[0]<<8))+(j != i%max(count, 1))
            values = [cell, m.rw(m.DATA_SEG, p)+[0, 199, 200, 201][i%4], m.rw(m.DATA_SEG, p+4), rng.randrange(65536), rng.randrange(65536), rng.randrange(65536), rng.randrange(65536)]
            m.wb(0x9000, j*14, struct.pack('<7H', *(v&65535 for v in values)))
        g, mem, planes = make_game(m)
        got = ctx.lib.vehicle_find_parked(ctypes.byref(g))
        out = m.call(0, 0x4248)
        CASES += 1
        matches += bool(got)
        if got != (out['flags']&1):
            return ['find parked carry %d'%i]
        compare('find parked %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(512):
        p = setup(i)
        count = 1+i%14
        word(0x04C6, count)
        word(0x1204, count*14)
        index = i%count
        g, mem, planes = make_game(m)
        ctx.lib.vehicle_remove_parked(ctypes.byref(g), index)
        m.call(0, 0x421B, ax=index)
        CASES += 1
        compare('parked removal byte count %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(512):
        p = setup(i)
        word(p+30, rng.randrange(65536))
        word(p+32, rng.randrange(65536))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.vehicle_initial_fuel(ds)
        m.call(0, 0x4177)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['initial fuel %d'%i]
    for i in range(128):
        p = setup(i)
        rec = 0x8114
        m.ds_write(rec, struct.pack('<6H', rng.randrange(65536), rng.randrange(65536), rng.randrange(65536), rng.randrange(65536), rng.randrange(117)*2, rng.randrange(65536)))
        word(0x03A6, 0x10F0 if i%2 else 0x0F70+(i%32)*12)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.map_note_removed(ds, rec)
        m.call(0, 0x4586, si=rec, es=m.DATA_SEG)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['removed map record %d'%i]
    calls = []
    active = [None]
    for off in [0x89A2, 0x02B5]:
        m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
        at = (dosemu.LOAD_SEG<<4)+off
        def hook(uc, address, size, user, off=off):
            if off == 0x89A2:
                calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255))
            else:
                active[0](m.r(dosemu.UC_X86_REG_BX))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
    transitions = notices = 0
    for i in range(1024):
        p = setup(i)
        word(p, 500)
        word(p+4, 600)
        word(p+34, 500)
        word(p+42, 600)
        word(p+30, 80)
        word(p+32, 40)
        m.ds_write(p+14, bytes([[1, 2, 9][i//8%3]]))
        word(0x72B0, i%4)
        word(0x72BA, 0x1000)
        word(0x72BC, 0x9000)
        word(0x91D4, 0x8000)
        word(0x5F74, 65535 if i//2%2 else 0x0200)
        word(0x5F78, 0)
        word(0x04C6, 4)
        word(0x1204, 56)
        word(0x03A6, 0x0F70)
        word(0x5F76, 20)
        word(0x72C8, i%4)
        word(0x72D0, i%117*2)
        word(0x5F70, 0x1020)
        word(0x5F72, 0x3040)
        word(0x020A, 65535 if i//256%2 else 0)
        word(9, 0)
        m.ds_write(0x5CE3, bytes([i//4%2]))
        m.ds_write(0x5BEB, bytes([i//16%2]))
        m.ds_write(0xC54A, bytes([i//32%2]))
        m.ds_write(0x11CA, bytes([i//64%3]))
        m.ds_write(0xADCF, bytes([0]))
        for j in range(4):
            x, z = [(0, 0), (20, 190), (190, 20), (200, 0), (3000, 3000)][(i+j)%5]
            m.wb(0x9000, 0x1000+j*14, struct.pack('<7H', (500+x)&65535, 0, (600+z)&65535, 0, (0x9400 if i%2 else 0x1400)|(i%4), 0x0200, i%117*2))
            cell = 80|(40<<8)
            m.wb(0x9000, j*14, struct.pack('<7H', cell if i//128%2 else 0, 500, 600, i%117*2, 0x1460, i%4, 0x1020))
        m.wb(0x8000, 0x0200, struct.pack('<6H', 500, 0, 600, i%4, i%117*2, 0x2060))
        g, mem, planes = make_game(m)
        logs = [[], []]
        calls.clear()
        c_events(ctx.lib)
        def effect(which, read, write, arg):
            actor = struct.unpack('<H', read(0x03A0, 2))[0]
            logs[which].append((arg, read(actor, 52), read(0x5F70, 16), read(0x72C8, 10)))
            write(actor+14, bytes([2]))
            write(actor+10, bytes(2))
            return 0
        active[0] = lambda arg:effect(1, m.ds_read, m.ds_write, arg)
        @CALLBACK
        def callback(gp, op, arg, user):
            if op != 0x02B5:
                return 0xFFFFFFFF
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), arg)
        host = Services(callback, None)
        status = ctx.lib.vehicle_interaction(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0x400E, max_instr=10_000_000, es=m.DATA_SEG)
        CASES += 1
        if status or logs[0] != logs[1] or c_events(ctx.lib) != calls:
            return ['vehicle interaction status/events %d'%i]
        compare('vehicle interaction %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        transitions += len(logs[0])
        notices += bool(calls)
    print('    vehicles: parked matches=%d transitions=%d notice sounds=%d'%(matches, transitions, notices))
    if not all([matches, transitions, notices]):
        return ['vehicle interaction coverage missing']
    return fails
