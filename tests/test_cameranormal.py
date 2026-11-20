"""Full 7946 camera reset in normal view: native resources, inventory, icons, overlays."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import compare, regions
from test_camera import Platform
from test_hudinit import prepare_weapons
CASES = 0

def run(ctx):
    global CASES
    fails = []
    for i in range(24):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        prepare_weapons(m, i%9)
        player = [0x508, 0x4D4][i%2]
        flags = [0, 1, 2, 8, 9, 10][(i//2)%6]
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player+14, bytes([flags]))
        m.ds_write(0x11CA, bytes([0]))
        m.ds_write(0x118E, struct.pack('<HH', 1, 2))
        m.ds_write(0x1234, struct.pack('<H', (i%3)*0x2000))
        host = Platform(ctx, m)
        g, mem, planes = make_game(m)
        status = ctx.lib.camera_reset(ctypes.byref(g), ctypes.byref(host.host), ctypes.byref(host.files.host))
        m.call(0, 0x7946, es=m.DATA_SEG, max_instr=100000000)
        CASES += 1
        if status:
            return ['normal camera unavailable %d'%i]
        compare('normal camera %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        if host.calls != [(0xFF10, 13, 0), (0x0C6B, 2, 0), (0x7AAF, 0, 0)]:
            return ['normal camera platform sequence']
        if host.vm.vga.attr != m.vga.attr or host.vm.vga.crtc[12:14] != m.vga.crtc[12:14]:
            return ['camera palette/page state differs']
        if host.files.handles:
            return ['normal camera file handles left open']
    return fails
