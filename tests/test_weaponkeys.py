"""Selection, reloads and hotkeys with native inventory, actual UI text and optics IO."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import Files, regions, compare
from test_hudcompose import HudCall, HudServices
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    rng = random.Random(0x1D03)
    ctx.lib.image_hud_service.restype = ctypes.c_uint32
    ctx.lib.image_hud_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, b'\x00')
        word(0x0200, 0)
        word(0x91C0, 0)
        word(0x91C2, 0x8000)
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.ds_write(0xC4AB, b'\x00')
        word(0x1234, i%3*0x2000)
        word(0x122A, i%3)
        word(0x122C, (i+1)%3)
        m.ds_write(0x11CA, bytes([i%3]))
        word(0x118E, i%9)
        word(0x1190, (i//9)%9)
        player = [0x4D4, 0x508][i%2]
        word(0x03A0, player)
        m.ds_write(player+15, b'\xff')
        for slot in range(8):
            m.ds_write(0x570+slot*6, bytes([slot, (i+slot)%4, 0, 0 if i%3 else 5, 10+slot, 3+slot]))
        m.ds_write(0x8096, bytes([[0, 1, 20, 240][(i//3)%4]]))
        m.ds_write(0x115D, b'\xff')
        return player
    def host_for(m):
        files = Files(m, record=False)
        @HudCall
        def service(gp, op, arg, user):
            return ctx.lib.image_hud_service(gp, op, arg, ctypes.byref(files.host))
        return files, service, HudServices(service, None)
    for i in range(192):
        setup(i)
        g, mem, planes = make_game(m)
        files, callback, host = host_for(m)
        status = ctx.lib.weapon_refresh_selection(ctypes.byref(g), ctypes.byref(host))
        m.call(0x11BC, 0x1E6B)
        CASES += 1
        if status or files.handles:
            return ['selection refresh service']
        compare('selection refresh %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    for i in range(512):
        player = setup(i)
        slot = 1+(i//3)%8
        al = 1<<(slot-1)
        g, mem, planes = make_game(m)
        files, callback, host = host_for(m)
        if i%2:
            status = ctx.lib.weapon_select_slot(ctypes.byref(g), player, slot, al, ctypes.byref(host))
            m.call(0x11BC, 0x1E1A, si=player, cx=slot, ax=al)
        else:
            status = ctx.lib.weapon_deselect_slot(ctypes.byref(g), slot, ctypes.byref(host))
            m.call(0x11BC, 0x1DD8, si=player, cx=slot)
        CASES += 1
        if status or files.handles:
            return ['selection service %d'%i]
        compare('select/deselect %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    reloaded = messages = compacted = 0
    def ammo(i, slot):
        kind = m.ds_read(0x80AF+slot-1, 1)[0]
        item = m.ds_read(0x80E2+kind, 1)[0]
        m.ds_write(0x1138+kind, bytes([0 if i%5 == 0 else 4]))
        # A real ammo item plus a following record exercises removal compaction.
        m.ds_write(0x5B0, struct.pack('<H4B', 0x8700, item, 0, 2, 1+i%2))
        m.ds_write(0x5B6, struct.pack('<H4B', 0x8708, 4, 0, 1, 1))
        m.ds_write(0x5BC, bytes(6))
        word(0x03A2, 0x5BC)
        m.ds_write(0x1145, b'\x03')
    for i in range(384):
        player = setup(i)
        slot = 1+i%8
        ammo(i, slot)
        word(0x0200, 1 if i%7 == 0 else 0)
        g, mem, planes = make_game(m)
        status = ctx.lib.weapon_reload_slot(ctypes.byref(g), slot)
        m.call(0x11BC, 0x1D59, cx=slot, si=player)
        CASES += 1
        if status:
            return ['reload rejected']
        compare('reload %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        reloaded += m.ds_read(0x570+(slot-1)*6+3, 1) == m.ds_read(0x570+(slot-1)*6+4, 1)
        messages += m.ds_read(0xC4AB, 1)[0] > 0
        compacted += m.rw(m.DATA_SEG, 0x03A2) == 0x5B6
    for i in range(384):
        player = setup(i)
        slot = 1+i%8
        ammo(i, slot)
        mask = [0, 1, 128, 255, 85, 170, rng.randrange(256)][i%7]
        m.ds_write(player+15, bytes([rng.randrange(256)]))
        for j in range(8):
            m.ds_write(0x5C14+j, bytes([(mask>>j)&1]))
        m.ds_write(0x5BF6, bytes([(i//7)%2]))
        m.ds_write(0x5C11, bytes([(i//14)%2]))
        g, mem, planes = make_game(m)
        files, callback, host = host_for(m)
        status = ctx.lib.weapon_hotkeys(ctypes.byref(g), player, ctypes.byref(host))
        m.call(0x11BC, 0x1D03, far=True, si=player)
        CASES += 1
        if status or files.handles:
            return ['hotkey status/file lifecycle %d'%i]
        compare('hotkeys %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    for i in range(1024):
        player = setup(i)
        word(0x020C, i%4)
        m.ds_write(0x5BF6, bytes([(i//4)%2]))
        word(player+8, rng.randrange(65536))
        for j, o in enumerate([0x5C21, 0x5C29, 0x5C26, 0x5C24]):
            m.ds_write(o, bytes([((i//8)>>j)&1]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.player_look_keys(ds)
        m.call(0, 0x0998)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['look-key priority %d'%i]
    print('    reloads: filled=%d panels=%d compacted=%d'%(reloaded, messages, compacted))
    if not all([reloaded, messages, compacted]):
        return ['missing reload paths']
    return fails
