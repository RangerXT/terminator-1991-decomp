"""Interactive-map destination math and information panel vs original instructions."""
import ctypes
import os
import random
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game, compare
import capture

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = ctx.game()
    ds0 = m.ds_read(0, 65536)
    rng = random.Random(0xCC8D)
    points = [(161, 93), (160, 92), (162, 94), (0, 0), (7, 7), (8, 8),
              (319, 199), (65535, 65535), (32767, 32768)]
    points += [(rng.randrange(65536), rng.randrange(65536)) for _ in range(250)]
    for off, fun in [(0xCC8D, 'map_local_destination'), (0xCD05, 'map_area_destination')]:
        for x, y in points:
            m.ds_write(0, ds0)
            m.ds_write(0x7C90, struct.pack('<HH', x, y))
            m.ds_write(0xE26A, struct.pack('<HH', rng.randrange(192), rng.randrange(128)))
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            result = getattr(ctx.lib, fun)(ds)
            out = m.call(0, off)
            CASES += 1
            if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
                fails.append(f'{fun}({x},{y}): DS differs')
                break
            if off == 0xCC8D and bool(result) != bool(out['flags'] & 1):
                fails.append(f'{fun}({x},{y}): carry differs')
    for i in range(200):
        m.ds_write(0, ds0)
        player = m.rw(m.DATA_SEG, 0x03A0)
        for at in [player, player + 4, player + 30, player + 32, 0xE26A, 0xE26C, 0xE26E, 0xE270]:
            m.ds_write(at, struct.pack('<H', rng.randrange(65536)))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.map_destination_measure(ds)
        m.call(0, 0xCBA5)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            fails.append(f'measure {i}: DS differs')
            break
    for i in range(24):
        m.ds_write(0, ds0)
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.vga.gc[5] = i % 4
        m.vga.gc[3] = (i % 4) << 3
        m.vga.gc[8] = (i * 37) & 255
        g, mem, planes = make_game(m)
        ctx.lib.map_clear_info(ctypes.byref(g))
        m.call(0, 0xCDE1)
        CASES += 1
        compare(f'clear info {i}', mem, planes, m, fails)
    for i in range(24):
        m.ds_write(0, ds0)
        m.ds_write(0x1234, struct.pack('<H', (i % 3) * 0x2000))
        m.ds_write(0x8000, b'Bearing 123\0Distance 999\0\0Destination\0\xff')
        m.ds_write(0xE25C, struct.pack('<HHHH', 0x11B7, 0x12A7, 0x1397, 0x1487))
        m.ds_write(0xE170, struct.pack('<H', 65535 if i % 2 else 0))
        m.ds_write(0xE16A, bytes([i % 16]))
        g, mem, planes = make_game(m)
        ctx.lib.map_draw_info(ctypes.byref(g), 0x8000)
        m.call(0, 0xCD4A, si=0x8000)
        CASES += 1
        compare(f'draw info {i}', mem, planes, m, fails)
    m.ds_write(0, ds0)
    for start in ['local_map', 'area_map']:
        import dosemu
        mm = dosemu.Machine()
        mm.load(os.path.join(dosemu.ROOT, 'out', 'emu', 'states', start + '.pkl'))
        initial = mm.ds_read(0, 65536)
        for i in range(64):
            mm.ds_write(0, initial)
            for k, at in enumerate([0x5C26, 0x5C24, 0x5C29, 0x5C21, 0x5C0F]):
                mm.ds_write(at, bytes([255 if i & (1 << k) else 0]))
            x = [0, 1, 161, mm.rw(mm.DATA_SEG, 0x724C)][(i // 16) % 4]
            y = [0, 1, 93, mm.rw(mm.DATA_SEG, 0x9A5A)][(i // 8) % 4]
            mm.ds_write(0x7C90, struct.pack('<HH', x, y))
            g, mem, planes = make_game(mm)
            status = ctx.lib.map_pointer_step(ctypes.byref(g))
            mm.call(0, 0x830F)
            CASES += 1
            if status:
                fails.append(f'{start} pointer {i}: untranslated branch')
            compare(f'{start} pointer {i}', mem, planes, mm, fails)
            if fails:
                return fails
    for name, symbol in [('mapscene', 'map_draw_grid'), ('mapmarkers', 'map_draw_markers')]:
        for before, after, _, _ in capture.replay(name, far=(name == 'mapscene')):
            g, mem, planes = make_game(before)
            getattr(ctx.lib, symbol)(ctypes.byref(g))
            CASES += 1
            compare(f'{symbol} live', mem, planes, after, fails)
    if fails:
        return fails
    import gzip
    import pickle
    from dosemu import UC_X86_REG_EFLAGS
    state = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'mapscene.pkl.gz'), 'rb'))[0]
    for i in range(8):
        mm = capture.restore(state)
        player = mm.rw(mm.DATA_SEG, 0x03A0)
        if i:
            mm.ds_write(player, struct.pack('<H', [0, 1023, 512][i % 3]))
            mm.ds_write(player + 4, struct.pack('<H', [0, 1023, 512][(i + 1) % 3]))
            mm.ds_write(0x114D, bytes([255 if i & 1 else 0]))
        g, mem, planes = make_game(mm)
        status = ctx.lib.map_draw_local_scene(ctypes.byref(g))
        target = (dosemu.LOAD_SEG << 4) + 0xCE9B
        mm.uc.reg_write(UC_X86_REG_EFLAGS, mm.r(UC_X86_REG_EFLAGS) & ~dosemu.IF_)
        for _ in range(100):
            mm.step(target, 1_000_000)
            if mm.pending is not None:
                mm._apply_pending()
            if ((mm.cs << 4) + mm.ip) == target:
                break
        else:
            fails.append(f'local scene {i}: original did not reach CE9B')
            break
        CASES += 1
        if status:
            fails.append(f'local scene {i}: C returned {status}')
        compare(f'local scene {i}', mem, planes, mm, fails)
        if fails:
            break
    return fails
