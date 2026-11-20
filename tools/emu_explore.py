"""Drive the game in tools/dosemu.py with a key script and build a contact sheet of the screens.

usage:
  python tools/emu_explore.py <out.png> <ticks> <every> [--keys "t:key[:hold],..."] [--hold N]
                              [--load FILE] [--save FILE] [--coverage] [--args "..."]

Menus react to one-tick taps; the 3D game polls the keyboard once per frame (about 4 ticks),
so in-game keys need --hold 6 or so.

The sheet shows one thumbnail every <every> ticks, labelled with the tick number.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('ticks', type=int)
    ap.add_argument('every', type=int)
    ap.add_argument('--keys', default='')
    ap.add_argument('--load')
    ap.add_argument('--save')
    ap.add_argument('--coverage', action='store_true')
    ap.add_argument('--args', default='')
    ap.add_argument('--cols', type=int, default=4)
    ap.add_argument('--hold', type=int, default=1, help='ticks a key stays down (in-game needs about 6)')
    a = ap.parse_args()
    from PIL import Image, ImageDraw
    m = dosemu.Machine(args=a.args, coverage=a.coverage)
    if a.load:
        m.load(a.load)
    base = m.ticks
    for item in filter(None, a.keys.split(',')):
        parts = item.split(':')
        m.press(base + int(parts[0]), parts[1].strip(), hold=int(parts[2]) if len(parts) > 2 else a.hold)
    thumbs = []
    t0 = time.time()
    end = m.ticks + a.ticks
    reason = 'ticks'
    while m.ticks < end:
        reason = m.run(ticks=min(a.every, end - m.ticks))
        s = m.vga.screenshot()
        if s:
            w, h, data = s
            im = Image.frombytes('RGB', (w, h), data)
            if h == 200 and w == 640:
                im = im.resize((640, 400))
            elif w == 320:
                im = im.resize((640, 400), Image.NEAREST)
            im = im.resize((320, im.height * 320 // im.width))
        else:
            im = Image.new('RGB', (320, 200), (0, 0, 60))
            ImageDraw.Draw(im).text((4, 20), m.text_screen()[:900], fill=(200, 200, 200))
        ImageDraw.Draw(im).text((3, 2), f't{m.ticks - base} m{m.vga.mode:02X}', fill=(255, 255, 0))
        thumbs.append(im)
        if reason != 'ticks':
            break
    cols = a.cols
    rows = (len(thumbs) + cols - 1) // cols
    ch = max(t.height for t in thumbs)
    sheet = Image.new('RGB', (cols * 324, rows * (ch + 4)), (40, 0, 40))
    for i, t in enumerate(thumbs):
        sheet.paste(t, ((i % cols) * 324, (i // cols) * (ch + 4)))
    sheet.save(a.out)
    print(f'stopped: {reason}; tick {m.ticks} (+{m.ticks - base}), at file {m.file_addr()}, '
          f'mode {m.vga.mode:02X}h, {time.time() - t0:.1f}s wall')
    print('console:', repr(''.join(m.console))[-300:])
    for ln in m.log[-14:]:
        print('  log:', ln)
    if m.unknown:
        print('unhandled services:', sorted(m.unknown))
    if m.port_log:
        print('unhandled ports:', {f'{k[0]} {k[1]:#x}': v for k, v in sorted(m.port_log.items())})
    if a.coverage:
        print('coverage entries:', m.write_coverage(os.path.join(dosemu.ROOT, 'disasm', 'coverage.txt')))
    if a.save:
        m.save(a.save)
        print('saved', a.save)


if __name__ == '__main__':
    main()
