"""Far opponent inventory and attack-choice bookkeeping with full memory comparison."""
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
    fails = []
    rng = random.Random(0xC0A7)
    ctx.lib.opponent_find_item.restype = ctypes.c_uint64
    ctx.lib.opponent_build_choices.restype = ctypes.c_uint16
    ctx.lib.opponent_select_choice.restype = ctypes.c_uint16
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i, ids):
        m.ds_write(0, saved)
        off = 0xFFD0 if i%3 == 0 else 0x100
        seg = 0x8000
        word(0x1208, off)
        word(0x120A, seg)
        for j, item in enumerate(ids):
            m.wb(seg, (off+j*6)&65535, struct.pack('<H4B', 0x8700+j, item, 0, 2, (i+j)%4))
        m.wb(seg, (off+len(ids)*6)&65535, bytes(6))
        return seg, off
    for i in range(512):
        ids = [1+j for j in range(10)]
        seg, off = setup(i, ids)
        item = i%13
        g, mem, planes = make_game(m)
        got = ctx.lib.opponent_find_item(ctypes.byref(g), item)
        out = m.call(0, 0xC125, ax=item)
        want = out['ax']|(out['di']<<16)|(out['es']<<32)|((out['flags']&1)<<48)
        CASES += 1
        if got != want:
            return ['opponent find register result %d'%i]
        compare('opponent find %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(64):
        seg, off = setup(i, [7, 7])
        m.wb(seg, (off+5)&65535, bytes([0]))
        m.wb(seg, (off+11)&65535, bytes([3]))
        g, mem, planes = make_game(m)
        got = ctx.lib.opponent_find_item(ctypes.byref(g), 7)
        out = m.call(0, 0xC125, ax=7)
        want = out['ax']|(out['di']<<16)|(out['es']<<32)|((out['flags']&1)<<48)
        CASES += 1
        if got != want or not (got>>48)&1:
            return ['zero-count duplicate must stop %d'%i]
        compare('opponent duplicate %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        seg, off = setup(i, [i%256])
        g, mem, planes = make_game(m)
        ctx.lib.opponent_sound_for_item(ctypes.c_void_p(g.ds), i%256)
        m.call(0, 0xC0F5, es=seg, di=off)
        CASES += 1
        compare('opponent item sound %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    built = chosen = 0
    for i in range(512):
        pairs = list(struct.unpack_from('<4H', saved, 0xDE3E))
        ids = []
        for j, pair in enumerate(pairs):
            if not (i>>(j+1))&1:
                ids.extend([pair&255, pair>>8])
        rng.shuffle(ids)
        seg, off = setup(i, ids)
        # Retain stale holes explicitly, as the original does.
        m.ds_write(0x035B, bytes([3, 2, 1, 0]));m.ds_write(0x0359, bytes([i%7 == 0]))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        word(0x97B8, i)
        g, mem, planes = make_game(m)
        set_clock(ctx.lib, m)
        if i%2:
            got = ctx.lib.opponent_select_choice(ctypes.byref(g), 0x1234)
            out = m.call(0, 0xC068, ax=0x1234)
        else:
            got = ctx.lib.opponent_build_choices(ctypes.byref(g))
            out = m.call(0, 0xC0A7)
        CASES += 1
        if got != out['ax']:
            return ['opponent choice AX %d: %x != %x'%(i, got, out['ax'])]
        compare('opponent choices %d'%i, mem, planes, m, fails)
        if fails:
            base = m.DATA_SEG<<4
            want = m.ds_read(0, 0xEA70)
            ours = mem.raw
            print('choice failure', i, 'ids', ids, 'AX', hex(got), hex(out['ax']))
            print('DS differences', [(hex(j), ours[base+j], want[j]) for j in range(0xEA70) if ours[base+j] != want[j]][:30])
            print('choice state C/ref', mem.raw[base+0x351:base+0x360].hex(), m.ds_read(0x351, 15).hex())
            return fails
        built += m.ds_read(0x035A, 1)[0] > 0
        chosen += bool(m.ds_read(0x0359, 1)[0])
    for i in range(512):
        ids = [1+j for j in range(i%11)]
        seg, off = setup(i, ids)
        m.ds_write(0x8200, bytes([i%14, 3, 2]))
        if i%5 == 0:
            for j in range(len(ids)):
                m.wb(seg, (off+j*6+5)&65535, bytes([1]))
        m.ds_write(0x8300, struct.pack('<4H', 0x8200, 0x8200, 0, 0))
        word(0x04C0, [0, 2, 4][i%3])
        g, mem, planes = make_game(m)
        if i%2:
            ctx.lib.opponent_add_item(ctypes.byref(g), 0x8200)
            m.call(0, 0xC16D, si=0x8200)
        else:
            ctx.lib.opponent_cycle_item(ctypes.byref(g), 0x8300)
            m.call(0, 0xC14C, ax=0x8300)
        CASES += 1
        compare('opponent inventory insertion/cycle %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    print('    opponent choices: %d populated tables, %d selected/retained choices'%(built, chosen))
    if not built or not chosen:
        return ['missing opponent choices']
    return fails
