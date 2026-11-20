"""Prepared pickup menu: original/native/diff and complete 531C interaction proof.
Uses the full-panel differential fixtures; selected page and default EGA preview.
"""
import json, struct, sys
from pathlib import Path
import difftest, dosemu, frame_demo
sys.path.insert(0, str(Path(dosemu.ROOT)/'tests'))
import test_pickupmenu
from PIL import Image, ImageDraw, ImageChops

def main():
    captured = []
    def record(native, original, m):
        captured.append((native, original, m.DATA_SEG))
    failures = test_pickupmenu.run(difftest.Ctx(), on_menu=record)
    if failures:
        raise RuntimeError(failures)
    native, original, ds_seg = captured[0]
    page = struct.unpack_from('<H', original[3], (ds_seg<<4)+0x7818)[0]
    images = []
    for raw in [original[4], native[4]]:
        w, h, rgb = frame_demo.image_of(raw, page, (0, 0, 319, 199))
        images.append(Image.frombytes('RGB', (w, h), rgb))
    difference = ImageChops.difference(*images)
    if difference.getbbox():
        raise RuntimeError('pickup menu pixels differ')
    sheet = Image.new('RGB', (960, 220), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(zip(['Original', 'Native C', 'Difference'], images+[difference])):
        draw.text((i*320+8, 5), label, fill='white')
        sheet.paste(im, (i*320, 20))
    path = Path(dosemu.ROOT)/'out/emu/pickup_c_vs_original.png'
    sheet.save(path)
    path.with_suffix('.json').write_text(json.dumps(dict(identical=True, page=page, scope='prepared nearby MEDKIT records, first input poll in full 531C panel; original and native full flows pass', palette='selected drawing page with default EGA palette preview, not live palette validation', comparisons=test_pickupmenu.CASES), indent=2))
    print(path)
if __name__ == '__main__':
    main()
