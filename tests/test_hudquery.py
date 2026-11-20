"""HUD query and its actual collision-grid line walk vs original; no service stubs."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import dosemu

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xA07B)
    ctx.lib.collision_grid_address.restype = ctypes.c_uint16
    ctx.lib.collision_line_blocker.restype = ctypes.c_uint8
    ctx.lib.collision_line_blocker_state.restype = ctypes.c_uint64
    ctx.lib.hud_scan_target.restype = ctypes.c_uint32
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 65535))
    for i in range(768):
        m.ds_write(0, saved)
        for off in [0x122E, 0x1230, 0x1232, 0xB662, 0xB666]:
            word(off, rng.randrange(65536) if i >= 384 else rng.randint(-1200, 2200))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        result = ctx.lib.collision_grid_address(ds)
        out = m.call(0x11BC, 0x21CA, far=True)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70) or result != out['di']:
            return [f'grid address {i}: state/DI differs']
    for i in range(512):
        m.ds_write(0, saved)
        for off in [0x11A2, 0x11A4, 0x8206, 0x8208, 0x820A, 0x820C]:
            word(off, rng.randint(-32768, 32767) if i >= 256 else rng.randint(0, 320))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        result = ctx.lib.hud_target_contains_sight(ds, 0x8200)
        out = m.call(0, 0xA2B3, si=0x8200)
        CASES += 1
        if result != out['flags'] & 1 or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return [f'target bounds {i}: result/state differs']
    blocked = clear = 0
    for i in range(768):
        m.ds_write(0, saved)
        word(0x91B2, 0x8000)
        grid = bytes([0 if i % 3 == 0 or j % 19 else 7 for j in range(65536)])
        m.wb(0x8000, 0, grid)
        for off in [0x122E, 0x1230, 0x1232, 0xB662, 0xB666]:
            word(off, rng.randint(-1200, 2200))
        # Exact six-cell shortening has different zero-count handling on the two axes.
        if i < 32:
            word(0x122E, 0)
            word(0x1232, 0)
            word(0xB662, 96 if i & 2 else 0)
            word(0xB666, 0 if i & 2 else 96)
        m.ds_write(0x8684, bytes([i % 2]))
        g, mem, planes = make_game(m)
        state = ctx.lib.collision_line_blocker_state(ctypes.byref(g))
        result = state & 255
        out = m.call(0x11BC, 0x25B0, far=True)
        CASES += 1
        if ((state >> 16) & 65535) != out['cx'] or ((state >> 32) & 65535) != out['dx']:
            return [f'collision line {i}: CX/DX differs']
        hit = out['flags'] & 1
        if bool(result) != bool(hit) or (hit and result != out['bx'] & 255):
            return [f'collision line {i}: blocker/carry differs']
        blocked += hit
        clear += not hit
        compare(f'collision line {i}', mem, planes, m, fails)
        if fails:
            return fails
    found = missing = 0
    for i in range(768):
        m.ds_write(0, saved)
        word(0x91B2, 0x8000)
        grid = bytes([0 if i % 3 == 0 or j % 13 else 11 for j in range(65536)])
        m.wb(0x8000, 0, grid)
        m.ds_write(0x7A18, b'\xff')
        m.ds_write(0x118E, bytes([1 + i % 3]))
        m.ds_write(0x8684, bytes([i % 2]))
        count = [0, 1, 2, 4][i % 4]
        word(0xB64E, count)
        word(0x11A2, 159)
        word(0x11A4, 60)
        word(0x118A, i * 17)
        word(0x118C, i * 29)
        player = m.rw(m.DATA_SEG, 0x03A0)
        for field in [0, 2, 4, 6, 8]:
            word(player + field, rng.randint(0, 700))
        for j in range(count):
            target = 0xB18E + j * 18
            m.ds_write(target, struct.pack('<9H', 0x8100, 0, [0, 16, 96, 512][(i + j) % 4],
                                           8 if (i + j) % 3 else 200, 311, 8, 110, 0, 0))
        g, mem, planes = make_game(m)
        result = ctx.lib.hud_scan_target(ctypes.byref(g))
        out = m.call(0, 0xA07B)
        CASES += 1
        if result != out['si'] | ((out['flags'] & 1) << 16):
            return [f'query {i}: SI/carry differs']
        found += bool(result & 65536)
        missing += not bool(result & 65536)
        compare(f'query {i}', mem, planes, m, fails)
        if fails:
            return fails
    print(f'    query: {found} found, {missing} missing; line walks {blocked} blocked, {clear} clear')
    return fails
