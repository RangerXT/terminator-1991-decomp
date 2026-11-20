"""The Terminator (1991) VGA cutscene reader: NAME.DFB + NAME.DFF -> GIF / PNG frames.

Player code: segment 14B5 of the unpacked exe (entry 14B5:000A), frame decoder 0000:B519.

  NAME.DFB  background
      u16 packed_len
      ByteKiller stream -> 64000 bytes, 320x200, one byte per pixel
      768-byte palette, 6-bit VGA DAC values (0-63)

  NAME.DFF  delta frames
      u16 frame_count
      per frame: u16 packed_len; if non-zero, a ByteKiller stream that unpacks to
          u16 total_bytes
          runs until total_bytes are used: { u16 count; u16 screen_offset; u8 pixel[count] }
      each frame patches the previous screen.

  NAME.ATF / TNAME.ATF  caption image shown with the scene (Reese / Terminator campaign);
      ordinary image files, see termimg.py.

  NAME.CAF  small 16-colour vignettes (96x49) shown in the game panel; loader 0000:70FB
      until end of file: u16 sequence_count; per sequence:
          4 x { u16 packed_len; ByteKiller -> 588 bytes }     one EGA bit plane each, 12 bytes x 49 rows
          u16 step_count
          per step: u16 packed_len; ByteKiller -> 4 sections (one per plane):
              u16 section_bytes (includes this word)
              runs: { u16 video_offset; u8 count; u8 data[count] }
              runs go DOWN the screen (stride 40 bytes) in mode 0Dh video memory;
              the picture sits at byte column 1, row 122.

usage:
  python tools/termanim.py info
  python tools/termanim.py gif <NAME> <out.gif> [ms_per_frame]
  python tools/termanim.py all <out_dir>          VGA cutscenes and CAF vignettes
"""
import os
import struct
import sys

import bytekiller

HERE = os.path.dirname(os.path.abspath(__file__))
VGA = os.path.join(HERE, '..', 'data', 'vga')
W, H = 320, 200


def read_dfb(path):
    d = open(path, 'rb').read()
    n = struct.unpack_from('<H', d, 0)[0]
    pix, ok = bytekiller.decode(d, 2, n)
    if not ok:
        raise ValueError('background checksum mismatch')
    pal = bytes(min(255, v * 255 // 63) for v in d[2 + n:2 + n + 768])
    return pix, pal, len(d) - (2 + n + 768)


def read_dff(path):
    """Yield one list of (screen_offset, bytes) runs per frame."""
    d = open(path, 'rb').read()
    count = struct.unpack_from('<H', d, 0)[0]
    pos = 2
    frames = []
    for _ in range(count):
        n = struct.unpack_from('<H', d, pos)[0]
        runs = []
        if n:
            raw, ok = bytekiller.decode(d, pos + 2, n)
            if not ok:
                raise ValueError('frame checksum mismatch')
            total = struct.unpack_from('<H', raw, 0)[0]
            p = 2
            while p < 2 + total:
                c, off = struct.unpack_from('<2H', raw, p)
                runs.append((off, raw[p + 4:p + 4 + c]))
                p += 4 + c
        frames.append(runs)
        pos += 2 + n
    return frames, len(d) - pos


def render(name):
    """Return (list of 64000-byte screens, palette). Screen 0 is the background."""
    pix, pal, _ = read_dfb(os.path.join(VGA, name + '.DFB'))
    frames, _ = read_dff(os.path.join(VGA, name + '.DFF'))
    screen = bytearray(pix[:W * H].ljust(W * H, b'\0'))
    out = [bytes(screen)]
    for runs in frames:
        for off, data in runs:
            screen[off:off + len(data)] = data
        out.append(bytes(screen[:W * H]))
    return out, pal


CAF_W_BYTES, CAF_H, CAF_ROW0, CAF_COL0 = 12, 49, 122, 1
EGA16 = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170), (170, 85, 0),
         (170, 170, 170), (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255), (255, 85, 85),
         (255, 85, 255), (255, 255, 85), (255, 255, 255)]


def read_caf(path):
    """Return a list of sequences; each is a list of images (96x49, one byte per pixel)."""
    d = open(path, 'rb').read()
    pos = 0
    seqs = []

    def chunky(planes):
        px = bytearray(CAF_W_BYTES * 8 * CAF_H)
        for pl in range(4):
            src = planes[pl]
            for i, b in enumerate(src):
                if b:
                    o = i * 8
                    for k in range(8):
                        if b & (0x80 >> k):
                            px[o + k] |= 1 << pl
        return bytes(px)

    while pos < len(d):
        n = struct.unpack_from('<H', d, pos)[0]
        pos += 2
        for _ in range(n):
            planes = []
            for _p in range(4):
                ln = struct.unpack_from('<H', d, pos)[0]
                raw, ok = bytekiller.decode(d, pos + 2, ln)
                if not ok:
                    raise ValueError('CAF checksum mismatch')
                planes.append(bytearray(raw))
                pos += 2 + ln
            steps = struct.unpack_from('<H', d, pos)[0]
            pos += 2
            images = [chunky(planes)]
            for _s in range(steps):
                ln = struct.unpack_from('<H', d, pos)[0]
                raw, ok = bytekiller.decode(d, pos + 2, ln)
                pos += 2 + ln
                q = 0
                for pl in range(4):
                    end = q + struct.unpack_from('<H', raw, q)[0]
                    q += 2
                    while q < end:
                        off, cnt = struct.unpack_from('<HB', raw, q)
                        row, col = off // 40 - CAF_ROW0, off % 40 - CAF_COL0
                        for i in range(cnt):
                            planes[pl][(row + i) * CAF_W_BYTES + col] = raw[q + 3 + i]
                        q += 3 + cnt
                images.append(chunky(planes))
            seqs.append(images)
    return seqs


def caf_gifs(path, prefix, ms=120):
    from PIL import Image
    pal = bytes(v for c in EGA16 for v in c)
    seqs = read_caf(path)
    for i, images in enumerate(seqs):
        ims = []
        for px in images:
            im = Image.frombytes('P', (CAF_W_BYTES * 8, CAF_H), px)
            im.putpalette(pal)
            ims.append(im)
        ims[0].save(f'{prefix}_{i}.gif', save_all=True, append_images=ims[1:], duration=ms, loop=0, disposal=1)
    return seqs


def names():
    return sorted(f[:-4] for f in os.listdir(VGA) if f.endswith('.DFB'))


def cmd_info():
    for n in names():
        pix, pal, tail_b = read_dfb(os.path.join(VGA, n + '.DFB'))
        frames, tail_f = read_dff(os.path.join(VGA, n + '.DFF'))
        print(f'{n:6} background {len(pix)} bytes, {len(frames)} frames, '
              f'unparsed bytes: DFB {tail_b}, DFF {tail_f}')


def cmd_gif(name, dst, ms=100):
    from PIL import Image
    screens, pal = render(name)
    ims = []
    for s in screens:
        im = Image.frombytes('P', (W, H), s)
        im.putpalette(pal)
        ims.append(im)
    ims[0].save(dst, save_all=True, append_images=ims[1:], duration=int(ms), loop=0, disposal=1)
    return len(ims)


def cmd_all(outdir):
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    for n in names():
        k = cmd_gif(n, os.path.join(outdir, n + '.gif'))
        screens, pal = render(n)
        im = Image.frombytes('P', (W, H), screens[0])
        im.putpalette(pal)
        im.save(os.path.join(outdir, n + '_background.png'))
        print(n, k, 'screens')
    common = os.path.join(HERE, '..', 'data', 'common')
    for f in sorted(os.listdir(common)):
        if f.endswith('.CAF'):
            seqs = caf_gifs(os.path.join(common, f), os.path.join(outdir, f[:-4] + '_CAF'))
            print(f, len(seqs), 'sequences of', len(seqs[0]), 'images')


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'info':
        cmd_info()
    elif a[0] == 'gif':
        cmd_gif(a[1], a[2], *(a[3:4]))
    elif a[0] == 'all':
        cmd_all(a[1])
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
