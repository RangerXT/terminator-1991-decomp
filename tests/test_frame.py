"""game_frame (src/frame.c) against the original main loop 0000:0155: whole frames.

Each recording is the machine at the top of the main loop in a live single-player game.
The C code runs one frame (game_frame); the original runs from 0155 until it comes back
to 0155 for the next frame (or leaves the loop at 024A). Compared afterwards: all
conventional memory except the stack, the four screen planes and the card registers, the
sounds started, border changes, palette reloads, and the return value.

Captures: python tools/capture.py 0000:0155 frameloop --count 40 --skip 4 --ticks 400 --keys "2:up:120,130:right:30,170:up:150,330:left:40"
          python tools/capture.py 0000:0155 frameloop_armed --count 30 --skip 2 --ticks 260 --from weapon_firing_fixture --keys "2:enter:10,20:up:40,30:tab:6,70:enter:30,110:right:10,130:tab:40"
          python tools/capture.py 0000:0155 frameloop_opponent --count 30 --skip 2 --ticks 260 --from opponent_near --keys "2:up:60,70:left:20,100:up:60"
          python tools/capture.py 0000:0155 frameloop_driving --count 30 --skip 2 --ticks 260 --from driving_controls --keys "2:home:10,14:up:80,100:right:20,130:up:60"
(one at a time: capture.py uses a shared temporary file)

Variants of each recording: as recorded; Alt+1, Alt+2 and Alt+3 held (detail level); the
timed message running out this frame; the end-of-frame border, palette and message
requests set.
"""
import ctypes
import gzip
import os
import pickle
import struct
import sys

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EFLAGS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture  # noqa: E402
import dosemu  # noqa: E402
from test_blast import GameEvent, set_clock  # noqa: E402
from test_drawlist import Game, make_game  # noqa: E402
from test_hudcompose import HudCall, HudServices  # noqa: E402
from test_imageload import Files, compare, regions  # noqa: E402
from test_mapsetupreal import RESOURCE, Resources  # noqa: E402
from test_vehicletransition import VehicleServices  # noqa: E402

CASES = 0
RECORDINGS = ('frameloop', 'frameloop_armed', 'frameloop_opponent', 'frameloop_driving')
BASE = dosemu.LOAD_SEG << 4
KEY_ENTER = 0x5BD9 + 0x1C
KEY_ESC = 0x5BD9 + 0x01
FRAME_CALL = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.POINTER(Game), ctypes.c_uint16, ctypes.c_void_p)
TEXT_POLL = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game), ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p)


class TextPlatform(ctypes.Structure):
    _fields_ = [('poll', TEXT_POLL), ('user', ctypes.c_void_p)]


class GameplayServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in (
        'text', 'keys', 'hud', 'movie', 'sound', 'vehicle', 'stream', 'shop',
        'menu', 'world', 'joystick', 'joystick_user')]


class FrameServices(ctypes.Structure):
    _fields_ = [('gameplay', ctypes.c_void_p), ('hud', ctypes.c_void_p), ('call', FRAME_CALL),
                ('user', ctypes.c_void_p), ('chunky_screen', ctypes.c_void_p), ('shop_entry_sp', ctypes.c_uint16),
                ('map', ctypes.c_void_p), ('phone', ctypes.c_void_p), ('menus', ctypes.c_void_p)]


def run_original(m, log):
    """One iteration of the main loop from 0155; returns 1 if it left the loop, else 0."""
    stubs = (0x89A2, 0x0A4F, 0x7AB6, 0x0D8D, 0x0DAA)
    code = {offset: m.rb(dosemu.LOAD_SEG, offset, 1) for offset in stubs}
    try:
        return run_stubbed(m, log)
    finally:
        for offset, byte in code.items():           # the comparison covers the code too
            m.wb(dosemu.LOAD_SEG, offset, byte)


def run_stubbed(m, log):
    for offset, entry in ((0x89A2, lambda: (1, m.ax() & 255, m.ds_read(0x80E9, 1)[0])),
                          (0x0A4F, lambda: (5, m.r(dosemu.UC_X86_REG_BX) & 255,
                                            m.ds_read(0x1510 + (m.r(dosemu.UC_X86_REG_BX) & 255), 1)[0])),
                          (0x7AB6, lambda: ('palette',))):
        m.wb(dosemu.LOAD_SEG, offset, bytes([0xC3]))
        m.uc.hook_add(UC_HOOK_CODE, lambda uc, a, s, u, entry=entry: log.append(entry()), None,
                      BASE + offset, BASE + offset)
    for offset in (0x0D8D, 0x0DAA):                 # waits for the vertical retrace; the host's in C
        m.wb(dosemu.LOAD_SEG, offset, bytes([0xC3]))
    # A message box first waits until Enter and Esc are up (both are let go at once), then for
    # one of them: press Enter at the first wait and let it go after.
    def release(*_):
        if m.ds_read(KEY_ESC, 1)[0] or m.ds_read(KEY_ENTER, 1)[0]:
            log.append(('key release',))
            m.ds_write(KEY_ESC, b'\x00')
            m.ds_write(KEY_ENTER, b'\x00')

    m.uc.hook_add(UC_HOOK_CODE, release, None, BASE + 0x5169, BASE + 0x5169)
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: (log.append(('key wait',)), m.ds_write(KEY_ENTER, b'\xff')),
                  None, BASE + 0x5180, BASE + 0x5180)
    m.uc.hook_add(UC_HOOK_CODE, lambda *_: m.ds_write(KEY_ENTER, b'\x00'), None, BASE + 0x5195, BASE + 0x5195)
    state = {'stop': None}

    def stop(uc, address, size, user):
        state['stop'] = address - BASE
        uc.emu_stop()

    m.uc.reg_write(UC_X86_REG_EFLAGS, m.uc.reg_read(UC_X86_REG_EFLAGS) & ~dosemu.IF_ & 0xFFFF)
    m.pending = None
    m.step(0, 1)                                    # leave 0155 before watching for it
    m.uc.hook_add(UC_HOOK_CODE, stop, None, BASE + 0x0155, BASE + 0x0155)
    m.uc.hook_add(UC_HOOK_CODE, stop, None, BASE + 0x024A, BASE + 0x024A)
    for _ in range(400):
        m.step(0, 1_000_000)
        if m.pending is not None:
            m._apply_pending()
            if m.blocked:
                raise RuntimeError(m.blocked)
        if state['stop'] is not None:
            return 1 if state['stop'] == 0x024A else 0
    raise RuntimeError(f'the frame did not finish: {m.file_addr()}')


def variants():
    def keys(*scancodes):
        def change(m):
            for sc in scancodes:
                m.ds_write(0x5BD9 + sc, b'\xff')
        return change

    def timed_message(m):
        m.ds_write(0xEA2E, struct.pack('<H', 1))

    def requests(m):
        m.ds_write(0x7BD5, b'\xff')
        m.ds_write(0x01DD, b'\xff')

    def messages(m):
        m.ds_write(0x01DC, b'\xff')
        m.ds_write(0xE1F2, b'\xff')

    return [('as recorded', None), ('Alt+1', keys(0x38, 0x02)), ('Alt+2', keys(0x38, 0x03)),
            ('Alt+3', keys(0x38, 0x04)), ('timed message', timed_message), ('border and palette', requests),
            ('map and 0343 messages', messages)]


def run(ctx):
    global CASES
    lib = ctx.lib
    lib.game_frame.restype = ctypes.c_int
    lib.image_hud_service.restype = ctypes.c_uint32
    lib.image_hud_service.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p]
    fails = []
    states = []
    for name in RECORDINGS:
        with gzip.open(os.path.join(capture.CAPDIR, name + '.pkl.gz'), 'rb') as f:
            states += [(name, n, st) for n, st in enumerate(pickle.load(f))]
    events = (GameEvent * 512)()
    ended = 0
    seen = {}
    for name, n, st in states:
        for label, change in variants():
            m = capture.restore(st)
            if change:
                change(m)
            g, mem, planes = make_game(m)
            files = Files(m, record=False)

            vm = dosemu.Machine()
            vm.vga.mode = m.vga.mode
            vm.vga.crtc[:] = m.vga.crtc[:]

            @RESOURCE
            def display(gp, op, a, b, user):
                if op == 0xFF05:            # BIOS select video page, as the original does
                    vm.w(dosemu.UC_X86_REG_AX, 0x0500 | a)
                    vm._video()
                    ctypes.c_uint8.from_address(g.mem + 0x462).value = vm.rb(0x40, 0x62, 1)[0]
                return 0

            native_log = []

            @TEXT_POLL
            def text_poll(gp, phase, ticks, user):
                key = lambda offset: ctypes.c_uint8.from_address(g.ds + offset)
                if phase == 0:              # waiting until Enter and Esc are up
                    if key(KEY_ESC).value or key(KEY_ENTER).value:
                        native_log.append(('key release',))
                    key(KEY_ESC).value = key(KEY_ENTER).value = 0
                elif phase == 1:            # waiting for the key
                    native_log.append(('key wait',))
                    ctypes.c_uint8.from_address(g.ds + KEY_ENTER).value = 0xFF
                elif phase == 2:            # waiting for its release
                    ctypes.c_uint8.from_address(g.ds + KEY_ENTER).value = 0
                return 0

            text = TextPlatform(text_poll, None)
            resources = Resources(display, None)
            vehicle = VehicleServices()
            vehicle.display = ctypes.pointer(resources)
            vehicle.images = ctypes.pointer(files.host)
            gameplay = GameplayServices(text=ctypes.addressof(text), vehicle=ctypes.addressof(vehicle))

            @HudCall
            def hud_service(gp, op, arg, user):
                return lib.image_hud_service(gp, op, arg, ctypes.byref(files.host))

            hud = HudServices(hud_service, None)

            @FRAME_CALL
            def frame_call(gp, op, user):
                if op == 0x7AB6:
                    native_log.append(('palette',))
                    return 0
                return 0xFFFFFFFF

            host = FrameServices(ctypes.addressof(gameplay), ctypes.addressof(hud), frame_call, None, None, 0)
            set_clock(lib, m)
            lib.game_events(events, 512)
            status = lib.game_frame(ctypes.byref(g), ctypes.byref(host))
            got = native_log + [(e.kind, e.a, e.b) for e in events[:lib.game_events(events, 512)]]

            original_log = []
            left = run_original(m, original_log)
            CASES += 1
            where = f'{name} {n}, {label}'
            for entry in set(e[0] for e in original_log):
                seen[entry] = seen.get(entry, 0) + 1
            if status < 0:
                fails.append(f'{where}: game_frame returned {status}')
                continue
            ended += status
            if status != left:
                fails.append(f'{where}: C says {"end" if status else "continue"}, original '
                             f'{"left" if left else "stayed in"} the loop')
                continue
            if sorted(map(str, got)) != sorted(map(str, original_log)):
                fails.append(f'{where}: requests differ: C {got[:6]}, original {original_log[:6]}')
                continue
            if vm.vga.crtc != m.vga.crtc:
                fails.append(f'{where}: displayed start address differs')
            compare(where, mem, planes, m, regions(m), fails)
            if len(fails) > 6:
                return fails
    kinds = {1: 'with sounds', 5: 'with border changes', 'palette': 'with a palette reload',
             'key wait': 'with a message box'}
    print(f'    frame: {CASES} frames from {len(states)} recordings; {ended} ended the session; '
          + ', '.join(f'{seen.get(k, 0)} {text}' for k, text in kinds.items()))
    return fails
