"""Animated HUD sweep state/pixels and its sound request vs original with sound stubbed."""
import ctypes
import os
import struct
import sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
from test_blast import GameEvent, c_events
import dosemu

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    for column in range(8):
        for byte in range(3):
            m.ds_write(0, saved)
            m.ds_write(0xE435, bytes([column, byte]))
            m.ds_write(0xE439, struct.pack('<H', 0xE43B + byte))
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            ctx.lib.hud_sweep_clear(ds)
            m.call(0, 0xE44A)
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                return ['sweep clear DS differs']
    m.wb(dosemu.LOAD_SEG, 0x89A2, b'\xc3')
    calls = []
    def sound(uc, address, size, ud):
        calls.append((1, uc.reg_read(dosemu.UC_X86_REG_AX) & 255))
    addr = (dosemu.LOAD_SEG << 4) + 0x89A2
    m.uc.hook_add(UC_HOOK_CODE, sound, None, addr, addr)
    requested = 0
    for i in range(2304):
        m.ds_write(0, saved)
        column = i % 8
        byte = (i // 8) % 3
        remaining = (i // 24) % 6
        delay = [0, 1, 2, 255][(i // 144) % 4]
        mode = (i // 576) % 4
        m.ds_write(0xE435, bytes([column, byte, delay, remaining]))
        m.ds_write(0xE439, struct.pack('<H', 0xE43B + byte))
        m.ds_write(0xE43B, bytes([(j * 13 + i) & 255 for j in range(40)]))
        for off, value in [(0x5BE5, mode & 1), (0xE4FE, mode >> 1),
                           (0x1141, 255 if i & 4 else 0)]:
            m.ds_write(off, bytes([value]))
        player = m.rw(m.DATA_SEG, 0x03A0)
        m.ds_write(player + 0x1A, struct.pack('<H', [0, 15, 16, 255, 1024, 65535][i % 6]))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.wb(dosemu.LOAD_SEG, 0x1B42, struct.pack('<H', 40))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        ctx.lib.hud_draw_sweep(ctypes.byref(g))
        events = c_events(ctx.lib)
        m.call(0, 0xE348)
        CASES += 1
        if events != calls:
            return [f'sweep {i}: sound calls differ {events}, {calls}']
        requested += len(calls)
        compare(f'sweep {i}', mem, planes, m, fails)
        if fails:
            return fails
    print(f'    HUD sweep: {requested} sound requests compared; sound body excluded')
    return fails
