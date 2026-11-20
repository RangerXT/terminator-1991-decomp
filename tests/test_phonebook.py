"""The P key's phone book (phone_book, src/phonebook.c) against the original, from live frames.

Each case starts at the top of a recorded main-loop frame with P held; C runs
frame_input_check, the original 0000:05A2. Boundaries (tests/boundaries.py): the video mode
switches (0BE5 and int 10h at 7A35), page selection 0C6B, the CRTC display start C571, the
retrace waits 0D8D/0DAA (stubbed), the default palette 7AAF, and the keyboard: the points
where the original polls for input (the scroll loop at C538, and keyboard_read's wait at
37AC while the buffer is empty). The scripted keys are written at chosen polls. The images
(PHONEHDR.IMG, YELLOWPG.CIF and the camera reset's) are loaded by C itself.

Recordings: those of tests/test_frame.py; the test also varies the number of shops in the
loaded window (DS:72B2): 0 (no scrolling, a plain key wait), 1, 3 and the recorded 6.
"""
import ctypes
import gzip
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from boundaries import Inline, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_frame import FRAME_CALL, FrameServices, GameplayServices  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapkey import WAIT, MapPlatform  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402

CASES = 0
KEY = 0x5BD9
SC_P, SC_UP, SC_DOWN = 0x19, 0x48, 0x50
POLL = 0x37AC                            # service id of an input poll, in both
KEY_POLL = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_void_p)


class KeyboardPlatform(ctypes.Structure):
    _fields_ = [('poll', KEY_POLL), ('user', ctypes.c_void_p)]


class PhoneBookServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in ('resources', 'platform', 'images', 'keys')]


def buffer_empty(m):
    return m.rw(m.DATA_SEG, 0x5BD4) == 0


BOUNDARIES = [
    Routine(0, 0x0BE5, registers=('ax',), service=0xFF10),
    Routine(0, 0x0C6B, registers=('ax',)),
    Routine(0, 0xC571, registers=('ax',)),
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Routine(0, 0x7AAF),
    Inline(0x7A35, 0x7A37, 0xFF10),
    Point(0xC538, POLL),
    Point(0x37AC, POLL, buffer_empty),
]


def type_key(m, char=0x20):
    """A key arrives in the keyboard buffer, as the keyboard interrupt puts it there."""
    at = m.rw(m.DATA_SEG, 0x5B6C)
    m.ds_write(at, bytes([char]))
    at = 0x5B70 if at + 1 == 0x5BD4 else at + 1
    m.ds_write(0x5B6C, struct.pack('<H', at))
    m.ds_write(0x5BD4, struct.pack('<H', m.rw(m.DATA_SEG, 0x5BD4) + 1))


SCENARIOS = [
    # name, {input poll number: action}
    ('closed at once', {1: 'type'}),
    ('down, down, up', {1: 'down', 2: 'release', 3: 'down', 4: 'release', 5: 'up', 6: 'release', 8: 'type'}),
    ('down held', {1: 'down', 9: 'type'}),
]
SHOPS = [None, 0, 1, 3]                   # as recorded (6 everywhere), or fewer
STARTS = [('frameloop', 0), ('frameloop', 30), ('frameloop_driving', 20)]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.frame_input_check.restype = ctypes.c_int
    fails = []
    recordings = {}
    events = (GameEvent * 512)()
    seen = {}
    for start, index in STARTS:
        if start not in recordings:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                recordings[start] = pickle.load(f)
        for shops in SHOPS:
            for label, script in SCENARIOS:
                where = f'{start} {index}, shops {shops if shops is not None else "as recorded"}, {label}'
                m = capture.restore(recordings[start][index])
                m.ds_write(KEY + SC_P, b'\xff')
                for off in (0x0200, 0x0201, 0x8096, 0xE1F2):   # no warning, reload overlay or message
                    m.ds_write(off, b'\x00')
                if shops is not None:
                    m.ds_write(0x72B2, struct.pack('<H', shops))
                stub_all(m, BOUNDARIES)
                g, mem, planes = make_game(m)
                files = Files(m, record=False)
                spans = regions(m)
                ds_base = m.DATA_SEG << 4
                polls = [0]

                def on_boundary(entry):
                    if entry['service'] != POLL:
                        return
                    polls[0] += 1
                    action = script.get(polls[0]) or ('type' if polls[0] > 40 else None)
                    if action == 'type':
                        type_key(m)
                    elif action in ('down', 'up'):
                        m.ds_write(KEY + (SC_DOWN if action == 'down' else SC_UP), b'\xff')
                    elif action == 'release':
                        m.ds_write(KEY + SC_DOWN, b'\x00')
                        m.ds_write(KEY + SC_UP, b'\x00')

                recorder = Recorder(m, BOUNDARIES, on_boundary).install()
                m.call(0, 0x05A2, max_instr=500_000_000)
                CASES += 1
                calls = recorder.calls
                count = m.rw(m.DATA_SEG, 0x72B2)
                scrolls = sum(1 for c in calls if c['service'] == 0xC571) // 86
                outcome = f'{min(count, 7)}{"+" if count > 6 else ""} shops, {scrolls} row scrolls'
                seen[outcome] = seen.get(outcome, 0) + 1

                replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)

                @RESOURCE
                def resource(gp, service, a, b, user):
                    return replay.serve(service, a, b)

                resources = Resources(resource, None)

                @WAIT
                def wait(gp, high, user):
                    return replay.serve(0x0D8D if high else 0x0DAA)

                platform = MapPlatform(wait, None)

                @KEY_POLL
                def key_poll(gp, user):
                    return replay.serve(POLL)

                keys = KeyboardPlatform(key_poll, None)
                services = PhoneBookServices(ctypes.addressof(resources), ctypes.addressof(platform),
                                             ctypes.addressof(files.host), ctypes.addressof(keys))
                gameplay = GameplayServices()
                no_call = FRAME_CALL(lambda *a: 0xFFFFFFFF)
                host = FrameServices(ctypes.addressof(gameplay), None, no_call, None, None, 0, None,
                                     ctypes.addressof(services))
                set_clock(lib, m)
                lib.game_events(events, 512)
                status = lib.frame_input_check(ctypes.byref(g), ctypes.byref(host))
                got = [(e.kind, e.a, e.b) for e in events[:lib.game_events(events, 512)]]
                problem = replay.finished()
                if status or problem:
                    fails.append(f'{where}: status {status}; {problem}')
                elif got:
                    fails.append(f'{where}: unexpected events {got[:4]}')
                else:
                    error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
                    if error:
                        fails.append(f'{where}: at the end, memory {error}')
                    else:
                        compare(where, mem, planes, m, spans, fails)
                if len(fails) > 4:
                    return fails
    print(f'    phonebook: {CASES} cases; ' + ', '.join(f'{n} with {o}' for o, n in sorted(seen.items())))
    return fails
