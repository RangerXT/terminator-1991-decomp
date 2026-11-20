"""Regular shop items/refunds plus native pay/permit/capacity windows vs DOS.
UI cases use source's explicit nonmodal gate; interactive dismissal is separate.
Capacity stack-unwind ADD SP,4 is NOPed only to isolate its structured failure return.
"""
import ctypes, os, random, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x855A)
    fails = []
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    stacked = appended = 0
    ids = [0x10, 0xA5, 15, 1, 2, 3, 4, 7, 8, 10, 11, 12, 30, 31, 35+1]
    for i in range(768):
        m.ds_write(0, saved)
        definition = 0x8300
        counter = 0x1138+i%6
        id = ids[i%len(ids)]
        count = i%12
        m.ds_write(0x05B0, bytes(144))
        word(0x03A2, 0x05B0+count*6)
        word(0x9A6E, 0x8400)
        word(0x9A70, i%4*2)
        word(0x8400+i%4*2, 0x8500)
        m.ds_write(0x8500, b'PURCHASE'+bytes([0]))
        m.ds_write(definition, bytes([id, i%128, 1+i%5, i%255]))
        word(0x03A0, 0x04D4 if i%2 else 0x0508)
        word(0x04C8, [0, 0xA5, 100, 65535][i%4])
        word(0x04CA, rng.randrange(65536))
        word(0x117E, rng.randrange(65536))
        m.ds_write(0x7A18, bytes([i%256]))
        m.ds_write(0xAAA6, bytes([1]))
        for j in range(count):
            m.ds_write(0x05B0+j*6, struct.pack('<H4B', 0x8510+j*8, id if j == i%max(count, 1) else 100+j, 1, 1+j%5, [0, 1, 2, 255][i%4]))
        g, mem, planes = make_game(m)
        got = ctx.lib.shop_add_regular_item(ctypes.byref(g), definition, counter)
        out = m.call(0, 0x855A, si=definition, di=counter, es=m.DATA_SEG, max_instr=20_000_000)
        CASES += 1
        if got != (out['flags']&1):
            return ['shop regular item carry %d'%i]
        compare('shop regular item %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        stacked += bool(got)
        appended += not got
    declined = accepted = 0
    for i in range(192):
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        mode = i%2
        kind = i//2%3
        definition = 0x8300
        if mode:
            m.w(dosemu.UC_X86_REG_AX, 0x13)
            m._video()
        m.ds_write(0xADCF, bytes([mode]))
        m.ds_write(0x5A4E, bytes([255]))
        word(0x1234, 0)
        m.ds_write(0xC4AB, bytes([0]))
        word(0xC4C4, 0xC4C6)
        word(0xC546, 0)
        m.call(0, 0x5032, si=0x0E7A, ax=12, bx=8, cx=22, dx=10, es=m.DATA_SEG, max_instr=100_000_000)
        word(0x9A6E, [0x9AB8, 0x9BE2, 0x8400][i//6%3])
        word(0x9A88, 0x8400)
        word(0x9A70, 0)
        word(0x8400, definition)
        m.ds_write(definition, bytes([0xA8 if i//18%2 else 15, [0, 1, 127, 128, 255][i//36%5], i//6%7, [0, 1, 2, 254, 255][i//6%5]]))
        m.ds_write(0xAAA4, bytes([i//12%2]))
        word(0x117E, [0, 4, 5, 8, 1000, 65535][i//6%6])
        word(0x116C, 500)
        word(0x03F2, [499, 500, 501, 600, 65535][i//6%5])
        for j in range(6):
            word(0x9A4E+j*2, 0x1138+j)
            m.ds_write(0x1138+j, bytes([[0, 19, 20][i//6%3]]))
        # Preserve nonmodal gate in both video modes, then compare complete window side effects.
        m.wb(dosemu.LOAD_SEG, 0x8738, bytes([0x90])*3)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        item = ctypes.c_uint16()
        counter = ctypes.c_uint16()
        if kind == 0:
            got = ctx.lib.shop_pay_item(ctypes.byref(g), definition, None, screen)
            entry = 0x868C
        elif kind == 1:
            got = ctx.lib.shop_check_permit(ctypes.byref(g), definition, None, screen)
            entry = 0x865C
        else:
            got = ctx.lib.shop_check_capacity(ctypes.byref(g), ctypes.byref(item), ctypes.byref(counter), None, screen)
            entry = 0x86EA
        out = m.call(0, entry, si=definition, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if got != (out['flags']&1):
            return ['shop gate status %d kind%d'%(i, kind)]
        if kind == 2 and not got and (item.value != out['si'] or counter.value != out['di']):
            return ['capacity item/counter %d'%i]
        if mode and screen.raw != bytes(m.vga.chunky):
            return ['shop gate VGA pixels %d'%i]
        compare('shop gate %d'%i, mem, planes, m, fails)
        if fails:
            return fails
        declined += bool(got)
        accepted += not got
    print('    shop actions: stacked=%d appended=%d accepted gates=%d declined gates=%d'%(stacked, appended, accepted, declined))
    if not all([stacked, appended, accepted, declined]):
        return ['shop action coverage missing']
    return fails
