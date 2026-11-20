"""All four installed shop masks: original bit hits and 83A6 file/cache reload.
Confirmation input remains idle because the pointer is outside all real rectangles.
"""
import ctypes, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare as compare_full
from test_imageload import Files, trace_dos, regions, compare, check_memory
from test_menu import Call, Platform
from test_shopconfirm import ShopServices
CASES = 0

def run(ctx):
    global CASES
    fails = []
    hits = misses = records = 0
    ctx.lib.shop_item_hit.restype = ctypes.c_uint8
    for filename in ['ARMORY.MSK', 'DRUGSTOR.MSK', 'GUNSTORE.MSK', 'SPORTSTO.MSK']:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        raw = Path(m._path(filename)).read_bytes()
        m.wb(0x9000, 0, raw)
        g, mem, planes = make_game(m)
        offset = 0
        while offset < len(raw):
            if offset+16 > len(raw):
                return ['shop mask incomplete header '+filename]
            h = struct.unpack_from('<8H', raw, offset)
            width, height, left, top = h[2:6]
            end = offset+16+h[7]
            if end > len(raw) or end <= offset:
                return ['shop mask bad record length '+filename]
            points = {(left-1, top), (left+width, top), (left, top-1), (left, top+height)}
            for u in range(9):
                for v in range(9):
                    points.add((left+u*max(0, width-1)//8, top+v*max(0, height-1)//8))
            for x, y in sorted(points):
                got = ctx.lib.shop_item_hit(ctypes.byref(g), 0x9000, offset, x&65535, y&65535)
                out = m.call(0, 0x8451, es=0x9000, di=offset, ax=x&65535, bx=y&65535)
                CASES += 1
                if got != (out['flags']&1):
                    return ['real shop mask pixel %s record%x'%(filename, offset)]
                hits += bool(got)
                misses += not got
            records += 1
            offset = end
        compare_full('real shop mask '+filename, mem, planes, m, fails)
        if fails:
            return fails
        for i in range(8):
            m = dosemu.Machine()
            m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
            mode = i%2
            cached = i//2%2
            def word(o, v):
                m.ds_write(o, struct.pack('<H', v&65535))
            if mode:
                m.w(dosemu.UC_X86_REG_AX, 19)
                m._video()
            m.ds_write(0xADCF, bytes([mode]))
            word(0x0208, 0x9000 if cached else 0)
            word(0x94E0, 0)
            word(0x94E2, 0x9000)
            word(0x9A84, len(raw))
            word(0x9A86, 0x8000)
            word(0xA612, 2 if i//4 else 0)
            word(0x009D, 0)
            word(0x009F, 0)
            m.ds_write(0x8000, filename.encode()+bytes([0]))
            if cached:
                m.wb(0x9000, 0, raw)
            trace_dos(m)
            spans = regions(m)
            files = Files(m)
            g, mem, planes = make_game(m)
            screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
            polls = []
            @Call
            def callback(gp, op, a, b, user):
                polls.append((op, a, b))
                return -1
            menu = Platform(callback, None)
            host = ShopServices(ctypes.pointer(files.host), ctypes.pointer(menu), None, ctypes.addressof(screen))
            status = ctx.lib.shop_confirm_item(ctypes.byref(g), 65535, 65535, ctypes.byref(host))
            m.call(0, 0x83A6, ax=65535, bx=65535, es=m.DATA_SEG, max_instr=100_000_000)
            CASES += 1
            if status or polls or (mode and screen.raw != bytes(m.vga.chunky)):
                return ['real mask confirmation status '+filename]
            if len(files.calls) != len(m.image_calls):
                return ['real mask IO count '+filename]
            for a, b in zip(files.calls, m.image_calls):
                if a[0] != b[0]:
                    return ['real mask IO args '+filename]
                error = check_memory(a[1], b[1], spans)
                if error:
                    return ['real mask IO state '+filename+': '+error]
            compare('real mask confirmation '+filename, mem, planes, m, spans, fails)
            if fails:
                return fails
            if files.handles:
                return ['real mask file handle leak']
    print('    real shop masks: records=%d hit points=%d miss points=%d; 32 file/cache entries'%(records, hits, misses))
    if not hits or not misses:
        return ['real mask point coverage missing']
    return fails
