"""Native normal HUD, drowning/reload/map-edge panels: original | C | difference.
Uses actual game files and the loaded UI text/font. Prepared conditions are labelled;
these comparisons do not claim a fully native gameplay loop.
"""
import ctypes, os, struct, sys
from PIL import Image, ImageChops, ImageDraw
import difftest, dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_drawlist import make_game
from test_imageload import Files, regions, compare
from test_hudinit import prepare_weapons

def main():
    ctx = difftest.Ctx()
    rows = []
    for label in ['Eight weapon icons', 'Drowning warning', 'Reloading panel', 'Map-edge warning']:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        word(0x03A0, 0x508)
        m.ds_write(0x516, bytes([1]))
        m.ds_write(0xADCF, bytes([0]))
        m.ds_write(0x11CA, bytes([0]))
        word(0x1234, 0)
        word(0x122A, 0)
        word(0x122C, 1)
        word(0x0200, 0)
        m.ds_write(0x8096, bytes([0]))
        m.ds_write(0x5A4E, bytes([0]))
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.ds_write(0xC4AB, bytes([0]))
        if label == 'Eight weapon icons':
            prepare_weapons(m, 8)
            word(0x118E, 1)
            word(0x1190, 2)
            m.call(0x5776, 0x012A, far=True)
        elif label == 'Drowning warning':
            m.ds_write(0x00B9, bytes([255, 0]))
        elif label == 'Reloading panel':
            m.ds_write(0x570, bytes([0, 0, 0, 0, 6, 3]))
            kind = m.ds_read(0x80AF, 1)[0]
            item = m.ds_read(0x80E2+kind, 1)[0]
            m.ds_write(0x1138+kind, bytes([2]))
            m.ds_write(0x5B0, struct.pack('<H4B', 0x8700, item, 0, 2, 2))
            m.ds_write(0x5B6, bytes(6))
            word(0x03A2, 0x5B6)
        else:
            word(0x526, 1)
            word(0x528, 50)
            m.ds_write(0x5CDC, bytes([0]))
            m.ds_write(0x5A4E, bytes([255]))
        g, mem, planes = make_game(m)
        if label == 'Eight weapon icons':
            files = Files(m, record=False)
            status = ctx.lib.hud_init_normal(ctypes.byref(g), ctypes.byref(files.host))
            m.call(0, 0x4F4B, max_instr=100000000)
        elif label == 'Drowning warning':
            status = ctx.lib.scene_warning(ctypes.byref(g))
            m.call(0, 0x093A)
        elif label == 'Reloading panel':
            status = ctx.lib.weapon_reload_slot(ctypes.byref(g), 1)
            m.call(0x11BC, 0x1D59, cx=1, si=0x508)
        else:
            status = ctx.lib.player_check_map_edge(ctypes.byref(g), None)
            m.call(0, 0x4609)
        fails = []
        compare(label, mem, planes, m, regions(m), fails)
        if status or fails:
            raise RuntimeError(label+': '+str(fails))
        page = m.rw(m.DATA_SEG, 0x1234)
        m.vga.crtc[12] = page>>8
        m.vga.crtc[13] = page&255
        w, h, data = m.vga.screenshot()
        original = Image.frombytes('RGB', (w, h), data)
        m.vga.planes = [bytearray(planes.raw[p*65536:(p+1)*65536]) for p in range(4)]
        w, h, data = m.vga.screenshot()
        native = Image.frombytes('RGB', (w, h), data)
        diff = ImageChops.difference(original, native)
        if diff.getbbox():
            raise RuntimeError(label+': visible difference')
        rows.append((label, original, native, diff))
    sheet = Image.new('RGB', (1920, 420*len(rows)), '#181818')
    draw = ImageDraw.Draw(sheet)
    for row, (label, original, native, diff) in enumerate(rows):
        for col, (im, caption) in enumerate([(original, 'Original - '+label), (native, 'Native C - '+label), (diff, 'Difference (black = identical)')]):
            sheet.paste(im.resize((640, 400), Image.Resampling.NEAREST), (col*640, row*420+20))
            draw.text((col*640+6, row*420+4), caption, fill='white')
    path = os.path.join(dosemu.ROOT, 'out/emu/hud_scene_c_vs_original.png')
    sheet.save(path)
    print('4 actual-resource HUD/UI comparisons matched memory and EGA; image differences are black.')
    print(path)

if __name__ == '__main__':
    main()
