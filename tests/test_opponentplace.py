"""Native encounter placement vs BBF1, C35F and DC7B, including failed searches."""
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
    rng = random.Random(0xBC02)
    fails = []
    moved = [0, 0, 0]
    unchanged = [0, 0, 0]
    offsets = set()
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(512):
        for op, (name, entry) in enumerate([('opponent_place_ahead', 0xBBF1), ('opponent_place_flank', 0xC35F), ('opponent_place_companion', 0xDC7B)]):
            m.ds_write(0, saved)
            player = [0x04D4, 0x0508][i%2]
            other = [0x0508, 0x04D4][i%2]
            word(0x03A0, player)
            word(0x04BA, other)
            word(player, rng.choice([500, -900, 1900, 6000]))
            word(player+4, rng.choice([600, -900, 1900, -6000]))
            heading = (i*37)%512
            word(player+6, heading)
            for axis in [34, 42]:
                word(player+axis, rng.randrange(65536))
                word(player+axis+2, [0, 1, 1023, 1024, 65535][i%5])
            word(0x0540, rng.randrange(1024))
            word(0x0558, [0, 7, 8, 100, 65535][i%5])
            word(0x0556, [0, 1, 20][(i//5)%3])
            word(0xDE58, (i*19)%512)
            m.ds_write(0x0359, b'\xff')
            m.ds_write(0x034C, b'\xff')
            m.ds_write(0xB735, b'\0')
            m.ds_write(0xB740, [bytes(144), bytes([1])*144, bytes(j%3 == 0 for j in range(144)), saved[0xB740:0xB7D0]][i%4])
            word(0x9948, 0x97B8)
            word(0x994A, 0x9948)
            word(0x97B8, [0, 0x9FFF, 0xA000, 65535][i%4])
            word(0xB662, 12345)
            word(0xB666, 23456)
            actor = 0x053C if op == 2 else other
            before = m.ds_read(actor+34, 12)
            g, mem, planes = make_game(m)
            set_clock(ctx.lib, m)
            getattr(ctx.lib, name)(ctypes.byref(g))
            m.call(0, entry, max_instr=1_000_000)
            CASES += 1
            compare('%s %d'%(name, i), mem, planes, m, fails)
            if fails:
                return fails
            different = m.ds_read(actor+34, 12) != before
            moved[op] += different
            unchanged[op] += not different
            if op == 1:
                offsets.add((m.rw(m.DATA_SEG, 0xDE58)-heading)&511)
    print('    placement changed/skipped=%s/%s; flank offsets=%s'%(moved, unchanged, sorted(offsets)))
    if any(not x for x in moved+unchanged) or len(offsets) != 4:
        return ['missing placement branches']
    return fails
