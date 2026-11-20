"""Status collection, complete seven-slot cycling, and actual text rendering."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import dosemu

CASES = 0


def conditions(m, saved, i):
    m.ds_write(0, saved)
    player = m.rw(m.DATA_SEG, 0x03A0)
    health = [0, 1, 20, 65535][i % 4]
    diff = [0, 19, 20, 21, 65535][(i // 4) % 5]
    m.ds_write(player + 0x1A, struct.pack('<HH', health, (health + diff) & 65535))
    for bit, off in enumerate([player + 0x19, 0xE4FB, 0x1154, 0x1153, 0x1152]):
        m.ds_write(off, bytes([255 if (i // 20) & (1 << bit) else 0]))
    m.ds_write(0xE47B, bytes([i % 3]) + b'\x55' * 6)


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    for i in range(640):
        conditions(m, saved, i)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.hud_collect_status(ds)
        m.call(0, 0xE29B)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return [f'status conditions {i}: DS differs']
    m.ds_write(0, saved)
    ds = ctypes.create_string_buffer(saved, 65536)
    for mask in range(128):
        for index in range(7):
            for timer in [0, 1, 5, 255]:
                state = bytes([(1 if j & 1 else 255) if mask & (1 << j) else 0
                               for j in range(7)] + [index, timer])
                m.ds_write(0xE47B, state)
                ctypes.memmove(ctypes.addressof(ds) + 0xE47B, state, len(state))
                result = ctx.lib.hud_cycle_status(ds)
                out = m.call(0, 0xE307, flags=3)
                CASES += 1
                if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70) or result != out['flags'] & 1:
                    return [f'status cycle {mask=}, {index=}, {timer=}: DS/carry differs']
    for i in range(140):
        conditions(m, saved, (i * 37) % 640)
        m.ds_write(0xE482, bytes([i % 7, [0, 1, 2, 255][i % 4]]))
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.ds_write(0xE170, struct.pack('<H', [0, 65535, 1, 32768][i % 4]))
        m.ds_write(0xE16A, bytes([i % 16]))
        g, mem, planes = make_game(m)
        ctx.lib.hud_draw_status(ctypes.byref(g))
        m.call(0, 0xE280)
        CASES += 1
        compare(f'status text {i}', mem, planes, m, fails)
        if fails:
            return fails
    pointers = struct.unpack('<7H', saved[0xE46D:0xE47B])
    texts = [saved[p:].split(b'\0', 1)[0].decode('ascii') for p in pointers]
    print(f'    status slots: {texts}')
    return fails
