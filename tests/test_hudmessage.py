"""C898/C957/C976 native HUD messages, clearing and page copies against DOS."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import c_events
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    calls = []
    m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
    addr = (dosemu.LOAD_SEG<<4)+0x89A2
    def sound(uc, a, size, user):
        calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255))
    m.uc.hook_add(UC_HOOK_CODE, sound, None, addr, addr)
    for i in range(144):
        m.ds_write(0, saved)
        player = [0x508, 0x4D4][(i//72)%2]
        m.ds_write(0x03A0, struct.pack('<H', player))
        m.ds_write(player+14, bytes([i%2]))
        m.ds_write(0x7AC6, bytes([(i//2)%2]))
        m.ds_write(0x11CA, bytes([(i//4)%3]))
        m.ds_write(0x1234, struct.pack('<H', (i%3)*0x2000))
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        op = (i//12)%3
        if op == 0:
            ctx.lib.hud_message(ctypes.byref(g), 0xB6A2)
            m.call(0, 0xC898, si=0xB6A2, es=m.DATA_SEG)
        elif op == 1:
            ctx.lib.hud_message_hide(ctypes.byref(g))
            m.call(0, 0xC957, es=m.DATA_SEG)
        else:
            ctx.lib.hud_message_clear(ctypes.byref(g))
            m.call(0, 0xC976, es=m.DATA_SEG)
        CASES += 1
        if c_events(ctx.lib) != calls:
            return ['HUD message sound %d'%i]
        compare('HUD message %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
