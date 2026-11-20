"""Shop visit history and item-mask selection against original helpers."""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = ctx.game()
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x8451)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    ctx.lib.shop_was_visited.restype = ctx.lib.shop_item_hit.restype = ctypes.c_uint8
    for i in range(512):
        m.ds_write(0, saved)
        record = 0x8000
        word(0x8546, record)
        m.ds_write(record, bytes(rng.randrange(256) for j in range(11)))
        count = [0, 1, 5, 6, 7, 20, 65535][i%7]
        word(0x1176, count)
        word(0x03A8, 0x03AA+(i%6)*11)
        for j in range(20):
            m.ds_write(0x03AA+j*11, bytes(rng.randrange(256) for k in range(11)))
        if i%2 or count == 65535:
            m.ds_write(0x03AA+(0 if count == 65535 else i%max(count, 1))*11, m.ds_read(record, 10)+bytes([i%256]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        got = ctx.lib.shop_was_visited(ds)
        out = m.call(0, 0x8962, es=m.DATA_SEG, max_instr=20_000_000)
        CASES += 1
        if got != (out['flags']&1) or ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['shop visited %d'%i]
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.shop_record_visit(ds)
        m.call(0, 0x893F, es=m.DATA_SEG)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['shop visit record %d'%i]
    hits = misses = 0
    for i in range(768):
        m.ds_write(0, saved)
        seg = 0x9000
        record = [0, 0x100, 0xFF00][i%3]
        width = [1, 8, 15, 16, 17, 32, 65535][i%7]
        height = [1, 8, 16, 255][i//7%4]
        left = [0, 20, 65530][i//28%3]
        top = [0, 40, 65530][i//84%3]
        m.wb(seg, 0, bytes([[0, 255, 128, 85, 170, 1][i%6]])*65536)
        m.wb(seg, record, struct.pack('<8H', 0, 0, width, height, left, top, 0, 0))
        x = (left+[0, 1, width-1, width, 65535][i//3%5])&65535
        y = (top+[0, 1, height-1, height, 65535][i//15%5])&65535
        g, mem, planes = make_game(m)
        got = ctx.lib.shop_item_hit(ctypes.byref(g), seg, record, x, y)
        out = m.call(0, 0x8451, es=seg, di=record, ax=x, bx=y)
        CASES += 1
        hits += bool(got)
        misses += not got
        if got != (out['flags']&1):
            return ['shop item mask %d'%i]
        compare('shop item mask %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    print('    shop mask: hits=%d misses=%d'%(hits, misses))
    if not hits or not misses:
        return ['shop mask coverage missing']
    return fails
