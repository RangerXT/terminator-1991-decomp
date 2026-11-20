"""Native buffered keys, map-edge UI and refuelling with scripted platform input."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import Game, make_game, compare
from test_textmodal import Poll, Platform
CASES = 0
KeyPoll = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_void_p)
class Keys(ctypes.Structure):
    _fields_ = [('poll', KeyPoll), ('user', ctypes.c_void_p)]

def run(ctx):
    global CASES
    ctx.lib.keyboard_read.restype = ctypes.c_uint32
    ctx.lib.keyboard_read_available.restype = ctypes.c_uint8
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    rng = random.Random(0x4495)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(1024):
        m.ds_write(0, saved)
        at = 0x5B70+i%100
        word(0x5B6E, at)
        word(0x5BD4, 0 if i%4 == 0 else 1+i%20)
        m.ds_write(at, bytes([rng.randrange(256)]))
        word(0x5B6A, 65535)
        g, mem, planes = make_game(m)
        if i%4 == 0 or i%2:
            got = ctx.lib.keyboard_read_available(ctypes.byref(g))
            out = m.call(0, 0x37D5)
        else:
            got = ctx.lib.keyboard_read(ctypes.byref(g), None)
            out = m.call(0, 0x37AC)
        CASES += 1
        if got != (out['ax']&255):
            return ['buffered key %d'%i]
        compare('keyboard ring %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    # Each side gets its own scripted external keyboard state. No native logic is replayed.
    def platform_pair(g, i):
        counts = [[0, 0, 0, 0], [0, 0, 0, 0]]
        def advance(which, phase, put):
            counts[which][phase] += 1
            if phase == 1:
                put(0x5BF5, b'\xff')
            elif phase in [0, 2]:
                put(0x5BF5, b'\x00')
                put(0x5BDA, b'\x00')
            else:
                choices = [ord(']'), ord('F' if i%2 else 'N')] if i%3 == 0 else [ord('f' if i%2 else 'n')]
                ch = choices[min(counts[which][3]-1, len(choices)-1)]
                put(0x5B70, bytes([ch]))
                put(0x5B6E, struct.pack('<H', 0x5B70))
                put(0x5B6C, struct.pack('<H', 0x5B71))
                put(0x5BD4, struct.pack('<H', 1))
        @Poll
        def poll(gp, phase, ticks, user):
            advance(0, phase, lambda o, b:ctypes.memmove(g.ds+o, b, len(b)))
            return 0
        @KeyPoll
        def key(gp, user):
            advance(0, 3, lambda o, b:ctypes.memmove(g.ds+o, b, len(b)))
            return 0
        def hook(uc, a, size, user):
            cs = uc.reg_read(dosemu.UC_X86_REG_CS)
            ip = uc.reg_read(dosemu.UC_X86_REG_IP)
            if cs == dosemu.LOAD_SEG+0x5776 and ip == 0x02C6:
                phase = 1
            elif cs == dosemu.LOAD_SEG and ip == 0x5195:
                phase = 2
            elif cs == dosemu.LOAD_SEG and ip == 0x5169 and (m.ds_read(0x5BDA, 1)[0] or m.ds_read(0x5BF5, 1)[0]):
                phase = 0
            elif cs == dosemu.LOAD_SEG and ip == 0x37AC and not m.rw(m.DATA_SEG, 0x5BD4):
                phase = 3
            else:
                return
            advance(1, phase, m.ds_write)
        token = m.uc.hook_add(UC_HOOK_CODE, hook)
        # This machine has already executed 37AC during ring-buffer cases. Flush
        # its translated blocks so newly installed instruction hooks take effect.
        m.uc.ctl_remove_cache(0, 0x100000)
        return poll, key, Platform(poll, None), Keys(key, None), counts, token
    def reset(i):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, b'\x00')
        word(0x0200, 0)
        m.ds_write(0x8096, b'\x00')
        m.ds_write(0x5A4E, b'\x00')
        m.ds_write(0x5BDA, b'\x00')
        m.ds_write(0x5BF5, b'\x00')
        word(0x5BD4, 0)
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.ds_write(0xC4AB, b'\x00')
        word(0x1234, i%3*0x2000)
        word(0x122A, (i+1)%3)
        m.wb(dosemu.LOAD_SEG+0x5776, 0x02C6, b'\xcb')
    for i in range(512):
        reset(i)
        player = [0x4D4, 0x508][i%2]
        word(0x03A0, player)
        word(player+30, [0, 1, 2, 100, 189, 190, 191, 65535][(i//2)%8])
        word(player+32, [0, 1, 2, 63, 125, 126, 127, 65535][(i//16)%8])
        m.ds_write(0x5CDC, bytes([(i//128)%2]))
        m.ds_write(player+14, bytes([i%4]))
        m.ds_write(0x11CA, bytes([(i//256)%2]))
        g, mem, planes = make_game(m)
        poll, key, ui, keys, counts, hook = platform_pair(g, i)
        status = ctx.lib.player_check_map_edge(ctypes.byref(g), ctypes.byref(ui))
        m.call(0, 0x4609)
        m.uc.hook_del(hook)
        CASES += 1
        if status or counts[0] != counts[1]:
            return ['edge UI phases/status %d'%i]
        compare('map-edge warning %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    filled = declined = broke = 0
    for i in range(384):
        reset(i)
        player = m.rw(m.DATA_SEG, 0x03A0)
        word(player, 100)
        word(player+4, 200)
        m.ds_write(player+14, bytes([2 if i%11 else 1]))
        word(player+10, 0 if i%13 else 1)
        fuel = [0, 1, 50, 99, 100, 101][(i//2)%6]
        cash = [0, 2, 100, 200, 201, 500][(i//12)%6]
        word(0x5F72, fuel)
        word(0x117E, cash)
        m.ds_write(0x5EE5, bytes([i%17 == 0]))
        m.ds_write(0x5EE3, b'\x11')
        word(0x50AC, 2)
        word(0x01FE, 0x9000)
        m.ds_write(0x9000, struct.pack('<6H', 900, 0, 200, 0, 17, 0))
        m.ds_write(0x900C, struct.pack('<6H', 100 if i%7 else 1000, 0, 200, 0, 17, 0))
        g, mem, planes = make_game(m)
        poll, key, ui, keys, counts, hook = platform_pair(g, i)
        status = ctx.lib.vehicle_refuel_nearby(ctypes.byref(g), ctypes.byref(ui), ctypes.byref(keys))
        m.call(0, 0x4495)
        m.uc.hook_del(hook)
        CASES += 1
        if status or counts[0] != counts[1]:
            return ['refuel phases/status %d %s'%(i, counts)]
        compare('refuel flow %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        filled += fuel != 100 and m.rw(m.DATA_SEG, 0x5F72) == 100
        declined += counts[0][3] > 0 and m.rw(m.DATA_SEG, 0x5F72) == fuel
        broke += counts[0] == [0, 0, 0, 0] and m.ds_read(0x5EE5, 1)[0] == 255 and fuel != 100 and ((100-fuel)*2&65535) >= cash
    print('    refuel: purchased=%d declined=%d insufficient-funds latch=%d'%(filled, declined, broke))
    if not all([filled, declined, broke]):
        return ['missing refuel paths']
    return fails
