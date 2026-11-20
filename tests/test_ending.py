"""The end-of-session cutscenes (ending_sequence, src/ending.c) against the original 0000:5B6A.

From recorded main-loop frames, the Terminator and Reese, EGA and VGA, with every
combination of the flags that choose the scenes (DS:5CDB skip, 00B9, 1156, 1158, practice
mode 0345), and a key that cuts the waits short. Boundaries (tests/boundaries.py): the movie
player B210 (stubbed; SI, BX and CX recorded), the pause 5776:02C6, the retrace waits 0D8D /
0DAA and the sample group 8AFE (stubbed as XOR CX,CX / RET: its loader leaves CX = 0, and
the group is never 6 before this - DS:A6E9). Compared at every boundary and at the end:
memory, planes and card, sounds.
"""
import ctypes
import gzip
import itertools
import os
import pickle
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from boundaries import BASE, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_damagepanel import ega_installation  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapkey import EVENTS  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import type_key  # noqa: E402

CASES = 0
BOUNDARIES = [
    Routine(0, 0xB210, stub=b'\xc3', registers=('si', 'bx')),
    Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Routine(0, 0x8AFE, stub=b'\x33\xc9\xc3'),
]


class EndingServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in ('resources', 'movie', 'sound')]


def run_original(m, key_at, log):
    waits = [0]

    def on_boundary(entry):
        if entry['service'] == 0xB210:
            entry['b'] = m.r(dosemu.UC_X86_REG_BX) | m.r(dosemu.UC_X86_REG_CX) << 8
        elif entry['service'] == 0x0D8D:
            waits[0] += 1
            if waits[0] == key_at:
                type_key(m, ord(' '))

    recorder = Recorder(m, BOUNDARIES, on_boundary).install()
    for off, entry in EVENTS:
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, entry=entry: None if recorder.pending else log.append(entry(m)),
                      None, BASE + off, BASE + off)
    m.call(0, 0x5B6A, cx=0x1234, max_instr=500_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.ending_sequence.restype = ctypes.c_int
    fails = []
    recordings = {}
    events = (GameEvent * 512)()
    scenes = set()
    combos = list(itertools.product(('frameloop', 'frameloop_reese'), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1)))
    for n, (start, skip, b9, down, lost, practice) in enumerate(combos + [('frameloop', 0, 0, 0, 0, 0)] * 2):
        if start not in recordings:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                recordings[start] = pickle.load(f)
        m = capture.restore(recordings[start][0])
        ega = n % 3 == 1
        if ega:
            ega_installation(m)
        for off, value in ((0x5CDB, skip), (0x00B9, b9), (0x1156, down), (0x1158, lost), (0x0345, practice)):
            m.ds_write(off, b'\xff' if value else b'\0')
        m.ds_write(0xA6E9, b'\x03')
        m.ds_write(0x5BD4, b'\0\0')
        key_at = 5 + n % 40 if n >= len(combos) or n % 4 == 3 else None
        stub_all(m, BOUNDARIES, [off for off, entry in EVENTS])
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        log = []
        recorder = run_original(m, key_at, log)
        CASES += 1
        scenes.update(c['a'] for c in recorder.calls if c['service'] == 0xB210)
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, a, b)

        resources = Resources(resource, None)
        services = EndingServices(ctypes.addressof(resources), None, None)
        set_clock(lib, m)
        lib.game_events(events, 512)
        status = lib.ending_sequence(ctypes.byref(g), ctypes.byref(services))
        got = [(e.kind, e.a, e.b) for e in events[:lib.game_events(events, 512)]]
        problem = replay.finished()
        where = f'{start}, {"EGA" if ega else "VGA"}, skip {skip} B9 {b9} down {down} lost {lost} practice {practice}'
        if status or problem:
            fails.append(f'{where}: status {status}; {problem}')
        elif got != log:
            fails.append(f'{where}: sounds differ: C {got[:5]}, original {log[:5]}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{where}: at the end, memory {error}')
            else:
                compare(where, mem, planes, m, spans, fails)
        if fails:
            return fails
    print(f'    ending: {CASES} runs, scenes ' + ', '.join(f'{s:04X}' for s in sorted(scenes)))
    return fails
