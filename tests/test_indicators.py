"""All post-scene direction-indicator paths against original 11BC:181B."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import capture
import dosemu
CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x181B)
    for i in range(320):
        m.ds_write(0, saved)
        player = [0x04D4, 0x0508][i % 2]
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player + 14, bytes([1 if i % 5 else 2]))
        m.ds_write(player + 6, struct.pack('<HH', rng.randrange(512), rng.randrange(512)))
        m.ds_write(0x11CA, bytes([2 if i % 7 == 0 else 0]))
        m.ds_write(0x122C, struct.pack('<H', i % 3))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.ds_write(0x04BA, struct.pack('<H', 0x053C if i % 3 else 0x04D4))
        for at in [0x0345, 0x1154, 0x1153]:
            m.ds_write(at, bytes([255 if rng.randrange(4) == 0 else 0]))
        for at in [0x1152, 0x01DE, 0xAF52, 0x7AC5]:
            m.ds_write(at, bytes([255 if rng.randrange(2) else 0]))
        for at in [0x7AC2, 0x7AC3, 0x7AC4]:
            m.ds_write(at, bytes([rng.choice([0, 1, 2, 255])]))
        for at in [0x7B64, 0x7B48, 0x7B56]:
            m.ds_write(at, struct.pack('<H', rng.randrange(512)))
        for record in [0x04D4, 0x0508, 0x053C]:
            m.ds_write(record + 30, struct.pack('<HH', rng.randrange(192), rng.randrange(128)))
        for history in [0x7B66, 0x7B4A, 0x7B58, 0x7B72]:
            for page in range(3):
                endpoint = (65535, 65535) if rng.randrange(3) == 0 else (rng.randrange(204, 221), rng.randrange(135, 152))
                m.ds_write(history + page * 4, struct.pack('<HH', *endpoint))
        g, mem, planes = make_game(m)
        ctx.lib.hud_draw_indicators(ctypes.byref(g))
        m.call(0x11BC, 0x181B, far=True)
        CASES += 1
        compare(f'indicators {i}', mem, planes, m, fails)
        if fails:
            return fails
    for i, (before, after, regs, _) in enumerate(capture.replay('indicators', far=True)):
        g, mem, planes = make_game(before)
        ctx.lib.hud_draw_indicators(ctypes.byref(g))
        CASES += 1
        compare(f'live indicators {i}', mem, planes, after, fails)
    return fails
