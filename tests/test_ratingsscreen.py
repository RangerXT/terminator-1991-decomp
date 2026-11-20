"""The ratings screen and name editor (src/ratingsscreen.c) against the original 0000:D300.

From a recorded main-loop frame (the Terminator, so RATINGS.TRM) of the VGA installation,
and as an EGA installation (DS:ADD0 = 0, Ratings.img from data/ega). Typed keys go into
the keyboard buffer whenever the original waits for one (keyboard_read at 37AC with the
buffer empty); the name editor's wait for Esc to be let go (E038) is a point where Esc is
let go. Boundaries (tests/boundaries.py, with the mode-13h screen): the video mode switches
(int 10h at D32D, D33B, D49E, 7A35), the palettes 7AAF and 7AB6, page selection 0C6B.
Images, fonts and the ratings file are read by C itself. Variants: the current session
does or does not make the table (the decoded table is set either way), 1-5 and Space, the
name editor with typing, backspace and too many letters, the editor left with Esc; the
session already named (DS:038A) or not; called from the main menu (DS:ABC8); Reese
(frameloop_reese, his own ratings file).
"""
import ctypes
import gzip
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from boundaries import Inline, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_damagepanel import ega_installation  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import KEY_POLL, KeyboardPlatform, buffer_empty, type_key  # noqa: E402

CASES = 0
KEY = 0x5BD9
ESC = 0x01
POLL = 0x37AC


class RatingsServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in ('resources', 'images', 'keys', 'screen', 'palette')]


BOUNDARIES = [
    Inline(0xD32D, 0xD32F, 0xFF10), Inline(0xD33B, 0xD33D, 0xFF10), Inline(0xD49E, 0xD4A0, 0xFF10),
    Inline(0x7A35, 0x7A37, 0xFF10),
    Routine(0, 0x7AAF), Routine(0, 0x7AB6), Routine(0, 0x0C6B, registers=('ax',)),
    Point(0x37AC, POLL, buffer_empty),
    Point(0xE038, 0xE038, lambda m: m.ds_read(KEY + ESC, 1)[0] != 0),
]

SCENARIOS = [
    # name, {keyboard wait number: keys typed}, settings. The recorded session makes the
    # table, so the name editor opens first unless the session already has a name.
    ('named, look, Esc', {1: [0x1B]}, {'named': True}),
    ('named, ranks and Space', {1: [ord('1')], 2: [ord('3')], 3: [ord(' ')], 4: [ord('5')], 5: [0x1B]},
     {'named': True}),
    ('named, N: the editor', {1: [ord('N')], 2: [ord('J')], 3: [ord('o')], 4: [ord('x')], 5: [8], 6: [ord('e')],
                              7: [0x0D], 8: [0x1B]}, {'named': True}),
    ('new best, a name', {1: [ord('B')], 2: [ord('o')], 3: [0x0D], 4: [ord('2')], 5: [0x1B]}, {}),
    ('new best, too long', {**{1 + i: [ord('A') + i] for i in range(12)}, 13: [8], 14: [0x0D], 15: [0x1B]}, {}),
    ('new best, editor left with Esc', {1: [ord('Q')], 2: ['esc'], 3: [0x1B]}, {}),
    ('EGA, named, look', {1: [ord('4')], 2: [0x1B]}, {'ega': True, 'named': True}),
    ('EGA, new best, a name', {1: [ord('K')], 2: [8], 3: [ord('Z')], 4: [0x0D], 5: [0x1B]}, {'ega': True}),
    ('EGA, named, N: the editor', {1: [ord('n')], 2: [ord('R')], 3: [0x0D], 4: [0x1B]}, {'ega': True, 'named': True}),
    # from the main menu (DS:ABC8): no mode switches, no session, N does nothing
    ('from the menu, ranks', {1: [ord('3')], 2: [ord('N')], 3: [ord(' ')], 4: [0x1B]}, {'menu': True}),
    ('EGA, from the menu', {1: [ord('2')], 2: [ord('n')], 3: [0x1B]}, {'ega': True, 'menu': True}),
    # Reese: his own ratings file
    ('Reese, a name, ranks', {1: [ord('D')], 2: [0x0D], 3: [ord('1')], 4: [0x1B]}, {'start': 'frameloop_reese'}),
    ('Reese, EGA, named', {1: [ord('3')], 2: [0x1B]}, {'start': 'frameloop_reese', 'ega': True, 'named': True}),
]


def run_original(m, script):
    polls = [0]

    def act(key):
        if key == 'esc':
            m.ds_write(KEY + ESC, b'\xff')
            type_key(m, 0x1B)
        else:
            type_key(m, key)

    def on_boundary(entry):
        if entry['service'] == POLL:
            polls[0] += 1
            for key in script.get(polls[0], [0x0D, 0x1B] if polls[0] > 60 else []):
                act(key)
        elif entry['service'] == 0xE038:
            m.ds_write(KEY + ESC, b'\0')

    recorder = Recorder(m, BOUNDARIES, on_boundary, chunky=True).install()
    m.call(0, 0xD300, max_instr=1_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, polls[0]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.ratings_screen.restype = ctypes.c_int
    fails = []
    states = {}
    events = (GameEvent * 512)()
    outcomes = []
    for label, script, settings in SCENARIOS:
        start = settings.get('start', 'frameloop')
        if start not in states:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                states[start] = pickle.load(f)[0]
        m = capture.restore(states[start])
        if settings.get('ega'):
            ega_installation(m)
        if settings.get('named'):
            m.ds_write(0x038A, b'Kyle\0')
        if settings.get('menu'):
            m.ds_write(0xABC8, b'\x01')
            if not settings.get('ega'):      # the main menu left the card in mode 13h
                m.vga.set_mode(0x13)
                m.uc.mem_write(0x449, b'\x13')
        stub_all(m, BOUNDARIES)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
        palette = ctypes.create_string_buffer(768)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        recorder, polls = run_original(m, script)
        CASES += 1
        name = m.ds_read(0x038A, 21).split(b'\0')[0]
        outcomes.append(f'{label}: {polls} keys, name {name!r}')

        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files, screen=screen)

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, a, b)

        resources = Resources(resource, None)

        @KEY_POLL
        def key_poll(gp, user):
            return replay.serve(POLL if not ctypes.c_uint8.from_address(g.ds + KEY + ESC).value else 0xE038)

        keys = KeyboardPlatform(key_poll, None)
        services = RatingsServices(ctypes.addressof(resources), ctypes.addressof(files.host), ctypes.addressof(keys),
                                   ctypes.addressof(screen), ctypes.addressof(palette))
        set_clock(lib, m)
        lib.game_events(events, 512)
        status = lib.ratings_screen(ctypes.byref(g), ctypes.byref(services))
        problem = replay.finished()
        where = f'{start}, {label}'
        if status or problem:
            fails.append(f'{where}: status {status}; {problem}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{where}: at the end, memory {error}')
            elif screen.raw != bytes(m.vga.chunky):
                fails.append(f'{where}: at the end, the mode-13h screen differs')
            else:
                compare(where, mem, planes, m, spans, fails)
        if len(fails) > 4:
            return fails
    print('    ratings: ' + '; '.join(outcomes))
    return fails
