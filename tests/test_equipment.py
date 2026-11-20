"""Equipment flag refresh, automatic component combination and menu text vs DOS."""
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
    rng = random.Random(0x93CA)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    ids = saved[0xAAB9:].split(bytes([0]))[0]
    combinations = menus = 0
    for i in range(1024):
        m.ds_write(0, saved)
        m.ds_write(0x05B0, bytes(6*24))
        count = 1+i%19
        word(0x03A2, 0x05B0+6*count)
        for j in range(count):
            m.ds_write(0x05B0+6*j, struct.pack('<H4B', 0x8200+j*8, ids[(i+j)%len(ids)], 1, 1+j%5, [0, 1, 2, 255][(i+j)%4]))
        m.ds_write(0xAA98, bytes([0])*0x12)
        for j in range(5):
            m.ds_write(0xAAA5+j, bytes([255 if (i>>j)&1 else 0]))
        # Force all component gates periodically; removal sees independent stocks.
        if i%7 == 0:
            m.ds_write(0xAA99, bytes([ids[0], ids[1], ids[2]]))
            m.ds_write(0xAAA6, bytes([0]))
            m.ds_write(0x05B0, struct.pack('<H4B', 0x8200, ids[0], 1, 2, 2)+struct.pack('<H4B', 0x8210, ids[1], 1, 3, 2))
        g, mem, planes = make_game(m)
        if i%3 == 0:
            ctx.lib.inventory_refresh_equipment(ctypes.byref(g))
            m.call(0, 0x93CA, es=m.DATA_SEG, max_instr=10_000_000)
        elif i%3 == 1:
            ctx.lib.inventory_combine_components(ctypes.c_void_p(g.ds))
            m.call(0, 0x943E, es=m.DATA_SEG, max_instr=10_000_000)
        else:
            ctx.lib.inventory_equipment_menu(ctypes.byref(g))
            m.call(0, 0x946C, es=m.DATA_SEG, max_instr=10_000_000)
        CASES += 1
        compare('equipment refresh %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        combinations += bool(m.ds_read(0xAAA6, 1)[0])
        menus += bool(m.ds_read(0xAAAA, 1)[0])
    for i in range(256):
        m.ds_write(0, saved)
        word(0x03A0, 0x04D4 if i%2 else 0x0508)
        for j in range(19):
            m.ds_write(0x05B2+6*j, bytes([rng.choice([0, ids[j%len(ids)]])]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.inventory_count_required(ds)
        m.call(0, 0x9407)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['required inventory %d'%i]
    print('    equipment: component/combined flag=%d populated menus=%d'%(combinations, menus))
    if not combinations or not menus:
        return ['equipment coverage missing']
    return fails
