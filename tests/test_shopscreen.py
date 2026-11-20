"""813E setup through 82C4 exit with original images, masks and sound groups."""
import ctypes
import os
from pathlib import Path
import struct
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.dirname(__file__))
from test_camera import Platform as Hardware
from test_blast import GameEvent, set_clock
from test_drawlist import Game, dosemu, make_game
from test_imageload import Files, check_memory, compare, regions, trace_dos
from test_mapsetupreal import RESOURCE, Resources
from test_menu import Call, Platform as MenuPlatform
from test_polyfill import planes_of, screen_differences
from test_shopconfirm import ShopServices
from test_sound import SoundServices

CASES = 0
TEXT_POLL = 0x1100
TextPoll = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(Game),
                           ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p)


class TextPlatform(ctypes.Structure):
    _fields_ = [('poll', TextPoll), ('user', ctypes.c_void_p)]


class ShopScreenServices(ctypes.Structure):
    _fields_ = [('actions', ctypes.POINTER(ShopServices)),
                ('platform', ctypes.POINTER(Resources)),
                ('sound', ctypes.POINTER(SoundServices)),
                ('extra', ctypes.c_void_p), ('palette', ctypes.c_void_p), ('facility', ctypes.c_void_p)]


def boundary_error(native, original, spans):
    if native[0] != original[0]:
        return f'{native[0]} versus {original[0]}'
    return (check_memory(native[1], original[1], spans)
            or screen_differences(native[2], original[2])
            or ('indexed pixels' if native[3:4] != original[3:4] else None)
            or ('DAC' if native[4:5] != original[4:5] else None))


def run(ctx, cases=range(36)):
    global CASES
    def drain_events():
        events = (GameEvent * 512)()
        count = ctx.lib.game_events(events, len(events))
        return [(event.kind, event.a, event.b) for event in events[:count]]

    for case in cases:
        kind = case % 4
        vga = case // 4 % 2
        route = ('escape' if case < 16 else 'continue' if case < 24 else
                 'visited' if case < 32 else 'buy' if case < 34 else 'steal')
        if route in ('buy', 'steal'):
            kind, vga = 2, case % 2
        through_interaction = case >= 8
        option = {'buy': 2, 'steal': 1}.get(route, 0)
        target_x, target_y, item = ((160, 100, 22), (157 if vga else 317, 103, 72),
                                    (160, 100, 6), (153, 93, 9))[kind]
        machine = dosemu.Machine()
        machine.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        actor = 0x0508 if vga else 0x04D4
        for offset, value in {
            0x03A0: actor, actor + 6: 64, actor + 10: 10, actor + 26: 0,
            actor + 28: 1000, 0x03A2: 0x05B0, 0x03A8: 0x03AA, 0x0208: 0,
            0x118E: 0, 0x1190: 0, 0x8546: 0x8600, 0x1212: 0x0100,
            0x1214: 0x9500, 0xA743: 0x8000, 0xA75F: 0x0D74,
            0x116C: 0, 0x1176: int(route == 'visited'), 0x117E: 4096, 0x11C4: 4095,
        }.items():
            machine.ds_write(offset, struct.pack('<H', value))
        for offset, value in {
            actor + 14: 1, 0x11CA: 0 if case < 8 else 2, 0x9A4B: 0,
            0xADD0: vga, 0xADCF: 0, 0x01DE: 0, 0xA6E9: 0, actor + 50: 0,
            0xAA83: 0, 0x80E9: 0, 0xC4AB: 0, 0xAE04: 0,
        }.items():
            machine.ds_write(offset, bytes([value]))
        machine.ds_write(0x5BD9, bytes(0x59))
        machine.ds_write(0x05B0, bytes(12))
        if through_interaction:
            machine.ds_write(0x1180, struct.pack('<H', kind + 1))
            machine.ds_write(0x8514, machine.ds_read(actor + 34, 2))
            machine.ds_write(0x8518, machine.ds_read(actor + 42, 2))
            machine.ds_write(0x5BF8, bytes([255]))
            machine.ds_write(0x8447, bytes([255]))
        if route == 'visited':
            machine.ds_write(0x03AA, machine.ds_read(0x8600, 11))
        spans = regions(machine)
        logs, stats = [[], []], [[], []]
        waits, choices, clicks = [0, 0], [0, 0], [0, 0]
        faults, events = [], []

        def press(side, read, write, operation):
            if operation == 0x0DAA:
                waits[side] += 1
                if route == 'escape':
                    write(0x5C26, bytes([255 if waits[side] < 7 else 0]))
                    write(0x5BDA, bytes([255 if waits[side] == 7 else 0]))
                else:
                    x, y = struct.unpack('<HH', read(0x7C90, 4))
                    for key, held in ((0x5C26, x < target_x), (0x5C24, x > target_x),
                                      (0x5C21, y > target_y), (0x5C29, y < target_y)):
                        write(key, bytes([255 if held else 0]))
                    if waits[side] % 3 == 1 and (x, y) == (target_x, target_y):
                        write(0x5BF5 if not clicks[side] else 0x5BDA, bytes([255]))
                        clicks[side] += 1
            elif operation == 0x02C6:
                write(0x5C29, bytes([255 if choices[side] < option else 0]))
                write(0x5BF5, bytes([255 if choices[side] >= option else 0]))
                choices[side] += 1
            elif operation in (0x1000, 0x1002):
                write(0x5BF5, bytes(1))
            elif TEXT_POLL <= operation <= TEXT_POLL + 2:
                write(0x5BF5, bytes([255 if operation == TEXT_POLL + 1 else 0]))
                write(0x5BDA, bytes(1))

        def stat(side, read, write, filename):
            stats[side].append((filename, read(0xA743, 48)))
            name = read(filename, 64).split(bytes(1), 1)[0].decode('ascii')
            path = Path(machine._path(name))
            dta = bytearray(43)
            struct.pack_into('<I', dta, 26, path.stat().st_size)
            short_name = path.name.upper().encode('ascii')[:12]
            dta[30:30 + len(short_name)] = short_name
            write(0x77E5, bytes(dta))

        def source_boundary(operation, argument=0):
            logs[1].append(((operation, argument), bytes(machine.uc.mem_read(0, 0xA0000)),
                            planes_of(machine), bytes(machine.vga.chunky), bytes(machine.vga.dac)))
            press(1, machine.ds_read, machine.ds_write, operation)

        def source_hook(offset, callback, stub=False, segment=0):
            if stub:
                machine.wb(dosemu.LOAD_SEG + segment, offset, bytes([0xCB if segment else 0xC3]))
            address = ((dosemu.LOAD_SEG + segment) << 4) + offset
            machine.uc.hook_add(UC_HOOK_CODE, lambda *_: callback(), None, address, address)

        def source_stat():
            stat(1, machine.ds_read, machine.ds_write, machine.r(dosemu.UC_X86_REG_SI))
            flags = machine.r(dosemu.UC_X86_REG_EFLAGS)
            machine.w(dosemu.UC_X86_REG_EFLAGS, flags | 0x40)

        def source_wait():
            return_ip = machine.rw(machine.r(dosemu.UC_X86_REG_SS), machine.r(dosemu.UC_X86_REG_SP))
            source_boundary(TEXT_POLL + 1 if return_ip == 0x5185 else 0x02C6,
                            machine.r(dosemu.UC_X86_REG_CX))

        def source_pressed():
            return machine.ds_read(0x5BF5, 1)[0] or machine.ds_read(0x5BDA, 1)[0]

        source_hook(0xF6B3, source_stat, stub=True)
        source_hook(0x89A2, lambda: events.append((1, machine.ax() & 255,
                                                   machine.ds_read(0x80E9, 1)[0])), stub=True)
        source_hook(0x02C6, source_wait, stub=True, segment=0x5776)
        source_hook(0x9E36 if vga else 0x4A6F, lambda: source_boundary(0x1000)
                    if machine.ds_read(0x5BF5, 1)[0] else None)
        source_hook(0x8449, lambda: source_boundary(0x1002) if machine.ds_read(0x5BF5, 1)[0] else None)
        text_seg = 0x11BC if vga else 0
        for offset, phase in ((0x2C27 if vga else 0x5169, 0), (0x2C45 if vga else 0x5195, 2)):
            source_hook(offset, lambda phase=phase: source_boundary(TEXT_POLL + phase)
                        if source_pressed() else None, segment=text_seg)
        if vga:
            source_hook(0x2C35, lambda: source_boundary(TEXT_POLL + 1)
                        if not source_pressed() else None, segment=text_seg)
        for offset in (0x0D8D, 0x0DAA, 0x0C6B, 0x7AAF, 0x7AB6):
            source_hook(offset, lambda offset=offset: source_boundary(
                offset, machine.ax() if offset == 0x0C6B else 0),
                stub=offset in (0x0D8D, 0x0DAA))
        original_video = machine._video

        def source_video():
            if machine.ax() < 256:
                source_boundary(0xFF10, machine.ax())
            original_video()

        machine._video = source_video
        trace_dos(machine)
        files, hardware = Files(machine), Hardware(ctx, machine)
        game, memory, planes = make_game(machine)
        screen = ctypes.create_string_buffer(bytes(machine.vga.chunky), 65536)
        palette = ctypes.create_string_buffer(bytes(machine.vga.dac), 768)

        def read(offset, size):
            return ctypes.string_at(game.ds + offset, size)

        def write(offset, data):
            ctypes.memmove(game.ds + offset, data, len(data))

        @RESOURCE
        def sound_call(game_ptr, operation, argument, unused, user):
            try:
                if operation == 0xF6B3:
                    stat(0, read, write, argument)
                elif operation == 0x0100:
                    write(0xAA83, bytes(1))
                else:
                    raise ValueError(f'unexpected sound operation {operation:04X}')
                return 0
            except Exception as error:
                faults.append(str(error))
                return -1

        @RESOURCE
        def display_call(game_ptr, operation, argument, other, user):
            try:
                logs[0].append(((operation, argument), memory.raw, planes.raw, screen.raw, palette.raw))
                if operation in (0x0D8D, 0x0DAA):
                    press(0, read, write, operation)
                    return 0
                hardware.vm.vga.chunky[:] = screen.raw
                hardware.vm.vga.dac[:] = palette.raw
                if operation == 0x7AB6:
                    operation, argument = 0x0BE8, 0x1510
                result = hardware.service(game_ptr, operation, argument, other, user)
                ctypes.memmove(screen, bytes(hardware.vm.vga.chunky), 65536)
                ctypes.memmove(palette, bytes(hardware.vm.vga.dac), 768)
                return result
            except Exception as error:
                faults.append(str(error))
                return -1

        display = Resources(display_call, None)
        sound = Resources(sound_call, None)
        audio = SoundServices(ctypes.pointer(files.host), ctypes.pointer(sound))

        @Call
        def menu_call(game_ptr, operation, argument, other, user):
            logs[0].append(((operation, argument), memory.raw, planes.raw, screen.raw, palette.raw))
            if operation not in (0x02C6, 0x1000, 0x1002):
                faults.append(f'unexpected menu operation {operation:04X}')
                return -1
            press(0, read, write, operation)
            return 0

        menu = MenuPlatform(menu_call, None)

        @TextPoll
        def text_poll(game_ptr, phase, ticks, user):
            operation = TEXT_POLL + phase
            logs[0].append(((operation, ticks), memory.raw, planes.raw, screen.raw, palette.raw))
            press(0, read, write, operation)
            return 0

        text = TextPlatform(text_poll, None)
        actions = ShopServices(ctypes.pointer(files.host), ctypes.pointer(menu), ctypes.addressof(text),
                               ctypes.addressof(screen))
        host = ShopScreenServices(ctypes.pointer(actions), ctypes.pointer(display),
                                  ctypes.pointer(audio), None, ctypes.addressof(palette))
        entry_sp = (machine.r(dosemu.UC_X86_REG_SP) - (4 if through_interaction else 2)) & 65535
        drain_events()
        set_clock(ctx.lib, machine)
        if through_interaction:
            result = ctx.lib.shop_interaction_native(ctypes.byref(game), ctypes.byref(host), entry_sp)
        else:
            result = ctx.lib.shop_screen(ctypes.byref(game), kind, entry_sp, ctypes.byref(host))
        machine.call(0, 0x74CE if through_interaction else 0x813E,
                     bx=kind, es=machine.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        label = f'shop {kind}, VGA {vga}, {route}, fixture {case}'
        if (result or faults or waits[0] != waits[1] or choices[0] != choices[1]
                or stats[0] != stats[1] or events != drain_events()):
            return [f'{label}: result={result}, waits={waits}, choices={choices}, events={events}, {faults}']
        if route in ('continue', 'buy', 'steal') and (choices[0] != option + 1
                or struct.unpack('<H', read(0x9A70, 2))[0] != item * 2):
            return [f'{label}: selected item or option coverage missing']
        if route in ('visited', 'steal') and [event[1] for event in events] != [22, 21]:
            return [f'{label}: alarm coverage missing']
        if route in ('buy', 'steal') and struct.unpack('<H', read(0x03A2, 2))[0] != 0x05B6:
            return [f'{label}: item not transferred to inventory']
        if through_interaction and read(0x1180, 2) != bytes(2):
            return [f'{label}: interaction did not clear the active shop']
        if len(logs[0]) != len(logs[1]):
            return [f'{label}: display order {[[row[0] for row in log] for log in logs]}']
        for native, original in zip(*logs):
            error = boundary_error(native, original, spans)
            if error:
                return [f'{label}: display boundary {native[0]}: {error}']
        if len(files.calls) != len(machine.image_calls) or files.handles:
            return [f'{label}: file counts {len(files.calls)}/{len(machine.image_calls)}; handles {list(files.handles)}']
        for native, original in zip(files.calls, machine.image_calls):
            error = boundary_error(native, original, spans)
            if error:
                return [f'{label}: file boundary {native[0]}: {error}']
        if (screen.raw != bytes(machine.vga.chunky) or palette.raw != bytes(machine.vga.dac)
                or hardware.vm.vga.mode != machine.vga.mode or hardware.vm.vga.attr != machine.vga.attr):
            return [f'{label}: display state differs after exit']
        failures = []
        compare(label, memory, planes, machine, spans, failures)
        if failures:
            return failures
    return []
