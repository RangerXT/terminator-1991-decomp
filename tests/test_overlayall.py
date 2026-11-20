"""All-window restore and UI bookkeeping reset against 5776:0295/02AF."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    fails = []
    for i in range(96):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        mode = i%2
        levels = i//2%4
        if mode:
            m.w(dosemu.UC_X86_REG_AX, 19)
            m._video()
        m.ds_write(0xADCF, bytes([mode]))
        m.ds_write(0x5A4E, bytes([255]))
        m.ds_write(0xC4AB, bytes([0]))
        m.ds_write(0xAE04, bytes([0]))
        m.ds_write(0xC4C4, struct.pack('<H', 0xC4C6))
        m.ds_write(0xC546, bytes(2))
        m.ds_write(0x1234, bytes(2))
        for j in range(levels):
            m.call(0, 0x5032, si=[0x0E7A, 0x0E49, 0x0FEC][j], ax=8+j, bx=3+j, cx=22, dx=10, es=m.DATA_SEG, max_instr=100_000_000)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        if i < 64:
            status = ctx.lib.scene_overlay_restore_all(ctypes.byref(g), screen)
            entry = 0x0295
        else:
            ctx.lib.scene_overlay_reset(ctypes.c_void_p(g.ds))
            status = 0
            entry = 0x02AF
        m.call(0x5776, entry, far=True, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if status or (mode and screen.raw != bytes(m.vga.chunky)):
            return ['all-window pixels/status %d'%i]
        compare('all-window restore/reset %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
