"""Off-screen world clock, actor clamping, wandering and companion normalization."""
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
    rng = random.Random(0xB9D2)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    lows = [0, 4095, 4096, 32767, 32768, 61439, 61440, 65535]
    highs = [0, 1, 2, 3, 32768, 65535]
    for i in range(768):
        m.ds_write(0, saved)
        for axis in range(2):
            word(0x8200+34+axis*8, lows[(i+axis)%8])
            word(0x8200+36+axis*8, highs[(i//8+axis)%6])
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.world_clamp_actor(ds, 0x8200)
        m.call(0, 0xBA60, si=0x8200)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['signed word clamp %d'%i]
    for i in range(512):
        m.ds_write(0, saved)
        for o in [0x55E, 0x566]:
            word(o, rng.randrange(65536))
            word(o+2, [0, 1, 2, 1023, 1024, 65535][i%6])
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.position_normalize_companion(ds)
        m.call(0, 0xDEB5)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['companion normalization %d'%i]
    moved = 0
    for i in range(768):
        m.ds_write(0, saved)
        actor = [0x4D4, 0x508][i%2]
        word(0x04BA, actor)
        m.ds_write(0x01DE, bytes([i%7 == 0]))
        m.ds_write(0x1153, bytes([i%5 == 0]))
        m.ds_write(0x1154, bytes([i%3 == 0]))
        m.ds_write(0xDE37, bytes([[0, 4, 5, 6, 255][i%5]]))
        m.ds_write(0x0348, bytes([[0, 58, 59, 60, 255][(i//5)%5]]))
        m.ds_write(0x034E, bytes([i%2]))
        word(0x04D2, [0, 1, 2, 65535][i%4])
        for o in [actor+34, actor+42]:
            word(o, rng.randrange(65536))
            word(o+2, i%4)
        word(0xDE50, rng.randrange(512))
        m.ds_write(0x7A18, bytes([i%2]))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        word(0x97B8, i)
        g, mem, planes = make_game(m)
        set_clock(ctx.lib, m)
        if i%3 == 0:
            ctx.lib.world_clock_step(ctypes.byref(g))
            m.call(0, 0xB9D2)
        elif i%3 == 1:
            ctx.lib.world_wander_vehicle(ctypes.byref(g), i)
            m.call(0, 0xBA1C, ax=i)
        else:
            ctx.lib.world_displace_vehicle(ctypes.byref(g))
            m.call(0, 0xBAB7)
        CASES += 1
        compare('clock/wander/displace %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        moved += mem.raw[(m.DATA_SEG<<4)+actor:(m.DATA_SEG<<4)+actor+6] != saved[actor:actor+6]
    print('    world motion: %d cases changed actor position'%moved)
    if not moved:
        return ['missing off-screen motion coverage']
    return fails
