"""Native collision steering, nearby destination selection and vehicle pursuit."""
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
    rng = random.Random(0xAA81)
    fails = []
    seg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(seg, 0, 0x9000)
    maps = [collision, bytes(0x9000), bytes([1])*0x9000, bytes(1 if (j%192)%9 == 0 else 0 for j in range(0x9000))]
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    ctx.lib.vehicle_choose_destination.restype = ctypes.c_uint8
    outside = exhausted = adjusted = 0
    for i in range(768):
        m.ds_write(0, saved)
        m.wb(seg, 0, maps[i%4])
        for o in [0x122E, 0x1230, 0x1232, 0xB662, 0xB666]:
            word(o, rng.randrange(-1100, 2100))
        word(0xB824, rng.randrange(512))
        word(0xB820, [0, 1, 2, 10, 20, 65535][(i//4)%6])
        m.ds_write(0x8684, bytes([(i//24)%2]))
        m.ds_write(0x7A18, bytes([i%2]))
        g, mem, planes = make_game(m)
        got = ctx.lib.collision_steer(ctypes.byref(g))
        out = m.call(0, 0xAA81)
        CASES += 1
        if got != (out['flags']&1):
            return ['steering carry %d'%i]
        compare('collision steering %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        outside += bool(got)
        exhausted += m.rw(m.DATA_SEG, 0xB82E) == 288
        adjusted += 0 < m.rw(m.DATA_SEG, 0xB82E) < 288 or m.rw(m.DATA_SEG, 0xB82E) > 32767
    for i in range(384):
        m.ds_write(0, saved)
        word(0xDE52, rng.randrange(-1100, 2100))
        word(0xDE54, rng.randrange(-1100, 2100))
        m.ds_write(0x034F, bytes([i%3 == 0]))
        m.ds_write(0x0349, bytes([i%2]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.vehicle_choose_destination(ds)
        out = m.call(0, 0xB755)
        CASES += 1
        if got != (out['flags']&1) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['vehicle destination %d'%i]
    for i in range(512):
        m.ds_write(0, saved)
        m.wb(seg, 0, maps[i%4])
        actor = [0x4D4, 0x508][i%2]
        word(0x04BA, actor)
        m.ds_write(0x1153, bytes([i%7 != 0]))
        m.ds_write(0x034F, bytes([i%3 == 0]))
        m.ds_write(0x0349, bytes([i%2]))
        x = rng.randrange(-900, 1900)
        z = rng.randrange(-900, 1900)
        word(0xDE52, x)
        word(0xDE54, z)
        word(0x04BC, x+[0, 20, 100, 400][i%4])
        word(0x04BE, z+[0, 20, 100, 400][i%4])
        word(actor+10, [0, 1, 10, 20][(i//4)%4])
        word(actor+34, 100*1024+(x&1023))
        word(actor+36, 1)
        word(actor+42, 60*1024+(z&1023))
        word(actor+44, 0)
        g, mem, planes = make_game(m)
        ctx.lib.vehicle_follow_route(ctypes.byref(g))
        m.call(0, 0xB6AA)
        CASES += 1
        compare('vehicle pursuit %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(1024):
        m.ds_write(0, saved)
        word(0x04D2, rng.randrange(65536))
        word(0x11C0, rng.randrange(65536))
        word(0x1174, i*64)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.world_update_delay(ds)
        m.call(0, 0xB790)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['world delay %d'%i]
    print('    steering: outside=%d exhausted=%d adjusted=%d'%(outside, exhausted, adjusted))
    if not all([outside, exhausted, adjusted]):
        return ['missing steering paths']
    return fails
