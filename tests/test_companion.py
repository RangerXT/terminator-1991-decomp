"""Original companion behavior leaves, steering/motion and composed modes 0..2."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xDD56)
    fails = []
    expired = 0
    adjusted = 0
    speeds = set()
    collisionseg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(collisionseg, 0, 0x9000)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        p = [0x4D4, 0x508][i%2]
        word(0x03A0, p)
        for at in [p, p+4, 0xE3EC, 0xE3EE, 0xDE52, 0xDE54]:
            word(at, rng.randrange(-2000, 4000))
        word(p+10, [0, 1, 10, 100, 32768, 65535][i%6])
        m.ds_write(p+50, bytes([i%256]))
        word(0x03F0, [0, 1, 2, 3, 4, 16, 31, 32, 255, 65535][i%10])
        word(0x11C2, [0, 1, 2, 65535][(i//10)%4])
        m.ds_write(0x0345, bytes([i%7 == 0]))
        m.ds_write(0x0349, bytes([i%11 == 0]))
        m.ds_write(0x1153, bytes([i%3 == 0]))
        word(0x0542, (i*37)%512)
        word(0x0546, [0, 1, 10, 15, 32768, 65535][i%6])
        for at in [0x055E, 0x0560, 0x0566, 0x0568]:
            word(at, rng.randrange(65536))
    for i in range(512):
        for mode, entry in enumerate([0xDD67, 0xDDBE, 0xDE05]):
            setup(i)
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            status = ctx.lib.companion_choose_behavior(ds, mode)
            m.call(0, entry)
            CASES += 1
            if status or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                return ['companion behavior %d/%d'%(i, mode)]
            expired += m.rb(m.DATA_SEG, 0x1158) == b'\xff'
            speeds.add(m.rw(m.DATA_SEG, 0x0546))
    for i in range(1024):
        setup(i)
        m.wb(collisionseg, 0, [collision, bytes(0x9000), bytes([1])*0x9000][i%3])
        before = m.rw(m.DATA_SEG, 0x0542)
        g, mem, planes = make_game(m)
        ctx.lib.companion_move(ctypes.byref(g))
        m.call(0, 0xDE46, max_instr=1_000_000)
        CASES += 1
        compare('companion movement %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        adjusted += m.rw(m.DATA_SEG, 0x0542) != before
    for i in range(256):
        setup(i)
        mode = i%3
        word(0x11BE, mode)
        # Start within the local neighborhood so combined steering sees both clear and blocked cells.
        p = m.rw(m.DATA_SEG, 0x03A0);col = m.rw(m.DATA_SEG, p+30);row = m.rw(m.DATA_SEG, p+32)
        wx = col*1024+500+(i%5-2)*100
        wz = row*1024+500+(i%7-3)*100
        word(0x055E, wx)
        word(0x0560, wx>>16)
        word(0x0566, wz)
        word(0x0568, wz>>16)
        m.wb(collisionseg, 0, [collision, bytes(0x9000)][i%2])
        g, mem, planes = make_game(m)
        status = ctx.lib.companion_step(ctypes.byref(g))
        m.call(0, 0xDD56, max_instr=1_000_000)
        CASES += 1
        if status:
            return ['combined companion unavailable']
        compare('companion step %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        setup(i)
        word(0x11C0, rng.randrange(65536))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.opponent_init_difficulty(ds)
        m.call(0, 0xB5B4)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['opponent difficulty %d'%i]
    for mode in [3, 4, 65535]:
        word(0x11BE, mode)
        g, mem, planes = make_game(m)
        before = mem.raw
        if ctx.lib.companion_step(ctypes.byref(g)) != -1 or mem.raw != before:
            return ['modal companion mode mutated state']
        CASES += 1
    print('    companion: separation expiry=%d steering adjustments=%d distinct speeds=%d'%(expired, adjusted, len(speeds)))
    if not expired or not adjusted:
        return ['missing companion branches']
    return fails
