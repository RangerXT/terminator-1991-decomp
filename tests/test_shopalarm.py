"""Original theft/alarm orchestration with native figure spawn/model+CAF reload.
Sound is an explicit event boundary; wait inputs and read-only file bytes independent.
Alarm text uses the source nonmodal gate, in both EGA and VGA modes.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import Files, trace_dos, regions, compare, check_memory
from test_menu import Call, Platform
from test_blast import GameEvent, set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x873D)
    fails = []
    for i in range(256):
        m.ds_write(0, saved)
        m.ds_write(0x9948, struct.pack('<HH', 0x97B8, 0x9948))
        m.ds_write(0x97B8, struct.pack('<2H', rng.randrange(65536), rng.randrange(65536)))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.shop_randomize_balances(ds)
        m.call(0, 0x87E9)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['shop random balances %d'%i]
    alarms = escaped = resources = spawned = 0
    for i in range(96):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        mode = i%2
        check = i >= 48
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        if mode:
            m.w(dosemu.UC_X86_REG_AX, 19)
            m._video()
        m.ds_write(0xADCF, bytes([mode]))
        m.ds_write(0x5A4E, bytes([255]))
        word(0x1234, 0)
        m.ds_write(0xC4AB, bytes([0]))
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        p = 0x04D4 if i//2%2 else 0x0508
        word(0x03A0, p)
        m.ds_write(p+50, bytes([[0, 1, 22, 23, 24, 25, 48, 49, 200, 255][i%10]]))
        m.ds_write(0x7A18, bytes([[0, 1, 2, 255][i//2%4]]))
        m.ds_write(0x115A, bytes([i//8%2]))
        word(0x11CD, 0x0101)
        word(0x9A6E, [0x9BE2, 0x9AB8, 0x8400][i//4%3])
        m.ds_write(0xA917, bytes([i//12%2]))
        collision = m.rw(m.DATA_SEG, 0x91B2)
        old_map = m.rb(collision, 0, 0x9000)
        phase = (((m.rw(m.DATA_SEG, p)+8)>>4)+64+3)%9
        walls = bytes(1 if (j%192)%9 == phase else 0 for j in range(0x9000))
        m.wb(collision, 0, [old_map, bytes(0x9000), walls][i%3])
        word(0x119A, 0)
        word(0x119C, 0)
        word(0x03A4, 0x0DF0)
        for j in range(32):
            m.ds_write(0x0B30+j*22, struct.pack('<11H', 0, 0, 0, 0, 0, 2, 0, j*7, 0x0301, 0, 0))
            m.ds_write(0x0DF0+j*12, bytes(12))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        values = [rng.randrange(65536) for j in range(200)]
        limit = [0, 1, 2000, 4095, 65535][i//3%5]
        word(0x11C4, limit)
        values[0] = [0, min(limit, 4095), min(limit+1, 4095), 4095][i%4]
        m.ds_write(0x97B8, struct.pack('<200H', *values))
        calls = []
        logs = [[], []]
        active = [None]
        m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
        at = (dosemu.LOAD_SEG<<4)+0x89A2
        def sound(uc, address, size, user):
            calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255, m.ds_read(0x80E9, 1)[0]))
        m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, bytes([0xCB]))
        at = ((dosemu.LOAD_SEG+0x5776)<<4)+0x02C6
        def wait(uc, address, size, user):
            active[0](m.r(dosemu.UC_X86_REG_CX))
        m.uc.hook_add(UC_HOOK_CODE, wait, None, at, at)
        trace_dos(m)
        spans = regions(m)
        files = Files(m)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        def effect(which, read, write, ticks):
            logs[which].append((ticks, read(0xAA94, 1), read(0x80E9, 1), read(p, 52)))
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            return 0
        active[0] = lambda ticks:effect(1, m.ds_read, m.ds_write, ticks)
        @Call
        def callback(gp, op, a, b, user):
            if op != 0x02C6 or b:
                return -1
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), a)
        host = Platform(callback, None)
        def events():
            buf = (GameEvent*512)()
            n = ctx.lib.game_events(buf, 512)
            return [(e.kind, e.a, e.b) for e in buf[:n]]
        events()
        set_clock(ctx.lib, m)
        fn = ctx.lib.shop_check_theft if check else ctx.lib.shop_alarm
        got = fn(ctypes.byref(g), ctypes.byref(files.host), ctypes.byref(host), None, screen)
        out = m.call(0, 0x873D if check else 0x874C, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if got != (out['flags']&1) or events() != calls or logs[0] != logs[1]:
            return ['shop alarm result/sound/wait %d'%i]
        if mode and screen.raw != bytes(m.vga.chunky):
            return ['shop alarm VGA pixels %d'%i]
        if len(files.calls) != len(m.image_calls):
            return ['shop alarm resource IO count %d'%i]
        for a, b in zip(files.calls, m.image_calls):
            if a[0] != b[0]:
                return ['shop alarm IO args %d'%i]
            error = check_memory(a[1], b[1], spans)
            if error:
                return ['shop alarm IO state %d: %s'%(i, error)]
        compare('shop alarm %d'%i, mem, planes, m, spans, fails)
        if fails:
            return fails
        if files.handles:
            return ['shop alarm file handle leak']
        alarms += got == 1
        escaped += got == 0
        resources += bool(files.calls)
        spawned += bool(m.rw(m.DATA_SEG, 0x119A))
    print('    shop alarms: alerts=%d escaped=%d resource-reloads=%d spawned=%d'%(alarms, escaped, resources, spawned))
    if not all([alarms, escaped, resources, spawned]):
        return ['shop alarm coverage missing']
    return fails
