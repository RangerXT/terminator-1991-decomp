"""Fast travel vs the executable with identical explicit external-service stubs.

This verifies controller/position behavior and the state at every external call. It does
not claim that simulation, cell loading, encounters or collision have been rewritten.
"""
import ctypes
import os
import random
import struct
import sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import Game, make_game, compare
import dosemu

CASES = 0
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(Game), ctypes.c_uint16,
                            ctypes.c_uint16, ctypes.c_void_p)
class Services(ctypes.Structure):
    _fields_ = [('call', CALLBACK), ('user', ctypes.c_void_p)]

SERVICES = [(0, x, False) for x in [0xB588, 0x3B88, 0xC42F, 0xBBF1, 0xC35F, 0xDC7B, 0x057C]]
SERVICES += [(0x11BC, 0x1FCC, True)]

class Side:
    def __init__(self, cfg, read, write):
        self.cfg, self.read, self.write = cfg, read, write
        self.events = []
        self.nsim = self.ncheck = self.ncollision = 0
    def word(self, off):
        return struct.unpack('<H', self.read(off, 2))[0]
    def call(self, service, arg):
        p = self.word(0x03A0)
        self.events.append((service, arg, self.read(0xE26A, 20), self.read(p, 48),
                            self.read(0x8683, 1), self.read(0xE1F2, 1)))
        # Deliberate external side effect: prove that the controller observes updated state.
        self.write(0x8682, bytes([(self.read(0x8682, 1)[0] + 1) & 255]))
        if service == 0xB588:
            self.nsim += 1
            mode = self.cfg.get('mode', 'complete')
            if mode == 'complete' or (mode == 'retry' and self.nsim > 1):
                return 0
            if mode == 'zero':
                remaining = arg
            elif mode == 'wrap':
                remaining = (arg + 1) & 65535
            else:
                remaining = min(self.cfg.get('remaining', 20), max(0, arg - 1))
            return 0x10000 | remaining
        if service == 0xC42F:
            self.ncheck += 1
            return 0x10000 if self.cfg.get('mode') == 'retry' and self.ncheck == 1 else 0
        if service == 0x1FCC:
            self.ncollision += 1
            return 0x10000 if self.ncollision <= self.cfg.get('blocked', 0) else 0
        return 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out', 'emu', 'states', 'ingame.pkl'))
    saved = m.ds_read(0, 65536)
    active = [None]
    for seg, off, far in SERVICES:
        m.wb(seg + dosemu.LOAD_SEG, off, b'\xcb' if far else b'\xc3')
        addr = ((seg + dosemu.LOAD_SEG) << 4) + off
        def hook(uc, address, size, ud, off=off):
            arg = m.r(dosemu.UC_X86_REG_CX) if off == 0xB588 else (m.r(dosemu.UC_X86_REG_BX) if off == 0x1FCC else 0)
            result = active[0].call(off, arg)
            if off == 0xB588:
                m.w(dosemu.UC_X86_REG_CX, result & 65535)
            m.w(dosemu.UC_X86_REG_EFLAGS, (m.r(dosemu.UC_X86_REG_EFLAGS) & ~dosemu.CF) | (1 if result & 0x10000 else 0))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
    configs = []
    for player in [0x04D4, 0x0508]:
        for distance in [0, 99, 100, 101, 400, 65535]:
            for speed in [0, 1, 50, 32768, 65535]:
                configs.append(dict(player=player, distance=distance, speed=speed))
        for mode in ['partial', 'zero', 'retry', 'wrap']:
            for remaining in [0, 1, 19, 20, 21]:
                configs.append(dict(player=player, distance=5000, speed=20, mode=mode, remaining=remaining))
    for n, cfg in enumerate(configs):
        m.ds_write(0, saved)
        player = cfg['player']
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player + 10, struct.pack('<H', cfg['speed']))
        m.ds_write(0xE272, struct.pack('<H', cfg['distance']))
        m.ds_write(0xE1F2, b'\0')
        col, row = m.rw(m.DATA_SEG, player + 30), m.rw(m.DATA_SEG, player + 32)
        m.ds_write(0xE26A, struct.pack('<HHHH', col + 3, row + 2, 111, 777))
        g, mem, planes = make_game(m)
        base = g.ds
        mine = Side(cfg, lambda off, count: ctypes.string_at(base + off, count),
                    lambda off, value: ctypes.memmove(base + off, value, len(value)))
        theirs = Side(cfg, m.ds_read, m.ds_write)
        active[0] = theirs
        errors = []
        @CALLBACK
        def callback(gp, service, arg, user):
            try:
                return mine.call(service, arg)
            except Exception as exc:
                errors.append(repr(exc))
                return 0xFFFFFFFF
        host = Services(callback, None)
        status = ctx.lib.travel_run(ctypes.byref(g), ctypes.byref(host))
        try:
            m.call(0, 0xD177, max_instr=5_000_000)
        except Exception as exc:
            fails.append(f'travel {n} {cfg}: original {exc}')
            return fails
        CASES += 1
        if status or errors or mine.events != theirs.events:
            fails.append(f'travel {n} {cfg}: status {status}, callback errors {errors}, event logs equal {mine.events == theirs.events}')
        compare(f'travel {n} {cfg}', mem, planes, m, fails)
        if fails:
            return fails
    for i in range(64):
        cfg = dict(blocked=i % 4)
        m.ds_write(0, saved)
        player = (0x04D4, 0x0508)[i % 2]
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player + 6, struct.pack('<H', (i * 37) % 512))
        m.ds_write(0x11BE, struct.pack('<H', 2 if i % 3 else 0))
        g, mem, planes = make_game(m)
        base = g.ds
        mine = Side(cfg, lambda off, count: ctypes.string_at(base + off, count),
                    lambda off, value: ctypes.memmove(base + off, value, len(value)))
        theirs = Side(cfg, m.ds_read, m.ds_write)
        active[0] = theirs
        @CALLBACK
        def callback(gp, service, arg, user):
            return mine.call(service, arg)
        host = Services(callback, None)
        status = ctx.lib.travel_clear_arrival(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0xD265)
        CASES += 1
        if status or mine.events != theirs.events:
            fails.append(f'arrival {i}: callback events/status differ')
        compare(f'arrival {i}', mem, planes, m, fails)
        if fails:
            return fails
    print(f'    travel: {len(configs)} controller cases and 64 collision-recovery cases, external calls stubbed')
    return fails