"""14B5:018A large reads including FFFF+1 boundaries and nonzero initial offsets."""
import ctypes, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare, STACK_BYTES
from test_imageload import Files, trace_dos, check_memory
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    fails = []
    reads = 0
    fixture = root/'out/verification/large_read_fixture.bin'
    items = [(p, None) for p in sorted((root/'data/vga').glob('*.DFF'))]+[(fixture, n) for n in [0, 65535, 65536, 131070, 131072]]
    for path, size in items:
        if size is not None:
            fixture.write_bytes(bytes((i*37+i//256)&255 for i in range(size)))
        for offset in [0, 1, 0x100]:
            m = dosemu.Machine();m.load(root/'out/emu/states/ingame.pkl');m._path = lambda name:str(path)
            m.ds_write(0x8200, path.name.encode('ascii')+bytes([0]))
            m.wb(0x2000, 0, bytes([0xCC])*0x30000)
            trace_dos(m)
            files = Files(m)
            g, mem, planes = make_game(m)
            status = ctx.lib.movie_load_large(ctypes.byref(g), ctypes.byref(files.host), 0x8200, 0x2000, offset)
            m.call(0x14B5, 0x018A, dx=0x8200, es=0x2000, bx=offset, max_instr=100_000_000)
            CASES += 1
            if status or len(files.calls) != len(m.image_calls):
                return ['large movie status/count '+path.name]
            stack = m.r(dosemu.UC_X86_REG_SS)<<4
            spans = [(0, stack), (stack+STACK_BYTES, 0xA0000)]
            for a, b in zip(files.calls, m.image_calls):
                if a[0] != b[0]:
                    return ['large movie IO args '+path.name]
                error = check_memory(a[1], b[1], spans)
                if error or a[2] != b[2]:
                    return ['large movie IO state '+path.name+' '+str(error)]
                reads += a[0][0] == 0x3F
            compare('large movie %s/%d'%(path.name, offset), mem, planes, m, fails)
            if fails:
                return fails
            if files.handles:
                return ['large movie handle leak']
    print('    large movie files: comparisons=%d reads=%d'%(CASES, reads))
    return fails
