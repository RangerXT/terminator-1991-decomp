"""Native opponent shots/bursts against on-foot targets; vehicle exit is excluded."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import c_events, set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xBC68)
    calls = []
    fails = []
    for kind, o, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
        m.wb(dosemu.LOAD_SEG, o, bytes([0xC3]))
        addr = (dosemu.LOAD_SEG<<4)+o
        def hook(uc, a, size, user, kind=kind, reg=reg):
            calls.append((kind, uc.reg_read(reg)&255))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        actor = [0x4D4, 0x508][i%2]
        word(0x03A0, actor)
        m.ds_write(actor+14, bytes([1]))
        word(actor+26, 0)
        word(actor+28, 200)
        word(0xB64C, 0xB520)
        m.ds_write(0xE3E0, bytes([i%3 == 0]))
        m.ds_write(0x7AC6, bytes([i%11 == 0]))
        m.ds_write(0x11CA, bytes([i%3]))
        m.ds_write(0xAA98, bytes([i%2]))
        m.ds_write(actor+51, bytes([[0, 1, 2, 255][(i//2)%4]]))
        m.ds_write(0x5B0, struct.pack('<H4B', 0x8700, 15, 0, 6, 1))
        m.ds_write(0x5B6, bytes(6))
        word(0x03A2, 0x5B6)
        word(0x9126, rng.randrange(65536))
        word(0x1174, rng.randrange(65536))
        word(0x03F0, i%32)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *[rng.randrange(65536) for _ in range(200)]))
        return actor
    hits = absorbed = 0
    for i in range(768):
        actor = setup(i)
        x = rng.randrange(-1024, 2048)&65535
        z = rng.randrange(-1024, 2048)&65535
        sound = i%18
        threshold = [0, 1000, 40000, 65000, 65535][i%5]
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        ax = ctx.lib.opponent_fire_on_foot_state(ctypes.byref(g), x, z, sound, threshold)
        out = m.call(0, 0xBC68, ax=x, bx=z, cx=sound, dx=threshold)
        if ax != out['ax']:
            return ['opponent shot AX %d: %04x != %04x'%(i, ax, out['ax'])]
        status = 0
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['opponent shot events/status %d'%i]
        compare('opponent shot %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        hits += any(k == 5 for k, a in calls)
        absorbed += m.ds_read(0xAA98, 1)[0] and not any(k == 5 for k, a in calls)
    bursts = 0
    for i in range(768):
        actor = setup(i)
        fast = i%2
        m.ds_write(0xAA83, bytes([i%13 == 0]))
        for o, v in [(0x356, [0, 1, 2, 255][(i//2)%4]), (0x357, [0, 1, 2, 255][(i//8)%4]), (0x358, [0, 1, 2, 255][(i//32)%4]), (0x355, [0, 1, 2, 127, 128, 255][(i//128)%6]), (0x359, i%5 != 0), (0x35F, i%18)]:
            m.ds_write(o, bytes([v]))
        word(0xDE46, (i//3)%4)
        m.ds_write(0x351, bytes([1, 2, 3, 4]))
        word(0xDE52, 100)
        word(0xDE54, 100)
        word(0xDEC8, 50000)
        word(0xDECA, 65535)
        word(0x1208, 0x100)
        word(0x120A, 0x8000)
        pairs = struct.unpack_from('<4H', saved, 0xDE3E)
        ids = [item for pair in pairs for item in [pair&255, pair>>8]]
        for j, item in enumerate(ids):
            m.wb(0x8000, 0x100+j*6, struct.pack('<H4B', 0, item, 0, 2, 2))
        m.wb(0x8000, 0x130, bytes(6))
        incoming = rng.randrange(65536)
        g, mem, planes = make_game(m)
        calls.clear()
        c_events(ctx.lib)
        set_clock(ctx.lib, m)
        status = ctx.lib.opponent_burst_on_foot(ctypes.byref(g), fast, incoming)
        m.call(0, 0xC397 if fast else 0xBF1B, dx=incoming)
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['opponent burst events/status %d'%i]
        compare('opponent burst %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        bursts += any(k == 1 for k, a in calls)
    m.ds_write(0, saved)
    actor = m.rw(m.DATA_SEG, 0x03A0)
    m.ds_write(actor+14, bytes([2]))
    g, mem, planes = make_game(m)
    before = (mem.raw, planes.raw)
    if ctx.lib.opponent_fire_on_foot(ctypes.byref(g), 0, 0, 3, 65535) != -1 or before != (mem.raw, planes.raw):
        return ['vehicle rejection must be atomic']
    CASES += 1
    print('    on-foot opponent fire: hits=%d retained-armor/no-hit=%d burst firing=%d'%(hits, absorbed, bursts))
    if not all([hits, absorbed, bursts]):
        return ['missing opponent firing paths']
    return fails
