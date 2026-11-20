"""Post-scene contact, periodic colour effects, vehicle remaining counter and saved overlays."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x0758)
    fails = []
    ctx.lib.scene_contact_test.restype = ctypes.c_uint8
    def word(off, v):
        m.ds_write(off, struct.pack('<H', v&65535))
    for i in range(1024):
        m.ds_write(0, saved)
        word(0x8206, rng.randrange(512))
        coords = [rng.randrange(-70, 71) for j in range(4)]
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.scene_contact_test(ds, 0x8200, *coords)
        out = m.call(0, 0xAEC4, si=0x8200, ax=coords[0]&65535, bx=coords[1]&65535, cx=coords[2]&65535, dx=coords[3]&65535)
        CASES += 1
        if got != (out['flags']&1) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['contact predicate %d'%i]
    for i in range(384):
        m.ds_write(0, saved)
        player = [0x4D4, 0x508, 0x8200][i%3]
        word(0x03A0, player)
        word(0x04BA, 0x8300)
        m.ds_write(player, struct.pack('<5H', 0, 0, 0, (i//3)%512, 0))
        m.ds_write(player+14, bytes([i%2]))
        m.ds_write(0x1153, bytes([(i//2)%2]))
        m.ds_write(0xB66D, bytes([(i//4)%2]))
        for off in [0xDE52, 0xDE54, 0xE3EC, 0xE3EE]:
            word(off, rng.randrange(-70, 71))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.scene_contact_update(ds)
        m.call(0, 0xAE2E)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['contact update %d'%i]
    for i in range(192):
        m.ds_write(0, saved)
        word(0x1234, i%3*0x2000)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        word(0x97B8, i%8)
        word(0x0B2E, [0, 1, 2, 65535][i%4])
        word(0x0404, 0 if i%3 else 200)
        word(0x0406, 0)
        player = m.rw(m.DATA_SEG, 0x03A0)
        word(player, 0)
        word(player+4, 0)
        g, mem, planes = make_game(m)
        if i%2:
            ctx.lib.scene_flash(ctypes.byref(g))
            m.call(0, 0x18D3)
        else:
            ctx.lib.scene_timed_effect(ctypes.byref(g))
            m.call(0, 0x9756)
        CASES += 1
        compare('scene flash %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(192):
        m.ds_write(0, saved)
        word(0x1234, i%3*0x2000)
        m.ds_write(0x11CA, bytes([i%3]))
        word(0x5F72, [0, 1, 127, 65535][i%4])
        g, mem, planes = make_game(m)
        ctx.lib.hud_vehicle_remaining(ctypes.byref(g))
        m.call(0, 0x41C4)
        CASES += 1
        compare('vehicle remaining %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    for i in range(192):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, bytes([0]))
        m.ds_write(0xC4AB, bytes([i%3]))
        word(0xC4C4, 0xC4CE)
        word(0xC546, 1000)
        word(0x1234, i%3*0x2000)
        m.ds_write(0xC4C6, struct.pack('<4H', 1+i%16, 1+i%20, 0x100+i%3*0x2000, 0x8100))
        g, mem, planes = make_game(m)
        if i%2:
            status = ctx.lib.scene_overlay_restore(ctypes.byref(g))
            m.call(0x5776, 0x0247, far=True)
        else:
            status = ctx.lib.scene_overlay_replay(ctypes.byref(g))
            m.call(0, 0x07D1)
        CASES += 1
        if status:
            return ['overlay unsupported']
        compare('overlay restore/replay %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    return fails
