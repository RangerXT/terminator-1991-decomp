"""AI and companion calls recorded at distinct original gameplay frames.
Actors/proximity and attack probabilities were prepared; calls are selected by the
original loop. Native dependencies execute C; only sound/border bodies are external.
"""
import ctypes, gzip, os, pickle, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture, dosemu
from test_drawlist import make_game, compare
from test_blast import c_events, set_clock
CASES = 0


def run(ctx):
    global CASES
    fails = []
    damaged = 0
    for kind, name, count in [('controller', 'opponent_controller_on_foot', 16), ('slowcontroller', 'opponent_controller_slow_on_foot', 16), ('companion', 'companion_step', 16), ('companionai', 'companion_ai_on_foot', 16), ('world', 'world_step_on_foot', 24), ('worldslow', 'world_step_on_foot', 24), ('companionfire', 'opponent_fire_at_companion', 12)]:
        caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'ai_'+kind+'_live.pkl.gz'), 'rb'))
        if len(caps) != count or len({st['trace_frame'] for st in caps}) != count:
            return ['expected distinct gameplay frames for '+kind]
        instructions = [st['state']['instr'] for st in caps]
        if any(b <= a for a, b in zip(instructions, instructions[1:])):
            return ['recording execution did not advance']
        for i, st in enumerate(caps):
            before = capture.restore(st)
            after = capture.restore(st)
            calls = []
            for k, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
                addr = (dosemu.LOAD_SEG<<4)+off
                def hook(uc, a, size, user, k=k, reg=reg):
                    calls.append((k, uc.reg_read(reg)&255))
                after.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
            g, mem, planes = make_game(before)
            set_clock(ctx.lib, before)
            c_events(ctx.lib)
            status = getattr(ctx.lib, name)(ctypes.byref(g), None) if kind in ['slowcontroller', 'world', 'worldslow'] else getattr(ctx.lib, name)(ctypes.byref(g))
            capture.run_to_return(after, max_instr=2_000_000)
            CASES += 1
            if kind != 'companionfire' and status:
                return ['real AI unavailable '+kind]
            if c_events(ctx.lib) != calls:
                return ['real AI events '+kind]
            compare('actual AI %s %d'%(kind, i), mem, planes, after, fails)
            if fails:
                return fails
            if kind == 'companionfire':
                damaged += before.ds_read(0x0556, 2) != after.ds_read(0x0556, 2)
        print('    actual %s: %d calls from %d distinct game frames'%(kind, count, count))
    if not damaged:
        return ['live companion attack damage not exercised']
    print('    actual companion attacks with damage:', damaged)
    return fails
