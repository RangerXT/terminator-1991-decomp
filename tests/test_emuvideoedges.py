"""CPU word accesses straddling video aperture: no lost overlap or wrapped byte."""
import json, os
from pathlib import Path
import dosemu
CASES = 0

def run(ctx):
    global CASES
    rows = []
    for ega in [False, True]:
        for writing in [False, True]:
            for above in [False, True]:
                m = dosemu.Machine()
                m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
                m.w(dosemu.UC_X86_REG_AX, 13 if ega else 19)
                m._video()
                seg, off = (0xA000, 65535) if above else (0x9FFF, 15)
                m.vga.chunky[0] = 0x22
                m.vga.chunky[65535] = 0x11
                m.vga.planes[0][0] = 0x22
                m.vga.planes[0][65535] = 0x11
                if ega:
                    m.vga.seq[2] = 4
                    m.vga.gc[8] = 0xF0
                m.wb(0x9FFF, 15, bytes([0x33]))
                m.wb(0xB000, 0, bytes([0x44]))
                m.wb(0x8000, 0, bytes([0xA3 if writing else 0xA1, off&255, off>>8, 0xC3]))
                out = m.call(0x7DF0, 0, ds=seg, ax=0xAABB)
                CASES += 1
                if not writing:
                    want = 0x4411 if above else 0x2233
                    if out['ax'] != want:
                        return ['CPU video edge read %s %s: %04x != %04x'%(ega, above, out['ax'], want)]
                elif ega:
                    where = 65535 if above else 0
                    want = 0xB0 if above else 0xA0
                    if m.vga.planes[2][where] != want or m.vga.planes[2][0 if above else 65535] != 0:
                        return ['EGA edge write/mask']
                    if m.rb(0xB000, 0, 1) != bytes([0xAA if above else 0x44]) or m.rb(0x9FFF, 15, 1) != bytes([0x33 if above else 0xBB]):
                        return ['EGA edge outside RAM']
                else:
                    expected = (0xBB, 0x22, 0xAA, 0x33) if above else (0x11, 0xAA, 0x44, 0xBB)
                    got = (m.vga.chunky[65535], m.vga.chunky[0], m.rb(0xB000, 0, 1)[0], m.rb(0x9FFF, 15, 1)[0])
                    if got != expected:
                        return ['VGA edge write: %r != %r'%(got, expected)]
                rows.append(dict(ega=ega, writing=writing, above=above, passed=True))
    (Path(dosemu.ROOT)/'out/verification/video_word_edges_after_fix.json').write_text(json.dumps(rows, indent=2))
    return []
