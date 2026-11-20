"""Shop proximity/fallback/HUD controller vs original; purchase panel external."""
import ctypes, os, random, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services
from test_blast import c_events
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    m = dosemu.Machine()
    m.load(root/'out/emu/states/ingame.pkl')
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x74CE)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    ctx.lib.shop_try_record_state.restype = ctypes.c_uint64
    ctx.lib.shop_distance.restype = ctx.lib.shop_fallback_records.restype = ctypes.c_uint16
    for i in range(1024):
        m.ds_write(0, saved)
        actor = [0x04D4, 0x0508][i%2]
        record = 0x8000
        word(actor+34, rng.randrange(65536))
        word(actor+42, rng.randrange(65536))
        word(record, rng.randrange(65536))
        word(record+4, rng.randrange(65536))
        word(record+8, 1+i%7)
        m.ds_write(record+10, bytes([i%2]))
        m.ds_write(0x0374, bytes([i//2%2]))
        if i%3 == 0:
            word(record, m.rw(m.DATA_SEG, actor+34)+[0, 299, 300, 301, 799, 800, 801][i%7])
            word(record+4, m.rw(m.DATA_SEG, actor+42))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.shop_try_record_state(ds, actor, record)
        out = m.call(0, 0x75B5, di=actor, si=record)
        CASES += 1
        want = out['si']|(out['ax']<<16)|(out['bx']<<32)|(((out['flags']>>6)&1)<<48)
        if got != want or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['shop record registers/state %d'%i]
    for i in range(256):
        m.ds_write(0, saved)
        actor = [0x04D4, 0x0508][i%2]
        word(0x03A0, actor)
        word(actor+34, rng.randrange(65536))
        word(actor+36, [0, 1, 65534, 65535][i%4])
        word(actor+44, i%2)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.shop_fallback_records(ds)
        out = m.call(0, 0xC5AF, max_instr=100_000_000)
        CASES += 1
        if got != out['si'] or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['shop fallback table %d'%i]
    active = [None]
    calls = []
    m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
    m.wb(dosemu.LOAD_SEG, 0x813E, bytes([0xC3]))
    at = (dosemu.LOAD_SEG<<4)+0x89A2
    def sound(uc, address, size, user):
        calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255))
    m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)
    at = (dosemu.LOAD_SEG<<4)+0x813E
    def panel(uc, address, size, user):
        active[0](m.r(dosemu.UC_X86_REG_BX))
    m.uc.hook_add(UC_HOOK_CODE, panel, None, at, at)
    panels = notices = 0
    for i in range(1024):
        m.ds_write(0, saved)
        actor = [0x04D4, 0x0508][i%2]
        word(0x03A0, actor)
        x = 500
        z = 100
        word(actor+34, x)
        word(actor+36, i//2%3)
        word(actor+42, z)
        word(actor+44, i//6%2)
        m.ds_write(actor+14, bytes([[1, 2, 9][i//12%3]]))
        word(0x72B2, i%4)
        word(0x1180, 0 if i%4 == 0 else 1+i%7)
        word(0x8514, x+[0, 300, 301, 800, 801][i%5])
        word(0x8518, z)
        word(0x8512, i%3*0x2000)
        word(0x1234, (i+1)%3*0x2000)
        m.ds_write(0x8447, bytes([i//4%2]))
        m.ds_write(0x0374, bytes([i//8%2]))
        m.ds_write(0x5BF8, bytes([i//16%2]))
        m.ds_write(0x11CA, bytes([i//32%3]))
        m.ds_write(0xADCF, bytes([0]))
        for base, count in [(0x5CE4, 4), (0x854E, 28)]:
            for j in range(count):
                at = base+j*11
                word(at, x+3000)
                word(at+4, z+3000)
                word(at+8, 1+(j+i)%7)
                m.ds_write(at+10, bytes([1]))
        # Alternate nearby objects in the primary and fallback lists.
        ds0 = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536);fallback = ctx.lib.shop_fallback_records(ds0)
        target = 0x5CE4 if i%2 == 0 else fallback
        word(target, x+[0, 300, 301, 800, 801][i%5])
        word(target+4, z)
        m.ds_write(target+10, bytes([i//2%2]))
        g, mem, planes = make_game(m)
        logs = [[], []]
        calls.clear()
        c_events(ctx.lib)
        def effect(which, read, write, arg):
            logs[which].append((arg, read(0x1180, 2), read(0x8447, 1), read(0x8512, 60)))
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            return 0
        active[0] = lambda arg:effect(1, m.ds_read, m.ds_write, arg)
        @CALLBACK
        def callback(gp, op, arg, user):
            if op != 0x813E:
                return 0xFFFFFFFF
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), arg)
        host = Services(callback, None)
        status = ctx.lib.shop_interaction(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0x74CE, max_instr=100_000_000)
        CASES += 1
        if status or logs[0] != logs[1] or c_events(ctx.lib) != calls:
            return ['shop controller status/events %d'%i]
        compare('shop controller %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        panels += len(logs[0])
        notices += bool(calls)
    print('    shops: external purchase panels=%d sound/notice cases=%d'%(panels, notices))
    if not panels or not notices:
        return ['shop coverage missing']
    return fails
