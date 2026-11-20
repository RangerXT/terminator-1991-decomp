"""Original EGA frame sequence/repeats/retrace timing/key skip, all installed clips."""
import ctypes, hashlib, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu, termega
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare, STACK_BYTES
from test_polyfill import planes_of
from test_mapsetupreal import RESOURCE, Resources
CASES = 0

def run(ctx):
    global CASES
    fails = []
    total_waits = 0
    for path in sorted(Path(dosemu.ROOT, 'data/ega').glob('*.DCF')):
        for variant in range(5):
            m = dosemu.Machine()
            m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
            width = termega.background(path.with_suffix('.DBI'))[1]
            stride = width//8
            def word(o, v):
                m.ds_write(o, struct.pack('<H', v&65535))
            m.w(dosemu.UC_X86_REG_AX, 14 if width == 640 else 13)
            m._video()
            word(0x91BA, 0x8000)
            word(0xDE20, 0x7000)
            word(0x91C6, 0x7000)
            m.wb(0x7000, 0, bytes(65536))
            m.wb(0x8000, 0, path.with_suffix('.DBI').read_bytes())
            m.call(0, 0xB36D, max_instr=100_000_000)
            raw = path.read_bytes()
            m.wb(0x8000, 0, raw)
            m.wb(dosemu.LOAD_SEG, 0xB423, struct.pack('<H', stride-1))
            m.ds_write(0xDB61, bytes([1 if variant == 1 else 0]))
            word(0xDBB3, 1+variant%2)
            word(0x5BD4, 1 if variant == 3 else 256 if variant == 4 else 0)
            for off in [0x0D8D, 0x0DAA]:
                m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
            g, mem, planes = make_game(m)
            logs = [[], []]
            waits = [0, 0]
            stack = m.r(dosemu.UC_X86_REG_SS)<<4
            def state(raw, screen):
                h = hashlib.sha256()
                h.update(raw[:stack])
                h.update(raw[stack+STACK_BYTES:0xA0000])
                h.update(screen)
                return h.digest()
            def effect(which, op, write):
                if op == 0x0DAA:
                    waits[which] += 1
                    if variant == 2 and waits[which] == 1:
                        write(0x5BD4, struct.pack('<H', 1))
            @RESOURCE
            def callback(gp, op, a, b, user):
                logs[0].append((op, state(mem.raw, planes.raw)))
                effect(0, op, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)))
                return 0
            def hook(uc, address, size, user):
                off = m.r(dosemu.UC_X86_REG_IP)
                logs[1].append((off, state(bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m))))
                effect(1, off, m.ds_write)
            for off in [0x0D8D, 0x0DAA]:
                at = (dosemu.LOAD_SEG<<4)+off
                m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
            host = Resources(callback, None)
            status = ctx.lib.cutscene_ega_sequence(ctypes.byref(g), ctypes.byref(host))
            m.call(0, 0xB31C, max_instr=500_000_000)
            CASES += 1
            if status or logs[0] != logs[1] or waits[0] != waits[1]:
                return ['EGA sequence boundary '+path.name+'/'+str(variant)+' waits '+str(waits)]
            compare('EGA sequence %s/%d'%(path.name, variant), mem, planes, m, fails)
            if fails:
                return fails
            total_waits += waits[0]
    print('    EGA complete sequence cases=%d retrace pairs=%d'%(CASES, total_waits))
    return fails
