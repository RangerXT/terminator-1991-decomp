"""Replaying the machine to C (MachineServices in src/term.h).

`traced(m)` turns on the emulator's trace (tools/dosemu.py: every port access, every
interrupt it services with the registers before and after, the memory pages it changed and
the video state afterwards, and each hardware interrupt it delivers to the program) and gives the VGA a clock that moves with every status read, so
retrace waits end in isolated calls. `MachineReplay(g, mem, planes, trace)` is a
MachineServices for the C side: each port read returns what the original read, each write
and each interrupt is checked against what the original did (the registers the function
reads), and an interrupt's results (registers, memory, video) are handed over; asked for a
hardware interrupt, it gives the one the original took next, if that came next.
"""
import ctypes
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
import dosemu  # noqa: E402

REGS = ('ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'ds', 'es', 'flags')


class CpuRegs(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint16) for name in REGS]


PORT_IN = ctypes.CFUNCTYPE(ctypes.c_uint16, ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_void_p)
PORT_OUT = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_void_p)
INTERRUPT = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint8, ctypes.POINTER(CpuRegs), ctypes.c_void_p)
IRQ = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


class MachineServices(ctypes.Structure):
    _fields_ = [('in_', PORT_IN), ('out', PORT_OUT), ('interrupt', INTERRUPT), ('user', ctypes.c_void_p),
                ('irq', IRQ)]


def traced(m):
    m.trace = []
    reads = [0]

    def clock():
        reads[0] += 1
        return reads[0] * (dosemu.FRAME_INSTR // 7)
    m.vga.clock = clock
    return m.trace


def inputs(vector, ax):
    """The registers an interrupt function reads ('ah' / 'al' for one half of AX)."""
    ah, al = ax >> 8, ax & 0xFF
    if vector == 0x10:
        if ah in (0x00, 0x05):
            return ('ax',)
        if ah in (0x0F, 0x1A):
            return ('ax',) if ah == 0x1A else ('ah',)
        if ah == 0x10:
            return ('ax', 'bx', 'cx', 'dx', 'es') if al in (0x12, 0x17) else ('ax', 'bx', 'cx', 'dx')
        if ah == 0x12:
            return ('ah', 'bx')
        return ('ax', 'bx', 'cx', 'dx')
    if vector == 0x21:
        return {0x09: ('ah', 'dx', 'ds'), 0x19: ('ah',), 0x1A: ('ah', 'dx', 'ds'), 0x25: ('ax', 'dx', 'ds'),
                0x2C: ('ah',), 0x30: ('ah',), 0x35: ('ax',), 0x3C: ('ah', 'cx', 'dx', 'ds'),
                0x3D: ('ax', 'dx', 'ds'), 0x3E: ('ah', 'bx'), 0x3F: ('ah', 'bx', 'cx', 'dx', 'ds'),
                0x40: ('ah', 'bx', 'cx', 'dx', 'ds'), 0x41: ('ah', 'dx', 'ds'), 0x42: ('ax', 'bx', 'cx', 'dx'),
                0x43: ('ax', 'cx', 'dx', 'ds') if al else ('ax', 'dx', 'ds'), 0x47: ('ah', 'dx', 'si', 'ds'), 0x48: ('ah', 'bx'),
                0x49: ('ah', 'es'), 0x4A: ('ah', 'bx', 'es'), 0x4C: ('ax',), 0x4E: ('ah', 'cx', 'dx', 'ds'),
                0x4F: ('ah',), 0x0E: ('ah', 'dx')}.get(ah, ('ax', 'bx', 'cx', 'dx', 'ds', 'es'))
    if vector == 0x67:
        return {0x43: ('ah', 'bx'), 0x44: ('ax', 'bx', 'dx'), 0x45: ('ah', 'dx'), 0x47: ('ah', 'dx'),
                0x48: ('ah', 'dx')}.get(ah, ('ah',))
    if vector in (0x09, 0x1C, 0x08):
        return ()
    return ('ax',)


def register(regs, name):
    if name == 'ah':
        return regs['ax'] >> 8 if isinstance(regs, dict) else regs.ax >> 8
    if name == 'al':
        return regs['ax'] & 0xFF if isinstance(regs, dict) else regs.ax & 0xFF
    return regs[name] if isinstance(regs, dict) else getattr(regs, name)


class MachineReplay:
    def __init__(self, g, mem, planes, trace, screen=None, video=True, check=None):
        """video: hand over the video state after each interrupt (or a function of the vector
        saying after which); check(vector, regs, event index)
        looks at an interrupt C makes before its results are applied (an error text or None)."""
        self.g, self.mem, self.planes, self.screen = g, mem, planes, screen
        self.trace, self.index, self.errors = list(trace), 0, []
        video_state = video

        @PORT_IN
        def port_in(gp, port, size, user):
            event = self._next('in', port, size)
            return event[3] if event else 0xFF

        @PORT_OUT
        def port_out(gp, port, size, value, user):
            event = self._next('out', port, size)
            if event and event[3] != value:
                self.errors.append(f'event {self.index}: out {port:03X} C {value:02X}, original {event[3]:02X}')

        @INTERRUPT
        def interrupt(gp, vector, regs, user):
            event = self._next('int', vector)
            if not event:
                return -1
            _, n, before, after, pages, video = event
            r = regs.contents
            for name in inputs(n, before['ax']):
                if register(r, name) != register(before, name):
                    self.errors.append(f'event {self.index}: INT {n:02X} AX {before["ax"]:04X}: {name} C '
                                       f'{register(r, name):04X}, original {register(before, name):04X}')
            if check:
                problem = check(n, r, self.index - 1)
                if problem:
                    self.errors.append(f'event {self.index}: {problem}')
                    return -1
            for name in REGS:
                setattr(r, name, after[name])
            for page, data in pages.items():
                if page < 0xA0:
                    ctypes.memmove(self.g.mem + page * 4096, data, len(data))
            if video_state(n) if callable(video_state) else video_state:
                planes, chunky = video[0], video[1]
                ctypes.memmove(self.planes, planes, len(planes))
                if self.screen is not None:
                    ctypes.memmove(self.screen, chunky, len(chunky))
            return 0

        @IRQ
        def irq(gp, user):
            if self.errors or self.index >= len(self.trace) or self.trace[self.index][0] != 'irq':
                return -1
            self.index += 1
            return self.trace[self.index - 1][1]

        self._callbacks = (port_in, port_out, interrupt, irq)
        self.services = MachineServices(port_in, port_out, interrupt, None, irq)

    def _next(self, kind, port, size=None):
        if self.errors:
            return None
        if self.index >= len(self.trace):
            self.errors.append(f'extra {kind} {port:X}')
            return None
        event = self.trace[self.index]
        self.index += 1
        if event[0] != kind or event[1] != port or (size is not None and event[2] != size):
            self.errors.append(f'event {self.index}: C {kind} {port:X}, original {event[:3]}')
            return None
        return event

    def finished(self):
        if self.errors:
            return '; '.join(self.errors[:2])
        if self.index != len(self.trace):
            return f'C made {self.index} of the original {len(self.trace)} machine events (next {self.trace[self.index][:3]})'
        return ''
