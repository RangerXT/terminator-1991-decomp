"""Nearby pickup cell/query quirks and controller; inventory panel body external."""
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
    rng = random.Random(0x884B)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        actor = [0x04D4, 0x0508][i%2]
        word(0x03A0, actor)
        word(actor, rng.randrange(1024))
        word(actor+4, rng.randrange(1024))
        col = i%192
        row = i%128
        word(actor+30, col)
        word(actor+32, row)
        for j in range(20):
            record = 0x0253+j*13
            m.ds_write(record, bytes(13))
            word(record, col+rng.randrange(-2, 3))
            word(record+2, row+rng.randrange(-2, 3))
            word(record+4, rng.randrange(1024))
            word(record+6, rng.randrange(1024))
            m.ds_write(record+10, bytes([rng.choice([0, 1, 255])]))
        if i%3 == 0:
            record = 0x0253+(i%20)*13
            word(record, col)
            word(record+2, row)
            word(record+4, m.rw(m.DATA_SEG, actor)+i%201)
            word(record+6, m.rw(m.DATA_SEG, actor+4))
            m.ds_write(record+10, bytes([1]))
        return actor
    ctx.lib.pickup_query_state.restype = ctypes.c_uint64
    found = 0
    for i in range(2048):
        actor = setup(i)
        record = 0x0253 if i < 1024 else 0x0253+(i%20)*13
        count = 20 if i < 1024 else 1+i%20
        bp = 0 if i < 1024 else rng.randrange(65536)
        ax = rng.randrange(65536)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.pickup_query_state(ds, actor, record, count, ax, bp)
        out = m.call(0, 0x889D if i < 1024 else 0x88A3, bx=actor, si=record, cx=count, bp=bp, ax=ax)
        CASES += 1
        want = out['si']|(out['ax']<<16)|(out['bp']<<32)|((out['flags']&1)<<48)
        if got != want or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['pickup query state %d: %016x != %016x'%(i, got, want)]
        found += bool(out['flags']&1)
    calls = []
    active = [None]
    m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
    m.wb(dosemu.LOAD_SEG, 0x531C, bytes([0xC3]))
    at = (dosemu.LOAD_SEG<<4)+0x89A2
    def sound(uc, address, size, user):
        calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255))
    m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)
    at = (dosemu.LOAD_SEG<<4)+0x531C
    def panel(uc, address, size, user):
        active[0]()
    m.uc.hook_add(UC_HOOK_CODE, panel, None, at, at)
    panels = 0
    for i in range(768):
        actor = setup(i)
        m.ds_write(actor+14, bytes([[1, 2, 9][i%3]]))
        m.ds_write(0x99ED, bytes([i//3%2]))
        m.ds_write(0x5BFF, bytes([i//6%2]))
        m.ds_write(0x11CA, bytes([i//12%3]))
        m.ds_write(0x7AC6, bytes([i//36%2]))
        word(0x9A60, m.rw(m.DATA_SEG, actor)+[0, 199, 200, 1000][i%4])
        word(0x9A62, m.rw(m.DATA_SEG, actor+4))
        m.ds_write(0xADCF, bytes([0]))
        g, mem, planes = make_game(m)
        logs = [[], []]
        calls.clear()
        c_events(ctx.lib)
        def effect(which, read, write):
            logs[which].append((read(0x99ED, 1), read(0x9A5C, 8), read(0x03A0, 2)))
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            return 0
        active[0] = lambda:effect(1, m.ds_read, m.ds_write)
        @CALLBACK
        def callback(gp, op, arg, user):
            if op != 0x531C or arg:
                return 0xFFFFFFFF
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)))
        host = Services(callback, None)
        status = ctx.lib.pickup_interaction(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0x884B, max_instr=100_000_000)
        CASES += 1
        if status or logs[0] != logs[1] or c_events(ctx.lib) != calls:
            return ['pickup interaction status/events %d'%i]
        compare('pickup interaction %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        panels += len(logs[0])
    print('    pickups: found queries=%d external inventory panels=%d'%(found, panels))
    if not found or not panels:
        return ['pickup coverage missing']
    return fails
