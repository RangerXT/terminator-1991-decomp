"""The main menu (main_menu, src/mainmenu.c) against the original 0000:9922.

From the in-game snapshot, a VGA installation (menu256.img, the chosen options lit through
DAC registers) and an EGA one (DS:ADD0 = 0, menu.img from data/ega, the options written in
the scalable font). Hotkeys are typed one per keyboard read (37AC with the buffer empty):
options changed (also to what they already are), keys that are no hotkey, V (the version
box), Q (quit), L and I (loading a game and the ratings: stubbed, the host's), J with a
joystick found and without (then the handler jumps back into the key loop, and the next
start only unwinds that). Boundaries (tests/boundaries.py): the default and game palettes
7AAF / 7AB6, page selection 0C6B, the mode switches at 997F / 99E0, the page at 0B94, the DAC
registers at 9C92 / 9CA1, the joystick 3A12 (CLC or STC) / 38F6, 4CE5, D300 (stubbed), the
message box's waits (5776:02C6 on EGA, 11BC:2C27 / 2C35 / 2C45 on VGA). Compared at every
boundary and at the end: memory, the EGA planes and card, the mode-13h screen.
"""
import ctypes
import os
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from boundaries import BASE, Inline, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import set_clock  # noqa: E402
from test_damagepanel import ega_installation  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_frame import TEXT_POLL, TextPlatform  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import KEY_POLL, KeyboardPlatform, buffer_empty, type_key  # noqa: E402

CASES = 0
KEY = 0x5BD9
ESC, ENTER = 0x01, 0x1C
POLL = 0x37AC


class MainMenuServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in
                ('resources', 'images', 'keys', 'text', 'ratings', 'screen', 'palette', 'saves')]


def held(m):
    return m.ds_read(KEY + ESC, 1)[0] or m.ds_read(KEY + ENTER, 1)[0]


def boundaries(joystick):
    return [
        Routine(0, 0x7AAF), Routine(0, 0x7AB6), Routine(0, 0x0C6B, registers=('ax',)),
        Inline(0x997F, 0x9981, 0xFF10), Inline(0x99E0, 0x99E2, 0xFF10), Inline(0x0B94, 0x0B96, 0xFF05),
        Inline(0x9C92, 0x9C94, 0x1010, registers=('bx', 'cx')), Inline(0x9CA1, 0x9CA3, 0x1010, registers=('bx', 'cx')),
        Routine(0, 0x3A12, stub=b'\xf8\xc3' if joystick else b'\xf9\xc3'), Routine(0, 0x38F6, stub=b'\xc3'),
        Routine(0, 0x4CE5, stub=b'\xc3'), Routine(0, 0xD300, stub=b'\xc3'),
        Point(POLL, POLL, buffer_empty),
        Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
        Point(0x2C27, 0x2C27, held, seg=0x11BC), Point(0x2C35, 0x2C35, lambda m: not held(m), seg=0x11BC),
        Point(0x2C45, 0x2C45, held, seg=0x11BC),
    ]


SCENARIOS = [
    # name, keys typed, settings
    ('VGA, start', 'g', {}),
    ('VGA, options, start', 'rshnpzg', {}),
    ('VGA, the same choice twice, back', 'rrtg', {}),
    ('VGA, quit', 'q', {}),
    ('VGA, no joystick: two starts', 'jgg', {}),
    ('VGA, joystick', 'jkg', {'joystick': True}),
    ('VGA, ratings, load, version', 'ilvg', {}),
    ('EGA, start', 'g', {'ega': True}),
    ('EGA, options, start', 'rdmkapsg', {'ega': True}),
    ('EGA, ratings, version, quit', 'ivq', {'ega': True}),
    ('EGA, no joystick: two starts', 'jgg', {'ega': True}),
]


def run_original(m, specs, keys):
    reads = [0]

    def on_boundary(entry):
        if entry['service'] == POLL:
            key = keys[reads[0]] if reads[0] < len(keys) else 'g'
            reads[0] += 1
            type_key(m, ord(key))
        elif entry['service'] == 0x02C6 and entry['caller'] == (0, 0x5185):
            m.ds_write(KEY + ENTER, b'\xff')         # a message box waits: Enter
        elif entry['service'] in (0x2C27, 0x2C45):
            m.ds_write(KEY + ESC, b'\0')
            m.ds_write(KEY + ENTER, b'\0')
        elif entry['service'] == 0x2C35:
            m.ds_write(KEY + ENTER, b'\xff')

    recorder = Recorder(m, specs, on_boundary, chunky=True).install()

    def release_before(uc, addr, size, user):
        if not recorder.pending and held(m):
            m.ds_write(KEY + ESC, b'\0')
            m.ds_write(KEY + ENTER, b'\0')

    def release_after(uc, addr, size, user):
        if not recorder.pending:
            m.ds_write(KEY + ENTER, b'\0')

    m.uc.hook_add(UC_HOOK_CODE, release_before, None, BASE + 0x5169, BASE + 0x5169)
    m.uc.hook_add(UC_HOOK_CODE, release_after, None, BASE + 0x51A1, BASE + 0x51A1)
    m.call(0, 0x9922, max_instr=2_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, reads[0]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.main_menu.restype = ctypes.c_int
    fails = []
    outcomes = []
    for label, keys, settings in SCENARIOS:
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        ega = settings.get('ega', False)
        if ega:
            ega_installation(m)
        m.ds_write(KEY, bytes(128))
        specs = boundaries(settings.get('joystick', False))
        stub_all(m, specs)
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
        palette = ctypes.create_string_buffer(768)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        set_clock(lib, m)
        recorder, reads = run_original(m, specs, keys)
        CASES += 1
        outcomes.append(f'{label}: {reads} keys, player {m.rw(m.DATA_SEG, 0x03A0):04X}, '
                        f'difficulty {m.rw(m.DATA_SEG, 0x03F0)}, quit {m.ds_read(0x1159, 1)[0]:02X}')
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files, screen=screen)

        @RESOURCE
        def resource(gp, service, a, b, user):
            if replay.serve(service, 0x0500 | a if service == 0xFF05 else a, b):
                return -1
            return 1 if service == 0x3A12 and replay.last['carry'] else 0

        resources = Resources(resource, None)

        @KEY_POLL
        def key_poll(gp, user):
            return replay.serve(POLL)

        keyboard = KeyboardPlatform(key_poll, None)

        def keyb(offset):
            return ctypes.c_uint8.from_address(g.ds + offset)

        @TEXT_POLL
        def text_poll(gp, phase, ticks, user):
            if not ega:
                return replay.serve((0x2C27, 0x2C35, 0x2C45)[phase])
            if phase == 0:
                keyb(KEY + ESC).value = keyb(KEY + ENTER).value = 0
                return 0
            if phase == 2:
                keyb(KEY + ENTER).value = 0
                return 0
            return replay.serve(0x02C6, ticks)

        text = TextPlatform(text_poll, None)
        services = MainMenuServices(ctypes.addressof(resources), ctypes.addressof(files.host), ctypes.addressof(keyboard),
                                    ctypes.addressof(text), None, ctypes.addressof(screen), ctypes.addressof(palette))
        status = lib.main_menu(ctypes.byref(g), ctypes.byref(services))
        problem = replay.finished()
        if status or problem:
            fails.append(f'{label}: status {status}; {problem}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{label}: at the end, memory {error}')
            elif screen.raw != bytes(m.vga.chunky):
                fails.append(f'{label}: at the end, the mode-13h screen differs')
            else:
                compare(label, mem, planes, m, spans, fails)
        if fails:
            return fails
    print('    mainmenu: ' + '; '.join(outcomes))
    return fails
