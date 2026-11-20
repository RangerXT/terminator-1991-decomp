"""bytekiller_unpack and lzhuf_unpack against the originals at 0000:B425 and 14B5:0216,
on real compressed blocks taken from the game's data files."""
import ctypes
import os
import struct

CASES = 0
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data')


def bytekiller_blocks():
    """Yield (label, packed bytes) for a spread of ByteKiller blocks."""
    # cutscene backgrounds and every 6th delta frame
    vga = os.path.join(DATA, 'vga')
    for f in sorted(os.listdir(vga)):
        d = open(os.path.join(vga, f), 'rb').read()
        if f.endswith('.DFB') and f in ('TS.DFB', 'NY.DFB', 'DOS.DFB'):
            n = struct.unpack_from('<H', d, 0)[0]
            yield f, d[0:2], d[2:2 + n]
        elif f.endswith('.DFF'):
            count = struct.unpack_from('<H', d, 0)[0]
            pos = 2
            for i in range(count):
                n = struct.unpack_from('<H', d, pos)[0]
                if n and i % 6 == 0:
                    yield f'{f}#{i}', d[pos:pos + 2], d[pos + 2:pos + 2 + n]
                pos += 2 + n
    # image planes (type bit 0x04)
    common = os.path.join(DATA, 'common')
    for f in ('DOR.ATF', 'WHEELS.CIF', 'WEAPONS.CIF', 'YELLOWPG.CIF', 'SHAPES.IMG', 'PANEL.IMG', 'MAP.IMG'):
        d = open(os.path.join(common, f), 'rb').read()
        pos = 0
        k = 0
        while pos + 32 <= len(d) and k < 12:
            mask, planes, w, h, x, y, typ, pb = struct.unpack_from('<8H', d, pos)
            if planes not in (1, 4, 8) or not w or not h:
                break
            stored = 1 if planes == 8 else bin(mask & 0xF).count('1')
            if not typ & 0x0C:
                pos += 16 + stored * pb
                continue
            sizes = struct.unpack_from('<8H', d, pos + 16)
            p = pos + 32
            for i in range(stored):
                if typ & 0x04:
                    yield f'{f}@{pos}.{i}', d[p - 2:p], d[p:p + sizes[i]]
                    k += 1
                p += sizes[i]
            pos = p
    # vignette planes
    d = open(os.path.join(common, 'COP.CAF'), 'rb').read()
    pos = 2
    for i in range(4):
        n = struct.unpack_from('<H', d, pos)[0]
        yield f'COP.CAF.{i}', d[pos:pos + 2], d[pos + 2:pos + 2 + n]
        pos += 2 + n


def lzhuf_blocks():
    vga = os.path.join(DATA, 'vga')
    for f in ('ARM256.IMG', 'DAM256.IMG', 'GUN256.IMG'):
        d = open(os.path.join(vga, f), 'rb').read()
        n = struct.unpack_from('<H', d, 0x10)[0]
        yield f, d[0x20:0x20 + n]
    common = os.path.join(DATA, 'common')
    d = open(os.path.join(common, 'BMAP.IMG'), 'rb').read()
    sizes = struct.unpack_from('<8H', d, 0x10)
    p = 0x20
    for i in range(4):
        yield f'BMAP.IMG.{i}', d[p:p + sizes[i]]
        p += sizes[i]


def run(ctx):
    global CASES
    m = ctx.boot()
    lib = ctx.lib
    lib.bytekiller_unpack.restype = ctypes.c_int
    lib.lzhuf_unpack.restype = ctypes.c_uint16
    fails = []
    src_seg, dst_seg = 0x7800, 0x8800          # free conventional memory above the program
    FILL = 0xA5

    # Each block is given the two bytes that precede it in its file, as in the game.
    for label, before, packed in bytekiller_blocks():
        size = struct.unpack_from('<H', packed, len(packed) - 2)[0]
        m.wb(src_seg, 0x10, before + packed)
        m.wb(dst_seg, 0, bytes([FILL]) * 0x10000)
        r = m.call(0x0000, 0xB425, stack=(0x12, src_seg, 0, dst_seg, len(packed)))
        want = m.rb(dst_seg, 0, 0x10000)
        want_ret = 0 if r['ax'] == 0 else -1
        buf = ctypes.create_string_buffer(bytes([FILL]) * 0x10000, 0x10000)
        src = ctypes.create_string_buffer(before + packed, len(packed) + 2)
        got_ret = lib.bytekiller_unpack(ctypes.byref(src, 2), ctypes.c_uint16(len(packed)), buf)
        CASES += 1
        if bytes(buf) != want or got_ret != want_ret:
            diff = next((i for i in range(0x10000) if buf.raw[i] != want[i]), None)
            fails.append(f'bytekiller {label}: size {size}, first difference at {diff}, '
                         f'return {got_ret} vs {want_ret}')

    for label, packed in lzhuf_blocks():
        m.wb(src_seg, 0, packed)
        m.wb(dst_seg, 0, bytes([FILL]) * 0x10000)
        m.call(0x14B5, 0x0216, far=True, ds=src_seg, es=dst_seg, si=0, di=0, cx=len(packed))
        want = m.rb(dst_seg, 0, 0x10000)
        buf = ctypes.create_string_buffer(bytes([FILL]) * 0x10000, 0x10000 + 64)
        lib.lzhuf_unpack(packed, buf)
        CASES += 1
        if buf.raw[:0x10000] != want:
            diff = next((i for i in range(0x10000) if buf.raw[i] != want[i]), None)
            fails.append(f'lzhuf {label}: first difference at {diff}')
    return fails
