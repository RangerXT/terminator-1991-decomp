"""Player/region damage with native shield message/removal; border and sound are events."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import GameEvent, set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(6386)
    fails = []
    calls = []
    ctx.lib.player_damage_region.restype = ctypes.c_uint32
    ctx.lib.player_hit_native_state.restype = ctypes.c_uint16
    ctx.lib.player_hit_native_registers.restype = ctypes.c_uint32
    for i in range(1024):
        m.ds_write(0, saved)
        actor = 0x8500
        region = [0, 1, 2, 3, 5, 255][i%6]
        damage = rng.randrange(65536)
        m.ds_write(actor, bytes(rng.randrange(256) for _ in range(320)))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.player_damage_region(ds, actor, region, damage)
        out = m.call(0, 0x643E, si=actor, bx=region, ax=damage)
        CASES += 1
        if got != (out['ax']|((out['flags']&1)<<16)):
            return ['region result %d'%i]
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['region state %d'%i]
    for off in [0x89A2, 0x0A4F]:
        m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
    def sound(uc, a, size, user):
        calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255, 0))
    def border(uc, a, size, user):
        logical = m.r(dosemu.UC_X86_REG_BX)&255
        calls.append((5, logical, m.ds_read(0x1510+logical, 1)[0]))
    for off, hook in [(0x89A2, sound), (0x0A4F, border)]:
        addr = (dosemu.LOAD_SEG<<4)+off
        m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
    def events():
        buf = (GameEvent*512)()
        n = ctx.lib.game_events(buf, 512)
        return [(e.kind, e.a, e.b) for e in buf[:n]]
    depleted = absorbed = dead = 0
    for i in range(1536):
        m.ds_write(0, saved)
        player = [0x508, 0x4D4][i%2]
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player+14, bytes([(i//2)%2]))
        m.ds_write(player+25, bytes([rng.choice([0, 8, 16, 24])]))
        m.ds_write(player+17, bytes([rng.randrange(32) for _ in range(4)]))
        m.ds_write(player+21, bytes([rng.choice([0, 10, 30, 100]) for _ in range(4)]))
        total = rng.choice([0, 0, 99, 65530])
        cap = rng.choice([0, 100, 65535])
        m.ds_write(player+26, struct.pack('<HH', total, cap))
        vest = (i//4)%2
        life = [0, 1, 2, 255][(i//8)%4]
        m.ds_write(0xAA98, bytes([vest]))
        m.ds_write(player+51, bytes([life]))
        m.ds_write(0x9948, struct.pack('<HH', 0x97B8, 0x9948))
        m.ds_write(0x97B8, struct.pack('<HH', i%4, (i//32)%16))
        m.ds_write(0x5B0, struct.pack('<H4B', 0x8700, 15, 1, 2, 1))
        m.ds_write(0x5B6, struct.pack('<H4B', 0x8710, 4, 1, 1, 2))
        m.ds_write(0x5BC, bytes(6))
        m.ds_write(0x03A2, struct.pack('<H', 0x5BC))
        m.ds_write(0x11CA, bytes([(i//512)%3]))
        m.ds_write(0x7AC6, bytes([0]))
        m.ds_write(0x1234, struct.pack('<H', i%3*0x2000))
        damage = [0, 1, 5, 127, 255, 256, 65535][(i//96)%7]
        g, mem, planes = make_game(m)
        calls.clear()
        events()
        set_clock(ctx.lib, m)
        incoming_bx = rng.randrange(65536)
        got = ctx.lib.player_hit_native_registers(ctypes.byref(g), damage, incoming_bx)
        out = m.call(0, 0x6386, ax=damage, bx=incoming_bx, es=m.DATA_SEG, max_instr=50000000)
        if got != (out['ax']|(out['bx']<<16)):
            return ['player hit AX/BX %d: %08x != %08x'%(i, got, out['ax']|(out['bx']<<16))]
        CASES += 1
        if events() != calls:
            return ['player hit events %d'%i]
        compare('player hit %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        depleted += vest and life == 1 and not m.ds_read(0xAA98, 1)[0]
        absorbed += vest and m.ds_read(player+51, 1)[0] != (life&255) and bool(m.ds_read(0xAA98, 1)[0])
        dead += m.ds_read(0x1156, 1)[0] == 2
    print('    player hit: vest depleted=%d absorbed=%d death states=%d'%(depleted, absorbed, dead))
    if not all([depleted, absorbed, dead]):
        return ['missing player hit coverage']
    return fails
