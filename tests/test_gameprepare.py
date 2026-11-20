"""0809 preparation phase: native retry/spawning, threat counters and modal toggle."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_textmodal import Poll, Platform
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    rng = random.Random(0x809)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(512):
        m.ds_write(0, saved)
        word(0x03A0, [0x4D4, 0x508][i%2])
        word(0x119A, rng.randrange(65536))
        word(0x119C, rng.randrange(65536))
        m.ds_write(0x1153, bytes([rng.randrange(256), rng.randrange(256)]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.player_update_threat(ds)
        m.call(0, 0x596C)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['threat byte wrap %d'%i]
    seg = m.rw(m.DATA_SEG, 0x91B2)
    collision = m.rb(seg, 0, 0x9000)
    for i in range(256):
        m.ds_write(0, saved)
        count = [0, 2, 8, 24][i%4]
        m.wb(seg, 0, bytes(0x9000) if i%2 else collision)
        word(0x119A, count)
        word(0x119C, count)
        word(0x03A4, 0xDF0+count*12)
        word(0x116E, i%3)
        word(0x1170, (i//3)%3)
        word(0xB738, [0, 1, 2, 100][(i//9)%4])
        m.ds_write(0xB69F, bytes([0 if i%5 else 3]))
        m.ds_write(0x115A, bytes([0 if i%7 else 1]))
        m.ds_write(0x5A50, b'\x00')
        m.ds_write(0x1153, b'\x00\x00')
        m.ds_write(0x1155, bytes([i%4]))
        word(0x854A, 1 if i%2 else 0)
        word(0x854C, 4)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *[rng.randrange(65536) for _ in range(200)]))
        if i%2:
            m.wb(dosemu.LOAD_SEG, 0x0820, b'\xc3')
        else:
            m.wb(dosemu.LOAD_SEG, 0x0820, b'\xe8')
        g, mem, planes = make_game(m)
        if i%2:
            status = ctx.lib.gameplay_prepare(ctypes.byref(g), None)
            m.call(0, 0x0809)
        else:
            status = 0
            ctx.lib.figure_retry_deferred(ctypes.byref(g))
            m.call(0, 0xA426)
        CASES += 1
        if status:
            return ['game preparation status']
        compare('deferred/preparation %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(24):
        m.ds_write(0, saved)
        m.ds_write(0x5A50, bytes([i%3 != 0]))
        m.ds_write(0x0200, bytes(2))
        m.ds_write(0x8096, b'\x00')
        m.ds_write(0x5A4E, b'\x00')
        m.ds_write(0xADCF, b'\x00')
        m.ds_write(0x5BDA, b'\x00')
        m.ds_write(0x5BF5, b'\x00')
        m.wb(dosemu.LOAD_SEG, 0x3B87, bytes([0 if i%2 else 255]))
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.ds_write(0xC4AB, b'\x00')
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, b'\xcb')
        g, mem, planes = make_game(m)
        @Poll
        def poll(gp, phase, ticks, user):
            ctypes.memmove(g.ds+0x5BF5, bytes([255 if phase == 1 else 0]), 1)
            return 0
        def keys(uc, a, size, user):
            cs = uc.reg_read(dosemu.UC_X86_REG_CS)
            ip = uc.reg_read(dosemu.UC_X86_REG_IP)
            if cs == dosemu.LOAD_SEG+0x5776 and ip == 0x02C6:
                m.ds_write(0x5BF5, b'\xff')
            elif cs == dosemu.LOAD_SEG and ip == 0x5195:
                m.ds_write(0x5BF5, b'\x00')
        hook = m.uc.hook_add(UC_HOOK_CODE, keys)
        host = Platform(poll, None)
        status = ctx.lib.debug_vector_toggle(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0x3B54)
        m.uc.hook_del(hook)
        CASES += 1
        if status:
            return ['toggle status']
        compare('vector-toggle modal %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
