"""Compare all five actual wheel frames: original DOS | native C | difference."""
import ctypes
import os
import sys
from PIL import Image, ImageChops, ImageDraw
import difftest
import dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_drawlist import make_game
from test_imageload import Files, regions, compare


def main():
    ctx = difftest.Ctx()
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    g, mem, planes = make_game(m)
    files = Files(m, record=False)
    fails = []
    if ctx.lib.vehicle_hud_load(ctypes.byref(g), ctypes.byref(files.host)):
        raise RuntimeError('Native wheel loading unavailable')
    m.call(0, 0x70AA)
    compare('wheel asset load', mem, planes, m, regions(m), fails)
    if fails:
        raise RuntimeError('; '.join(fails))
    player = m.rw(m.DATA_SEG, 0x03A0)
    m.wb(m.DATA_SEG, player + 14, b'\x02')
    m.wb(m.DATA_SEG, 0x11CA, b'\0')
    m.ww(m.DATA_SEG, 0x8544, 4)
    panel_w, panel_h, scale = 144, 80, 3
    cell_w, cell_h = panel_w * scale, panel_h * scale
    sheet = Image.new('RGB', (cell_w * 3, (cell_h + 20) * 5), '#181818')
    for i in range(5):
        m.ww(m.DATA_SEG, 0x11A6, i * 2)
        m.ww(m.DATA_SEG, 0x1182, 65535)
        g, mem, planes = make_game(m)
        if ctx.lib.vehicle_hud_draw(ctypes.byref(g)):
            raise RuntimeError('Native wheel drawing unavailable')
        m.call(0, 0x7250)
        compare(f'wheel frame {i}', mem, planes, m, regions(m), fails)
        if fails:
            raise RuntimeError('; '.join(fails))
        original_planes = m.vga.planes
        m.vga.crtc[0x0C] = m.vga.crtc[0x0D] = 0
        w, h, data = m.vga.screenshot()
        original = Image.frombytes('RGB', (w, h), data).crop((0, 112, panel_w, 192))
        m.vga.planes = [bytearray(planes.raw[p * 65536:(p + 1) * 65536]) for p in range(4)]
        w, h, data = m.vga.screenshot()
        native = Image.frombytes('RGB', (w, h), data).crop((0, 112, panel_w, 192))
        m.vga.planes = original_planes
        for j, (picture, label) in enumerate([(original, f'Original wheel frame {i}'),
                                             (native, 'Native C (actual file bytes)'),
                                             (ImageChops.difference(original, native), 'Difference (black = identical)')]):
            x, y = j * cell_w, i * (cell_h + 20)
            sheet.paste(picture.resize((cell_w, cell_h), Image.Resampling.NEAREST), (x, y + 20))
            ImageDraw.Draw(sheet).text((x + 4, y + 4), label, fill='white')
    path = os.path.abspath(os.path.join(dosemu.ROOT, 'out/emu/vehicle_hud_frames_c_vs_original.png'))
    sheet.save(path)
    print('All five wheel frames and all three screen pages match; file loading/decoding/drawing native')
    print(path)


if __name__ == '__main__':
    main()
