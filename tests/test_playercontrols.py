"""Walking and vehicle input leaves with original key tables and fault behavior."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0


def run(ctx):
    global CASES
    ctx.lib.walking_step_bx.restype = ctypes.c_uint16
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x30A0)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        p = [0x04D4, 0x0508][i%2]
        word(0x03A0, p)
        word(p+6, [0, 127, 128, 256, 384, 511, 65535][i%7])
        word(p+10, [0, 1, 2, 10, 33, 127, 32767, 32768, 65535][i%9])
        word(p+12, rng.randrange(65536))
        m.ds_write(p+14, bytes([1 if i%3 else 2]))
        m.ds_write(p+25, bytes([i%64]))
        m.ds_write(0x5BDB, bytes([255 if rng.randrange(5) == 0 else 0 for _ in range(0x59)]))
        for off in [0x8096, 0x5C12, 0x1155, 0x5BF6, 0x114A, 0xAA9D, 0x0346]:
            m.ds_write(off, bytes([255 if i%(off%11+2) == 0 else 0]))
        m.ds_write(0x5CDA, bytes([i%16]))
        m.ds_write(0x5A22, bytes([[0, 1, 2, 255][i%4]]))
        word(0x5A44, i%10)
        word(0x0410, [0, 1, 399, 400, 65535][i%5])
        word(0x03F2, [0, 1, 5, 10, 1275, 1276, 65535][i%7])
        word(0x116C, rng.randrange(65536))
        word(0x0200, i%3)
        word(0x5A42, [0, 128, 65408][i%3])
        return p
    ctx.lib.player_movement_gate.restype = ctx.lib.driving_gear_key.restype = ctypes.c_uint32
    for i in range(1024):
        p = setup(i)
        ax = rng.randrange(65536)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.player_movement_gate(ds, ax)
        out = m.call(0, 0x2E9E, ax=ax)
        CASES += 1
        if got != out['ax']|((out['flags']&1)<<16) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['movement gate %d'%i]
    for i in range(1024):
        for scan in [0, 1]:
            p = setup(i)
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            ctx.lib.walking_speed_step(ds, p, scan)
            m.call(0, 0x300B if scan else 0x302E, si=p, es=m.DATA_SEG)
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                return ['walking speed %d/%d'%(i, scan)]
        for name, entry in [('driving_steer', 0x331D), ('driving_accelerate', 0x33A5)]:
            p = setup(i)
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            getattr(ctx.lib, name)(ds, p)
            m.call(0, entry, si=p)
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                return [name+' %d'%i]
    for i in range(512):
        setup(i)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.driving_gear_key(ds)
        out = m.call(0, 0x354E)
        CASES += 1
        if got != out['ax']|((out['flags']&1)<<16):
            return ['gear key %d'%i]
    for i in range(256):
        for name, entry in [('player_position_backup', 0x36D0), ('player_position_restore', 0x36EF), ('player_keep_inside', 0x370E)]:
            p = setup(i)
            word(p+30, [0, 1, 190, 191][i%4])
            word(p+32, [0, 1, 126, 127][(i//4)%4])
            g, mem, planes = make_game(m)
            if name == 'player_keep_inside':
                getattr(ctx.lib, name)(ctypes.byref(g))
            else:
                getattr(ctx.lib, name)(ctypes.c_void_p(g.ds))
            m.call(0, entry)
            CASES += 1
            compare(name+' %d'%i, mem, planes, m, fails)
            if fails:
                return fails
    for i in range(128):
        setup(i)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.driving_reset(ds)
        m.call(0, 0x36A9)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['driving reset']
    for i in range(1024):
        p = setup(i)
        word(p+6, (i*37)%512)
        col = [0, 1, 96, 190, 191][i%5]
        row = [0, 1, 64, 126, 127][(i//5)%5]
        word(p+30, col)
        word(p+32, row)
        wx = col*1024+[0, 500, 1023][i%3]
        wz = row*1024+[0, 500, 1023][(i//3)%3]
        word(p+34, wx)
        word(p+36, wx>>16)
        word(p+42, wz)
        word(p+44, wz>>16)
        g, mem, planes = make_game(m)
        incoming = rng.randrange(65536)
        bx = ctx.lib.walking_step_bx(ctypes.byref(g), incoming)
        out = m.call(0, 0x30A0, bx=incoming, es=m.DATA_SEG, max_instr=2_000_000)
        CASES += 1
        if bx != out["bx"]:
            return ["walking BX %d: %04x != %04x"%(i, bx, out["bx"])]
        compare('complete walking %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
