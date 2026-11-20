"""C travel controller using recorded effects of real original external services.

This is boundary replay, not a native rewrite of the simulation or cell loader. Every
external-call input and the complete final memory/screen state must match the recording.
"""
import ctypes
import gzip
import os
import pickle
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game
from test_travel import CALLBACK, Services
import capture

CASES = 0


def run(ctx):
    global CASES
    fails = []
    trace = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'travel_realtrace.pkl.gz'), 'rb'))
    m = capture.restore(trace['state'])
    g, mem, planes = make_game(m)
    calls = trace['calls']
    next_call = [0]
    stack = trace['stack']
    def matches_memory(actual, want, label):
        for lo, hi in [(0, stack), (stack + 1024, 0xA0000)]:
            if actual[lo:hi] != want[lo:hi]:
                first = next(i for i in range(lo, hi) if actual[i] != want[i])
                fails.append(f'{label}: first memory difference at linear {first:05X}')
                return False
        return True
    def screen(pair):
        card, bits = pair
        return b''.join(bits) + card
    @CALLBACK
    def replay(gp, service, arg, user):
        if next_call[0] >= len(calls):
            fails.append(f'unexpected service {service:04X}')
            return 0xFFFFFFFF
        entry = calls[next_call[0]]
        next_call[0] += 1
        if (service, arg) != (entry['service'], entry['argument']):
            fails.append(f'service/argument differs at call {next_call[0]}')
            return 0xFFFFFFFF
        if not matches_memory(mem.raw, entry['before'], f'before {service:04X}'):
            return 0xFFFFFFFF
        if planes.raw != screen(entry['screen_before']):
            fails.append(f'screen state differs before {service:04X}')
            return 0xFFFFFFFF
        ctypes.memmove(g.mem, entry['after'], len(entry['after']))
        data = screen(entry['screen_after'])
        ctypes.memmove(g.planes, data, len(data))
        return entry['result']
    host = Services(replay, None)
    status = ctx.lib.travel_run(ctypes.byref(g), ctypes.byref(host))
    CASES += 1
    if status or next_call[0] != len(calls):
        fails.append(f'status {status}, consumed {next_call[0]}/{len(calls)} calls')
    matches_memory(mem.raw, trace['after'], 'final')
    CASES += 1
    if planes.raw != screen(trace['screen_after']):
        fails.append('final EGA state differs')
    print(f'    real travel: {len(calls)} actual original service calls replayed with matching inputs')
    return fails