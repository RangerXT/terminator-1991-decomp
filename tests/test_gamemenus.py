"""The menus opened during play and their options (src/gamemenus.c) against the original.

Each case starts at the top of a recorded main-loop frame with Esc, F10 or Q held; C runs
frame_input_check, the original 0000:05A2. The keys are scripted at the menu's waits
(5776:02C6): Up/Down/Enter/Esc are let go at every wait, then the wait's own presses are
made. Boundaries (tests/boundaries.py): the waits; the points where a menu waits for Esc
and Enter to be let go (4A6F, 4B3A), where both are let go; and, stubbed on both sides,
the host screens and hardware the options call: joystick detection 3A12 (stubbed "found"
or "none") and calibration 38F6, the music driver F494/F4A1, ratings D300 and the damage
panel 5F06. A message box gets Enter at its wait. The inventory, the drop menus and Sarah's
exchange run on stocked lists (STOCK, SARAH) whose names point at resident strings.

Recordings: frameloop (the Terminator) from tests/test_frame.py, and for Sarah's orders
    python tools/capture.py 0000:0155 frameloop_reese --count 16 --skip 2 --ticks 160 --from ai_companion --keys "2:up:60,70:left:20,100:up:50"
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
from boundaries import BASE, Point, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_frame import FRAME_CALL, TEXT_POLL, FrameServices, TextPlatform  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapkey import EVENTS  # noqa: E402

CASES = 0
KEY = 0x5BD9
SC = {'esc': 0x01, 'enter': 0x1C, 'q': 0x10, 'f10': 0x44, 'up': 0x48, 'down': 0x50}
MENU_CALL = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint16,
                             ctypes.c_void_p)


class MenuPlatform(ctypes.Structure):
    _fields_ = [('call', MENU_CALL), ('user', ctypes.c_void_p)]


class GameMenuServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in ('menu', 'text', 'images', 'damage', 'ratings', 'machine')]


def held(m, *names):
    return any(m.ds_read(KEY + SC[n], 1)[0] for n in names)


def boundaries(joystick_found):
    return [
        Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
        Point(0x4A6F, 0x1000, lambda m: held(m, 'esc', 'enter')),
        Point(0x4B3A, 0x1001, lambda m: held(m, 'esc')),
        Routine(0, 0x3A12, stub=b'\xf8\xc3' if joystick_found else b'\xf9\xc3'),   # CLC / STC; RET
        Routine(0, 0x38F6, stub=b'\xc3'),
        Routine(0, 0xF494, stub=b'\xc3'), Routine(0, 0xF4A1, stub=b'\xc3'),
        Routine(0, 0xD300, stub=b'\xc3'), Routine(0, 0x5F06, stub=b'\xc3'),
    ]


def down(n, then):
    """Down at waits 2.., then the key `then` at the next wait."""
    script = {2 + i: ['down'] for i in range(n)}
    script[2 + n] = [then]
    return script


SCENARIOS = [
    # name, recording, key held, joystick found, {menu wait: keys}, what must happen
    ('game menu, Esc', 'frameloop', 'esc', False, {3: ['esc']}, {}),
    ('joystick, none found', 'frameloop', 'esc', False, down(0, 'enter'), {'calls': {0x3A12}, 'not': {0x38F6}}),
    ('joystick, found', 'frameloop', 'esc', True, down(0, 'enter'), {'calls': {0x3A12, 0x38F6}, 'set': {0x5A4F: 1}}),
    ('audio off', 'frameloop', 'esc', False, down(1, 'enter'), {'calls': {0xF494}}),
    ('quit, yes', 'frameloop', 'esc', False, {**down(4, 'enter'), 8: ['enter']}, {'set': {0x1159: 0x55}}),
    ('quit, no', 'frameloop', 'esc', False, {**down(4, 'enter'), 8: ['down'], 9: ['enter']}, {'set': {0x1159: 0}}),
    ('quit, Esc', 'frameloop', 'esc', False, {**down(4, 'enter'), 8: ['esc']}, {'set': {0x1159: 0}}),
    ('new game, yes', 'frameloop', 'esc', False, {**down(5, 'enter'), 9: ['enter']}, {'set': {0x1159: 0xAA}}),
    ('new game, no', 'frameloop', 'esc', False, {**down(5, 'enter'), 9: ['down'], 10: ['enter']}, {'set': {0x1159: 0}}),
    ('ratings', 'frameloop', 'esc', False, {2: ['up'], 3: ['enter']}, {'calls': {0xD300}}),
    ('player menu, Esc', 'frameloop', 'f10', False, {2: ['esc']}, {}),
    ('inventory, Esc', 'frameloop', 'f10', False, {**down(0, 'enter'), 5: ['esc']}, {'actions': 0x7970}),
    ('weapons', 'frameloop', 'f10', False, {2: ['enter'], 3: ['enter'], 5: ['esc']},
     {'stock': 0, 'message': True, 'actions': 0x7970}),
    ('ammunition', 'frameloop', 'f10', False, {2: ['enter'], 3: ['down'], 4: ['enter'], 6: ['esc']},
     {'stock': 0, 'message': True, 'actions': 0x7970}),
    ('two categories in a row', 'frameloop', 'f10', False,
     {2: ['enter'], 3: ['up'], 4: ['up'], 5: ['enter'], 6: ['down'], 7: ['down'], 8: ['down'], 9: ['enter'],
      11: ['esc']}, {'stock': 0, 'message': True, 'actions': 0x7970}),
    ('misc., with cash', 'frameloop', 'f10', False, {2: ['enter'], 3: ['up'], 4: ['enter'], 6: ['esc']},
     {'stock': 1234, 'message': True, 'actions': 0x7970}),
    ('misc., no cash', 'frameloop', 'f10', False, {2: ['enter'], 3: ['up'], 4: ['enter'], 6: ['esc']},
     {'stock': 0, 'message': True, 'actions': 0x7970}),
    ('empty category', 'frameloop', 'f10', False, {2: ['enter'], 3: ['enter'], 5: ['esc']},
     {'message': True, 'actions': 0x7970}),
    ('drop the 2nd weapon', 'frameloop', 'f10', False, {**down(2, 'enter'), 5: ['enter'], 6: ['down'], 7: ['enter']},
     {'stock': 0, 'actions': 0x7994, 'dropped': 0x06}),
    ('drop the last of one', 'frameloop', 'f10', False, {**down(2, 'enter'), 5: ['enter'], 6: ['enter']},
     {'stock': 0, 'actions': 0x7994, 'dropped': 0x01}),
    ('drop misc. line 1', 'frameloop', 'f10', False, {**down(2, 'enter'), 5: ['up'], 6: ['enter'], 7: ['enter']},
     {'stock': 0, 'actions': 0x7994, 'dropped': 0x10}),
    ('drop misc. line 2', 'frameloop', 'f10', False,
     {**down(2, 'enter'), 5: ['up'], 6: ['enter'], 7: ['down'], 8: ['enter']},
     {'stock': 0, 'actions': 0x7994, 'dropped': 0x20}),
    ('nothing to drop', 'frameloop', 'f10', False, {**down(2, 'enter'), 5: ['enter']}, {'message': True}),
    ('physical status', 'frameloop', 'f10', False, down(1, 'enter'), {'calls': {0x5F06}}),
    ('drop item, Esc', 'frameloop', 'f10', False, {**down(2, 'enter'), 7: ['esc']}, {'actions': 0x7988}),
    ('special action, nothing', 'frameloop', 'f10', False, down(3, 'enter'), {'message': True}),
    ('Sarah, Esc', 'frameloop_reese', 'q', False, {2: ['esc']}, {}),
    ('Sarah, stay', 'frameloop_reese', 'q', False, down(0, 'enter'), {'set': {0x11BE: 0}}),
    ('Sarah, run away', 'frameloop_reese', 'q', False, down(1, 'enter'), {'set': {0x11BE: 1}}),
    ('Sarah, follow', 'frameloop_reese', 'q', False, down(2, 'enter'), {'set': {0x11BE: 2}}),
    ('Sarah, order 3, Esc', 'frameloop_reese', 'q', False, {**down(3, 'enter'), 6: ['esc']}, {'actions': 0x79E4}),
    ('Sarah, order 4, Esc', 'frameloop_reese', 'q', False, {2: ['up'], 3: ['enter'], 5: ['esc']},
     {'actions': 0x79E4}),
    ('Sarah, order 3, a weapon', 'frameloop_reese', 'q', False, {**down(3, 'enter'), 6: ['enter'], 7: ['enter']},
     {'stock': 0, 'sarah': True, 'load': 20, 'actions': 0x79F0, 'moved': True}),
    ('Sarah, order 4, a weapon', 'frameloop_reese', 'q', False, {2: ['up'], 3: ['enter'], 4: ['enter'], 5: ['enter']},
     {'stock': 0, 'sarah': True, 'actions': 0x79F0, 'moved': True}),
    ('Sarah, order 4, ammunition', 'frameloop_reese', 'q', False,
     {2: ['up'], 3: ['enter'], 4: ['down'], 5: ['enter'], 6: ['enter']},
     {'stock': 0, 'sarah': True, 'actions': 0x79F0, 'moved': True}),
    ('Sarah, order 4, too heavy', 'frameloop_reese', 'q', False,
     {2: ['up'], 3: ['enter'], 4: ['enter'], 5: ['enter']}, {'stock': 0, 'sarah': True, 'load': 34, 'message': True}),
    ('Sarah, order 3, load below 0', 'frameloop_reese', 'q', False,
     {**down(3, 'enter'), 6: ['enter'], 7: ['enter']}, {'stock': 0, 'sarah': True, 'load': 0, 'message': True}),
    ('Sarah, nothing to exchange', 'frameloop_reese', 'q', False,
     {**down(3, 'enter'), 6: ['down'], 7: ['down'], 8: ['enter']}, {'stock': 0, 'sarah': True, 'message': True}),
]
# Stocked inventory for the viewer cases: 6-byte records (name, id, -, category, count) at
# DS:05B0. Names point at resident strings; the viewer only copies them. Ids 10 and A5 and
# categories 1-5 are left out of "Misc."; a count above 127 prints as negative.
STOCK = [(0x8448, 0x01, 1, 1), (0x8452, 0x02, 2, 12), (0x845D, 0x03, 3, 3), (0x8469, 0x10, 6, 2),
         (0x8474, 0x20, 6, 200), (0x8479, 0x21, 0, 7), (0x8483, 0xA5, 7, 1), (0x81AB, 0x05, 5, 99),
         (0x8448, 0x06, 1, 10)]
FRAMES = (0, 9)


SARAH = [(0x845D, 0x30, 1, 2), (0x8469, 0x31, 2, 1), (0x8474, 0x32, 1, 1)]


def stock(m, cash, sarah=False, load=0):
    at = 0x05B0
    for name, ident, category, count in STOCK:
        m.ds_write(at, struct.pack('<HBBBB', name, ident, ident % 5 + 1, category, count))
        at += 6
    m.ds_write(at, b'\0\0')
    if sarah:
        to = 0x085C
        for name, ident, category, count in SARAH:
            m.ds_write(to, struct.pack('<HBBBB', name, ident, ident % 3 + 1, category, count))
            to += 6
        m.ds_write(to, bytes(6))
        m.ds_write(0x0402, struct.pack('<H', load))
    m.ds_write(0x03A2, struct.pack('<H', at))  # the end of the list
    m.ds_write(0x117E, struct.pack('<H', cash))


def run_original(m, specs, script, log):
    waits = [0]

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
        elif entry['service'] in (0x1000, 0x1001):
            keys(['esc', 'enter'], 0)

    recorder = Recorder(m, specs, on_boundary).install()

    def release_before(uc, addr, size, user):       # a message box first waits for Enter/Esc up
        if not recorder.pending and held(m, 'esc', 'enter'):
            keys(['esc', 'enter'], 0)

    def release_after(uc, addr, size, user):
        if not recorder.pending:
            keys(['enter'], 0)

    for off, entry in EVENTS:
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, entry=entry: None if recorder.pending else log.append(entry(m)),
                      None, BASE + off, BASE + off)
    m.uc.hook_add(UC_HOOK_CODE, release_before, None, BASE + 0x5169, BASE + 0x5169)
    m.uc.hook_add(UC_HOOK_CODE, release_after, None, BASE + 0x5195, BASE + 0x5195)
    m.call(0, 0x05A2, max_instr=500_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.frame_input_check.restype = ctypes.c_int
    fails = []
    recordings = {}
    events = (GameEvent * 512)()
    outcomes = {}
    for label, start, key, found, script, expect in SCENARIOS:
        if start not in recordings:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                recordings[start] = pickle.load(f)
        for index in FRAMES:
            where = f'{start} {index}, {label}'
            m = capture.restore(recordings[start][index])
            for off in (0x0200, 0x0201, 0x8096, 0xE1F2):   # no warning, reload overlay or message
                m.ds_write(off, b'\x00')
            m.ds_write(KEY + SC[key], b'\xff')
            if 'stock' in expect:
                stock(m, expect['stock'], expect.get('sarah', False), expect.get('load', 0))
            lists = m.ds_read(0x05B0, 0x400)
            specs = boundaries(found)
            stub_all(m, specs, [off for off, entry in EVENTS])
            g, mem, planes = make_game(m)
            files = Files(m, record=False)
            spans = regions(m)
            ds_base = m.DATA_SEG << 4
            log = []
            recorder = run_original(m, specs, script, log)
            CASES += 1
            services = {c['service'] for c in recorder.calls}
            reached = (expect.get('calls', set()) <= services and not expect.get('not', set()) & services
                       and all(m.ds_read(v, 1)[0] == value for v, value in expect.get('set', {}).items())
                       and m.rw(m.DATA_SEG, 0x7816) == expect.get('actions', m.rw(m.DATA_SEG, 0x7816))
                       and ('dropped' not in expect or m.ds_read(0x0253 + 10, 1)[0] == expect['dropped'])
                       and (not expect.get('moved') or m.ds_read(0x05B0, 0x400) != lists)
                       and (not expect.get('message') or any(c['caller'] == (0, 0x5185) for c in recorder.calls)))
            if not reached:
                fails.append(f'{where}: the script did not reach what it is meant to test')
                continue
            outcomes[label] = outcomes.get(label, 0) + 1

            replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)

            @MENU_CALL
            def menu_call(gp, op, a, b, user):
                if replay.serve(op, a if op == 0x02C6 else 0, 0):
                    return -1
                return 1 if op == 0x3A12 and replay.last['carry'] else 0

            menu = MenuPlatform(menu_call, None)

            def keyb(offset):
                return ctypes.c_uint8.from_address(g.ds + offset)

            @TEXT_POLL
            def text_poll(gp, phase, ticks, user):
                if phase == 0:
                    keyb(KEY + SC['esc']).value = keyb(KEY + SC['enter']).value = 0
                    return 0
                if phase == 2:
                    keyb(KEY + SC['enter']).value = 0
                    return 0
                return replay.serve(0x02C6, ticks)

            text = TextPlatform(text_poll, None)
            menus = GameMenuServices(ctypes.addressof(menu), ctypes.addressof(text), ctypes.addressof(files.host))
            no_call = FRAME_CALL(lambda *a: 0xFFFFFFFF)
            host = FrameServices(None, None, no_call, None, None, 0, None, None, ctypes.addressof(menus))
            set_clock(lib, m)
            lib.game_events(events, 512)
            status = lib.frame_input_check(ctypes.byref(g), ctypes.byref(host))
            got = [(e.kind, e.a, e.b) for e in events[:lib.game_events(events, 512)]]
            problem = replay.finished()
            if status or problem:
                fails.append(f'{where}: status {status}; {problem}')
            elif got != log:
                fails.append(f'{where}: sounds or border differ: C {got[:5]}, original {log[:5]}')
            else:
                error = difference(mem.raw, bytes(m.uc.mem_read(0, 0xA0000)), spans, ds_base)
                if error:
                    fails.append(f'{where}: at the end, memory {error}')
                else:
                    compare(where, mem, planes, m, spans, fails)
            if len(fails) > 4:
                return fails
    print(f'    gamemenus: {CASES} cases, each reaching what it tests ({len(outcomes)} scenarios x {len(FRAMES)} frames)')
    return fails
