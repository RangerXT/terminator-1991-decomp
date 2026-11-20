"""The damage panel (damage_panel, src/damagepanel.c) against the original 0000:5F06.

Starts from recorded main-loop frames of a VGA installation (so the mode-13h panel), the
Terminator and Reese, with damage set on the body parts. Typed keys (H, T, A, L, Enter)
are put into the keyboard buffer and Esc into the key table at chosen retrace waits.
Boundaries (tests/boundaries.py, with the mode-13h screen): page selection 0C6B, the video
mode switches (int 10h at 5F44, 602C, 7A35), the default palette 7AAF, the retrace waits
0D8D/0DAA and the pause 5776:02C6 (stubbed), and for the world that runs while healing the
movie player B210 (stubbed). Cell loading and camera resets inside the world steps run in
C on both sides. The VGA message box's busy-waits (11BC:2C27, 2C35, 2C45) are points where
its keys are let go and Enter is pressed. Compared at every boundary and at
the end: memory, the EGA planes and card registers, the mode-13h screen, sounds, border.

Recordings: frameloop, frameloop_opponent and frameloop_reese (tests/test_frame.py,
tests/test_gamemenus.py).
"""
import ctypes
import gzip
import os
import pickle
import struct
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from boundaries import BASE, Inline, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_frame import TEXT_POLL, TextPlatform  # noqa: E402
from test_gamemenus import MENU_CALL, MenuPlatform  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapkey import CALL, EVENTS, WAIT, MapPlatform, Services  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import type_key  # noqa: E402
from test_vehicletransition import VehicleServices  # noqa: E402

CASES = 0
KEY = 0x5BD9
ESC, ENTER = 0x01, 0x1C


class DamagePanelServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in
                ('resources', 'platform', 'menu', 'images', 'text', 'travel', 'opponents', 'vehicle', 'screen',
                 'palette')]


BOUNDARIES = [
    Routine(0, 0x0C6B, registers=('ax',)),
    Inline(0x5F44, 0x5F46, 0xFF10), Inline(0x602C, 0x602E, 0xFF10), Inline(0x7A35, 0x7A37, 0xFF10),
    Routine(0, 0x7AAF),
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
    Routine(0, 0xB210, stub=b'\xc3', argument=0xDE34),
    # the VGA message box (11BC:2BCC) busy-waits: Enter and Esc up, a key, the key up again
    Point(0x2C27, 0x2C27, lambda m: held(m), seg=0x11BC),
    Point(0x2C35, 0x2C35, lambda m: not held(m), seg=0x11BC),
    Point(0x2C45, 0x2C45, lambda m: held(m), seg=0x11BC),
]
WAITS = (0x0D8D, 0x0DAA)

# damage per part (head, torso, arms, legs), maximum per part
DAMAGE = (2, 1, 0, 3)
MAXIMUM = (10, 20, 10, 20)

SCENARIOS = [
    # name, recording, {retrace wait: action}, settings. The panel reads one typed key per
    # frame (three waits), so keys are typed a frame apart.
    ('look, Esc', 'frameloop', {6: 'esc'}, {}),
    ('select and deselect', 'frameloop', {3: 'H', 6: 'T', 9: 'A', 12: 'T', 15: 'L', 24: 'esc'}, {}),
    ('Enter with nothing selected', 'frameloop', {3: 'enter', 9: 'esc'}, {}),
    ('treat the head', 'frameloop', {3: 'H', 6: 'enter', 15: 'esc'}, {}),
    ('treat everything', 'frameloop', {3: 'H', 6: 'T', 9: 'A', 12: 'L', 15: 'enter', 24: 'esc'}, {}),
    ('treat twice', 'frameloop', {3: 'H', 6: 'enter', 12: 'L', 15: 'enter', 24: 'esc'}, {}),
    ('treat, in battle', 'frameloop', {3: 'L', 6: 'enter', 30: 'esc'}, {'battle': True}),
    ('treat, opponent comes', 'frameloop_opponent', {3: 'L', 6: 'enter', 15: 'enter', 24: 'esc'}, {}),
    ('Reese, treat the legs', 'frameloop_reese', {3: 'L', 6: 'enter', 15: 'esc'}, {}),
    ('Reese, look', 'frameloop_reese', {5: 'esc'}, {}),
    # an EGA installation (DS:ADD0 = 0): the panel in the mode-0Dh pages
    ('EGA, look', 'frameloop', {6: 'esc'}, {'ega': True}),
    ('EGA, select and deselect', 'frameloop', {2: 'H', 4: 'T', 6: 'A', 8: 'T', 10: 'L', 16: 'esc'}, {'ega': True}),
    ('EGA, treat the head', 'frameloop', {2: 'H', 4: 'enter', 10: 'esc'}, {'ega': True}),
    ('EGA, treat everything', 'frameloop', {2: 'H', 4: 'T', 6: 'A', 8: 'L', 10: 'enter', 16: 'esc'}, {'ega': True}),
]


def ega_installation(m):
    """DS:ADD0 = 0, and files missing from the VGA install are taken from data/ega
    (Damage.img)."""
    m.ds_write(0xADD0, b'\0')
    lookup = m._path

    def path(name):
        found = lookup(name)
        if not os.path.exists(found):
            ega = os.path.join(dosemu.ROOT, 'data', 'ega', os.path.basename(found).upper())
            if os.path.exists(ega):
                return ega
        return found
    m._path = path


def held(m):
    return m.ds_read(KEY + ESC, 1)[0] or m.ds_read(KEY + ENTER, 1)[0]


def wound(m):
    player = m.rw(m.DATA_SEG, 0x03A0)
    m.ds_write(player + 0x11, bytes(DAMAGE) + bytes(MAXIMUM))
    m.ds_write(player + 0x1A, struct.pack('<H', sum(DAMAGE)))
    m.ds_write(player + 0x1C, struct.pack('<H', 100))


def run_original(m, script, log):
    waits = [0]

    def act(action):
        if action == 'esc':
            m.ds_write(KEY + ESC, b'\xff')
        elif action == 'enter':
            type_key(m, 0x0D)
        else:
            type_key(m, ord(action))

    def on_boundary(entry):
        if entry['service'] in (0x2C27, 0x2C45):     # the VGA message box: let go of the keys
            m.ds_write(KEY + ESC, b'\0')
            m.ds_write(KEY + ENTER, b'\0')
        elif entry['service'] == 0x2C35:             # ... and its key: Enter
            m.ds_write(KEY + ENTER, b'\xff')
        elif entry['service'] in WAITS:
            waits[0] += 1
            action = script.get(waits[0]) or ('esc' if waits[0] > 400 else None)
            if action:
                act(action)

    recorder = Recorder(m, BOUNDARIES, on_boundary, chunky=True).install()

    for off, entry in EVENTS:
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, entry=entry: None if recorder.pending else log.append(entry(m)),
                      None, BASE + off, BASE + off)
    m.call(0, 0x5F06, max_instr=3_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, waits[0]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.damage_panel.restype = ctypes.c_int
    lib.update_visible_cells.restype = ctypes.c_int
    lib.camera_reset.restype = ctypes.c_int
    fails = []
    recordings = {}
    events = (GameEvent * 4096)()
    healed_total = 0
    outcomes = []
    for label, start, script, settings in SCENARIOS:
        if start not in recordings:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                recordings[start] = pickle.load(f)
        where = f'{start}, {label}'
        m = capture.restore(recordings[start][0])
        wound(m)
        if settings.get('battle'):
            m.ds_write(0x115A, b'\x01')
        if settings.get('ega'):
            ega_installation(m)
        stub_all(m, BOUNDARIES, [off for off, entry in EVENTS])
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
        palette = ctypes.create_string_buffer(768)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        log = []
        player = m.rw(m.DATA_SEG, 0x03A0)
        recorder, waits = run_original(m, script, log)
        CASES += 1
        healed = sum(DAMAGE) - sum(m.ds_read(player + 0x11, 4))
        healed_total += healed
        outcomes.append(f'{label}: {healed} healed' + (', interrupted' if m.ds_read(0x7BD4, 1)[0] else ''))

        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files, screen=screen)

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, a, b)

        resources = Resources(resource, None)

        @WAIT
        def wait(gp, high, user):
            return replay.serve(0x0D8D if high else 0x0DAA)

        platform = MapPlatform(wait, None)

        @MENU_CALL
        def menu_call(gp, op, a, b, user):
            return replay.serve(op, a, 0)

        menu = MenuPlatform(menu_call, None)

        @TEXT_POLL
        def text_poll(gp, phase, ticks, user):
            return replay.serve((0x2C27, 0x2C35, 0x2C45)[phase])

        text = TextPlatform(text_poll, None)
        vehicle = VehicleServices()
        vehicle.display = ctypes.pointer(resources)
        vehicle.images = ctypes.pointer(files.host)

        @CALL
        def opponent_call(gp, service, arg, user):
            if service == 0x3B88:
                return 0 if lib.update_visible_cells(gp, ctypes.byref(files.host)) == 0 else 0xFFFFFFFF
            if service == 0x7A28:
                ok = lib.camera_reset(gp, ctypes.byref(resources), ctypes.byref(files.host)) == 0
                return 0 if ok else 0xFFFFFFFF
            return 0 if replay.serve(service, arg if service in (0x02C6, 0xB210) else 0) == 0 else 0xFFFFFFFF

        opponents = Services(opponent_call, None)
        services = DamagePanelServices(ctypes.addressof(resources), ctypes.addressof(platform), ctypes.addressof(menu),
                                       ctypes.addressof(files.host), ctypes.addressof(text), None,
                                       ctypes.addressof(opponents), ctypes.addressof(vehicle),
                                       ctypes.addressof(screen), ctypes.addressof(palette))
        set_clock(lib, m)
        lib.game_events(events, 4096)
        status = lib.damage_panel(ctypes.byref(g), ctypes.byref(services))
        got = [(e.kind, e.a, e.b) for e in events[:lib.game_events(events, 4096)]]
        problem = replay.finished()
        if status or problem:
            fails.append(f'{where}: status {status}; {problem}')
        elif got != log:
            fails.append(f'{where}: sounds or border differ: C {got[:5]}, original {log[:5]}')
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
    print(f'    damagepanel: {CASES} cases, {healed_total} points healed in all; ' + '; '.join(outcomes))
    return fails
