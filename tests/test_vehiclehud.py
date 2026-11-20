"""Actual WHEELS.CIF loading, shared decoders, five-pass blit and vehicle composition."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game
from test_imageload import Files, trace_dos, regions, compare, check_memory
from test_imageunpack import write_wrapped
import dosemu

CASES = 0


def wheel_records(m):
    data = open(m._path('WHEELS.CIF'), 'rb').read()
    off = 0
    for i in range(5):
        lengths = struct.unpack_from('<4H', data, off + 16)
        size = 32 + sum(lengths)
        yield f'WHEELS#{i}', data[off:off + size], False
        off += size


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    spans = regions(m)
    trace_dos(m)
    ctx.lib.image_unpack_shared.restype = ctypes.c_uint64
    ctx.lib.screen_blit_five_planes.restype = ctypes.c_uint32
    def word(off, value):
        m.ds_write(off, struct.pack('<H', value & 65535))
    for i in range(3):
        m.ds_write(0, saved)
        g, mem, planes = make_game(m)
        files = Files(m)
        m.image_calls.clear()
        status = ctx.lib.vehicle_hud_load(ctypes.byref(g), ctypes.byref(files.host))
        m.call(0, 0x70AA)
        CASES += 1
        if status or len(files.calls) != len(m.image_calls):
            return ['wheel load status/IO count differs']
        for c, original in zip(files.calls, m.image_calls):
            if c[0] != original[0]:
                return ['wheel load DOS inputs differ']
            error = check_memory(c[1], original[1], spans)
            if error:
                return ['wheel load DOS boundary: ' + error]
        compare('wheel load', mem, planes, m, spans, fails)
        if fails:
            return fails
    loaded = m.ds_read(0, 65536)
    records = list(wheel_records(m))
    records.append(('BMAP', open(m._path('BMAP.IMG'), 'rb').read(), True))
    for label, raw, lzhuf in records:
        for i in range(12):
            m.ds_write(0, loaded)
            source = [0x100, 0xFFF0, 0xFFFE][i % 3]
            dest = [0, 0xFF80][i % 2]
            write_wrapped(m, 0x7800, source, raw)
            word(0x850E, 0x7800)
            word(0x8510, 0x8800)
            if lzhuf:
                m.wb(0x7800, 0x8510, struct.pack('<H', 0x8700 if i % 2 else 0x8800))
            word(0x8544, [1, 2, 4][(i // 3) % 3])
            g, mem, planes = make_game(m)
            result = ctx.lib.image_unpack_shared(ctypes.byref(g), source, dest, lzhuf)
            out = m.call(0, 0x731D if lzhuf else 0x72E5, si=source, di=dest, max_instr=80_000_000)
            CASES += 1
            expected = out['si'] | (out['di'] << 16) | (out['bx'] << 32) | (out['ax'] << 48)
            if result != expected:
                return [f'{label} decoder {i}: SI/DI/BX/AX differs']
            compare(f'{label} decoder {i}', mem, planes, m, spans, fails)
            if fails:
                return fails
    for i in range(48):
        m.ds_write(0, loaded)
        source = [0, 0xFFFE, 0x100][i % 3]
        write_wrapped(m, 0x8000, source, bytes((j * 37 + i) & 255 for j in range(8192)))
        dest, words, rows, stride = 0x11FC + (i % 3) * 0x2000, 1 + i % 6, 1 + i % 64, 40 + i % 2
        m.vga.gc[3] = (i % 4) << 3
        m.vga.gc[5] = i % 3
        m.vga.gc[4] = i % 4
        m.vga.gc[1] = i % 16
        g, mem, planes = make_game(m)
        result = ctx.lib.screen_blit_five_planes(ctypes.byref(g), 0x8000, source, dest, words, rows, stride)
        out = m.call(0x5776, 0x00A6, far=True, ds=0x8000, si=source, di=dest, cx=words, bx=rows, bp=stride)
        CASES += 1
        if result != out['si'] | (out['di'] << 16):
            return [f'five-pass blit {i}: SI/DI differs']
        compare(f'five-pass blit {i}', mem, planes, m, spans, fails)
        if fails:
            return fails
    rendered = set()
    for i in range(225):
        m.ds_write(0, loaded)
        player = m.rw(m.DATA_SEG, 0x03A0)
        m.ds_write(player + 14, bytes([[0, 1, 2, 3, 10][i % 5]]))
        m.ds_write(0x11CA, bytes([(i // 5) % 3]))
        frame = ((i // 15) % 5) * 2
        word(0x11A6, frame)
        word(0x1182, frame if i & 1 else 65535)
        word(0x8544, 4)
        word(0x850E, 0x1234)
        word(0x8510, 0x4321)
        word(0x1234, (i % 3) * 0x2000)
        g, mem, planes = make_game(m)
        if m.ds_read(player + 14, 1)[0] & 2 and not m.ds_read(0x11CA, 1)[0] and m.rw(m.DATA_SEG, 0x1182) != frame:
            rendered.add(frame)
        status = ctx.lib.vehicle_hud_draw(ctypes.byref(g))
        m.call(0, 0x7250)
        CASES += 1
        if status:
            return ['vehicle HUD unexpectedly unavailable']
        compare(f'vehicle HUD {i}', mem, planes, m, spans, fails)
        if fails:
            return fails
    if rendered != {0, 2, 4, 6, 8}:
        return [f'vehicle frame coverage incomplete: {rendered}']
    print(f'    vehicle HUD: frame offsets {sorted(rendered)}, native file loading and three-page rendering')
    return fails
