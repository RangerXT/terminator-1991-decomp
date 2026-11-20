"""Actual BC68 entries from an automated, prepared nearby gameplay encounter."""
import ctypes, gzip, os, pickle, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture, dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import c_events, set_clock
CASES = 0

def run(ctx):
    global CASES
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'opponentfire_live.pkl.gz'), 'rb'))
    fails = []
    slots = set()
    hit = 0
    if len(caps) != 12:
        return ['expected twelve encounter firing entries']
    for i, st in enumerate(caps):
        before = capture.restore(st)
        after = capture.restore(st)
        slots.add(before.rw(before.DATA_SEG, 0xB64C))
        calls = []
        for kind, o, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
            addr = (dosemu.LOAD_SEG<<4)+o
            def hook(uc, a, size, user, kind=kind, reg=reg):
                calls.append((kind, uc.reg_read(reg)&255))
            after.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
        g, mem, planes = make_game(before)
        set_clock(ctx.lib, before)
        c_events(ctx.lib)
        status = ctx.lib.opponent_fire_on_foot(ctypes.byref(g), before.r(dosemu.UC_X86_REG_AX), before.r(dosemu.UC_X86_REG_BX), before.r(dosemu.UC_X86_REG_CX), before.r(dosemu.UC_X86_REG_DX))
        capture.run_to_return(after)
        CASES += 1
        if status or c_events(ctx.lib) != calls:
            return ['encounter shot events/status %d'%i]
        compare('actual encounter opponent shot %d'%i, mem, planes, after, fails)
        if fails:
            return fails
        hit += any(kind == 5 for kind, arg in calls)
    if len(slots) < 2 or not hit:
        return ['missing distinct actual shots/hits']
    print('    encounter shots: %d distinct ring positions, %d player-hit calls'%(len(slots), hit))
    return fails
