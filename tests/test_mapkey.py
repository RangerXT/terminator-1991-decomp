"""The M key's map screen (map_screen, src/mapkey.c) against the original, from live frames.

Each case starts at the top of a recorded main-loop frame with M (and maybe Alt or Ctrl)
held; C runs frame_input_check, the original 0000:05A2. Boundaries (tests/boundaries.py):
page selection 0C6B, the map setup's image and file loads and palette 6962/FAAF/FACE/7AB6
(only when called from CE00..D000; elsewhere C loads through ImageIO itself), the default
palette 7AAF, the video mode switches (int 10h at 7A35 and CF77), the retrace waits
0D8D/0DAA and 5776:02C6, the movie player B210, the companion panels 57E7/57D4 and the
arrival follow-up 057C. The waits, the movie, the panels and 057C are stubbed (nothing
happens in them) on both sides. The scripted keys are written at chosen retrace waits.
Cell loading and camera resets inside fast travel run in C (update_visible_cells,
camera_reset) as in the original. At the end all memory, the screen, the card registers,
the sounds and the border changes are compared.

Recordings: those of tests/test_frame.py.
"""
import ctypes
import gzip
import os
import pickle
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from boundaries import BASE, Inline, Recorder, Replayer, Routine, difference, stub_all  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_frame import FRAME_CALL, TEXT_POLL, FrameServices, GameplayServices, TextPlatform  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_vehicletransition import VehicleServices  # noqa: E402

CASES = 0
KEY = 0x5BD9
SC = {'esc': 0x01, 'enter': 0x1C, 'ctrl': 0x1D, 'alt': 0x38, 'rshift': 0x36, 'f': 0x21, 'h': 0x23, 'm': 0x32,
      'up': 0x48, 'left': 0x4B, 'right': 0x4D, 'down': 0x50}
WAIT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint8, ctypes.c_void_p)
CALL = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(Game), ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p)


class MapPlatform(ctypes.Structure):
    _fields_ = [('wait', WAIT), ('user', ctypes.c_void_p)]


class Services(ctypes.Structure):          # TravelServices and OpponentServices
    _fields_ = [('call', CALL), ('user', ctypes.c_void_p)]


class MapKeyServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in
                ('resources', 'platform', 'images', 'text', 'travel', 'opponents', 'vehicle')]


MAP_SETUP = ((0xCE00, 0xD000),)
BOUNDARIES = [
    Routine(0, 0x0C6B, registers=('ax',)),
    Routine(0, 0x6962, registers=('dx',), callers=MAP_SETUP),
    Routine(0, 0xFAAF, registers=('dx', 'bx'), callers=MAP_SETUP),
    Routine(0, 0xFACE, registers=('dx', 'bx'), callers=MAP_SETUP),
    Routine(0, 0x7AB6, callers=MAP_SETUP),
    Routine(0, 0x7AAF),
    Routine(0, 0x0D8D, stub=b'\xc3'), Routine(0, 0x0DAA, stub=b'\xc3'),
    Routine(0x5776, 0x02C6, far=True, stub=b'\xcb', registers=('cx',)),
    Routine(0, 0xB210, stub=b'\xc3', argument=0xDE34),
    Routine(0, 0x57E7, stub=b'\xc3'), Routine(0, 0x57D4, stub=b'\xc3'), Routine(0, 0x057C, stub=b'\xc3'),
    Inline(0x7A35, 0x7A37, 0xFF10), Inline(0xCF77, 0xCF79, 0xFF10),
]
EVENTS = [(0x89A2, lambda m: (1, m.ax() & 255, m.ds_read(0x80E9, 1)[0])),
          (0x0A4F, lambda m: (5, m.r(dosemu.UC_X86_REG_BX) & 255,
                              m.ds_read(0x1510 + (m.r(dosemu.UC_X86_REG_BX) & 255), 1)[0]))]
WAITS = (0x0D8D, 0x0DAA)


def run_original(m, script, log):
    """Run 05A2; returns the recorder (its calls) and the number of world steps."""
    state = {'waits': 0, 'held': False, 'steps': 0}
    last_press = max(script) if script else 0

    def keys(writes):
        for name, value in writes:
            m.ds_write(KEY + SC[name], bytes([value]))

    def on_boundary(entry):
        if entry['service'] in WAITS:
            state['waits'] += 1
            presses = list(script.get(state['waits'], ()))
            if state['waits'] > last_press + 60:
                presses.append(('esc', 0xFF))  # the map came back (place off the map): leave it
            keys(presses)
            state['held'] = state['held'] or any(value for name, value in presses)
        elif state['held'] and state['waits'] >= last_press:
            state['held'] = False             # the first other boundary after the map: let go
            keys([(name, 0) for name in SC])
        if entry['service'] == 0x02C6 and entry['caller'] == (0, 0x5185):
            keys([('enter', 0xFF)])           # a message box waits: press Enter

    recorder = Recorder(m, BOUNDARIES, on_boundary).install()

    def release_before(uc, addr, size, user):   # a message box first waits for Enter/Esc up
        if not recorder.pending and (m.ds_read(KEY + SC['esc'], 1)[0] or m.ds_read(KEY + SC['enter'], 1)[0]):
            keys([('esc', 0), ('enter', 0)])

    def release_after(uc, addr, size, user):
        if not recorder.pending:
            keys([('enter', 0)])

    def world_step(uc, addr, size, user):
        state['steps'] += 1

    for off, entry in EVENTS:
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, entry=entry: None if recorder.pending else log.append(entry(m)),
                      None, BASE + off, BASE + off)
    m.uc.hook_add(UC_HOOK_CODE, release_before, None, BASE + 0x5169, BASE + 0x5169)
    m.uc.hook_add(UC_HOOK_CODE, release_after, None, BASE + 0x5195, BASE + 0x5195)
    m.uc.hook_add(UC_HOOK_CODE, world_step, None, BASE + 0xB5F9, BASE + 0xB5F9)
    m.call(0, 0x05A2, max_instr=2_000_000_000)
    if recorder.pending:
        raise RuntimeError('a boundary call did not return')
    return recorder, state['steps']


SCENARIOS = [
    # name, keys held on entry, {retrace wait number: [(key, value)]}
    ('Esc', ['m'], {4: [('esc', 0xFF)]}),
    ('homing', ['m'], {2: [('right', 0xFF), ('rshift', 0xFF)], 26: [('right', 0), ('h', 0xFF)]}),
    ('fast travel', ['m'], {2: [('up', 0xFF), ('rshift', 0xFF)], 50: [('up', 0), ('f', 0xFF)]}),
    ('fast travel, short', ['m'], {2: [('left', 0xFF)], 14: [('left', 0), ('f', 0xFF)]}),
    ('area map, Esc', ['m', 'alt'], {3: [('esc', 0xFF)]}),
    ('area map, homing', ['m', 'alt'], {2: [('down', 0xFF)], 20: [('down', 0), ('h', 0xFF)]}),
    ('area map, fast travel', ['m', 'alt'], {2: [('right', 0xFF), ('rshift', 0xFF)], 32: [('right', 0), ('f', 0xFF)]}),
    ('Ctrl+M', ['m', 'ctrl'], {}),
]
STARTS = [('frameloop', 0), ('frameloop', 25), ('frameloop_driving', 12), ('frameloop_opponent', 10)]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.frame_input_check.restype = ctypes.c_int
    lib.update_visible_cells.restype = ctypes.c_int
    lib.camera_reset.restype = ctypes.c_int
    fails = []
    recordings = {}
    events = (GameEvent * 4096)()
    seen = {}
    steps_total = 0
    for start, index in STARTS:
        if start not in recordings:
            with gzip.open(os.path.join(capture.CAPDIR, start + '.pkl.gz'), 'rb') as f:
                recordings[start] = pickle.load(f)
        for label, held, script in SCENARIOS:
            where = f'{start} {index}, {label}'
            m = capture.restore(recordings[start][index])
            for key in held:
                m.ds_write(KEY + SC[key], b'\xff')
            for off in (0x0200, 0x0201, 0x8096, 0xE1F2):   # no warning, reload overlay or message
                m.ds_write(off, b'\x00')
            stub_all(m, BOUNDARIES, [off for off, entry in EVENTS])
            g, mem, planes = make_game(m)
            files = Files(m, record=False)
            spans = regions(m)
            ds_base = m.DATA_SEG << 4
            log = []
            player = m.rw(m.DATA_SEG, 0x03A0)
            before = m.ds_read(player + 34, 12)
            recorder, steps = run_original(m, script, log)
            calls = recorder.calls
            CASES += 1
            action = chr(m.ds_read(0xE25A, 1)[0] or 0x2D)
            outcome = ('travelled' if m.ds_read(player + 34, 12) != before else 'stayed') + f' after {action}'
            if any(c['service'] == 0x02C6 and c['a'] == 5 for c in calls):
                outcome += ', message box'
            if steps:
                outcome += ', world steps'
            seen[outcome] = seen.get(outcome, 0) + 1
            steps_total += steps

            replay = Replayer(g, mem, planes, spans, ds_base, recorder, files)

            @RESOURCE
            def resource(gp, service, a, b, user):
                return replay.serve(service, a, b)

            resources = Resources(resource, None)

            @WAIT
            def wait(gp, high, user):
                return replay.serve(0x0D8D if high else 0x0DAA)

            platform = MapPlatform(wait, None)

            def key(offset):
                return ctypes.c_uint8.from_address(g.ds + offset)

            @TEXT_POLL
            def text_poll(gp, phase, ticks, user):
                if phase == 0:
                    key(KEY + SC['esc']).value = key(KEY + SC['enter']).value = 0
                    return 0
                if phase == 2:
                    key(KEY + SC['enter']).value = 0
                    return 0
                return replay.serve(0x02C6, ticks)

            text = TextPlatform(text_poll, None)

            @CALL
            def travel_call(gp, service, arg, user):
                return 0 if replay.serve(service) == 0 else 0xFFFFFFFF

            travel = Services(travel_call, None)
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
            services = MapKeyServices(ctypes.addressof(resources), ctypes.addressof(platform),
                                      ctypes.addressof(files.host), ctypes.addressof(text),
                                      ctypes.addressof(travel), ctypes.addressof(opponents),
                                      ctypes.addressof(vehicle))
            gameplay = GameplayServices(text=ctypes.addressof(text), vehicle=ctypes.addressof(vehicle))
            no_call = FRAME_CALL(lambda *a: 0xFFFFFFFF)
            host = FrameServices(ctypes.addressof(gameplay), None, no_call, None, None, 0, ctypes.addressof(services))
            set_clock(lib, m)
            lib.game_events(events, 4096)
            status = lib.frame_input_check(ctypes.byref(g), ctypes.byref(host))
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
                else:
                    compare(where, mem, planes, m, spans, fails)
            if len(fails) > 4:
                return fails
    print(f'    mapkey: {CASES} cases, {steps_total} world steps in all; '
          + ', '.join(f'{count} {outcome}' for outcome, count in sorted(seen.items())))
    return fails
