"""Original protection-screen image loader only; no challenge/answer behavior changed."""
import ctypes, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import Files, trace_dos, regions, compare, check_memory
from test_polyfill import planes_of
from PIL import Image
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    raw = (root/'data/vga/PASS256.IMG').read_bytes()
    fails = []
    for i in range(12):
        m = dosemu.Machine()
        m.load(root/'out/emu/states/ingame.pkl')
        m.w(dosemu.UC_X86_REG_AX, 19)
        m._video()
        pattern = bytes((j*37+i)&255 for j in range(65536))
        m.vga.chunky[:] = pattern
        trace_dos(m)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        palette = ctypes.create_string_buffer(bytes(m.vga.dac), 768)
        original = []
        class VideoFiles(Files):
            def __init__(self, m):
                self.video = []
                super().__init__(m)
            def call(self, *args):
                self.video.append((screen.raw, palette.raw))
                return super().call(*args)
        files = VideoFiles(m)
        logged = m._dos
        def dos():
            if m.ax()>>8 in [0x3D, 0x3F, 0x3E]:
                original.append((bytes(m.vga.chunky), bytes(m.vga.dac)))
            return logged()
        m._dos = dos
        status = ctx.lib.image_vga_protection_load(ctypes.byref(g), ctypes.byref(files.host), screen, palette)
        m.call(0, 0xEE9F, max_instr=100_000_000)
        CASES += 1
        if status or len(files.calls) != len(m.image_calls) or files.video != original:
            return ['protection image IO/video status %d'%i]
        spans = regions(m)
        for a, b in zip(files.calls, m.image_calls):
            if a[0] != b[0] or check_memory(a[1], b[1], spans) or a[2] != b[2]:
                return ['protection image IO state %d'%i]
        compare('protection image %d'%i, mem, planes, m, spans, fails)
        if fails:
            return fails
        if screen.raw != bytes(m.vga.chunky) or palette.raw != bytes(m.vga.dac):
            return ['protection image pixels/palette %d'%i]
        if screen.raw[:64000] != raw[16:64016] or palette.raw != bytes(b>>2 for b in raw[64016:64784]):
            return ['protection image differs from extracted asset']
        if files.handles:
            return ['protection image handle leak']
        if i == 0:
            rgb = b''.join(bytes(min(255, c*4+c//16) for c in palette.raw[index*3:index*3+3]) for index in screen.raw[:64000])
            Image.frombytes('RGB', (320, 200), rgb).save(root/'out/emu/protection_image_native.png')
    return fails
