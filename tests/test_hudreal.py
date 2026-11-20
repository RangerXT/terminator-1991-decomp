"""Complete system HUD with actual bitmap IO replay and native target-query execution."""
import ctypes
import gzip
import os
import pickle
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game
from test_hudcompose import HudCall, HudServices
from test_blast import c_events
import capture

CASES = 0


def run(ctx):
    global CASES
    fails = []
    jobs = [(f'systemhud{i}', 'hud_draw_system') for i in range(4)]
    jobs += [(f'hudoptics{i}', 'hud_draw_optics') for i in range(2)]
    for name, symbol in jobs:
        trace = pickle.load(gzip.open(os.path.join(capture.CAPDIR, name + '_realtrace.pkl.gz'), 'rb'))
        m = capture.restore(trace['state'])
        g, mem, planes = make_game(m)
        calls = [c for c in trace['calls'] if c['service'] not in [0x89A2, 0xA07B]]
        sounds = [(1, c['argument'] & 255) for c in trace['calls'] if c['service'] == 0x89A2]
        index = [0]
        stack = trace['stack']
        def matches(actual, want, label):
            for lo, hi in [(0, stack), (stack + 1024, 0xA0000)]:
                if actual[lo:hi] != want[lo:hi]:
                    first = next(j for j in range(lo, hi) if actual[j] != want[j])
                    fails.append(f'{name} {label}: first memory difference {first:05X}')
                    return False
            return True
        def screen(pair):
            card, bits = pair
            return b''.join(bits) + card
        @HudCall
        def replay(gp, service, arg, user):
            if index[0] >= len(calls):
                fails.append(f'{name}: unexpected service {service:04X}')
                return 0xFFFFFFFF
            entry = calls[index[0]]
            index[0] += 1
            if (service, arg) != (entry['service'], entry['argument']):
                fails.append(f'{name}: service arguments differ')
                return 0xFFFFFFFF
            if not matches(mem.raw, entry['before'], f'before {service:04X}'):
                return 0xFFFFFFFF
            if planes.raw != screen(entry['screen_before']):
                fails.append(f'{name}: EGA differs before {service:04X}')
                return 0xFFFFFFFF
            ctypes.memmove(g.mem, entry['after'], len(entry['after']))
            state = screen(entry['screen_after'])
            ctypes.memmove(g.planes, state, len(state))
            return 0
        host = HudServices(replay, None)
        c_events(ctx.lib)
        status = getattr(ctx.lib, symbol)(ctypes.byref(g), ctypes.byref(host))
        CASES += 1
        if status or index[0] != len(calls):
            fails.append(f'{name}: status/call count differs')
        if c_events(ctx.lib) != sounds:
            fails.append(f'{name}: sound requests differ')
        matches(mem.raw, trace['after'], 'final')
        CASES += 1
        if planes.raw != screen(trace['screen_after']):
            fails.append(f'{name}: final EGA differs')
        print(f'    {name}: {len(calls)} actual IO calls replayed, scan native; {len(sounds)} sound requests')
    return fails
