"""Combined C travel controller + elapsed simulation, with the world-step body external."""
import ctypes
import os
import struct
import sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services, Side, SERVICES
import dosemu
CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    active = [None]
    stubs = [s for s in SERVICES if s[1] != 0xB588] + [(0, 0xB5F9, False)]
    for seg, off, far in stubs:
        m.wb(seg + dosemu.LOAD_SEG, off, b'\xcb' if far else b'\xc3')
        at = ((seg + dosemu.LOAD_SEG) << 4) + off
        def hook(uc, addr, size, ud, off=off):
            result = active[0](off, 0)
            m.w(dosemu.UC_X86_REG_EFLAGS, (m.r(dosemu.UC_X86_REG_EFLAGS) & ~1) | (1 if result & 0x10000 else 0))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
    ctx.lib.travel_simulate.restype = ctypes.c_uint32
    for mode in ['complete', 'partial', 'retry']:
        for player in [0x04D4, 0x0508]:
            m.ds_write(0, saved)
            m.ds_write(0x03A0, struct.pack('<H', player))
            m.ds_write(player + 10, struct.pack('<H', 20))
            m.ds_write(0xE272, struct.pack('<H', 400))
            col, row = m.rw(m.DATA_SEG, player + 30), m.rw(m.DATA_SEG, player + 32)
            m.ds_write(0xE26A, struct.pack('<HHHH', col + 3, row + 2, 111, 777))
            g, mem, planes = make_game(m)
            mine = Side(dict(mode=mode), lambda off, count: ctypes.string_at(g.ds + off, count),
                        lambda off, value: ctypes.memmove(g.ds + off, value, len(value)))
            theirs = Side(dict(mode=mode), m.ds_read, m.ds_write)
            counts = [0, 0]
            def effect(which, side, service, arg):
                result = side.call(service, arg)
                if service == 0xB5F9:
                    counts[which] += 1
                    side.write(0x1153, bytes([255 if mode != 'complete' and counts[which] == 12 else 0]))
                return result
            active[0] = lambda service, arg: effect(1, theirs, service, arg)
            @CALLBACK
            def callback(gp, service, arg, user):
                if service == 0xB588:
                    return ctx.lib.travel_simulate(gp, ctypes.byref(host), arg)
                return effect(0, mine, service, arg)
            host = Services(callback, None)
            status = ctx.lib.travel_run(ctypes.byref(g), ctypes.byref(host))
            m.call(0, 0xD177, max_instr=20_000_000)
            CASES += 1
            if status or counts[0] != counts[1] or mine.events != theirs.events:
                fails.append(f'{mode} {player:04X}: native chain/service sequence differs')
            compare(f'native travel {mode} {player:04X}', mem, planes, m, fails)
            if fails:
                return fails
    return fails