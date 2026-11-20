"""Native vehicle control, original 3269/3402/3584/35C0/3646/3684.
Only 02B5 exit is an external stub; HUD, damage, coordinates and other leaves are C.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services
from test_blast import GameEvent, set_clock
CASES = 0


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x3269)
    calls = []
    fails = []
    active = [None]
    exits = 0
    starts = 0
    for kind, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
        m.wb(dosemu.LOAD_SEG, off, b'\xc3')
        at = (dosemu.LOAD_SEG<<4)+off
        def event(uc, address, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&255, m.ds_read(0x80E9, 1)[0] if kind == 1 else 0))
        m.uc.hook_add(UC_HOOK_CODE, event, None, at, at)
    m.wb(dosemu.LOAD_SEG, 0x02B5, b'\xc3')
    at = (dosemu.LOAD_SEG<<4)+0x02B5
    def transition(uc, address, size, user):
        active[0](0x02B5, m.r(dosemu.UC_X86_REG_BX))
    m.uc.hook_add(UC_HOOK_CODE, transition, None, at, at)
    def events():
        buf = (GameEvent*512)()
        n = ctx.lib.game_events(buf, 512)
        return [(e.kind, e.a, e.b if e.kind == 1 else 0) for e in buf[:n]]
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        p = [0x04D4, 0x0508][i%2]
        word(0x03A0, p)
        m.ds_write(p+14, bytes([2 if i%3 else 10]))
        word(p+6, (i*37)%512)
        word(p+10, [0, 1, 2, 4, 5, 10, 11, 15, 16, 32, 33, 32767, 32768, 65535][i%14])
        word(p+12, rng.randrange(65536))
        word(p+48, [0, 1, 100, 65535][i%4])
        word(p+26, 0)
        word(p+28, 1000)
        m.ds_write(0x5BD9, bytes(0x59))
        for off in [0x5BF4, 0x5BF8, 0x5C0F, 0x5C11, 0x5BF6, 0x5C21, 0x5C29, 0x5BE7, 0x5C24, 0x5C26]:
            m.ds_write(off, bytes([255 if rng.randrange(4) == 0 else 0]))
        for off in [0x114A, 0x114B, 0x114C, 0x5A24, 0xAA94]:
            m.ds_write(off, bytes([255 if i%(off%5+2) == 0 else 0]))
        word(0x5A40, [0, 1, 4, 10, 16, 32, 32767, 32768, 65535][i%9])
        word(0x0412, [0x5A28, 0x5A34][i%2])
        word(0x0414, i%6)
        m.ds_write(0x0347, bytes([[0, 1, 4, 9, 10, 255][i%6]]))
        word(0x0416, [0, 1, 300][i%3])
        word(0x0200, i%2)
        m.ds_write(0x00B9, bytes([i%13 == 0]))
        m.ds_write(0x11CA, bytes([i%3]))
        m.ds_write(0x80E9, bytes([0]))
        m.ds_write(0xAA98, bytes([0]))
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *[rng.randrange(65536) for _ in range(200)]))
        # Direct gear keys force both table families and every marker slot.
        if i%3 == 0:
            keys = [0x5C2B, 0x5C2C, 0x5C20, 0x5C28, 0x5C22, 0x5C2A]
            m.ds_write(keys[i//3%6], bytes([255]))
        return p
    for i in range(1024):
        for name, entry, takes_game in [('driving_brake', 0x3584, False), ('driving_smooth_speed', 0x35C0, True), ('driving_displace', 0x3646, False), ('driving_transmission', 0x3402, True)]:
            p = setup(i)
            g, mem, planes = make_game(m)
            getattr(ctx.lib, name)(ctypes.byref(g) if takes_game else ctypes.c_void_p(g.ds), p)
            m.call(0, entry, si=p, es=m.DATA_SEG)
            CASES += 1
            compare('%s %d'%(name, i), mem, planes, m, fails)
            if fails:
                return fails
    for i in range(1024):
        p = setup(i)
        m.ds_write(0x114C, bytes([i%2]))
        m.ds_write(0x5CDA, bytes([i%16]))
        m.ds_write(0x8096, bytes([i%17 == 0]))
        m.ds_write(0x5C12, bytes([0]))
        m.ds_write(0x1155, bytes([0]))
        word(0x5F72, i%3)
        g, mem, planes = make_game(m)
        calls.clear()
        events()
        set_clock(ctx.lib, m)
        logs = [[], []]
        def effect(which, read, write, op, arg):
            logs[which].append((op, arg, read(0x1172, 2), read(p, 52)))
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            return 0
        active[0] = lambda op, arg:effect(1, m.ds_read, m.ds_write, op, arg)
        @CALLBACK
        def callback(gp, op, arg, user):
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, b:ctypes.memmove(g.ds+o, b, len(b)), op, arg)
        host = Services(callback, None)
        status = ctx.lib.driving_step(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0x3269, es=m.DATA_SEG, max_instr=2_000_000)
        CASES += 1
        native_events = events()
        if status or native_events != calls or logs[0] != logs[1]:
            return ['complete driving status/events %d: %s != %s'%(i, native_events, calls)]
        compare('complete driving %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        exits += bool(logs[0])
        starts += any(k == 1 and a == 9 for k, a, b in calls)
    print('    driving: destruction/exit callbacks=%d engine starts=%d'%(exits, starts))
    if not exits or not starts:
        return ['missing driving branches']
    return fails
