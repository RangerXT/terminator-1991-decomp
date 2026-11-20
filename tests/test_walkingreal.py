"""Actual 30A0 updates in the original gameplay loop with scripted movement keys.
Regenerate: capture.py 0000:30A0 walking_live --count 48 --skip 3 --ticks 160
 --keys '2:up:12,16:right:10,28:alt:10,28:right:10,42:down:10,54:rshift:14,54:up:14,74:left:10'
"""
import ctypes, gzip, os, pickle, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
from test_drawlist import make_game, compare
CASES = 0


def run(ctx):
    global CASES
    caps = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'walking_live.pkl.gz'), 'rb'))
    fails = []
    modes = set()
    frames = {st['trace_frame'] for st in caps}
    moved = 0
    if len(caps) != 48 or len(frames) < 24:
        return ['walking captures did not advance']
    for i, st in enumerate(caps):
        before = capture.restore(st)
        after = capture.restore(st)
        p = before.rw(before.DATA_SEG, 0x03A0)
        for mode, off in [('forward', 0x5C21), ('backward', 0x5C29), ('left', 0x5C24), ('right', 0x5C26), ('strafe modifier', 0x5C11), ('run modifier', 0x5C0F)]:
            if before.ds_read(off, 1)[0]:
                modes.add(mode)
        g, mem, planes = make_game(before)
        ctx.lib.walking_step(ctypes.byref(g))
        capture.run_to_return(after, max_instr=2_000_000)
        CASES += 1
        compare('actual walking %d'%i, mem, planes, after, fails)
        if fails:
            return fails
        moved += before.ds_read(p+34, 12) != after.ds_read(p+34, 12)
    print('    actual walking: distinct frames=%d moved=%d inputs=%s'%(len(frames), moved, sorted(modes)))
    if not moved or len(modes) < 5:
        return ['walking movement/input branches missing']
    return fails
