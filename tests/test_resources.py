"""Whole map/HUD passes with native resource loading and actual asset bytes.

Only BIOS/palette/page services are replayed. Resource-service outputs and scanner
effects are never copied from the original. LZHUF private scratch is excluded; its
history ring, conventional memory outside stack, and complete EGA state are checked.
"""
import ctypes
import gzip
import os
import pickle
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game
from test_hudcompose import HudCall, HudServices
from test_mapsetupreal import RESOURCE, Resources
from test_imageload import Files, regions, check_memory
from test_blast import c_events
import capture

CASES = 0
NATIVE = {0x6962, 0xFAAF, 0xFACE}


def screen(pair):
    card, bits = pair
    return b''.join(bits) + card


def apply_delta(pointer, before, after, spans):
    # Before was already checked. Copy only platform changes; retain native state
    # in untouched chunks, including the private decoder workspace.
    for lo, hi in spans:
        for start in range(lo, hi, 256):
            end = min(hi, start + 256)
            if before[start:end] != after[start:end]:
                ctypes.memmove(pointer + start, after[start:end], end - start)


def execute(ctx, name, symbol, hud):
    trace = pickle.load(gzip.open(os.path.join(capture.CAPDIR, name + '_realtrace.pkl.gz'), 'rb'))
    m = capture.restore(trace['state'])
    g, mem, planes = make_game(m)
    files = Files(m, record=False)
    files_ptr = ctypes.cast(ctypes.byref(files.host), ctypes.c_void_p)
    calls = [c for c in trace['calls'] if c['service'] not in [0x89A2, 0xA07B]]
    sounds = [(1, c['argument'] & 255) for c in trace['calls'] if c['service'] == 0x89A2]
    index, native_count, platform_count = [0], [0], [0]
    spans = regions(m)
    fails = []

    def same(want, want_screen, label):
        error = check_memory(mem.raw, want, spans)
        if error:
            fails.append(f'{name} {label}: {error}')
        if planes.raw != want_screen:
            fails.append(f'{name} {label}: EGA differs')
        return not fails

    def service(gp, op, a, b):
        if index[0] >= len(calls):
            fails.append(f'{name}: unexpected service {op:04X}')
            return -1
        entry = calls[index[0]]
        index[0] += 1
        if (op, a, b) != (entry['service'], entry['argument'], entry['argument2']):
            fails.append(f'{name}: service arguments differ')
            return -1
        if not same(entry['before'], screen(entry['screen_before']), f'before {op:04X}'):
            return -1
        if op in NATIVE:
            native_count[0] += 1
            if hud:
                result = ctx.lib.image_hud_service(gp, op, a, files_ptr)
                if result == 0xFFFFFFFF:
                    return -1
            else:
                result = ctx.lib.image_map_service(gp, op, a, b, files_ptr)
                if result:
                    return -1
            if not same(entry['after'], screen(entry['screen_after']), f'after native {op:04X}'):
                return -1
        else:
            platform_count[0] += 1
            apply_delta(g.mem, entry['before'], entry['after'], spans)
            apply_delta(g.planes, screen(entry['screen_before']), screen(entry['screen_after']),
                        [(0, len(planes.raw))])
        return 0

    @HudCall
    def hud_call(gp, op, a, user):
        return 0xFFFFFFFF if service(gp, op, a, 0) else 0
    @RESOURCE
    def map_call(gp, op, a, b, user):
        return service(gp, op, a, b)
    host = HudServices(hud_call, None) if hud else Resources(map_call, None)
    c_events(ctx.lib)
    result = getattr(ctx.lib, symbol)(ctypes.byref(g), ctypes.byref(host))
    if result or index[0] != len(calls):
        fails.append(f'{name}: status/service count differs')
    if c_events(ctx.lib) != sounds:
        fails.append(f'{name}: sound requests differ')
    if files.handles:
        fails.append(f'{name}: file handles left open')
    same(trace['after'], screen(trace['screen_after']), 'final')
    return fails, (m, g, mem, planes, trace), (native_count[0], platform_count[0])


def run(ctx):
    global CASES
    ctx.lib.image_hud_service.restype = ctypes.c_uint32
    ctx.lib.image_map_service.restype = ctypes.c_int
    ctx.lib.image_hud_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    ctx.lib.image_map_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    fails = []
    jobs = [('mapsetup', 'map_setup_local', False), ('mapbegin', 'map_begin_local', False)]
    jobs += [(f'{base}{i}', symbol, False) for base, symbol in
             [('mapsetup_area', 'map_setup_area'), ('mapbegin_area', 'map_begin_area')] for i in range(2)]
    jobs += [(f'systemhud{i}', 'hud_draw_system', True) for i in range(4)]
    jobs += [(f'hudoptics{i}', 'hud_draw_optics', True) for i in range(2)]
    for name, symbol, hud in jobs:
        errors, state, counts = execute(ctx, name, symbol, hud)
        CASES += 2
        fails += errors
        print(f'    {name}: {counts[0]} native resource services, {counts[1]} platform services replayed')
        if fails:
            return fails
    return fails
