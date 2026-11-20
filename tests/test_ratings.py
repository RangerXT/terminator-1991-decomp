"""Ratings codecs/records vs original. All file write/create bodies are bypassed;
no installed game files are written. The original byte-transform instructions execute.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
CASES = 0


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xD628)
    read_count = [0]
    inserted = 0
    # D628's read service is a pure test stub. D615's write/close bodies return.
    for off in [0xFAAF, 0xF84D, 0xF770]:m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
    def read(uc, address, size, user):
        m.w(dosemu.UC_X86_REG_AX, read_count[0])
    at = (dosemu.LOAD_SEG<<4)+0xFAAF
    m.uc.hook_add(UC_HOOK_CODE, read, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def check(ds, label):
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return [label]
        return []
    for i in range(512):
        m.ds_write(0, saved)
        count = i if i < 256 else 207
        blob = bytes(rng.randrange(256) for _ in range(512))
        m.ds_write(0x50B2, blob)
        read_count[0] = count
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.ratings_decode(ctypes.byref(ds, 0x50B2), count)
        m.call(0, 0xD628)
        CASES += 1
        error = check(ds, 'ratings decode %d'%i)
        if error:
            return error
        m.ds_write(0, saved)
        m.ds_write(0x50B2, blob)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.ratings_encode(ctypes.byref(ds, 0x50B2))
        m.call(0, 0xD615, cx=207, si=0x50B2)
        CASES += 1
        error = check(ds, 'ratings encode %d'%i)
        if error:
            return error
    for i in range(1024):
        m.ds_write(0, saved)
        count = i%5+1
        word(0x50B2, count)
        m.ds_write(0x0376, bytes(rng.randrange(256) for _ in range(41)))
        m.ds_write(0x50B4, bytes(rng.randrange(256) for _ in range(205)))
        word(0x0376, [-32768, -1000, 0, 1000, 32767][i%5])
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.ratings_insert(ds)
        m.call(0, 0xD67F, es=m.DATA_SEG)
        CASES += 1
        error = check(ds, 'ratings insertion %d'%i)
        if error:
            return error
        inserted += m.rw(m.DATA_SEG, 0x11A8) != 65535
    for i in range(64):                         # counts outside 1..5: as the original's LOOP
        m.ds_write(0, saved)
        word(0x50B2, [0, 6, 7, 0x105][i % 4])
        m.ds_write(0x0376, bytes(rng.randrange(256) for _ in range(41)))
        m.ds_write(0x50B4, bytes(rng.randrange(256) for _ in range(205)))
        word(0x0376, [32767, -32768][(i // 4) % 2])
        word(0x50B4, rng.randrange(-32768, 32767) & 0xFFFF)
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        ctx.lib.ratings_insert(ds)
        m.call(0, 0xD67F, es=m.DATA_SEG, max_instr=50_000_000)
        CASES += 1
        error = check(ds, 'ratings insertion, count %X, %d' % ([0, 6, 7, 0x105][i % 4], i))
        if error:
            return error
    for i in range(128):
        for name, entry in [('ratings_stats_save', 0xD64C), ('ratings_stats_restore', 0xD658), ('ratings_select', 0xD66C), ('ratings_update_time', 0xD739), ('ratings_clear_stats', 0xD740)]:
            m.ds_write(0, saved)
            m.ds_write(0x0376, bytes(rng.randrange(256) for _ in range(41)))
            m.ds_write(0xE39C, bytes(rng.randrange(256) for _ in range(41)))
            word(0xE34C, i)
            word(0x1174, i*37)
            ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
            if name == 'ratings_select':
                ctx.lib.ratings_select(ds, i%5)
            else:
                getattr(ctx.lib, name)(ds)
            m.call(0, entry, ax=i%5, es=m.DATA_SEG)
            CASES += 1
            error = check(ds, '%s %d'%(name, i))
            if error:
                return error
    print('    rating records inserted:', inserted)
    return []
