"""Opponent destination, follow-mode and native travel-interruption helpers."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_blast import set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xC1CB)
    fails = []
    ctx.lib.opponent_destination_query.restype = ctypes.c_uint64
    ctx.lib.opponent_has_openings.restype = ctypes.c_uint8
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        m.ds_write(0xB740, [bytes(144), bytes([1])*144, bytes(j%3 == 0 for j in range(144)), saved[0xB740:0xB7D0]][i%4])
        word(0xDE52, rng.randrange(-1200, 2200))
        word(0xDE54, rng.randrange(-1200, 2200))
        m.ds_write(0xB735, bytes([i%2]))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        word(0x97B8, i)
    failed = 0
    for i in range(512):
        setup(i)
        g, mem, planes = make_game(m)
        set_clock(ctx.lib, m)
        if i%2:
            got = ctx.lib.opponent_destination_query(ctypes.byref(g))
            out = m.call(0, 0xC1CB)
            want = out['ax']|(out['bx']<<16)|(out['cx']<<32)
            if got != want:
                return ['destination register state %d: %x != %x'%(i, got, want)]
            failed += out['cx'] == 60000
        else:
            ctx.lib.opponent_pick_destination(ctypes.byref(g))
            m.call(0, 0xC1B0)
            failed += m.rw(m.DATA_SEG, 0x04C2) == 2
        CASES += 1
        compare('opponent destination %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        for op in range(3):
            setup(i)
            actor = [0x4D4, 0x508][i%2]
            word(0x04BA, actor)
            word(0x03A0, [0x4D4, 0x508][(i//2)%2])
            word(actor+28, [0, 1, 100, 200, 65535][i%5])
            word(actor+26, [0, 1, 50, 100, 65535][(i//5)%5])
            m.ds_write(0x034F, bytes([(i//25)%2]))
            m.ds_write(0x0349, bytes([(i//50)%2]))
            m.ds_write(0xB69F, bytes([(i//100)%2]))
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            if op == 0:
                ctx.lib.opponent_choose_follow_mode(ds)
                m.call(0, 0xB94A)
            elif op == 1:
                ctx.lib.opponent_follow_destination(ds)
                m.call(0, 0xB973)
            else:
                got = ctx.lib.opponent_has_openings(ds)
                out = m.call(0, 0xB91F)
                if got != (out['flags']&1):
                    return ['opening count carry %d'%i]
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                return ['follow/opening state %d/%d'%(i, op)]
    seg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(seg, 0, 0x9000)
    ready = 0
    for i in range(256):
        setup(i)
        barriers = bytes(1 if (j%192)%9 == 0 else 0 for j in range(0x9000))
        m.wb(seg, 0, [collision, bytes(0x9000), barriers][i%3])
        # Retain the nine block-position words after the 144-byte grid. Black
        # map pixels allow hidden, unobstructed locations behind the barriers.
        for plane in m.vga.planes:plane[0x6000:0x8000] = bytes(8192)
        actor = [0x4D4, 0x508][i%2]
        word(0x04BA, actor)
        word(actor+28, [0, 5, 6, 200][(i//2)%4])
        word(actor+26, 0)
        m.ds_write(0x0359, bytes([i%3 != 0]))
        word(0x1208, 0x100)
        word(0x120A, 0x8000)
        pairs = struct.unpack_from('<4H', saved, 0xDE3E)
        ids = [item for pair in pairs for item in [pair&255, pair>>8]]
        for j, item in enumerate(ids):
            m.wb(0x8000, 0x100+j*6, struct.pack('<H4B', 0, item, 0, 2, 2 if i%7 else 0))
        m.wb(0x8000, 0x130, bytes(6))
        g, mem, planes = make_game(m)
        set_clock(ctx.lib, m)
        got = ctx.lib.opponent_check_travel_interrupt(ctypes.byref(g))
        out = m.call(0, 0xC42F)
        CASES += 1
        if got != (out['flags']&1):
            return ['travel interrupt carry %d'%i]
        compare('native opponent travel interrupt %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        ready += not got
    print('    destination/search fallback cases=%d; travel gate accepted=%d'%(failed, ready))
    if not failed or not ready:
        return ['missing destination/travel branches']
    return fails
