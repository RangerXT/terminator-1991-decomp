"""Native normal HUD initialization, raw armor overlay and marker primitives."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import Files, regions, compare
from test_imageunpack import write_wrapped
CASES = 0

def prepare_weapons(m, count=8):
    raw = open(m._path('WEAPONS.CIF'), 'rb').read()
    m.wb(dosemu.LOAD_SEG+0x19BA, 0, raw)
    off = 0
    for i in range(8):
        m.ds_write(0x80F4+i*2, struct.pack('<H', off))
        off += 32+sum(struct.unpack_from('<4H', raw, off+16))
    for i in range(count):
        m.ds_write(0x5B0+i*6, struct.pack('<H4B', 0x8700+i, m.ds_read(0x78DC+i, 1)[0], 0, 1, 1))
    m.ds_write(0x5B0+count*6, bytes(6))
    m.ds_write(0x8544, struct.pack('<H', 4))

def run(ctx):
    global CASES
    fails = []
    rng = random.Random(0x4F4B)
    ctx.lib.screen_blit_five_plane_bytes.restype = ctypes.c_uint32
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    for i in range(64):
        m.ds_write(0, saved)
        source = 0xFFF0 if i%2 else 0x100
        dest = 0xFFF0 if i%3 == 0 else 0x1800
        width = 1+i%9
        rows = 1+i%23
        stride = 40
        write_wrapped(m, 0x7800, source, bytes(rng.randrange(256) for _ in range(4096)))
        g, mem, planes = make_game(m)
        got = ctx.lib.screen_blit_five_plane_bytes(ctypes.byref(g), 0x7800, source, dest, width, rows, stride)
        out = m.call(0x5776, 0x00E5, far=True, ds=0x7800, si=source, di=dest, cx=width, bx=rows, bp=stride)
        CASES += 1
        if got != (out['si']|(out['di']<<16)):
            return ['raw overlay registers %d'%i]
        compare('raw overlay %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    for i in range(192):
        m.ds_write(0, saved)
        player = [0x508, 0x4D4][i%2]
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player+14, bytes([(i//2)%4]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.hud_choose_panel(ds)
        m.call(0x5776, 0x012A, far=True)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['panel choice %d'%i]
        m.ds_write(0x11CA, bytes([(i//8)%3]))
        m.ds_write(0x0414, struct.pack('<H', (i//24)%8))
        m.ds_write(0x5A23, bytes([i%16]))
        g, mem, planes = make_game(m)
        ctx.lib.hud_field_marker(ctypes.byref(g))
        m.call(0, 0x745B)
        CASES += 1
        compare('HUD field marker %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    for i in range(24):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        prepare_weapons(m, i%9)
        player = [0x508, 0x4D4][i%2]
        flags = [0, 1, 2, 8, 9, 10][(i//2)%6]
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player+14, bytes([flags]))
        m.ds_write(0x11CA, bytes([0]))
        m.ds_write(0x118E, struct.pack('<HH', 1, 2))
        m.ds_write(0x1234, struct.pack('<H', (i%3)*0x2000))
        m.call(0x5776, 0x012A, far=True)
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        status = ctx.lib.hud_init_normal(ctypes.byref(g), ctypes.byref(files.host))
        m.call(0, 0x4F4B, es=m.DATA_SEG, max_instr=100000000)
        CASES += 1
        if status:
            return ['normal HUD unavailable %d'%i]
        compare('normal HUD %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        if files.handles:
            return ['normal HUD handle leak']
    return fails
