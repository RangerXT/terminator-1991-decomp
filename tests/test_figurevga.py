"""Map sampler/spawn in indexed VGA: same byte per read plane, no EGA latching."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_blast import set_clock
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    m.w(dosemu.UC_X86_REG_AX, 19)
    m._video()
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x5CFA)
    fails = []
    colours = set()
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def setup(i):
        m.ds_write(0, saved)
        m.ds_write(0xADCF, bytes([1]))
        word(0xADDC, 0xA000)
        pattern = bytes((j*37+i)&255 for j in range(65536))
        m.vga.chunky[:] = pattern
        m.vga.latch = [(i+j*47)&255 for j in range(4)]
        return pattern
    ctx.lib.figure_map_sample_display.restype = ctypes.c_uint16
    for i in range(256):
        pattern = setup(i)
        x = rng.randrange(-4096, 4096)
        z = rng.randrange(-4096, 4096)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        got = ctx.lib.figure_map_sample_display(ctypes.byref(g), x, z, screen)
        out = m.call(0, 0x5CFA, ax=x, bx=z, es=m.DATA_SEG)
        CASES += 1
        colours.add(got&255)
        if got != out['ax'] or screen.raw != bytes(m.vga.chunky):
            return ['VGA figure map sample AX/pixels %d'%i]
        compare('VGA figure map sample %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    seg = m.rw(m.DATA_SEG, 0x91B2)
    spawned = deferred = 0
    for i in range(96):
        pattern = setup(i)
        p = 0x04D4 if i%2 else 0x0508
        word(0x03A0, p)
        phase = (((m.rw(m.DATA_SEG, p)+8)>>4)+64+3)%9
        m.wb(seg, 0, bytes(1 if (j%192)%9 == phase else 0 for j in range(0x9000)) if i%3 else bytes(0x9000))
        word(0x119A, 0)
        word(0x119C, 0)
        word(0x03A4, 0xDF0)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, struct.pack('<200H', *(rng.randrange(65536) for j in range(200))))
        for j in range(32):
            m.ds_write(0xB30+j*22, struct.pack('<11H', 0, 0, 0, 0, 0, 2, 0, j*7, 0x0301, 0, 0))
            m.ds_write(0xDF0+j*12, bytes(12))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(pattern, 65536)
        set_clock(ctx.lib, m)
        if i < 64:
            status = ctx.lib.figure_spawn_grid_display(ctypes.byref(g), screen)
            m.call(0, 0xA46F, es=m.DATA_SEG, max_instr=100_000_000)
        else:
            status = ctx.lib.figure_spawn_display(ctypes.byref(g), 1+i%3, 0, screen)
            m.call(0, 0xAD00, ax=1+i%3, es=m.DATA_SEG, max_instr=100_000_000)
            spawned += bool(m.rw(m.DATA_SEG, 0x119A))
            deferred += not m.rw(m.DATA_SEG, 0x119A)
        CASES += 1
        if status or screen.raw != bytes(m.vga.chunky):
            return ['VGA figure grid/spawn %d'%i]
        compare('VGA figure grid/spawn %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    print('    indexed figure samples=%s armed spawns=%d deferred=%d'%(sorted(colours), spawned, deferred))
    if colours != {0, 15} or not spawned or not deferred:
        return ['VGA figure coverage missing']
    return fails
