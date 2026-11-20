"""VGA ATF text mask to palette index FE, including wrapped pointers."""
import ctypes, os, random, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    fails = []
    rng = random.Random(0x01C2)
    assets = sorted((root/'data/common').glob('*.ATF'))
    ctx.lib.cutscene_vga_overlay.restype = ctypes.c_uint32
    for i in range(64+len(assets)):
        m = dosemu.Machine()
        m.load(root/'out/emu/states/ingame.pkl')
        m.w(dosemu.UC_X86_REG_AX, 0x13)
        m._video()
        if i < 64:
            mask = bytes(rng.randrange(256) for _ in range(65536))
            source = [0, 0xFF00][i%2]
            dest = [0xB540, 0xFFF0, 0, 1234][i%4]
            rows = [7, 8, 55, 61, 100][i%5]
            m.wb(0x8000, 0, mask)
        else:
            m.wb(0x7000, 0, assets[i-64].read_bytes())
            m.ds_write(0x850E, struct.pack('<H', 0x7000))
            m.ds_write(0x8510, struct.pack('<H', 0x8000))
            m.ds_write(0x8544, struct.pack('<H', 4))
            m.call(0, 0x72E5, si=0, di=0)
            mask = m.rb(0x8000, 0, 65536)
            source = 0
            dest = 0xB540
            rows = 55
        pattern = bytes((j*19+i)&255 for j in range(65536))
        m.vga.chunky[:] = pattern
        screen = ctypes.create_string_buffer(pattern, 65536)
        buf = ctypes.create_string_buffer(mask, 65536)
        g, mem, planes = make_game(m)
        got = ctx.lib.cutscene_vga_overlay(buf, screen, source, dest, rows)
        out = m.call(0x14B5, 0x01C2, ds=0x8000, si=source, di=dest, bx=rows, cx=20, max_instr=100_000_000)
        CASES += 1
        if got != out['si']|(out['di']<<16) or screen.raw != bytes(m.vga.chunky):
            return ['VGA overlay %d state/pixels'%i]
        compare('VGA overlay %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
