"""Render map/HUD comparisons with native resource loading from real asset files."""
import argparse
import ctypes
import os
import sys
from PIL import Image, ImageChops, ImageDraw
import difftest
import dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_resources import execute

JOBS = {
    'local': ('mapbegin', 'map_begin_local', False),
    'area': ('mapbegin_area0', 'map_begin_area', False),
    'overlay': ('mapbegin_area1', 'map_begin_area', False),
    'hud': ('systemhud0', 'hud_draw_system', True),
    'lock': ('systemhud3', 'hud_draw_system', True),
    'binos': ('hudoptics0', 'hud_draw_optics', True),
    'scope': ('hudoptics1', 'hud_draw_optics', True),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', choices=JOBS, default='overlay')
    args = ap.parse_args()
    ctx = difftest.Ctx()
    ctx.lib.image_hud_service.restype = ctypes.c_uint32
    ctx.lib.image_hud_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    ctx.lib.image_map_service.restype = ctypes.c_int
    ctx.lib.image_map_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    fails, state, counts = execute(ctx, *JOBS[args.case])
    if fails:
        raise RuntimeError('; '.join(fails))
    m, g, mem, planes, trace = state
    for key, value in trace['display_after'].items():
        setattr(m.vga, key, value)
    page = ctypes.c_uint16.from_address(g.ds + 0x1234).value
    m.vga.crtc[0x0C], m.vga.crtc[0x0D] = page >> 8, page & 255
    m.vga.planes = [bytearray(p) for p in trace['screen_after'][1]]
    w, h, data = m.vga.screenshot()
    original = Image.frombytes('RGB', (w, h), data)
    m.vga.planes = [bytearray(planes.raw[i * 65536:(i + 1) * 65536]) for i in range(4)]
    w, h, data = m.vga.screenshot()
    native = Image.frombytes('RGB', (w, h), data)
    scale = 1 if w == 640 else 2
    cell_w, cell_h = w * scale, h * scale
    sheet = Image.new('RGB', (cell_w * 3, cell_h + 20), '#181818')
    for i, (picture, label) in enumerate([(original, 'Original DOS'),
                                         (native, 'Native C resource loading and drawing'),
                                         (ImageChops.difference(original, native), 'Difference (black = identical)')]):
        sheet.paste(picture.resize((cell_w, cell_h), Image.Resampling.NEAREST), (i * cell_w, 20))
        ImageDraw.Draw(sheet).text((i * cell_w + 4, 4), label, fill='white')
    path = os.path.abspath(os.path.join(dosemu.ROOT, 'out/emu', f'native_resources_{args.case}_c_vs_original.png'))
    sheet.save(path)
    print(f'{args.case}: identical; {counts[0]} native resource services, {counts[1]} platform services replayed')
    print(path)


if __name__ == '__main__':
    main()
