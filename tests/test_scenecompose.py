"""0758 composition before and after weapon_frame; actual file IO, native rendering."""
import ctypes, gzip, os, pickle, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture, dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game
from test_hudcompose import HudCall, HudServices
from test_imageload import Files, regions, compare
from test_blast import c_events, set_clock
CASES = 0

def run(ctx):
    global CASES
    fails = []
    ctx.lib.image_hud_service.restype = ctypes.c_uint32
    ctx.lib.image_hud_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    for i in range(72):
        if i < 48:
            m = dosemu.Machine()
            m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        else:
            trace = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'systemhud%d_realtrace.pkl.gz'%(i%4)), 'rb'))
            m = capture.restore(trace['state'])
        def word(off, v):
            m.ds_write(off, struct.pack('<H', v&65535))
        m.wb(dosemu.LOAD_SEG, 0x07B0, b'\xc3')
        m.wb(dosemu.LOAD_SEG, 0x89A2, b'\xc3')
        m.ds_write(0xADCF, b'\x00')
        m.ds_write(0x01DE, b'\x00')
        word(0xC4C4, 0xC4DE)
        word(0xC546, 2000)
        m.ds_write(0xC4AB, b'\x03')
        for j in range(3):
            m.ds_write(0xC4C6+j*8, struct.pack('<4H', 12, 24, 0x506+j*0x2000, 0x8100+j*960))
        m.ds_write(0x8096, bytes([i%4]))
        word(0x0200, [0, 1, 2, 200][(i//4)%4])
        m.ds_write(0x00B9, bytes([(i//16)%2]))
        m.ds_write(0x00BA, bytes([(i//8)%2]))
        word(0x0B2E, i%3)
        word(0x1234, i%3*0x2000)
        word(0x122A, i%3)
        word(0x122C, (i+1)%3)
        if i < 48:
            word(0x03A0, [0x4D4, 0x508][i%2])
            m.ds_write(0x11CA, bytes([(i//2)%3]))
            word(0x91C0, 0)
            word(0x91C2, 0x8000)
            m.ds_write(0x8161, b'\x01')
            m.ds_write(0x114F, bytes([i%2]))
            m.ds_write(0x1150, bytes([(i//4)%2]))
            m.ds_write(0xAAA0, b'\x01')
            # Existing mask in the far buffer for cases without a load is valid too.
            m.wb(0x8000, 0, open(m._path('SCOPES.IMG' if (i//4)%2 else 'BINOS.IMG'), 'rb').read())
        sounds = []
        def sound(uc, a, size, user):
            sounds.append((1, uc.reg_read(dosemu.UC_X86_REG_AX)&255))
        addr = (dosemu.LOAD_SEG<<4)+0x89A2
        m.uc.hook_add(UC_HOOK_CODE, sound, None, addr, addr)
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        @HudCall
        def service(gp, op, arg, user):
            return ctx.lib.image_hud_service(gp, op, arg, ctypes.byref(files.host))
        host = HudServices(service, None)
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.scene_draw_overlays(ctypes.byref(g), ctypes.byref(host))
        m.call(0, 0x0758, es=m.DATA_SEG, max_instr=100000000)
        CASES += 1
        if status or c_events(ctx.lib) != sounds:
            return ['overlay composition status/sounds %d'%i]
        compare('scene overlays %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
        if files.handles:
            return ['composed overlay file leak']
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    for i in range(96):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, b'\x00')
        m.ds_write(0x11CA, bytes([i%3]))
        m.ds_write(0x1234, struct.pack('<H', i%3*0x2000))
        player = m.rw(m.DATA_SEG, 0x03A0)
        m.ds_write(player+14, b'\x01')
        m.ds_write(0xAA96, bytes([(i//3)%2]))
        g, mem, planes = make_game(m)
        status = ctx.lib.scene_draw_instruments(ctypes.byref(g))
        m.call(0, 0x07B3)
        CASES += 1
        if status:
            return ['instruments rejected']
        compare('scene instruments %d'%i, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    return fails
