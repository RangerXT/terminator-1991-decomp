"""Compare gameplay gameport input, including the original pulse counting loop."""
import ctypes
import random
import struct

import dosemu

CASES = 0


class Gameport(dosemu.Machine):
    def _out8(self, port, value):
        if port == 0x201:
            self.reads = 0
        super()._out8(port, value)

    def _on_in(self, uc, port, size, user):
        if port != 0x201:
            return super()._on_in(uc, port, size, user)
        x_pulse = self.reads < self.x
        y_pulse = self.reads < self.y
        self.reads += 1
        return self.released | x_pulse | (y_pulse << 1)


def run(ctx):
    global CASES
    machine = Gameport()
    machine.load(dosemu.ROOT + '/out/emu/states/ingame.pkl')
    saved = machine.ds_read(0, 65536)
    randomizer = random.Random(0x3A6E)
    seen = set()
    for case in range(384):
        calibration = []
        samples = []
        for axis in range(2):
            calibration.extend((0, 64, 128) if case < 128 else
                               (randomizer.randrange(160), randomizer.randrange(160), randomizer.randrange(160)))
            samples.append([0, 7, 8, 31, 32, 33, 55, 56, 63, 64, 65, 95, 96, 97, 119, 120,
                            121, 127, 128, 129][(case // (7 if axis else 1)) % 20] if case < 128
                           else randomizer.randrange(256))
        machine.ds_write(0, saved)
        machine.ds_write(0x5A52, struct.pack('<6H', *calibration))
        for key in (0x5C26, 0x5C24, 0x5C21, 0x5C29, 0x5C0F, 0x5BF5, 0x5C12):
            machine.ds_write(key, bytes([randomizer.randrange(256)]))
        machine.x, machine.y = samples
        machine.released = (case % 4) << 4
        native = ctypes.create_string_buffer(machine.ds_read(0, 65536), 65536)
        ctx.lib.joystick_apply(native, *samples, machine.released)
        machine.call(0, 0x3A6E)
        CASES += 1
        if machine.reads != max(samples) + 1:
            return [f'gameport pulses {case}: {machine.reads} reads for {samples}']
        if native.raw[:0xEA70] != machine.ds_read(0, 0xEA70):
            return [f'joystick {case}: sample {samples}, calibration {calibration}']
        seen.add(tuple(bool(native[offset][0]) for offset in (0x5C26, 0x5C24, 0x5C21, 0x5C29, 0x5C0F)))
    if len(seen) < 12:
        return [f'joystick coverage only {len(seen)} direction/speed combinations']
    return []
