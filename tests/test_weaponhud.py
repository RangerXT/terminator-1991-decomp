"""Normal-view weapon inventory, actual icons and selection outlines vs DOS."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    seg = dosemu.LOAD_SEG+0x19BA
    raw = open(m._path('WEAPONS.CIF'), 'rb').read()
    m.wb(seg, 0, raw)
    off = 0
    for i in range(8):
        m.ds_write(0x80F4+i*2, struct.pack('<H', off))
        off += 32+sum(struct.unpack_from('<4H', raw, off+16))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x1C7D)
    fails = []
    for i in range(256):
        m.ds_write(0, saved)
        dest = 0x1C20+(i%8)*6
        m.wb(seg, 0x13B0, bytes(rng.randrange(256) for _ in range(480)))
        m.ds_write(0x9A4A, bytes([i%3 == 0]))
        m.ds_write(0x11CA, bytes([(i//3)%3]))
        mask = [0, 65535, 0xAAAA, 0x5555, 0x1234][(i//9)%5]
        g, mem, planes = make_game(m)
        ctx.lib.hud_weapon_icon(ctypes.byref(g), dest, mask)
        m.call(0x11BC, 0x1BE1, di=dest, bx=mask)
        CASES += 1
        compare('weapon icon %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(192):
        m.ds_write(0, saved)
        m.ds_write(0x11CA, bytes([i%3]))
        slot = 1+(i//3)%8
        colour = [0, 12, 14, 15][(i//24)%4]
        g, mem, planes = make_game(m)
        ctx.lib.hud_weapon_selection(ctypes.byref(g), slot, colour)
        m.call(0x11BC, 0x1EEB, cx=slot, ax=colour<<8)
        CASES += 1
        compare('weapon selection %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    ids = saved[0x78DC:0x78DC+8]
    for i in range(384):
        m.ds_write(0, saved)
        m.ds_write(0x118E, struct.pack('<HH', i%9, (i//9)%9))
        mask = [0, 255, 1, 128, 0x55, 0xAA, rng.randrange(256)][i%7]
        items = [(slot, id) for slot, id in enumerate(ids) if mask&(1<<slot)]
        rng.shuffle(items)
        for j, (slot, item) in enumerate(items):
            m.ds_write(0x5B0+j*6, struct.pack('<H4B', 0x8700+slot, item, 0, 1, 1))
        m.ds_write(0x5B0+len(items)*6, bytes(6))
        m.ds_write(0x11CA, bytes([i%3]))
        m.ds_write(0x9A4A, bytes([i%5 == 0]))
        m.ds_write(0x8544, struct.pack('<H', 4))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.weapon_inventory_rebuild(ds)
        m.call(0, 0x985C, es=m.DATA_SEG)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['weapon inventory %d'%i]
        g, mem, planes = make_game(m)
        status = ctx.lib.hud_weapon_slots(ctypes.byref(g))
        m.call(0x11BC, 0x1C7D, far=True, es=m.DATA_SEG, max_instr=50000000)
        CASES += 1
        if status:
            return ['weapon slots unavailable']
        compare('weapon slots %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
