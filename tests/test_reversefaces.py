"""157C whole-mesh cut-out winding reversal, including point/line faces."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
CASES = 0

def run(ctx):
    global CASES
    m = ctx.game()
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x157C)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    for i in range(256):
        m.ds_write(0, saved)
        count = 1+i%32
        word(0x8002, count)
        word(0x8006, 0x8100)
        word(0x40E0, 0x8A00)
        m.ds_write(0x8A00, bytes([255])*64)
        at = 0x8100
        for j in range(count):
            n = 1+(i+j)%8
            m.ds_write(at, struct.pack('<BBHH', rng.randrange(136), rng.randrange(16), 1, n)+struct.pack('<'+'H'*n, *(rng.randrange(30)*6 for _ in range(n))))
            at += 6+n*2
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.mesh_reverse_all_faces(ds, 0x8000)
        m.call(0x11BC, 0x157C, far=True, bx=0x8000)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['whole-mesh winding reversal %d'%i]
    return []
