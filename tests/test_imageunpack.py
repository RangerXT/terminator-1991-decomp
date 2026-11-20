"""Compressed image dispatcher vs original 19CC on real assets and segmented buffers.

The LZHUF adaptive tables/bit-reader are local in C: only their original private scratch
ranges (5819:0004..1139 and 233A) are excluded. The history ring, all other conventional
memory outside the DOS stack, output guard bytes, EGA state and returned AX are checked.
"""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game
from test_polyfill import planes_of, screen_differences
import dosemu

CASES = 0


def records():
    root = os.path.join(dosemu.ROOT, 'data')
    for folder, names in [('common', ['MAPMASK.IMG', 'BMAP.IMG', 'MAP.IMG', 'FRAME.IMG',
                                      'WEAPONS.CIF', 'WHEELS.CIF', 'PANEL.IMG', 'DOR.ATF']),
                          ('vga', ['ARM256.IMG', 'DAM256.IMG', 'GUN256.IMG'])]:
        for name in names:
            data = open(os.path.join(root, folder, name), 'rb').read()
            pos = 0
            for frame in range(3):
                if pos + 32 > len(data):
                    break
                mask, bits, w, h, x, y, typ, pb = struct.unpack_from('<8H', data, pos)
                if bits not in [1, 4, 8] or not w or not h:
                    break
                count = (mask & ((1 << bits) - 1)).bit_count()
                if not count:
                    break
                if typ & 12:
                    lengths = struct.unpack_from('<8H', data, pos + 16)
                    size = 32 + sum(lengths[:count])
                    if size <= 65536:
                        yield f'{name}#{frame}', data[pos:pos + size]
                else:
                    size = 16 + count * pb
                pos += size
                if bits == 8:
                    break


def write_wrapped(m, seg, off, data):
    n = min(len(data), 65536 - off)
    m.wb(seg, off, data[:n])
    if n < len(data):
        m.wb(seg, 0, data[n:])


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    source_seg, dest_seg = 0x7800, 0x8800
    scratch = ((dosemu.LOAD_SEG + 0x5819) << 4)
    stack = m.r(dosemu.UC_X86_REG_SS) << 4
    excluded = [(scratch + 4, scratch + 0x113A), (scratch + 0x233A, scratch + 0x233B), (stack, stack + 1024)]
    excluded.sort()
    regions = []
    lo = 0
    for a, b in excluded:
        regions.append((lo, a))
        lo = b
    regions.append((lo, 0xA0000))
    frames = list(records())
    for label, raw in frames:
        variants = [('normal', 0x100, 0, raw), ('source wraps', 0xFFF0, 0, raw),
                    ('destination wraps', 0x100, 0xFF80, raw)]
        if label.startswith(('MAP.IMG#0', 'BMAP.IMG#0')):
            copy = bytearray(raw)
            struct.pack_into('<H', copy, 0, 5)
            variants.append(('sparse planes', 0x100, 0, bytes(copy)))
            copy = bytearray(raw)
            struct.pack_into('<H', copy, 14, 3)
            variants.append(('overlapping planes', 0x100, 0, bytes(copy)))
        if label == 'MAPMASK.IMG#0':
            copy = bytearray(raw)
            struct.pack_into('<H', copy, 32, 0)
            variants.append(('zero LZHUF size', 0x100, 0, bytes(copy)))
        if label == 'MAP.IMG#0':
            copy = bytearray(raw)
            first_size = struct.unpack_from('<H', raw, 16)[0]
            copy[32 + first_size - 4] ^= 1
            variants.append(('bad checksum ignored', 0x100, 0, bytes(copy)))
        for variant, source, dest, data in variants:
            m.wb(source_seg, 0, b'\x5e' * 65536)
            write_wrapped(m, source_seg, source, data)
            m.wb(dest_seg, 0, b'\xa5' * 65536)
            g, mem, planes = make_game(m)
            ax = ctypes.c_uint16()
            status = ctx.lib.image_unpack_compressed(ctypes.byref(g), source_seg, source, dest_seg, dest, ctypes.byref(ax))
            out = m.call(0, 0x19CC, ds=source_seg, si=source, es=dest_seg, di=dest, max_instr=80_000_000)
            CASES += 1
            if status or ax.value != out['ax']:
                fails.append(f'{label}, {variant}: status {status}, AX {ax.value:04X} vs {out["ax"]:04X}')
            want = bytes(m.uc.mem_read(0, 0xA0000))
            for lo, hi in regions:
                if mem.raw[lo:hi] != want[lo:hi]:
                    first = next(i for i in range(lo, hi) if mem.raw[i] != want[i])
                    fails.append(f'{label}, {variant}: memory differs at linear {first:05X}')
                    break
            problem = screen_differences(planes.raw, planes_of(m))
            if problem:
                fails.append(f'{label}, {variant}: {problem}')
            if out['di'] != dest:
                fails.append(f'{label}: original DI not restored')
            if fails:
                return fails
    print(f'    image unpack: {len(frames)} real image records, codec-private scratch excluded; history ring included')
    return fails