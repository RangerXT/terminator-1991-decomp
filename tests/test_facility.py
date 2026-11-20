"""The facility screens (facility_screen, src/facility.c) against the original 0000:8CB0.

From recorded main-loop frames, the Terminator (frameloop) and Kyle Reese (frameloop_reese),
on an EGA installation (DS:ADD0 = 0, images from data/ega) and a VGA one: the hospital (kind 6: Reese is
asked and treated - the damage panel 5F06 stubbed - or not; the Terminator gets a message
and the alarm) and the bank (kind 4: Reese's menu, withdraw or rob, and the robbery prompt
once he has had his money; the Terminator robs it or not), and the firing range (kind 5: six
targets shot on the spot, aimed with the arrow keys, with Tab, or timed out; the timer
interrupt's counting is done at the pause's busy loop 9029 and at the retrace waits). Menu keys go into the key table at the menu waits (5776:02C6), as in
tests/test_gamemenus.py. Boundaries: those of tests/test_gamemenus.py, the mode switch
(INT 10h at 8CE9) and the camera reset's (7A35), page selection 0C6B, the palettes 7AAF /
7AB6, the sample groups 8ABE / 8ADE (stubbed); on VGA the mode switch at 8CC3, the
mode-13h menu's key releases (9E36, 9F07) and its message box's busy-waits (11BC:2C27,
2C35, 2C45). Compared at every boundary and at the end: memory, planes and card, the
mode-13h screen, sounds.
"""
import ctypes
import gzip
import os
import pickle
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
from boundaries import BASE, Inline, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_damagepanel import ega_installation  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_frame import TEXT_POLL, TextPlatform  # noqa: E402
from test_gamemenus import KEY, MENU_CALL, SC, GameMenuServices, MenuPlatform, boundaries, held  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapkey import EVENTS  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_phonebook import KEY_POLL, KeyboardPlatform, buffer_empty, type_key  # noqa: E402

CASES = 0
BANK, RANGE, HOSPITAL = 4, 5, 6


class FacilityServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in
                ('resources', 'images', 'menus', 'sound', 'screen', 'palette', 'keys')]


EXTRA = [
    Inline(0x8CE9, 0x8CEB, 0xFF10), Inline(0x7A35, 0x7A37, 0xFF10),
    Routine(0, 0x0C6B, registers=('ax',)), Routine(0, 0x7AAF), Routine(0, 0x7AB6),
    Routine(0, 0x8ABE, stub=b'\xc3'), Routine(0, 0x8ADE, stub=b'\xc3'),
    # the firing range: retrace waits, the pause's busy loop (the timer ticks there), the key at the end
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Point(0x9029, 0x9029, lambda m: m.rw(m.DATA_SEG, 0xA964) != 0),
    Point(0x37AC, 0x37AC, buffer_empty),
]
TIMER = 0xA964
RIGHT, LEFT, UP, DOWN, TAB, ENTER = 0x4D, 0x4B, 0x48, 0x50, 0x0F, 0x1C
# per target: (key held, waits held, shot key at that wait or None for a timeout)
STILL = [(None, 0, ENTER)] * 6
MOVES = [(RIGHT, 6, ENTER), (DOWN, 4, ENTER), (LEFT, 9, TAB), (UP, 3, ENTER), (None, 0, None), (RIGHT, 2, ENTER)]
# a VGA installation: the mode switch at 8CC3, the mode-13h menu's key releases (9E36, 9F07)
# and message box busy-waits (11BC:2C27 / 2C35 / 2C45)
VGA = [
    Inline(0x8CC3, 0x8CC5, 0xFF10),
    Point(0x9E36, 0x1000, lambda m: held(m, 'esc', 'enter')), Point(0x9F07, 0x1001, lambda m: held(m, 'esc')),
    Point(0x2C27, 0x2C27, lambda m: held(m, 'esc', 'enter'), seg=0x11BC),
    Point(0x2C35, 0x2C35, lambda m: not held(m, 'esc', 'enter'), seg=0x11BC),
    Point(0x2C45, 0x2C45, lambda m: held(m, 'esc', 'enter'), seg=0x11BC),
]

SCENARIOS = [
    # name, recording, kind, {menu wait: keys}, settings
    ('Terminator, hospital: the alarm', 'frameloop', HOSPITAL, {}, {}),
    ('Reese, hospital: no', 'frameloop_reese', HOSPITAL, {2: ['down'], 3: ['enter']}, {}),
    ('Reese, hospital: treated', 'frameloop_reese', HOSPITAL, {2: ['enter']}, {}),
    ('Reese, bank: withdraw', 'frameloop_reese', BANK, {2: ['down'], 3: ['enter']}, {}),
    ('Reese, bank: rob', 'frameloop_reese', BANK, {2: ['enter']}, {}),
    ('Reese, bank after withdrawing: no', 'frameloop_reese', BANK, {2: ['down'], 3: ['enter']}, {'withdrawn': True}),
    ('Terminator, bank: rob', 'frameloop', BANK, {2: ['enter']}, {}),
    ('Terminator, bank: no', 'frameloop', BANK, {2: ['down'], 3: ['enter']}, {}),
    ('firing range, shots on the spot', 'frameloop', RANGE, {}, {'range': STILL}),
    ('firing range, aimed, Tab, a timeout', 'frameloop', RANGE, {}, {'range': MOVES}),
    ('firing range, ranks from the third', 'frameloop', RANGE, {}, {'range': STILL, 'ranks': 3}),
    ('VGA, Terminator, hospital: the alarm', 'frameloop', HOSPITAL, {}, {'vga': True}),
    ('VGA, Reese, hospital: treated', 'frameloop_reese', HOSPITAL, {2: ['enter']}, {'vga': True}),
    ('VGA, Reese, bank: withdraw', 'frameloop_reese', BANK, {2: ['down'], 3: ['enter']}, {'vga': True}),
    ('VGA, Reese, bank: rob', 'frameloop_reese', BANK, {2: ['enter']}, {'vga': True}),
    ('VGA, Terminator, bank: no', 'frameloop', BANK, {2: ['down'], 3: ['enter']}, {'vga': True}),
    ('VGA, firing range, aimed', 'frameloop', RANGE, {}, {'vga': True, 'range': MOVES}),
    ('VGA, firing range, all time out', 'frameloop', RANGE, {}, {'vga': True, 'range': [(None, 0, None)] * 6}),
]


def run_original(m, specs, kind, script, log, vga, plan):
    waits = [0]
    shooting = {'target': -1, 'wait': 0, 'aiming': False, 'held': None}

    def keys(names, value):
        for name in names:
            m.ds_write(KEY + SC[name], bytes([value]))

    def on_boundary(entry):
        if entry['service'] == 0x02C6 and entry['caller'] == (0, 0x5185):
            keys(['enter'], 0xFF)                   # a message box waits: press Enter
        elif entry['service'] == 0x02C6:
            waits[0] += 1
            keys(['up', 'down', 'enter', 'esc'], 0)
            keys(script.get(waits[0], ['esc'] if waits[0] > 40 else []), 0xFF)
        elif entry['service'] in (0x1000, 0x1001, 0x2C27, 0x2C45):
            keys(['esc', 'enter'], 0)
        elif entry['service'] == 0x2C35:            # the VGA message box's key: Enter
            keys(['enter'], 0xFF)
        elif entry['service'] == 0x9029:            # the pause: the timer interrupt counts
            if shooting['aiming']:
                shooting['aiming'] = False
            m.ds_write(TIMER, (m.rw(m.DATA_SEG, TIMER) + 8 & 0xFFFF).to_bytes(2, 'little'))
        elif entry['service'] == 0x0D8D:
            if not shooting['aiming']:
                shooting.update(target=shooting['target'] + 1, wait=0, aiming=True)
            shooting['wait'] += 1
            for code in (RIGHT, LEFT, UP, DOWN, TAB, ENTER):
                m.ds_write(KEY + code, b'\0')
            held, waits_held, shot = plan[shooting['target']] if plan else (None, 0, None)
            if held and shooting['wait'] <= waits_held:
                m.ds_write(KEY + held, b'\xff')
            elif shot and shooting['wait'] == waits_held + 1:
                m.ds_write(KEY + shot, b'\xff')
        elif entry['service'] == 0x0DAA:
            m.ds_write(TIMER, (m.rw(m.DATA_SEG, TIMER) + 4 & 0xFFFF).to_bytes(2, 'little'))
        elif entry['service'] == 0x37AC:
            type_key(m, 0x0D)

    recorder = Recorder(m, specs, on_boundary, chunky=vga).install()

    def release_before(uc, addr, size, user):
        if not recorder.pending and held(m, 'esc', 'enter'):
            keys(['esc', 'enter'], 0)

    def release_after(uc, addr, size, user):
        if not recorder.pending:
            keys(['enter'], 0)

    for off, entry in EVENTS:
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, entry=entry: None if recorder.pending else log.append(entry(m)),
                      None, BASE + off, BASE + off)
    m.uc.hook_add(UC_HOOK_CODE, release_before, None, BASE + 0x5169, BASE + 0x5169)
    m.uc.hook_add(UC_HOOK_CODE, release_after, None, BASE + 0x51A1, BASE + 0x51A1)
    m.call(0, 0x8CB0, bx=kind, max_instr=2_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.facility_screen.restype = ctypes.c_int
    lib.update_visible_cells.restype = ctypes.c_int
    fails = []
    recordings = {}
    events = (GameEvent * 1024)()
    outcomes = []
    for label, start, kind, script, settings in SCENARIOS:
        if start not in recordings:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                recordings[start] = pickle.load(f)
        m = capture.restore(recordings[start][0])
        vga = settings.get('vga', False)
        if not vga:
            ega_installation(m)
        m.ds_write(KEY, bytes(128))
        m.ds_write(0x115B, b'\xff' if settings.get('withdrawn') else b'\0')
        if 'ranks' in settings:                     # the rank thresholds: none met before this one
            for i in range(6):
                m.ds_write(0xA9AA + 4 * i, b'\0\0\0\0' if i < settings['ranks'] else b'\xff\xff\xff\xff')
        specs = boundaries(False) + EXTRA + (VGA if vga else [])
        stub_all(m, specs, [off for off, entry in EVENTS])
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 0x10000)
        palette = ctypes.create_string_buffer(768)
        files = Files(m, record=False)
        spans = regions(m)
        ds_base = m.DATA_SEG << 4
        log = []
        cash = m.rw(m.DATA_SEG, 0x117E)
        recorder = run_original(m, specs, kind, script, log, vga, settings.get('range'))
        CASES += 1
        outcomes.append(f'{label}: rank {m.rw(m.DATA_SEG, 0xA9A8)}, ' if kind == RANGE else f'{label}: cash {m.rw(m.DATA_SEG, 0x117E) - cash:+d}, '
                        f'{"treated, " if any(c["service"] == 0x5F06 for c in recorder.calls) else ""}'
                        f'{len(recorder.calls)} calls')
        replay = Replayer(g, mem, planes, spans, ds_base, recorder, files, screen=screen if vga else None)

        @MENU_CALL
        def menu_call(gp, op, a, b, user):
            if replay.serve(op, a if op == 0x02C6 else 0, 0):
                return -1
            return 0

        menu = MenuPlatform(menu_call, None)

        def keyb(offset):
            return ctypes.c_uint8.from_address(g.ds + offset)

        @TEXT_POLL
        def text_poll(gp, phase, ticks, user):
            if vga:
                return replay.serve((0x2C27, 0x2C35, 0x2C45)[phase])
            if phase == 0:
                keyb(KEY + SC['esc']).value = keyb(KEY + SC['enter']).value = 0
                return 0
            if phase == 2:
                keyb(KEY + SC['enter']).value = 0
                return 0
            return replay.serve(0x02C6, ticks)

        text = TextPlatform(text_poll, None)
        menus = GameMenuServices(ctypes.addressof(menu), ctypes.addressof(text), ctypes.addressof(files.host))

        @RESOURCE
        def resource(gp, service, a, b, user):
            return replay.serve(service, a, b)

        resources = Resources(resource, None)
        @KEY_POLL
        def key_poll(gp, user):
            return replay.serve(0x37AC)

        keyboard = KeyboardPlatform(key_poll, None)
        services = FacilityServices(ctypes.addressof(resources), ctypes.addressof(files.host), ctypes.addressof(menus),
                                    None, ctypes.addressof(screen), ctypes.addressof(palette),
                                    ctypes.addressof(keyboard))
        set_clock(lib, m)
        lib.game_events(events, 1024)
        status = lib.facility_screen(ctypes.byref(g), kind, ctypes.byref(services))
        got = [(e.kind, e.a, e.b) for e in events[:lib.game_events(events, 1024)]]
        problem = replay.finished()
        if status or problem:
            fails.append(f'{label}: status {status}; {problem}')
        elif got != log:
            fails.append(f'{label}: sounds differ: C {got[:5]}, original {log[:5]}')
        else:
            error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
            if error:
                fails.append(f'{label}: at the end, memory {error}')
            elif vga and screen.raw != bytes(m.vga.chunky):
                fails.append(f'{label}: at the end, the mode-13h screen differs')
            else:
                compare(label, mem, planes, m, spans, fails)
        if fails:
            return fails
    print('    facility: ' + '; '.join(outcomes))
    return fails
