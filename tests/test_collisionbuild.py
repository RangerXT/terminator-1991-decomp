"""Native collision rebuild with real cell/BMP data and extra-object path."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    fails = []
    stamped = 0
    for i in range(48):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0x8685, bytes([0 if i == 0 else 255]))
        player = m.rw(m.DATA_SEG, 0x03A0)
        # Existing loaded cells; choose nearby 3x3 windows within their 24x24 table.
        col = m.rw(m.DATA_SEG, player+30)+(i%3)-1;row = m.rw(m.DATA_SEG, player+32)+((i//3)%3)-1
        m.ds_write(player+30, struct.pack('<HH', col, row))
        m.ds_write(0x913C, bytes([0, 0]))
        if i >= 24:
            entries = []
            for j in range(9):
                key = ((col+(j%3)-1)&255)|(((row+(j//3)-1)&255)<<8)
                entries.append(struct.pack('<7H', key, 100+j*40, 300+j*20, 0, 30, 0, j))
            m.wb(0x7800, 0, b''.join(entries))
            m.ds_write(0x1200, struct.pack('<HH', 0, 0x7800))
            m.ds_write(0x04C6, struct.pack('<H', 9))
        g, mem, planes = make_game(m)
        ctx.lib.collision_map_build(ctypes.byref(g))
        m.call(0x11BC, 0x2251, far=True, max_instr=50000000)
        CASES += 1
        compare('collision rebuild %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        stamped += m.rw(m.DATA_SEG, 0x8FEA)//12
    if not stamped:
        return ['no collision footprints stamped']
    saved = m.ds_read(0, 65536)
    n = m.rw(m.DATA_SEG, 0x8FEA)//12
    ids = sorted(set(m.rw(m.DATA_SEG, 0x8B42+12*j) for j in range(n)))
    for ident in ids:
        for i in range(16):
            m.ds_write(0, saved)
            for off, val in [(0x912E, ident), (0x9140, i%4), (0x9128, [-20, 0, 8, 96, 180, 192, 211, 250][i%8]), (0x912A, [0, 8, 96, 180, 192, 211, -20, 250][(i//2)%8])]:
                m.ds_write(off, struct.pack('<H', val&65535))
            g, mem, planes = make_game(m)
            ctx.lib.collision_stamp_setup(ctypes.byref(g))
            m.call(0x11BC, 0x2491, si=0, es=m.DATA_SEG)
            CASES += 1
            compare('footprint clip %d/%d'%(ident, i), mem, planes, m, fails)
            if fails:
                return fails
    print('    collision rebuild: %d source footprints stamped; %d real footprint shapes clipped'%(stamped, len(ids)))
    return fails
