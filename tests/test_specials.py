"""The special actions of the game menu (game_menu_action, src/gamemenus.c) against the
original handlers 0000:94DA, 95A5, 965C, 9699 and 971D, called as the menu calls them (their
ADD SP,2 / RET drops a word the test pushes) from recorded main-loop frames, the Terminator
and Reese, with the special items in the inventory (DS:AAA5 .. AAA9). The time bomb's minutes
are typed into the name editor (digits, a sign, Esc first, nothing typed, too many); 9699 on
foot and in a car (its message box). Boundaries: page selection 0C6B, the keyboard read 37AC
(keys typed there), the editor's Esc release E038, the message box wait 5776:02C6. Compared
at every boundary and at the end: memory, planes and card, sounds.
"""
import ctypes
import gzip
import os
import pickle
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from boundaries import BASE, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_frame import TEXT_POLL, TextPlatform  # noqa: E402
from test_gamemenus import MENU_CALL, GameMenuServices, MenuPlatform  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapkey import EVENTS  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import KEY_POLL, KeyboardPlatform, buffer_empty, type_key  # noqa: E402
from test_ratingsscreen import RatingsServices  # noqa: E402

CASES = 0
KEY = 0x5BD9
ESC, ENTER = 0x01, 0x1C
BOUNDARIES = [
    Routine(0, 0x0C6B, registers=('ax',)),
    Point(0x37AC, 0x37AC, buffer_empty),
    Point(0xE038, 0xE038, lambda m: m.ds_read(KEY + ESC, 1)[0] != 0),
    Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
]

SCENARIOS = [
    # name, recording, handler, keys typed for the editor ('esc' = Esc), settings
    ('homing beacon', 'frameloop', 0x94DA, [], {}),
    ('decoy, the Terminator', 'frameloop', 0x965C, [], {}),
    ('decoy, Reese', 'frameloop_reese', 0x965C, [], {}),
    ('marker', 'frameloop', 0x971D, [], {}),
    ('device on foot, the Terminator', 'frameloop', 0x9699, [], {'foot': True}),
    ('device on foot, Reese', 'frameloop_reese', 0x9699, [], {'foot': True}),
    ('device in a car', 'frameloop', 0x9699, [], {'foot': False}),
    ('time bomb, 15 minutes', 'frameloop', 0x95A5, ['1', '5', 0x0D], {}),
    ('time bomb, Esc, nothing, then 7', 'frameloop', 0x95A5, ['esc', 0x0D, '7', 0x0D], {}),
    ('time bomb, a sign, a letter', 'frameloop_reese', 0x95A5, ['-', '3', 0x0D, ], {}),
    ('time bomb, +, then 9Z', 'frameloop', 0x95A5, ['+', 0x0D], {}),
    ('time bomb, a letter first', 'frameloop', 0x95A5, ['x', '2', 0x0D, '9', 'z', 0x0D], {}),
]


def run_original(m, address, keys, log):
    reads = [0]

    def on_boundary(entry):
        if entry['service'] == 0x37AC:
            key = keys[reads[0]] if reads[0] < len(keys) else 0x0D
            reads[0] += 1
            if key == 'esc':
                m.ds_write(KEY + ESC, b'\xff')
                type_key(m, 0x1B)
            else:
                type_key(m, ord(key) if isinstance(key, str) else key)
        elif entry['service'] == 0xE038:
            m.ds_write(KEY + ESC, b'\0')
        elif entry['service'] == 0x02C6 and entry['caller'] == (0, 0x5185):
            m.ds_write(KEY + ENTER, b'\xff')         # a message box waits: Enter

    recorder = Recorder(m, BOUNDARIES, on_boundary).install()

    def release(uc, addr, size, user):
        if not recorder.pending:
            m.ds_write(KEY + ENTER, b'\0')
            m.ds_write(KEY + ESC, b'\0')

    for off, entry in EVENTS:
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, entry=entry: None if recorder.pending else log.append(entry(m)),
                      None, BASE + off, BASE + off)
    m.uc.hook_add(UC_HOOK_CODE, release, None, BASE + 0x5169, BASE + 0x5169)
    m.uc.hook_add(UC_HOOK_CODE, release, None, BASE + 0x51A1, BASE + 0x51A1)
    m.call(0, address, stack=(0xFFFF,), max_instr=500_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, reads[0]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.game_menu_action.restype = ctypes.c_int
    fails = []
    recordings = {}
    events = (GameEvent * 512)()
    outcomes = []
    for label, start, address, keys, settings in SCENARIOS:
        if start not in recordings:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                recordings[start] = pickle.load(f)
        m = capture.restore(recordings[start][0])
        m.ds_write(KEY, bytes(128))
        for i, off in enumerate((0xAAA5, 0xAAA6, 0xAAA7, 0xAAA8, 0xAAA9)):
            m.ds_write(off, bytes([0x2A + i]))
        if 'foot' in settings:
            player = m.rw(m.DATA_SEG, 0x03A0)
            flags = m.ds_read(player + 0x0E, 1)[0]
            m.ds_write(player + 0x0E, bytes([flags | 1 if settings['foot'] else flags & 0xFE]))
        stub_all(m, BOUNDARIES, [off for off, entry in EVENTS])
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
        palette = ctypes.create_string_buffer(768)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        log = []
        recorder, reads = run_original(m, address, keys, log)
        CASES += 1
        outcomes.append(f'{label}: {reads} keys, time {m.rw(m.DATA_SEG, 0x0B0E)}')
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)

        @MENU_CALL
        def menu_call(gp, op, a, b, user):
            return -1 if replay.serve(op, a if op == 0x02C6 else 0, 0) else 0

        menu = MenuPlatform(menu_call, None)

        def keyb(offset):
            return ctypes.c_uint8.from_address(g.ds + offset)

        @TEXT_POLL
        def text_poll(gp, phase, ticks, user):
            if phase in (0, 2):
                keyb(KEY + ENTER).value = keyb(KEY + ESC).value = 0
                return 0
            return replay.serve(0x02C6, ticks)

        text = TextPlatform(text_poll, None)

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, a, b)

        resources = Resources(resource, None)

        @KEY_POLL
        def key_poll(gp, user):
            return replay.serve(0x37AC if not ctypes.c_uint8.from_address(g.ds + KEY + ESC).value else 0xE038)

        keyboard = KeyboardPlatform(key_poll, None)
        ratings = RatingsServices(ctypes.addressof(resources), ctypes.addressof(files.host), ctypes.addressof(keyboard),
                                  ctypes.addressof(screen), ctypes.addressof(palette))
        menus = GameMenuServices(ctypes.addressof(menu), ctypes.addressof(text), ctypes.addressof(files.host), None,
                                 ctypes.addressof(ratings))
        set_clock(lib, m)
        lib.game_events(events, 512)
        status = lib.game_menu_action(ctypes.byref(g), address, ctypes.byref(menus))
        got = [(e.kind, e.a, e.b) for e in events[:lib.game_events(events, 512)]]
        problem = replay.finished()
        if status < 0 or problem:
            fails.append(f'{label}: status {status}; {problem}')
        elif got != log:
            fails.append(f'{label}: sounds differ: C {got[:5]}, original {log[:5]}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{label}: at the end, memory {error}')
            else:
                compare(label, mem, planes, m, spans, fails)
        if fails:
            return fails
    print('    specials: ' + '; '.join(outcomes))
    return fails
