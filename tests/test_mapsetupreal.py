"""Complete local/area map initialization using actual recorded resource/platform effects."""
import ctypes
import gzip
import os
import pickle
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import Game, make_game
import capture

CASES = 0
RESOURCE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint16,
                             ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p)
class Resources(ctypes.Structure):
    _fields_ = [('call', RESOURCE), ('user', ctypes.c_void_p)]


def run(ctx):
    global CASES
    fails = []
    for name, symbol in [('mapsetup', 'map_setup_local'), ('mapbegin', 'map_begin_local'),
                         ('mapsetup_area0', 'map_setup_area'), ('mapsetup_area1', 'map_setup_area'),
                         ('mapbegin_area0', 'map_begin_area'), ('mapbegin_area1', 'map_begin_area')]:
        trace = pickle.load(gzip.open(os.path.join(capture.CAPDIR, name + '_realtrace.pkl.gz'), 'rb'))
        m = capture.restore(trace['state'])
        g, mem, planes = make_game(m)
        calls = trace['calls']
        index = [0]
        stack = trace['stack']
        def matches(actual, want, label):
            excluded = [(stack, stack + 1024)]
            # Only after the native overlay decoder has run: exclude its adaptive
            # tables/bit-reader state. The history ring and all other state remain checked.
            if '_area1' in name and index[0] == len(calls):
                scratch = ((m.DATA_SEG - 0x5C27 + 0x5819) << 4)
                excluded += [(scratch + 4, scratch + 0x113A), (scratch + 0x233A, scratch + 0x233B)]
            regions = []
            last = 0
            for lo, hi in sorted(excluded):
                regions.append((last, lo))
                last = hi
            regions.append((last, 0xA0000))
            for lo, hi in regions:
                if actual[lo:hi] != want[lo:hi]:
                    first = next(i for i in range(lo, hi) if actual[i] != want[i])
                    fails.append(f'{name} {label}: first memory difference at {first:05X}')
                    return False
            return True
        def screen(pair):
            card, bits = pair
            return b''.join(bits) + card
        @RESOURCE
        def replay(gp, service, a, b, user):
            if index[0] >= len(calls):
                fails.append(f'{name}: unexpected service {service:04X}')
                return -1
            entry = calls[index[0]]
            index[0] += 1
            if (service, a, b) != (entry['service'], entry['argument'], entry['argument2']):
                fails.append(f'{name}: resource arguments differ')
                return -1
            if not matches(mem.raw, entry['before'], f'before {service:04X}'):
                return -1
            if planes.raw != screen(entry['screen_before']):
                fails.append(f'{name}: EGA differs before {service:04X}')
                return -1
            ctypes.memmove(g.mem, entry['after'], len(entry['after']))
            data = screen(entry['screen_after'])
            ctypes.memmove(g.planes, data, len(data))
            return 0
        host = Resources(replay, None)
        status = getattr(ctx.lib, symbol)(ctypes.byref(g), ctypes.byref(host))
        CASES += 1
        if status or index[0] != len(calls):
            fails.append(f'{name}: status {status}, calls {index[0]}')
        matches(mem.raw, trace['after'], 'final')
        CASES += 1
        if planes.raw != screen(trace['screen_after']):
            fails.append(f'{name}: final EGA differs')
        print(f'    {name}: {len(calls)} original resource calls, complete initialization state compared')
    return fails