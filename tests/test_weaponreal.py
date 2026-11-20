"""24 actual complete weapon-frame entries from a prepared armed gameplay fixture."""
import ctypes
import gzip
import os
import pickle
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture, dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare
from test_blast import GameEvent, set_clock
CASES = 0

def run(ctx):
    global CASES
    fails = []
    fired = 0
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'weaponframes_prepared.pkl.gz'), 'rb'))
    for i, st in enumerate(caps):
        before = capture.restore(st)
        after = capture.restore(st)
        calls = []
        def sound(uc, address, size, user):
            calls.append((1, after.r(dosemu.UC_X86_REG_AX)&255, after.ds_read(0x80E9, 1)[0]))
        addr = (dosemu.LOAD_SEG<<4)+0x89A2
        after.uc.hook_add(UC_HOOK_CODE, sound, None, addr, addr)
        g, mem, planes = make_game(before)
        set_clock(ctx.lib, before)
        buf = (GameEvent*512)()
        ctx.lib.game_events(buf, 512)
        status = ctx.lib.weapon_frame(ctypes.byref(g), before.r(dosemu.UC_X86_REG_DX))
        capture.run_to_return(after, max_instr=50000000)
        n = ctx.lib.game_events(buf, 512)
        events = [(e.kind, e.a, e.b) for e in buf[:n]]
        CASES += 1
        if status or calls != events:
            return ['prepared weapon events/status %d'%i]
        compare('complete gameplay weapon frame %d'%i, mem, planes, after, fails)
        if fails:
            return fails
        fired += before.rw(before.DATA_SEG, 0x0378) != after.rw(after.DATA_SEG, 0x0378)
    if CASES != 24 or not fired:
        return ['missing actual firing captures']
    print('    complete gameplay weapon frames: %d matched, %d fired'%(CASES, fired))
    return fails
