"""Full-height entry and camera hotkeys, with native image/HUD and platform-only services."""
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
    for i in range(48):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        prepare_weapons(m, i%9)
        m.ds_write(0x1234, struct.pack('<H', i%3*0x2000))
        m.ds_write(0x11CA, bytes([i%3]))
        m.ds_write(0x5C1C, bytes([(i//3)%2]))
        m.ds_write(0x5C0F, bytes([(i//6)%2]))
        host = Platform(ctx, m)
        g, mem, planes = make_game(m)
        if i < 12:
            status = ctx.lib.camera_full_height(ctypes.byref(g), ctypes.byref(host.host), ctypes.byref(host.files.host))
            m.call(0, 0x794A, max_instr=100000000)
        else:
            status = ctx.lib.camera_key_step(ctypes.byref(g), ctypes.byref(host.host), ctypes.byref(host.files.host))
            m.call(0, 0x79C3, max_instr=100000000)
        CASES += 1
        if status:
            return ['camera key status %d'%i]
        compare('camera keys/full-height %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        if host.files.handles:
            return ['camera key leaked image handle']
        if host.vm.vga.attr != m.vga.attr and host.calls:
            return ['camera key palette differs']
    return fails
