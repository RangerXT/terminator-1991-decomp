"""Render complete C local/area-map initialization with recorded original resource effects."""
import argparse
import ctypes
import gzip
import os
import pickle
import sys
from PIL import Image, ImageChops
import capture
import difftest
import dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_drawlist import make_game
from test_mapsetupreal import RESOURCE, Resources


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--area', action='store_true')
    ap.add_argument('--overlay', action='store_true')
    args = ap.parse_args()
    area = args.area or args.overlay
    trace_name = 'mapbegin_area' + str(int(args.overlay)) if area else 'mapbegin'
    ctx = difftest.Ctx()
    trace = pickle.load(gzip.open(os.path.join(capture.CAPDIR, trace_name + '_realtrace.pkl.gz'), 'rb'))
    m = capture.restore(trace['state'])
    g, mem, planes = make_game(m)
    index = [0]
    errors = []
    stack = trace['stack']
    def same_memory(want):
        excluded = [(stack, stack + 1024)]
        if args.overlay and index[0] == len(trace['calls']):
            scratch = ((m.DATA_SEG - 0x5C27 + 0x5819) << 4)
            excluded += [(scratch + 4, scratch + 0x113A), (scratch + 0x233A, scratch + 0x233B)]
        regions = []
        last = 0
        for lo, hi in sorted(excluded):
            regions.append((last, lo))
            last = hi
        regions.append((last, 0xA0000))
        return all(mem.raw[lo:hi] == want[lo:hi] for lo, hi in regions)
    @RESOURCE
    def replay(gp, service, a, b, user):
        if index[0] >= len(trace['calls']):
            return -1
        entry = trace['calls'][index[0]]
        index[0] += 1
        if (service, a, b) != (entry['service'], entry['argument'], entry['argument2']) or not same_memory(entry['before']):
            errors.append(f'before {service:04X}')
            return -1
        ctypes.memmove(g.mem, entry['after'], len(entry['after']))
        card, bits = entry['screen_after']
        data = b''.join(bits) + card
        ctypes.memmove(g.planes, data, len(data))
        return 0
    host = Resources(replay, None)
    begin = ctx.lib.map_begin_area if area else ctx.lib.map_begin_local
    if begin(ctypes.byref(g), ctypes.byref(host)) or errors or not same_memory(trace['after']):
        raise RuntimeError(f'C initialization differs: {errors}')
    card, original_planes = trace['screen_after']
    if planes.raw != b''.join(original_planes) + card:
        raise RuntimeError('EGA state differs')
    for key, value in trace['display_after'].items():
        setattr(m.vga, key, value)
    m.vga.planes = [bytearray(p) for p in original_planes]
    w, h, data = m.vga.screenshot()
    original = Image.frombytes('RGB', (w, h), data)
    m.vga.planes = [bytearray(planes.raw[i*65536:(i+1)*65536]) for i in range(4)]
    w, h, data = m.vga.screenshot()
    rewritten = Image.frombytes('RGB', (w, h), data)
    sheet = Image.new('RGB', (w * 3, h))
    for i, picture in enumerate([original, rewritten, ImageChops.difference(original, rewritten)]):
        sheet.paste(picture, (i*w, 0))
    filename = ('area_map_overlay' if args.overlay else 'area_map_complete') if area else 'local_map_complete'
    path = os.path.abspath(os.path.join(dosemu.ROOT, 'out/emu', filename + '_c_vs_original.png'))
    scale = 1 if area else 2
    sheet.resize((w*3*scale, h*scale), Image.Resampling.NEAREST).save(path)
    print('Complete map initialization: original | C | difference, identical')
    print('Resource IO, palette and page selection supplied by original-effect replay')
    print(path)


if __name__ == '__main__':
    main()