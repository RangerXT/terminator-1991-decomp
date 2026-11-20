"""Native gameplay update through target collection using unchanged live captures."""
import ctypes
import gzip
import os
import pickle
import struct
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(__file__))
from test_blast import GameEvent, set_clock
from test_drawlist import capture, compare, dosemu, make_game
from test_vehicletransition import VehicleServices

CASES = 0


class GameplayServices(ctypes.Structure):
    _fields_ = [(name, ctypes.c_void_p) for name in (
        'text', 'keys', 'hud', 'movie', 'sound', 'vehicle', 'stream', 'shop',
        'menu', 'world', 'joystick', 'joystick_user')]


def run(ctx):
    global CASES
    with gzip.open(os.path.join(capture.CAPDIR, 'gameplay_update_live.pkl.gz'), 'rb') as file:
        states = pickle.load(file)

    def drain():
        events = (GameEvent * 512)()
        count = ctx.lib.game_events(events, len(events))
        return [(event.kind, event.a, event.b) for event in events[:count]]

    vehicle = VehicleServices()
    services = GameplayServices(vehicle=ctypes.addressof(vehicle))
    failures = []

    for index, state in enumerate(states * 5):
        machine = capture.restore(state)
        events = []
        flight = index // len(states)
        if flight:
            actor = machine.rw(machine.DATA_SEG, 0x03A0)
            position = (machine.rw(machine.DATA_SEG, actor), machine.rw(machine.DATA_SEG, actor + 4))
            machine.ds_write(0x0373, bytes([255]))
            machine.ds_write(0x0367, struct.pack('<6H', position[0], 40, position[1], 64, 128,
                                                2 if flight == 1 else 1))
            for slot in range(30):
                machine.ds_write(0xB526 + 10 * slot, bytes([255, 255]))
            if flight >= 3:
                machine.ds_write(0x115D, bytes([255]))
                machine.ds_write(0x0364, bytes([15]))
                machine.ds_write(0x11A0, bytes(2))
                machine.ds_write(0x10F0, bytes(72))
                machine.ds_write(0x119C, bytes(2))
            if flight == 4:
                machine.ds_write(0xB520, struct.pack('<5H', 10, 100, 20, 96, 3))

        def stub(offset, callback=None):
            machine.wb(dosemu.LOAD_SEG, offset, bytes([0xC3]))
            if callback:
                address = (dosemu.LOAD_SEG << 4) + offset
                machine.uc.hook_add(UC_HOOK_CODE, lambda *_: callback(), None, address, address)

        inherited_dx = []
        watch = (dosemu.LOAD_SEG << 4) + 0x0897
        machine.uc.hook_add(UC_HOOK_CODE, lambda *_: inherited_dx.append(machine.r(dosemu.UC_X86_REG_DX)),
                            None, watch, watch)
        stub(0x89A2, lambda: events.append((1, machine.ax() & 255, machine.ds_read(0x80E9, 1)[0])))
        stub(0x0A4F, lambda: events.append((5, machine.r(dosemu.UC_X86_REG_BX) & 255,
                                           machine.ds_read(0x1514, 1)[0])))
        game, memory, planes = make_game(machine)
        drain()
        set_clock(ctx.lib, machine)
        native_dx = ctypes.c_uint32()
        result = ctx.lib.gameplay_update_controls_dx(ctypes.byref(game), ctypes.byref(services), 0,
                                                   ctypes.byref(native_dx))
        capture.run_to_return(machine)
        if len(inherited_dx) != 1:
            return [f'gameplay {index}: did not reach one projectile phase']
        if not result and native_dx.value != inherited_dx[0]:
            return [f'gameplay {index}: inherited DX {native_dx.value:04X}/{inherited_dx[0]:04X}']
        if not result:
            result = ctx.lib.gameplay_update_projectiles(ctypes.byref(game), native_dx.value)
        CASES += 1
        native_events = drain()
        if result or events != native_events:
            return [f'gameplay {index}: status={result}, events={native_events}/{events}']
        if flight >= 3 and machine.rw(machine.DATA_SEG, 0x11A0) != 1:
            return [f'gameplay {index}: unguided launch coverage missing']
        compare(f'gameplay {index}', memory, planes, machine, failures)
        if failures:
            return failures
    return failures
