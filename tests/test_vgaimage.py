"""9F17 native LZHUF VGA image and palette handling on all installed compressed images.
Check both far-buffer choices and preserve/switch-palette branches with real assets.
"""
import ctypes, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import Files, trace_dos, regions, check_memory, compare
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    fails = []
    images = []
    for path in sorted((root/'data/vga').glob('*.IMG')):
        raw = path.read_bytes()
        if struct.unpack_from('<H', raw, 12)[0]&8:
            images.append(path)
    for path in images:
        for i in range(8):
            m = dosemu.Machine();m.load(root/'out/emu/states/ingame.pkl');m._path = lambda name:str(path)
            def word(o, v):
                m.ds_write(o, struct.pack('<H', v&65535))
            m.w(dosemu.UC_X86_REG_AX, 0x13)
            m._video()
            m.ds_write(0x8200, path.name.encode('ascii')+bytes([0]))
            m.ds_write(0xABC8, bytes([i%2]))
            word(0x91BC, 0x100 if i//4 else 0)
            word(0x91BE, 0x8000)
            word(0x7B8A, 0x200 if i//4 else 0)
            word(0x7B8C, 0x9000 if i//2%2 else 0)
            pattern = bytes((j*37+i)&255 for j in range(65536))
            m.vga.chunky[:] = pattern
            trace_dos(m)
            files = Files(m)
            g, mem, planes = make_game(m)
            screen = ctypes.create_string_buffer(pattern, 65536)
            palette = ctypes.create_string_buffer(bytes(m.vga.dac), 768)
            status = ctx.lib.image_vga_load(ctypes.byref(g), ctypes.byref(files.host), 0x8200, screen, palette)
            m.call(0, 0x9F17, dx=0x8200, max_instr=100_000_000)
            CASES += 1
            if status or len(files.calls) != len(m.image_calls):
                return ['VGA image status/IO '+path.name]
            spans = regions(m)
            for a, b in zip(files.calls, m.image_calls):
                if a[0] != b[0] or check_memory(a[1], b[1], spans) or a[2] != b[2]:
                    return ['VGA image IO state '+path.name]
            compare('VGA image %s/%d'%(path.name, i), mem, planes, m, spans, fails)
            if fails:
                return fails
            if screen.raw != bytes(m.vga.chunky) or palette.raw != bytes(m.vga.dac):
                return ['VGA image pixels/palette '+path.name]
            if files.handles:
                return ['VGA image handles '+path.name]
    print('    VGA images:', len(images), 'real assets,', CASES, 'palette/buffer cases')
    return fails
