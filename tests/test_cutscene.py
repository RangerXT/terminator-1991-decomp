"""VGA DFB backgrounds/DFF deltas vs original B558/B519 on linear RAM buffers.
The full original decoder/frame routines execute. No pixels/palette copied to C.
This does not exercise the movie player, timing, audio or an EGA DCF/DBI decoder.
"""
import ctypes, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu, termanim
from test_drawlist import make_game, compare
CASES = 0


def packets(path):
    raw = path.read_bytes()
    count = struct.unpack_from('<H', raw)[0]
    pos = 2
    result = []
    for i in range(count):
        size = struct.unpack_from('<H', raw, pos)[0]
        result.append(raw[pos:pos+size+2])
        pos += 2+size
    return result


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    changed = 0
    zero = 0
    source_seg, work_seg, screen_seg = 0x8000, 0x7000, 0x9000
    source_base, work_base, screen_base = [x<<4 for x in [source_seg, work_seg, screen_seg]]
    backgrounds = sorted(Path(dosemu.ROOT, 'data/vga').glob('*.DFB'))
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    pattern = bytes((i*37+i//320)&255 for i in range(65536))
    for path in backgrounds:
        m.ds_write(0, saved)
        word(0x91B8, 0)
        word(0x91BA, source_seg)
        word(0xADDC, screen_seg)
        word(0x5B6A, 123)
        word(0x5BD4, 456)
        word(0x5B6C, 0x5BA0)
        word(0x5B6E, 0x5BC0)
        m.wb(source_seg, 0, path.read_bytes())
        m.wb(screen_seg, 0, pattern)
        g, mem, planes = make_game(m)
        palette = ctypes.create_string_buffer(768)
        ctx.lib.cutscene_background(ctypes.c_void_p(g.ds), ctypes.c_void_p(g.mem+source_base), ctypes.c_void_p(g.mem+screen_base), palette)
        m.call(0, 0xB558, far=True, es=m.DATA_SEG, max_instr=50_000_000)
        CASES += 1
        if palette.raw != bytes(m.vga.dac):
            return ['DFB palette '+path.name]
        compare('native DFB '+path.name, mem, planes, m, fails)
        if fails:
            return fails
        decoded, pal = termanim.render(path.stem)
        if m.rb(screen_seg, 0, 64000) != decoded[0]:
            return ['VGA background export '+path.name]
        word(0x91C6, work_seg)
        ctypes.memmove(g.ds+0x91C6, struct.pack('<H', work_seg), 2)
        m.wb(work_seg, 0, bytes([0xCC])*65536)
        ctypes.memset(g.mem+work_base, 0xCC, 65536)
        frames = packets(path.with_suffix('.DFF'))
        for index, frame in list(enumerate(frames))+[(-1, bytes(2))]:
            before = m.rb(screen_seg, 0, 65536)
            m.wb(source_seg, 0, frame)
            ctypes.memmove(g.mem+source_base, frame, len(frame))
            ctx.lib.cutscene_apply_frame(ctypes.c_void_p(g.mem+source_base), ctypes.c_void_p(g.mem+work_base), ctypes.c_void_p(g.mem+screen_base))
            m.call(0, 0xB519, far=True, ds=source_seg, si=0, max_instr=50_000_000)
            CASES += 1
            compare('native DFF %s frame %d'%(path.stem, index), mem, planes, m, fails)
            if fails:
                return fails
            if index >= 0 and m.rb(screen_seg, 0, 64000) != decoded[index+1]:
                return ['VGA frame export %s/%d'%(path.stem, index)]
            changed += m.rb(screen_seg, 0, 65536) != before
            zero += frame == bytes(2)
    print('    VGA cinematic primitives: backgrounds=%d changed deltas=%d empty frames=%d'%(len(backgrounds), changed, zero))
    if not changed or not zero:
        return ['missing cinematic branches']
    return fails
