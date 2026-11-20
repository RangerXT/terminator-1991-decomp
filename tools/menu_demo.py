"""Original/native pause-menu comparison; selected page, default EGA palette preview."""
import ctypes, gzip, json, pickle, sys
from pathlib import Path
import capture, difftest, dosemu, frame_demo
sys.path.insert(0, str(Path(dosemu.ROOT)/'tests'))
from test_drawlist import make_game, compare
from test_menu import Call, Platform
from test_polyfill import planes_of
from unicorn import UC_HOOK_CODE
from PIL import Image, ImageChops, ImageDraw

def main():
    ctx = difftest.Ctx()
    caps = pickle.load(gzip.open(Path(dosemu.ROOT)/'tests/captures/menu_live.pkl.gz', 'rb'))
    m = capture.restore(caps[0])
    params = [m.r(m.REG_BY_NAME[n]) for n in ['si', 'ax', 'bx', 'cx', 'dx', 'di']]
    m.wb(dosemu.LOAD_SEG, 0x4A96, bytes([0xC3]))
    g, mem, planes = make_game(m)
    @Call
    def release(gp, op, a, b, user):
        ctypes.memset(g.ds+0x5BDA, 0, 1)
        ctypes.memset(g.ds+0x5BF5, 0, 1)
        return 0
    def hook(uc, addr, size, user):
        if m.r(dosemu.UC_X86_REG_CS) == dosemu.LOAD_SEG and m.r(dosemu.UC_X86_REG_IP) == 0x4A6F:
            m.ds_write(0x5BDA, bytes([0]))
            m.ds_write(0x5BF5, bytes([0]))
    m.uc.hook_add(UC_HOOK_CODE, hook)
    host = Platform(release, None)
    status = ctx.lib.menu_prepare(ctypes.byref(g), *params, ctypes.byref(host))
    m.call(0, 0x48E6, si=params[0], ax=params[1], bx=params[2], cx=params[3], dx=params[4], di=params[5], max_instr=100_000_000)
    fails = []
    compare('menu visual', mem, planes, m, fails)
    if status or fails:
        raise RuntimeError((status, fails))
    page = m.rw(m.DATA_SEG, 0x7818)
    images = []
    for raw in [planes_of(m), planes.raw]:
        w, h, rgb = frame_demo.image_of(raw, page, (0, 0, 319, 199))
        images.append(Image.frombytes('RGB', (w, h), rgb))
    diff = ImageChops.difference(*images)
    sheet = Image.new('RGB', (960, 220), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(zip(['Original', 'Native C', 'Difference'], images+[diff])):
        draw.text((i*320+8, 5), label, fill='white')
        sheet.paste(im, (i*320, 20))
    path = Path(dosemu.ROOT)/'out/emu/menu_c_vs_original.png'
    sheet.save(path)
    meta = {'identical':True, 'page':page, 'preview':'selected drawing page with default EGA palette; not live palette validation', 'menu':dict(zip(['text', 'x', 'y', 'width', 'height', 'actions'], params))}
    path.with_suffix('.json').write_text(json.dumps(meta, indent=2))
    print(path)
if __name__ == '__main__':
    main()
