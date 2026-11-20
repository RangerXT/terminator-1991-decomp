"""Render complete C system HUD with actual bitmap IO replay and native target query; sound is excluded."""
import argparse
import ctypes
import gzip
import os
import pickle
import sys
from PIL import Image, ImageChops, ImageDraw
import capture
import difftest
import dosemu
sys.path.insert(0, os.path.join(dosemu.ROOT, 'tests'))
from test_drawlist import make_game
from test_hudcompose import HudCall, HudServices
from test_blast import c_events


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--optics', choices=['binos', 'scope'])
    ap.add_argument('--case', type=int, choices=range(4), default=0)
    args = ap.parse_args()
    ctx = difftest.Ctx()
    name = ('hudoptics' + str(int(args.optics == 'scope'))) if args.optics else f'systemhud{args.case}'
    trace = pickle.load(gzip.open(os.path.join(capture.CAPDIR, name + '_realtrace.pkl.gz'), 'rb'))
    m = capture.restore(trace['state'])
    g, mem, planes = make_game(m)
    calls = [c for c in trace['calls'] if c['service'] not in [0x89A2, 0xA07B]]
    index = [0]
    errors = []
    stack = trace['stack']
    def same(want):
        return mem.raw[:stack] == want[:stack] and mem.raw[stack + 1024:0xA0000] == want[stack + 1024:0xA0000]
    def screen(pair):
        card, bits = pair
        return b''.join(bits) + card
    @HudCall
    def replay(gp, service, arg, user):
        if index[0] >= len(calls):
            return 0xFFFFFFFF
        entry = calls[index[0]]
        index[0] += 1
        if (service, arg) != (entry['service'], entry['argument']) or not same(entry['before']) or planes.raw != screen(entry['screen_before']):
            errors.append(f'before {service:04X}')
            return 0xFFFFFFFF
        ctypes.memmove(g.mem, entry['after'], len(entry['after']))
        state = screen(entry['screen_after'])
        ctypes.memmove(g.planes, state, len(state))
        return 0
    host = HudServices(replay, None)
    c_events(ctx.lib)
    render = ctx.lib.hud_draw_optics if args.optics else ctx.lib.hud_draw_system
    result = render(ctypes.byref(g), ctypes.byref(host))
    expected_sounds = [(1, c['argument'] & 255) for c in trace['calls'] if c['service'] == 0x89A2]
    if result or errors or index[0] != len(calls) or not same(trace['after']) or c_events(ctx.lib) != expected_sounds:
        raise RuntimeError(f'C system HUD differs: {errors}')
    if planes.raw != screen(trace['screen_after']):
        raise RuntimeError('EGA differs')
    for key, value in trace['display_after'].items():
        setattr(m.vga, key, value)
    # The HUD is drawn on the next render page, before the game's page flip.
    page = int.from_bytes(trace['after'][(m.DATA_SEG << 4) + 0x1234:(m.DATA_SEG << 4) + 0x1236], 'little')
    m.vga.crtc[0x0C] = page >> 8
    m.vga.crtc[0x0D] = page & 255
    m.vga.planes = [bytearray(p) for p in trace['screen_after'][1]]
    w, h, data = m.vga.screenshot()
    original = Image.frombytes('RGB', (w, h), data)
    m.vga.planes = [bytearray(planes.raw[i * 65536:(i + 1) * 65536]) for i in range(4)]
    w, h, data = m.vga.screenshot()
    rewritten = Image.frombytes('RGB', (w, h), data)
    sheet = Image.new('RGB', (w * 6, h * 2 + 20), '#181818')
    for i, (picture, label) in enumerate([(original, 'Original DOS HUD'), (rewritten, 'C HUD'),
                                         (ImageChops.difference(original, rewritten), 'Difference (black = identical)')]):
        sheet.paste(picture.resize((w * 2, h * 2), Image.Resampling.NEAREST), (i * w * 2, 20))
        ImageDraw.Draw(sheet).text((i * w * 2 + 4, 4), label, fill='white')
    filename = ('hud_' + args.optics) if args.optics else 'system_hud'
    path = os.path.abspath(os.path.join(dosemu.ROOT, 'out/emu', filename + '_c_vs_original.png'))
    sheet.save(path)
    print('Complete system HUD: original | C | difference, identical')
    print(f'{name}: {len(calls)} original resource effects replayed; scan native, sound bodies excluded')
    print(path)


if __name__ == '__main__':
    main()
