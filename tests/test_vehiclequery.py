"""Relative vehicle transform and both native line-of-sight queries (BB2B)."""
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
    rng = random.Random(0xBB2B)
    fails = []
    seg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(seg, 0, 0x9000)
    maps = [collision, bytes(0x9000), bytes([1])*0x9000, bytes(1 if (j%192)%9 == 0 else 0 for j in range(0x9000))]
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    outside = visible = blocked = 0
    for i in range(1024):
        m.ds_write(0, saved)
        m.wb(seg, 0, maps[(i//49)%4])
        player, vehicle = (0x4D4, 0x508) if i%2 else (0x508, 0x4D4)
        word(0x03A0, player)
        word(0x04BA, vehicle)
        word(player+30, 100)
        word(player+32, 60)
        word(vehicle+30, 100+i%7-3)
        word(vehicle+32, 60+(i//7)%7-3)
        for actor in [player, vehicle, 0x53C]:
            word(actor, rng.randrange(1024))
            word(actor+4, rng.randrange(1024))
        g, mem, planes = make_game(m)
        got = ctx.lib.position_relative_vehicle(ctypes.byref(g))
        out = m.call(0, 0xBB2B)
        CASES += 1
        if got != (out['flags']&1):
            return ['relative vehicle carry %d'%i]
        compare('relative vehicle visibility %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        outside += bool(got)
        visible += not got and bool(m.ds_read(0x0349, 1)[0])
        blocked += not got and not m.ds_read(0x0349, 1)[0]
    print('    vehicle queries: outside=%d clear=%d blocked=%d'%(outside, visible, blocked))
    if not all([outside, visible, blocked]):
        return ['missing vehicle visibility paths']
    return fails
