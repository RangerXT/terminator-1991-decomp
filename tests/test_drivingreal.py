"""Actual 3269 updates after original resource-backed 02B5 vehicle preparation.
Only audio-group/hardware setup is external during preparation. Native driving
executes its real HUD/damage/position dependencies; no reference state supplied to C.
"""
import ctypes, gzip, os, pickle, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture, dosemu
from test_drawlist import make_game, compare
from test_blast import GameEvent, set_clock
CASES = 0


def run(ctx):
    global CASES
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'driving_live.pkl.gz'), 'rb'))
    fails = []
    moved = 0
    active = 0
    inputs = set()
    if len(caps) != 48 or len({st['trace_frame'] for st in caps}) < 24:
        return ['driving recordings not distinct']
    def events():
        buf = (GameEvent*512)()
        n = ctx.lib.game_events(buf, 512)
        return [(e.kind, e.a, e.b if e.kind == 1 else 0) for e in buf[:n]]
    for i, st in enumerate(caps):
        before = capture.restore(st)
        after = capture.restore(st)
        p = before.rw(before.DATA_SEG, 0x03A0)
        calls = []
        for kind, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
            at = (dosemu.LOAD_SEG<<4)+off
            def event(uc, address, size, user, kind=kind, reg=reg):
                calls.append((kind, uc.reg_read(reg)&255, after.ds_read(0x80E9, 1)[0] if kind == 1 else 0))
            after.uc.hook_add(UC_HOOK_CODE, event, None, at, at)
        for mode, off in [('engine', 0x5BF8), ('forward', 0x5C21), ('backward', 0x5C29), ('left', 0x5C24), ('right', 0x5C26), ('brake', 0x5BF4)]:
            if before.ds_read(off, 1)[0]:
                inputs.add(mode)
        g, mem, planes = make_game(before)
        events()
        set_clock(ctx.lib, before)
        status = ctx.lib.driving_step(ctypes.byref(g), None)
        capture.run_to_return(after, max_instr=2_000_000)
        CASES += 1
        if status or events() != calls:
            return ['real driving status/events %d'%i]
        compare('actual driving %d'%i, mem, planes, after, fails)
        if fails:
            return fails
        moved += before.ds_read(p+34, 12) != after.ds_read(p+34, 12)
        active += bool(before.ds_read(0x114C, 1)[0])
    print('    actual driving: moved=%d engine active=%d inputs=%s'%(moved, active, sorted(inputs)))
    if not moved or not active or len(inputs) < 3:
        return ['missing live driving branches']
    return fails
