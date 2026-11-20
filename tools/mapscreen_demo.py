"""Compare the C local-map scene against the original, after MAP.IMG is loaded.

The original still supplies the static frame/legend and file loading. The C pass supplies
the grid, projected ground, place/vehicle markers and coordinate labels (CE72..CE9B).
"""
import ctypes
import gzip
import os
import pickle
import sys
from PIL import Image, ImageChops

import capture
import difftest
import dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_drawlist import make_game, compare


def main():
    ctx = difftest.Ctx()
    st = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'mapscene.pkl.gz'), 'rb'))[0]
    m = capture.restore(st)
    g, mem, planes = make_game(m)
    status = ctx.lib.map_draw_local_scene(ctypes.byref(g))
    if status:
        raise RuntimeError(f'C returned {status}')
    target = (dosemu.LOAD_SEG << 4) + 0xCE9B
    m.uc.reg_write(dosemu.UC_X86_REG_EFLAGS, m.r(dosemu.UC_X86_REG_EFLAGS) & ~dosemu.IF_)
    for _ in range(100):
        m.step(target, 1_000_000)
        if m.pending is not None:
            m._apply_pending()
        if (m.cs << 4) + m.ip == target:
            break
    else:
        raise RuntimeError('Original did not reach CE9B')
    fails = []
    compare('map scene', mem, planes, m, fails)
    if fails:
        raise RuntimeError('; '.join(fails))
    w, h, data = m.vga.screenshot()
    original = Image.frombytes('RGB', (w, h), data)
    m.vga.planes = [bytearray(planes.raw[i * 65536:(i + 1) * 65536]) for i in range(4)]
    w, h, data = m.vga.screenshot()
    rewritten = Image.frombytes('RGB', (w, h), data)
    diff = ImageChops.difference(original, rewritten)
    sheet = Image.new('RGB', (w * 3, h))
    for i, picture in enumerate([original, rewritten, diff]):
        sheet.paste(picture, (i * w, 0))
    path = os.path.join(dosemu.ROOT, 'out', 'emu', 'local_map_c_vs_original.png')
    sheet.resize((w * 6, h * 2), Image.Resampling.NEAREST).save(path)
    print('Original | C | difference: identical memory, EGA planes and register state')
    print(path)


if __name__ == '__main__':
    main()
