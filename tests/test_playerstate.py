"""Companion compass feedback, drowning-map sample and periodic record flags."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import c_events
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.wb(dosemu.LOAD_SEG, 0x89A2, b'\xc3')
    saved = m.ds_read(0, 65536)
    fails = []
    calls = []
    rng = random.Random(0x1796)
    addr = (dosemu.LOAD_SEG<<4)+0x89A2
    def sound(uc, a, size, user):
        calls.append((1, uc.reg_read(dosemu.UC_X86_REG_AX)&255))
    m.uc.hook_add(UC_HOOK_CODE, sound, None, addr, addr)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(768):
        m.ds_write(0, saved)
        player = 0x4D4 if i%12 else 0x508
        word(0x03A0, player)
        m.ds_write(0xAA9F, bytes([i%11 != 0]))
        m.ds_write(0x0343, bytes([[0, 1, 127, 128, 254, 255][i%6]]))
        m.ds_write(player+14, bytes([1 if i%13 else 2]))
        m.ds_write(0x1153, bytes([i%7 != 0]))
        m.ds_write(0x7AC0, bytes([i%6]))
        m.ds_write(0x7AC1, bytes([[0, 1, 2, 255][(i//6)%4]]))
        word(0x1234, i%3*0x2000)
        word(0x122C, i%3)
        for o in [player, player+4, 0xDE52, 0xDE54]:
            word(o, rng.randrange(-512, 513))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        word(0x97B8, rng.randrange(65536))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        ctx.lib.player_companion_indicator(ctypes.byref(g))
        m.call(0x11BC, 0x1796, far=True)
        CASES += 1
        if c_events(ctx.lib) != calls:
            return ['companion sound %d'%i]
        compare('companion indicator %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        m.ds_write(0, saved)
        actor = m.rw(m.DATA_SEG, 0x03A0)
        word(actor, rng.randrange(4096))
        word(actor+4, rng.randrange(4096))
        g, mem, planes = make_game(m)
        ctx.lib.player_sample_warning(ctypes.byref(g))
        m.call(0, 0x091F)
        CASES += 1
        compare('warning map sample %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(256):
        m.ds_write(0, saved)
        word(0x854A, [0, 1, 2, 4000, 65535][i%5])
        word(0x854C, 1+i%32)
        m.ds_write(0x854E, bytes(rng.randrange(256) for _ in range(400)))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.world_toggle_records(ds)
        m.call(0, 0x7088, es=m.DATA_SEG)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['periodic record flags %d'%i]
    m.wb(dosemu.LOAD_SEG, 0x0860, bytes([0xC3]))
    for height in (0, 27, 28, 29, 59, 60, 61, 32767, 32768, 65535):
        for flags in (0, 1, 2, 3):
            for fuel in (0, 32767, 32768):
                for notoriety in (199, 200, 255):
                    m.ds_write(0, saved)
                    actor = 0x04D4 if height%2 else 0x0508
                    word(0x03A0, actor)
                    word(actor+2, height)
                    word(actor+48, fuel)
                    m.ds_write(actor+14, bytes([flags]))
                    m.ds_write(actor+50, bytes([notoriety]))
                    ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
                    ctx.lib.player_recover_pose(ds)
                    m.call(0, 0x082C)
                    CASES += 1
                    if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                        return [f'player pose recovery {height}/{flags}/{fuel}/{notoriety}']
    return fails
