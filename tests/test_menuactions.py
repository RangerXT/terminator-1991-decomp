"""Native audio-toggle/yes/no/close handlers; music driver is a host boundary."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_menu import Call, Platform
CASES = 0

def run(ctx, vga=False):
    global CASES
    CASES = 0
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    active = [None]
    submitted = 0
    for off in [0xF494, 0xF4A1]:
        m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
        at = (dosemu.LOAD_SEG<<4)+off
        def hook(uc, address, size, user, off=off):
            active[0](off)
        m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(192):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, bytes([0]))
        m.ds_write(0xC4AB, bytes([1 if i%3 else 0]))
        word(0xC4C4, 0xC4CE)
        word(0xC546, 9*40)
        word(0x9A72, 40)
        m.ds_write(0xC4C6, struct.pack('<4H', 10, 9, 0x300, 0x8000))
        m.ds_write(0x0361, bytes([[0, 1, 2, 255][i//4%4]]))
        m.ds_write(0xA616, bytes([i//16%2]))
        m.ds_write(0x7810, bytes([0xA5]))
        if vga:
            m.w(dosemu.UC_X86_REG_AX, 19)
            m._video()
            m.ds_write(0xADCF, bytes([1]))
            m.ds_write(0xAE04, bytes([i%3 != 0]))
            word(0x91BC, 0x100)
            word(0x91BE, 0x9000)
            word(0xAF22, 0x1200)
            word(0xAF24, 35)
            word(0xAF26, 9)
            m.vga.chunky[:] = bytes((j*37+i)&255 for j in range(65536))
        target = [0x4B4A, 0x4ED2, 0x4EDC, 0x4EEB][i%4]
        g, mem, planes = make_game(m)
        logs = [[], []]
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        def effect(which, read, write, op):
            logs[which].append((op, read(0x0361, 1), read(0x11CC, 1), read(0xA616, 1)))
            write(0x8682, bytes([(read(0x8682, 1)[0]+1)&255]))
            return 0
        active[0] = lambda op:effect(1, m.ds_read, m.ds_write, op)
        @Call
        def callback(gp, op, a, b, user):
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op)
        host = Platform(callback, None)
        status = ctx.lib.menu_vga_basic_action(ctypes.byref(g), screen, target, ctypes.byref(host)) if vga else ctx.lib.menu_basic_action(ctypes.byref(g), target, ctypes.byref(host))
        out = m.call(0, target, stack=(0xFFFF,))
        CASES += 1
        if status != 1 or logs[0] != logs[1] or out['flags']&1:
            return ['menu action status/boundary %d'%i]
        if vga and screen.raw != bytes(m.vga.chunky):
            return ['VGA basic action pixels %d'%i]
        compare('menu basic action %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        submitted += len(logs[0])
    if not submitted:
        return ['music option boundary not covered']
    print('    menu basic actions: music driver submissions=%d'%submitted)
    return fails
