"""Prepared gameplay sight captures: original DOS | native C | difference.
Requires a built build/term.dll and weaponsights_prepared captures.
"""
import ctypes
import os
import sys
from PIL import Image, ImageChops, ImageDraw
import capture
import dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_drawlist import make_game, compare

def main():
    lib = ctypes.CDLL(os.path.join(dosemu.ROOT, 'build/term.dll'))
    rows = []
    for i, (before, after, _, _) in enumerate(capture.replay('weaponsights_prepared')):
        g, mem, planes = make_game(before)
        lib.weapon_draw_sights(ctypes.byref(g))
        fails = []
        compare('prepared sight %d'%i, mem, planes, after, fails)
        if fails:
            raise RuntimeError('; '.join(fails))
        if i not in [0, 5, 11]:
            continue
        page = before.rw(before.DATA_SEG, 0x1234)
        after.vga.crtc[0x0C] = (page>>8)&255
        after.vga.crtc[0x0D] = page&255
        w, h, data = after.vga.screenshot()
        original = Image.frombytes('RGB', (w, h), data).crop((0, 0, 320, 112))
        after.vga.planes = [bytearray(planes.raw[p*65536:(p+1)*65536]) for p in range(4)]
        w, h, data = after.vga.screenshot()
        native = Image.frombytes('RGB', (w, h), data).crop((0, 0, 320, 112))
        rows.append((i, original, native))
    if len(rows) != 3:
        raise RuntimeError('Expected three selected capture rows')
    sheet = Image.new('RGB', (1920, 244*len(rows)), '#181818')
    for row, (i, original, native) in enumerate(rows):
        for col, (im, label) in enumerate([(original, 'Original capture %d'%i), (native, 'Native post-firing sights'), (ImageChops.difference(original, native), 'Difference: black = identical')]):
            sheet.paste(im.resize((640, 224), Image.Resampling.NEAREST), (col*640, row*244+20))
            ImageDraw.Draw(sheet).text((col*640+5, row*244+4), label, fill='white')
    path = os.path.join(dosemu.ROOT, 'out/emu/weapon_sights_c_vs_original.png')
    sheet.save(path)
    print('12 prepared gameplay sight replays matched; screenshot crops show the selected draw page.')
    print(path)

if __name__ == '__main__':
    main()
