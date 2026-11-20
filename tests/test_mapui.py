"""Modal map input loop vs executable; retrace waits are explicit identical test inputs."""
import ctypes
import os
import struct
import sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import Game, make_game, compare
import dosemu

CASES = 0
WAIT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint8, ctypes.c_void_p)
class Platform(ctypes.Structure):
    _fields_ = [('wait', WAIT), ('user', ctypes.c_void_p)]
KEYS = [0x5BFA, 0x5BFC, 0x5BDA, 0x01DE, 0x5C0A, 0x5BEF, 0x5C0B, 0x5BF8, 0x5BFE, 0x5BFF,
        0x5C26, 0x5C24, 0x5C29, 0x5C21, 0x5C0F]


def run(ctx):
    global CASES
    fails = []
    for area, snap, entry in [(0, 'local_map', 0xCC43), (1, 'area_map', 0xD021)]:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states', snap + '.pkl'))
        saved = m.ds_read(0, 65536)
        active = [None]
        for off, high in [(0x0DAA, 0), (0x0D8D, 1)]:
            m.wb(dosemu.LOAD_SEG, off, b'\xc3')
            at = (dosemu.LOAD_SEG << 4) + off
            def hook(uc, addr, size, ud, high=high):
                active[0](high)
            m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
        for scenario in range(24):
            m.ds_write(0, saved)
            for at in KEYS:
                m.ds_write(at, b'\0')
            m.ds_write(0xE1F1, b'\0')
            if scenario % 3 == 0:
                m.ds_write(0x01DE, b'\xff')
            if scenario % 4 == 0:
                m.ds_write(0x5BFA, b'\xff')
                m.ds_write(0x5BFC, b'\xff')
            elif scenario % 4 == 1:
                m.ds_write(0x5BDA, b'\x80')
            elif scenario % 4 == 2:
                m.ds_write(0x5BDA, b'\x01')
            if scenario & 1:
                m.ds_write(0x5C26, b'\xff')
            if scenario & 2:
                m.ds_write(0x5C0F, b'\xff')
            g, mem, planes = make_game(m)
            logs = [[], []]
            def effect(which, high, write):
                logs[which].append(high)
                n = len(logs[which])
                # Exercise an extra loop, modifier handling and the area-only key combination.
                if n == 1 and scenario % 4 in [2, 3]:
                    for at in [0x5C0A, 0x5BEF, 0x5C0B, 0x5BF8, 0x5BFE, 0x5BFF]:
                        write(at, b'\xff')
                if n == 7:
                    write(0x5BFA if scenario % 2 and scenario % 3 else 0x5BFC, b'\xff')
                if n > 30:
                    raise RuntimeError('Map loop did not finish')
            active[0] = lambda high: effect(1, high, m.ds_write)
            errors = []
            @WAIT
            def wait(gp, high, user):
                try:
                    effect(0, high, lambda off, value: ctypes.memmove(g.ds + off, value, len(value)))
                    return 0
                except Exception as exc:
                    errors.append(str(exc))
                    return -1
            platform = Platform(wait, None)
            got = ctx.lib.map_select(ctypes.byref(g), ctypes.byref(platform), area)
            out = m.call(0, entry, max_instr=5_000_000)
            CASES += 1
            if errors or got != (out['flags'] & 1) or logs[0] != logs[1]:
                fails.append(f'{snap} {scenario}: result/waits differ ({got}, errors {errors})')
            compare(f'{snap} selection {scenario}', mem, planes, m, fails)
            if fails:
                return fails
    return fails