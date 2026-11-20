"""Elapsed fast-travel simulation loop; only the world-step body is external."""
import ctypes
import os
import sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
from test_travel import CALLBACK, Services
import dosemu
CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.wb(dosemu.LOAD_SEG, 0xB5F9, b'\xc3')
    saved = m.ds_read(0, 65536)
    active = [None]
    def hook(uc, addr, size, ud):
        active[0]()
    at = (dosemu.LOAD_SEG << 4) + 0xB5F9
    m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
    ctx.lib.travel_simulate.restype = ctypes.c_uint32
    configs = [(0, 0), (0, 1), (0, 3), (1, 0), (1, 1), (2, 0), (2, 1), (2, 2),
               (20, 19), (20, 20), (20, 21), (65535, 0), (65535, 65535)]
    for ticks, stop in configs:
        m.ds_write(0, saved)
        g, mem, planes = make_game(m)
        ccount, rcount = [0], [0]
        events = [[], []]
        def reference_step():
            rcount[0] += 1
            if rcount[0] <= 3 or rcount[0] % 10000 == 0:
                events[1].append(m.ds_read(0xDE3C, 2))
            m.ds_write(0x1153, bytes([255 if stop and rcount[0] == stop else 0]))
        active[0] = reference_step
        @CALLBACK
        def step(gp, service, arg, user):
            if service != 0xB5F9 or arg:
                return 0xFFFFFFFF
            ccount[0] += 1
            if ccount[0] <= 3 or ccount[0] % 10000 == 0:
                events[0].append(ctypes.string_at(g.ds + 0xDE3C, 2))
            ctypes.memmove(g.ds + 0x1153, bytes([255 if stop and ccount[0] == stop else 0]), 1)
            return 0
        host = Services(step, None)
        got = ctx.lib.travel_simulate(ctypes.byref(g), ctypes.byref(host), ticks)
        out = m.call(0, 0xB588, cx=ticks)
        want = out['cx'] | (0x10000 if out['flags'] & 1 else 0)
        CASES += 1
        if got != want or ccount != rcount or events[0] != events[1]:
            fails.append(f'ticks={ticks}, stop={stop}: result/count/flags differ')
        compare(f'simulation {ticks},{stop}', mem, planes, m, fails)
        if fails:
            break
    return fails