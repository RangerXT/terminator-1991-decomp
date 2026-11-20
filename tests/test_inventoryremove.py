"""5546 inventory removal, compaction and category counters against DOS."""
import ctypes, os, random, struct
import dosemu
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(5546)
    for i in range(384):
        m.ds_write(0, saved)
        count = i%24
        for j in range(count):
            m.ds_write(0x5B0+j*6, struct.pack('<H4B', 0x8700+j, j+1, rng.randrange(256), 1+j%6, [0, 1, 2, 255][(i+j)%4]))
        m.ds_write(0x5B0+count*6, bytes([0, 0, 0, 77, 0, 66]))
        m.ds_write(0x03A2, struct.pack('<H', 0x5B0+count*6))
        item = [1, count, max(1, count//2), 250][(i//24)%4]
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.inventory_remove(ds, item)
        m.call(0, 0x5546, ax=item, es=m.DATA_SEG)
        CASES += 1
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['inventory removal %d'%i]
    return []
