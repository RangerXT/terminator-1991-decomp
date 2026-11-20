"""Raw menu-image blitter: actual MENU256/PASS256 and odd-width/offset quirks."""
import ctypes, os, random, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    m = dosemu.Machine()
    m.load(root/'out/emu/states/ingame.pkl')
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x9132)
    fails = []
    for i in range(66):
        m.ds_write(0, saved)
        m.w(dosemu.UC_X86_REG_AX, 19)
        m._video()
        seg = 0x8000
        if i < 2:
            raw = (root/'data/vga'/['MENU256.IMG', 'PASS256.IMG'][i]).read_bytes()
            offset = 0
            m.wb(seg, 0, raw)
        else:
            offset = [0, 0x100, 0xFF00][i%3]
            raw = bytes(rng.randrange(256) for _ in range(65536))
            m.wb(seg, 0, raw)
            header = struct.pack('<8H', 1, 8, 1+i%37, 1+i%23, i*17%320, i*11%200, 65, 0)
            m.wb(seg, offset, header)
        m.ds_write(0x91BC, struct.pack('<HH', offset, seg))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        ctx.lib.image_vga_blit_raw(ctypes.byref(g), screen)
        m.call(0, 0x9132, max_instr=100_000_000)
        CASES += 1
        if screen.raw != bytes(m.vga.chunky):
            return ['raw VGA pixels %d'%i]
        compare('raw VGA %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
