"""Whole frames: the game is played live in the emulator (interrupts on, scripted keys) and
every frame of the 3D view is produced a second time by the C code and compared: the
background, the frame's object list, the finished scene and the card's registers.
See tools/frame_demo.py for exactly what is compared. Nothing is copied from the original's
screen; in frames where the lists were rebuilt the overhead-map page is redrawn by C too.

No recordings: this runs from the snapshots in out/emu/states/. Longer runs by hand:
    python tools/frame_demo.py --sequence 900 --quiet --keys "2:up:200,210:right:40,260:up:300"
If a frame differs, tools/frame_diag.py <frame> --keys ... finds the first differing record.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import frame_demo  # noqa: E402

CASES = 0

RUNS = [
    ('ingame', 240, [(2, 'up', 60), (70, 'right', 30), (110, 'up', 80), (200, 'left', 50), (260, 'up', 80)]),
    ('ingame', 160, [(2, 'right', 120), (130, 'down', 40), (180, 'left', 80)]),
    ('ingame_walked', 200, [(2, 'left', 100), (110, 'up', 200)]),
]


def run(ctx):
    global CASES
    fails = []
    cells = set()
    panel = 0
    for start, count, keys in RUNS:
        for frame, stats in frame_demo.sequence(start, count, keys, lib=ctx.lib):
            if stats is None:
                continue
            CASES += 1
            cells.add(stats['cell'])
            panel += stats['map_redrawn']
            if not stats['identical']:
                fails.append(f'from {start}, frame {frame}: {frame_demo.describe(stats)}')
                if len(fails) > 8:
                    return fails
    print(f'    frames: {CASES} live frames compared, {len(cells)} map cells visited; '
          f'the overhead-map page was redrawn in {panel} of them')
    return fails
