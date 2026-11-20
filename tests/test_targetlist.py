"""Guided-target list builder, including independent per-list capacity/index quirks."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x77F6)
    ctx.lib.weapon_target_candidate.restype = ctypes.c_uint8
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(512):
        m.ds_write(0, saved)
        word(0x72CA, 1)
        word(0x72CC, 2)
        word(0x72CE, 3)
        word(0x9008, i%8)
        word(0x9006, [0, 0x2000, 0x4000, 0x6000][(i//8)%4])
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.weapon_target_candidate(ds, 0x9000)
        out = m.call(0, 0x7852, si=0x9000)
        CASES += 1
        if got != (out['flags']&1) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['target candidate %d'%i]
    maximum = 0
    for i in range(512):
        m.ds_write(0, saved)
        m.ds_write(0x115D, bytes([i%7 != 0]))
        word(0x1194, 13)
        word(0x11AA, [0, 1, 20, 40, 41, 99][i%6])
        objects = [0, 1, 10, 40, 41, 42, 55, 60][(i//2)%8]
        figures = [0, 1, 5, 30][(i//16)%4]
        word(0x7240, objects)
        word(0x119A, figures)
        word(0x72CA, 1)
        word(0x72CC, 2)
        word(0x72CE, 3)
        for base, count in [(0x5F80, objects), (0xDF0, figures)]:
            for j in range(count):
                flags = 0x2000 if i%5 == 0 else [0, 0x2000, 0x4000, 0x6000][rng.randrange(4)]
                m.ds_write(base+j*12, struct.pack('<6H', rng.randrange(65536), 0, rng.randrange(65536), flags, rng.randrange(8), 65535 if j%2 else 0))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.weapon_collect_targets(ds)
        m.call(0, 0x77F6, es=m.DATA_SEG)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['target collection %d'%i]
        maximum = max(maximum, m.rw(m.DATA_SEG, 0x1194))
    if maximum != 42:
        return ['missing two-list capacity quirk']
    print('    target collection: original two-list maximum of 42 reproduced')
    return []
