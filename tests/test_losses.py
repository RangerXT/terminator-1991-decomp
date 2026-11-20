"""089E non-movie loss branches, A28A copy, and 8C45 sample completion wait."""
import ctypes, os, random, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services
from movie_helpers import MovieServices
from test_sound import SoundServices
from test_mapsetupreal import RESOURCE, Resources
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    m = dosemu.Machine()
    m.load(root/'out/emu/states/ingame.pkl')
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x089E)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(192):
        m.ds_write(0, saved)
        word(0x04BA, [0x04D4, 0x0508, 0x053C][i%3])
        m.ds_write(0x053C, bytes(rng.randrange(256) for _ in range(52)))
        m.ds_write(0x1154, bytes([i]))
        g, mem, planes = make_game(m)
        ctx.lib.companion_promote_record(ctypes.c_void_p(g.ds))
        m.call(0, 0xA28A, es=m.DATA_SEG)
        CASES += 1
        compare('loss promotion %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    m.wb(dosemu.LOAD_SEG+0x151B, 0x0248, bytes([0xCB]))
    m.wb(dosemu.LOAD_SEG+0x151B, 0x023B, bytes([0xCB]))
    active = [None]
    for off in [0x0248, 0x023B]:
        at = ((dosemu.LOAD_SEG+0x151B)<<4)+off
        def notify(uc, address, size, user, off=off):
            if m.ds_read(0x01DE, 1)[0]:
                active[0](off)
        m.uc.hook_add(UC_HOOK_CODE, notify, None, at, at)
    for i in range(384):
        m.ds_write(0, saved)
        p = [0x04D4, 0x0508][i%2]
        actor = [0x0508, 0x04D4][i%2]
        word(0x03A0, p)
        word(0x04BA, actor)
        m.ds_write(0x01DE, bytes([i//2%2]))
        m.ds_write(0x1152, bytes([i%2 or i//4%2]))
        word(actor+26, [0, 1, 50, 100, 65535][i%5])
        word(actor+28, [1, 50, 100, 65535][i//5%4])
        word(0x0556, i%4)
        word(0x0558, i//4%4)
        g, mem, planes = make_game(m)
        logs = [[], []]
        def effect(which, read, write, op):
            logs[which].append((op, read(0x0300, 0x300), read(0x1152, 8)))
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            return 0
        active[0] = lambda op:effect(1, m.ds_read, m.ds_write, op)
        @CALLBACK
        def callback(gp, op, arg, user):
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op)
        other = Services(callback, None)
        host = MovieServices(None, None, None, None, ctypes.pointer(other))
        status = ctx.lib.gameplay_check_losses(ctypes.byref(g), ctypes.byref(host), None)
        m.call(0, 0x089E)
        CASES += 1
        if status or logs[0] != logs[1]:
            return ['loss branch status/boundaries %d'%i]
        compare('loss branch %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    original_wait = [None]
    at = (dosemu.LOAD_SEG<<4)+0x8C4A
    def waiting(uc, address, size, user):
        if m.ds_read(0xAA83, 1)[0]:
            original_wait[0]()
    m.uc.hook_add(UC_HOOK_CODE, waiting, None, at, at)
    for i in range(96):
        m.ds_write(0, saved)
        m.ds_write(0xAA94, bytes([i]))
        m.ds_write(0xAA83, bytes([i%3]))
        g, mem, planes = make_game(m)
        logs = [[], []]
        counts = [0, 0]
        def complete(which, read, write):
            logs[which].append((read(0xAA83, 1), read(0xAA94, 1)))
            counts[which] += 1
            if counts[which] >= 1+i%3:
                write(0xAA83, bytes([0]))
        original_wait[0] = lambda:complete(1, m.ds_read, m.ds_write)
        @RESOURCE
        def callback(gp, op, a, b, user):
            if op != 0x0100:
                return -1
            complete(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)))
            return 0
        platform = Resources(callback, None)
        host = SoundServices(None, ctypes.pointer(platform))
        status = ctx.lib.sound_stop_and_wait(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0x8C45, max_instr=100_000_000)
        CASES += 1
        if status or logs[0] != logs[1]:
            return ['sample completion wait %d'%i]
        compare('sample completion %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
