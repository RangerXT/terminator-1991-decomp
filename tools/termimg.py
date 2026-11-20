"""The Terminator (1991) image reader: .IMG / .CIF / .MSK / .ATF -> PNG.

A file is one or more images back to back. Each image:

  u16 plane_mask   which bit planes are stored (0x0F = all four; 0x02 = only plane 1; 1 for 256-colour)
  u16 planes       1, 4 (EGA-style bit planes) or 8 (one byte per pixel)
  u16 width, u16 height
  u16 x, u16 y     screen position
  u16 type         bit 0x08 = LZHUF, bit 0x04 = ByteKiller, neither = stored raw
  u16 plane_bytes  unpacked size of one plane: row_bytes*height, rows padded to an even byte count
                   (width*height for 8-plane)
  if compressed:   u16 packed_size[8]  (one per stored plane; 8-plane images use only the first)
  data             planes one after another
  256-colour files end with a 768-byte 8-bit RGB palette.

Files without that header (handled by `all`):
  HORIZON.IMG    raw 512x53, 4 bit planes one after another (64 bytes x 53 rows each)
  FONT.DMP       128 glyphs, 8x8, one byte per row
  FONT.PCK       70 glyphs, 16x12, one big-endian u16 per row (24 bytes per glyph), starts at 'A'
  SPECCHAR.CHR   36 glyphs (0-9, A-Z), 8x7, stored row-interleaved: row 0 of every glyph, then row 1...

usage:
  python tools/termimg.py info <file>...
  python tools/termimg.py png  <file> <out_prefix> [palette_file]
  python tools/termimg.py all  <out_dir>
"""
import os
import struct
import sys

import bytekiller
import lzhuf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
EGA16 = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170), (170, 85, 0),
         (170, 170, 170), (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255), (255, 85, 85),
         (255, 85, 255), (255, 255, 85), (255, 255, 255)]


class Image_:
    __slots__ = ('mask', 'planes', 'w', 'h', 'x', 'y', 'type', 'plane_bytes', 'pixels', 'offset')


def read_images(d):
    """Return (images, palette_or_None). pixels is one byte per pixel, row-major."""
    out = []
    pos = 0
    pal = None
    while pos + 16 <= len(d):
        mask, planes, w, h, x, y, typ, pb = struct.unpack_from('<8H', d, pos)
        if planes not in (1, 4, 8) or w == 0 or h == 0 or w > 1024 or h > 1024:
            break
        im = Image_()
        im.mask, im.planes, im.w, im.h, im.x, im.y, im.type, im.plane_bytes = mask, planes, w, h, x, y, typ, pb
        im.offset = pos
        stored = [0] if planes == 8 else [b for b in range(planes) if mask >> b & 1]
        nchunks = len(stored)
        p = pos + 16
        chunks = []
        if typ & 0x0c:
            sizes = struct.unpack_from('<8H', d, p)
            p += 16
            for i in range(nchunks):
                if typ & 0x08:
                    raw, _ = lzhuf.decode(d, p)
                else:
                    raw, ok = bytekiller.decode(d, p, sizes[i])
                    if not ok:
                        raise ValueError('ByteKiller checksum mismatch')
                chunks.append(raw)
                p += sizes[i]
        else:
            for i in range(nchunks):
                chunks.append(d[p:p + pb])
                p += pb
        if planes == 8:
            im.pixels = chunks[0][:w * h]
        else:
            rb = pb // h  # rows are padded to a whole number of 16-bit words
            px = bytearray(w * h)
            for pl, raw in zip(stored, chunks):
                bit = 1 << pl
                for yy in range(h):
                    row = raw[yy * rb:(yy + 1) * rb]
                    o = yy * w
                    for xx in range(w):
                        if row[xx >> 3] & (0x80 >> (xx & 7)):
                            px[o + xx] |= bit
            im.pixels = bytes(px)
        out.append(im)
        pos = p
        if planes == 8 and len(d) - pos == 768:
            pal = d[pos:pos + 768]
            pos += 768
    return out, pal, pos


def load_palette(path):
    d = open(path, 'rb').read()
    return d[-768:]


def to_png(im, pal, dst):
    from PIL import Image
    img = Image.frombytes('P', (im.w, im.h), im.pixels)
    if pal is None:
        flat = []
        for c in EGA16:
            flat += c
        if im.planes == 1:
            flat = [0, 0, 0, 255, 255, 255]
        pal = bytes(flat)
    img.putpalette(pal)
    img.save(dst)


def planar_raw(d, row_bytes, h, planes=4):
    w = row_bytes * 8
    px = bytearray(w * h)
    for pl in range(planes):
        base = pl * row_bytes * h
        for i in range(row_bytes * h):
            b = d[base + i]
            if b:
                for k in range(8):
                    if b & (0x80 >> k):
                        px[i * 8 + k] |= 1 << pl
    im = Image_()
    im.w, im.h, im.planes, im.pixels = w, h, planes, bytes(px)
    return im


def glyph_sheet(glyphs, gw, gh, per_row=16):
    """glyphs: list of lists of row bit-strings (ints, gw bits wide). Returns a 1-plane Image_."""
    rows = (len(glyphs) + per_row - 1) // per_row
    cw, ch = gw + 2, gh + 2
    w, h = per_row * cw, rows * ch
    px = bytearray(w * h)
    for g, rws in enumerate(glyphs):
        ox, oy = (g % per_row) * cw + 1, (g // per_row) * ch + 1
        for y, bits in enumerate(rws):
            for x in range(gw):
                if bits >> (gw - 1 - x) & 1:
                    px[(oy + y) * w + ox + x] = 1
    im = Image_()
    im.w, im.h, im.planes, im.pixels = w, h, 1, bytes(px)
    return im


def read_fonts(common):
    """Return {name: (glyph_w, glyph_h, glyphs)} for the three font files."""
    out = {}
    d = open(os.path.join(common, 'FONT.DMP'), 'rb').read()
    out['FONT_DMP'] = (8, 8, [list(d[i * 8:i * 8 + 8]) for i in range(len(d) // 8)])
    d = open(os.path.join(common, 'FONT.PCK'), 'rb').read()
    out['FONT_PCK'] = (16, 12, [[d[i * 24 + r * 2] << 8 | d[i * 24 + r * 2 + 1] for r in range(12)]
                                for i in range(len(d) // 24)])
    d = open(os.path.join(common, 'SPECCHAR.CHR'), 'rb').read()
    n = len(d) // 7
    out['SPECCHAR_CHR'] = (8, 7, [[d[r * n + i] for r in range(7)] for i in range(n)])
    return out


def cmd_info(paths):
    for p in paths:
        d = open(p, 'rb').read()
        try:
            ims, pal, end = read_images(d)
        except Exception as e:
            print(f'{os.path.basename(p)}: ERROR {e}')
            continue
        tail = len(d) - end
        print(f'{os.path.basename(p)}: {len(ims)} image(s), palette {"yes" if pal else "no"}, {tail} unparsed bytes')
        for i, im in enumerate(ims[:6]):
            print(f'   #{i} {im.w}x{im.h} planes {im.planes} at ({im.x},{im.y}) type {im.type:#04x}')


def cmd_png(src, prefix, palfile=None):
    d = open(src, 'rb').read()
    ims, pal, _ = read_images(d)
    if palfile:
        pal = load_palette(palfile)
    for i, im in enumerate(ims):
        to_png(im, pal, f'{prefix}.png' if len(ims) == 1 else f'{prefix}_{i:02d}.png')
    return len(ims)


def cmd_all(outdir):
    n = 0
    for sub in ('common', 'vga', 'ega'):
        src = os.path.join(ROOT, 'data', sub)
        dst = os.path.join(outdir, sub)
        os.makedirs(dst, exist_ok=True)
        for f in sorted(os.listdir(src)):
            ext = f.rsplit('.', 1)[-1]
            if ext not in ('IMG', 'CIF', 'MSK', 'ATF'):
                continue
            try:
                k = cmd_png(os.path.join(src, f), os.path.join(dst, f.replace('.', '_')))
                n += k
                if k == 0 and f != 'HORIZON.IMG':
                    print('no images parsed:', sub, f)
            except Exception as e:
                print('FAILED', sub, f, e)
    common = os.path.join(ROOT, 'data', 'common')
    dst = os.path.join(outdir, 'common')
    to_png(planar_raw(open(os.path.join(common, 'HORIZON.IMG'), 'rb').read(), 64, 53), None,
           os.path.join(dst, 'HORIZON_IMG.png'))
    for name, (gw, gh, glyphs) in read_fonts(common).items():
        to_png(glyph_sheet(glyphs, gw, gh), None, os.path.join(dst, name + '.png'))
    print(n + 4, 'images written to', outdir)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'info':
        cmd_info(a[1:])
    elif a[0] == 'png':
        cmd_png(*a[1:4])
    elif a[0] == 'all':
        cmd_all(a[1])
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
