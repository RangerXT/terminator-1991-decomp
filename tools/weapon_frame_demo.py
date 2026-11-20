"""Full 6B54 from prepared gameplay: original | native C | difference.
Build term.dll first. Fixture grants one weapon; the original sound body is external.
"""
import ctypes
import gzip
import os
import pickle
import sys
from PIL import Image, ImageChops, ImageDraw
from unicorn import UC_HOOK_CODE
import capture, dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_drawlist import make_game, compare
from test_blast import GameEvent, set_clock

def main():
    lib = ctypes.CDLL(os.path.join(dosemu.ROOT, 'build/term.dll'))
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'weaponframes_prepared.pkl.gz'), 'rb'))
    rows = []
    fired = 0
    for i, st in enumerate(caps):
        before = capture.restore(st)
        after = capture.restore(st)
        calls = []
        def sound(uc, address, size, user):
            calls.append((1, after.r(dosemu.UC_X86_REG_AX)&255, after.ds_read(0x80E9, 1)[0]))
        addr = (dosemu.LOAD_SEG<<4)+0x89A2
        after.uc.hook_add(UC_HOOK_CODE, sound, None, addr, addr)
        g, mem, planes = make_game(before)
        set_clock(lib, before)
        buf = (GameEvent*512)()
        lib.game_events(buf, 512)
        status = lib.weapon_frame(ctypes.byref(g), before.r(dosemu.UC_X86_REG_DX))
        capture.run_to_return(after, max_instr=50000000)
        n = lib.game_events(buf, 512)
        events = [(e.kind, e.a, e.b) for e in buf[:n]]
        fails = []
        if status or calls != events:
            fails.append('events/status')
        compare('complete weapon frame %d'%i, mem, planes, after, fails)
        if fails:
            raise RuntimeError('; '.join(fails))
        shot = before.rw(before.DATA_SEG, 0x0378) != after.rw(after.DATA_SEG, 0x0378)
        fired += shot
        if i not in [2, 10, 22]:
            continue
        page = before.rw(before.DATA_SEG, 0x1234)
        after.vga.crtc[0x0C] = (page>>8)&255
        after.vga.crtc[0x0D] = page&255
        w, h, data = after.vga.screenshot()
        original = Image.frombytes('RGB', (w, h), data)
        after.vga.planes = [bytearray(planes.raw[p*65536:(p+1)*65536]) for p in range(4)]
        w, h, data = after.vga.screenshot()
        native = Image.frombytes('RGB', (w, h), data)
        rows.append((i, shot, original, native))
    sheet = Image.new('RGB', (1920, len(rows)*420), '#181818')
    for row, (i, shot, original, native) in enumerate(rows):
        for col, (im, label) in enumerate([(original, 'Original frame %d, shot=%s'%(i, shot)), (native, 'Native numbers / firing / damage / sights'), (ImageChops.difference(original, native), 'Difference: black = identical')]):
            sheet.paste(im.resize((640, 400), Image.Resampling.NEAREST), (col*640, row*420+20))
            ImageDraw.Draw(sheet).text((col*640+4, row*420+4), label, fill='white')
    path = os.path.join(dosemu.ROOT, 'out/emu/weapon_frame_c_vs_original.png')
    sheet.save(path)
    print('%d complete gameplay weapon-frame comparisons passed; %d fired.'%(len(caps), fired))
    print(path)

if __name__ == '__main__':
    main()
