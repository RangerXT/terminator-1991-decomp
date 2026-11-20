"""All EGA DBI backgrounds and every DCF packet vs B36D/B3BC, to actual EGA.
Compare complete memory/card planes, including the background's copied scratch tail.
"""
import ctypes, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu, termega
from test_drawlist import make_game, compare
CASES = 0


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    changed = 0
    source_seg, work_seg = 0x8000, 0x7000
    source_base, work_base = source_seg<<4, work_seg<<4
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    scratch = bytes((i*37+i//40)&255 for i in range(65536))
    for path in sorted(Path(dosemu.ROOT, 'data/ega').glob('*.DBI')):
        raw, width, _ = termega.background(path)
        stride = width//8
        visible = stride*200
        m.ds_write(0, saved)
        m.w(dosemu.UC_X86_REG_AX, 14 if width == 640 else 13)
        m._video()
        word(0x91BA, source_seg)
        word(0xDE20, work_seg)
        word(0x91C6, work_seg)
        m.wb(dosemu.LOAD_SEG, 0xB423, struct.pack('<H', stride-1))
        m.wb(source_seg, 0, path.read_bytes())
        m.wb(work_seg, 0, scratch)
        g, mem, planes = make_game(m)
        ctx.lib.cutscene_ega_background(ctypes.byref(g), ctypes.c_void_p(g.mem+source_base), ctypes.c_void_p(g.mem+work_base))
        m.call(0, 0xB36D, max_instr=50_000_000)
        CASES += 1
        compare('native EGA background '+path.name, mem, planes, m, fails)
        if fails:
            return fails
        exported = [bytearray(p)+bytearray(65536-len(p)) for p in raw]
        for index, frame in enumerate(termega.packets(path.with_suffix('.DCF'))):
            m.wb(source_seg, 0, frame)
            ctypes.memmove(g.mem+source_base, frame, len(frame))
            before = [bytes(p) for p in m.vga.planes]
            ctx.lib.cutscene_ega_frame(ctypes.byref(g), ctypes.c_void_p(g.mem+source_base), ctypes.c_void_p(g.mem+work_base), stride)
            m.call(0, 0xB3BC, ds=source_seg, si=0, max_instr=50_000_000)
            CASES += 1
            compare('native EGA delta %s/%d'%(path.stem, index), mem, planes, m, fails)
            if fails:
                return fails
            termega.apply(exported, termega.delta(frame), stride)
            if any(p[:visible] != q[:visible] for p, q in zip(exported, m.vga.planes)):
                return ['extracted EGA pixels '+path.name]
            changed += any(bytes(p) != b for p, b in zip(m.vga.planes, before))
        # Check dimensions and palette interpretation independently of the plane test.
        w, h, rgb = m.vga.screenshot();image = termega.image_of(exported, width).convert('RGB')
        if image.size != (w, h) or image.tobytes() != rgb:
            return ['EGA export RGB '+path.name]
    print('    original/native EGA cinematic drawing: changed deltas=', changed)
    if not changed:
        return ['EGA delta drawing was not exercised']
    return fails
