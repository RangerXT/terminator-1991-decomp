"""Real CSF/CAF loader/indexer vs B187/B199/B1AD/AE13/70DF, including every DOS boundary."""
import ctypes, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_imageload import Files, trace_dos, check_memory
CASES = 0


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    fails = []
    trace_dos(m)
    stack = m.r(dosemu.UC_X86_REG_SS)<<4
    spans = [(0, stack), (stack+1024, 0xA0000)]
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def verify(label, mem, planes, files):
        if len(files.calls) != len(m.image_calls):
            return ['resource DOS count '+label]
        for a, b in zip(files.calls, m.image_calls):
            if a[0] != b[0]:
                return ['resource DOS arguments '+label]
            error = check_memory(a[1], b[1], spans)
            if error:
                return ['resource DOS memory '+label+': '+error]
        if files.handles:
            return ['resource handle leak '+label]
        compare(label, mem, planes, m, fails)
        return fails
    for i in range(12):
        m.ds_write(0, saved)
        kind = i%3
        g, mem, planes = make_game(m)
        files = Files(m)
        m.image_calls.clear()
        status = ctx.lib.character_models_load(ctypes.byref(g), ctypes.byref(files.host), kind)
        m.call(0, [0xB187, 0xB199, 0xB1AD][kind])
        CASES += 1
        if status:
            return ['CSF loader unavailable']
        problems = verify('CSF family %d/%d'%(kind, i), mem, planes, files)
        if problems:
            return problems
    for i in range(8):
        m.ds_write(0, saved)
        word(0x11CD, [0, 1, 256, 65535][i%4])
        word(0x7A84, [0, 100, 65535][i%3])
        g, mem, planes = make_game(m)
        files = Files(m)
        m.image_calls.clear()
        status = ctx.lib.character_resources_load(ctypes.byref(g), ctypes.byref(files.host))
        m.call(0, 0x70DF, max_instr=20_000_000)
        CASES += 1
        if status:
            return ['full character resource loader unavailable']
        problems = verify('CSF/CAF resource chain %d'%i, mem, planes, files)
        if problems:
            return problems
    return fails
