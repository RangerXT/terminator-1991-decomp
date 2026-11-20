"""The closing credits (credits_screen, src/credits.c) against the original 0000:91EA.

From the in-game snapshot: the real credits file run to the end (several wraps of the
360-row screen), a key early and after the first wrap, and to the end with the music
playing (DS:EA3C set: then it waits for a key). Boundaries (tests/boundaries.py): the mode
switches at 91F5 / 9285, the retrace waits 0D8D / 0DAA and the display start C571
(stubbed), the final wait for a key (927B, a point while the buffer is empty). Compared at
every boundary and at the end: memory, the EGA planes and card.
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import Inline, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import KEY_POLL, KeyboardPlatform, type_key  # noqa: E402

CASES = 0
WAIT_KEY = 0x927B


class CreditsServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in ('resources', 'images', 'keys')]


BOUNDARIES = [
    Inline(0x91F5, 0x91F7, 0xFF10), Inline(0x9285, 0x9287, 0xFF10),
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Routine(0, 0xC571, stub=b'\xc3', registers=('ax',)),
    Point(WAIT_KEY, WAIT_KEY, lambda m: not m.ds_read(0x5BD4, 1)[0]),
]

SCENARIOS = [
    # name, retrace wait at which a key is typed (None: none), music playing
    ('to the end', None, False),
    ('a key early', 40, False),
    ('a key after the first wrap', 1700, False),
    ('to the end with music: a key', None, True),
]


def run_original(m, key_at):
    waits = [0]

    def on_boundary(entry):
        if entry['service'] in (0x0D8D, 0x0DAA):
            waits[0] += 1
            if waits[0] == key_at:
                type_key(m, ord(' '))
        elif entry['service'] == WAIT_KEY:
            type_key(m, ord(' '))

    recorder = Recorder(m, BOUNDARIES, on_boundary).install()
    m.call(0, 0x91EA, max_instr=3_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, waits[0]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.credits_screen.restype = ctypes.c_int
    fails = []
    outcomes = []
    for label, key_at, music in SCENARIOS:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        m.ds_write(0xEA3C, b'\xff' if music else b'\0')
        stub_all(m, BOUNDARIES)
        g, mem, planes = make_game(m)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        recorder, waits = run_original(m, key_at)
        CASES += 1
        outcomes.append(f'{label}: {waits // 4} rows')
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, a, b)

        resources = Resources(resource, None)

        @KEY_POLL
        def key_poll(gp, user):
            return replay.serve(WAIT_KEY)

        keys = KeyboardPlatform(key_poll, None)
        services = CreditsServices(ctypes.addressof(resources), ctypes.addressof(files.host), ctypes.addressof(keys))
        status = lib.credits_screen(ctypes.byref(g), ctypes.byref(services))
        problem = replay.finished()
        if status or problem:
            fails.append(f'{label}: status {status}; {problem}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{label}: at the end, memory {error}')
            else:
                compare(label, mem, planes, m, spans, fails)
        if fails:
            return fails
    print('    credits: ' + '; '.join(outcomes))
    return fails
