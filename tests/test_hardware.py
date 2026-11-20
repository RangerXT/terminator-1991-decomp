"""The hardware routines of src/machine.c against the originals, through the machine replay
(tests/machine.py): every port read the original made is handed to C, every port write and
every interrupt (with the registers its function reads) must match in order, and memory, the
planes and card, and the returned registers must be equal afterwards.

Covered: the retrace waits 0D8D / 0DAA and the frame pause 5776:02C6, the CRTC start C571,
INT 10h through 0BE5 (mode, page, DAC register), the EGA palette registers 0BE8 / 7AAF /
7AB6, the DAC block 9FA4, the BIOS ticks F654, interrupt vectors F008 / F01D, the divide-error
handler 03D1 / 03F2 / 0407, the keyboard vector 3756 / 3783, the joystick 3A12 / 3A33 (a
scripted port 201h), EMS 5D52 / 5E0E (no driver; the emulator's small EMM with every failure
point), the adapter check F4E5.
"""
import ctypes
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from machine import CpuRegs, MachineReplay, traced  # noqa: E402
from test_drawlist import make_game  # noqa: E402
from test_imageload import compare, regions  # noqa: E402

CASES = 0


def fresh():
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    return m


def joystick(across, down, buttons):
    """Port 201h: bit 0 for `across` reads, bit 1 for `down`, the button bits as given."""
    count = [0]

    def read():
        count[0] += 1
        n = count[0]
        return 0xC0 | buttons | (1 if n <= across else 0) | (2 if n <= down else 0)
    return read


def run(ctx):
    global CASES
    lib = ctx.lib
    for name in ('bios_video_call', 'dac_block', 'joystick_absent', 'keyboard_install', 'keyboard_remove',
                 'ems_setup', 'ems_release', 'adapter_detect'):
        getattr(lib, name).restype = ctypes.c_int
    for name in ('bios_ticks', 'vector_get', 'joystick_read_port'):
        getattr(lib, name).restype = ctypes.c_uint32
    rng = random.Random(0x0D8D)
    cases = []
    ds_segment = [0]

    def case(label, address, c, regs=None, setup=None, far=False, seg=0, result=None):
        cases.append((label, address, c, regs or {}, setup, far, seg, result))

    # waits, CRTC, BIOS video, palettes
    case('0D8D', 0x0D8D, lambda g, s: lib.retrace_wait_start(g, s))
    case('0DAA', 0x0DAA, lambda g, s: lib.retrace_wait_end(g, s))
    for n in (1, 2, 5):
        case(f'02C6 {n}', 0x02C6, lambda g, s, n=n: lib.pause_frames(g, s, n), {'cx': n}, far=True, seg=0x5776)
    for v in (0, 0x1234, rng.randrange(0x10000)):
        case(f'C571 {v:04X}', 0xC571, lambda g, s, v=v: lib.crtc_display_start(g, s, v), {'ax': v})
    for regs in ({'ax': 0x0F00}, {'ax': 0x0500}, {'ax': 0x1010, 'bx': 5, 'cx': 0x1020, 'dx': 0x3000},
                 {'ax': 0x000D}):
        def call(g, s, regs=regs):
            out = CpuRegs()
            for k in ('ax', 'bx', 'cx', 'dx'):
                setattr(out, k, regs.get(k, 0))
            status = lib.bios_video_call(g, s, ctypes.byref(out))
            return status, out
        case(f'0BE5 {regs["ax"]:04X}', 0x0BE5, call, dict(regs, bx=regs.get('bx', 0), cx=regs.get('cx', 0),
                                                         dx=regs.get('dx', 0)), result='video')
    for table in (0x1510, 0x1521, rng.randrange(0x400, 0xE000)):
        case(f'0BE8 {table:04X}', 0x0BE8, lambda g, s, t=table: lib.palette_registers(g, s, t), {'dx': table})
    case('7AAF', 0x7AAF, lambda g, s: lib.palette_registers(g, s, 0x1521))
    case('7AB6', 0x7AB6, lambda g, s: lib.palette_registers(g, s, 0x1510))
    case('9FA4', 0x9FA4, lambda g, s: lib.dac_block(g, s, 0x8200, ds_segment[0]), {'bx': 0x8200})
    # memory-only ones
    for i in range(4):
        ticks = rng.randrange(1 << 32)
        case(f'F654 {ticks:08X}', 0xF654, lambda g, s: lib.bios_ticks(g),
             setup=lambda m, t=ticks: m.uc.mem_write(0x46C, struct.pack('<I', t)), result='dxax')
    for i in range(6):
        n, off, seg = rng.choice([rng.randrange(256), rng.randrange(0x10000)]), rng.randrange(0x10000), rng.randrange(0x10000)
        if n in (0, 8, 9, 0x10, 0x21) or n << 2 & 0xFFFF in (0, 0x20, 0x24, 0x40, 0x84):
            n = 0x60
        case(f'F008 {n:X}', 0xF008, lambda g, s, n=n, o=off, sg=seg: lib.vector_set(g, n, o, sg),
             {'bx': n, 'ax': off, 'dx': seg})
        case(f'F01D {n:X}', 0xF01D, lambda g, s, n=n: lib.vector_get(g, n), {'bx': n}, result='dxax')
    case('03D1', 0x03D1, lambda g, s: lib.divide_handler_install(g))
    case('03F2', 0x03F2, lambda g, s: lib.divide_handler_remove(g),
         setup=lambda m: m.ds_write(0x0202, struct.pack('<HH', rng.randrange(0x10000), rng.randrange(0x10000))))
    case('0407', 0x0407, None, far=True, result='frame')
    # the keyboard vector
    case('3756', 0x3756, lambda g, s: lib.keyboard_install(g, s),
         setup=lambda m: m.uc.mem_write(0x24, struct.pack('<HH', 0x0024, dosemu.BIOS_SEG)))
    case('3783', 0x3783, lambda g, s: lib.keyboard_remove(g, s))
    # the joystick
    for label, script in (('none', lambda: (lambda: 0xFF)), ('there', lambda: joystick(40, 0, 0x30))):
        case(f'3A12 {label}', 0x3A12, lambda g, s: lib.joystick_absent(g, s),
             setup=lambda m, sc=script: setattr(m, 'joystick', sc()), result='carry')
    for i in range(6):
        across, down, buttons, al = rng.randrange(0, 300), rng.randrange(0, 300), rng.choice([0, 0x10, 0x20, 0x30]), \
            rng.randrange(256)
        case(f'3A33 {across},{down},{buttons:02X}', 0x3A33, lambda g, s, a=al: lib.joystick_read_port(g, s, a),
             {'ax': al}, setup=lambda m, a=across, d=down, b=buttons: (setattr(m, 'joystick', joystick(a, d, b)),
                                                                     m.ds_write(0x5BD9, bytes(128))), result='axbx')
    # EMS
    def ems_setup(fail=None, version=0x40, free=16, named=True):
        def setup(m):
            m.ems = {'fail': fail, 'version': version, 'free': free}
            seg = m.ivt(0x67)[0]                     # the vector stays the emulator's, which serves it
            m.uc.mem_write(seg * 16 + 0x0A, m.ds_read(0x7AB7, 8) if named else b'NOTEMS!!')
        return setup
    for label, setup in (('no driver', ems_setup(named=False)), ('good', ems_setup()),
                         ('status fails', ems_setup(fail=0x40)), ('version 2', ems_setup(version=0x20)),
                         ('no frame', ems_setup(fail=0x41)), ('too few pages', ems_setup(free=3)),
                         ('allocation fails', ems_setup(fail=0x43)), ('mapping fails', ems_setup(fail=0x44))):
        case(f'5D52 {label}', 0x5D52, lambda g, s: lib.ems_setup(g, s), setup=setup, result='carry')
    for flag in (0, 0xFF):
        case(f'5E0E {flag:02X}', 0x5E0E, lambda g, s: lib.ems_release(g, s),
             setup=lambda m, f=flag: (setattr(m, 'ems', {}), m.ds_write(0x7ABF, bytes([f]))))
    for ah in (0, 0x12, 0xFF):
        def detect(g, s, ah=ah):
            out = ctypes.c_uint16()
            return lib.adapter_detect(g, s, ah << 8, ctypes.byref(out)), out.value
        case(f'F4E5 AH {ah:02X}', 0xF4E5, lambda g, s, d=detect: d(g, s), {'ax': ah << 8 | 0x55}, result='ax')

    fails = []
    for label, address, c, regs, setup, far, seg, result in cases:
        m = fresh()
        if setup:
            setup(m)
        ds_segment[0] = m.DATA_SEG
        if label == '9FA4':
            regs = dict(regs, es=m.DATA_SEG)
        g, mem, planes = make_game(m)
        ctypes.memmove(g.mem + 0xC0000, bytes(m.uc.mem_read(0xC0000, 0x40000)), 0x40000)   # the BIOS area too
        trace = traced(m)
        if result == 'frame':      # 0407: the interrupted IP + 2; return through BIOS_SEG:FF02 -> FF00
            m.wb(dosemu.BIOS_SEG, 0xFF02, b'\xeb\xfc')
            sp_entry = (m.r(dosemu.UC_X86_REG_SP) - 6) & 0xFFFF
            ss = m.r(dosemu.UC_X86_REG_SS)
            m.call(0, 0x0407, far=True, stack=(0x0002,))
            frame = struct.pack('<HHH', 0xFF00, dosemu.BIOS_SEG, 0x0002)   # as the call pushed it
            ctypes.memmove(g.mem + ss * 16 + sp_entry, frame, 6)
            lib.divide_error_resume(ctypes.byref(g), ss, sp_entry)
            CASES += 1
            got = ctypes.c_uint16.from_address(g.mem + ss * 16 + sp_entry).value
            if got != m.rw(ss, sp_entry):
                return [f'0407: the frame IP C {got:04X}, original {m.rw(ss, sp_entry):04X}']
            continue
        try:
            out = m.call(seg, address, far=far, max_instr=50_000_000, **regs)
        except RuntimeError as error:
            return [f'{label}: the original stopped: {error}']
        carry = m.r(dosemu.UC_X86_REG_EFLAGS) & 1
        replay = MachineReplay(g, mem, planes, trace)
        value = c(ctypes.byref(g), ctypes.byref(replay.services))
        CASES += 1
        problem = replay.finished()
        if problem:
            return [f'{label}: {problem}']
        if result == 'video':
            status, regs_out = value
            if status or any(getattr(regs_out, k) != out[k] for k in ('ax', 'bx', 'cx', 'dx')):
                return [f'{label}: status {status}, registers differ']
        elif result == 'dxax' and value != (out['ax'] | out['dx'] << 16):
            return [f'{label}: C {value:08X}, original {out["dx"]:04X}:{out["ax"]:04X}']
        elif result == 'axbx' and value != (out['ax'] | out['bx'] << 16):
            return [f'{label}: C {value:08X}, original BX {out["bx"]:04X} AX {out["ax"]:04X}']
        elif result == 'carry' and value != carry:
            return [f'{label}: C {value}, original carry {carry}']
        elif result == 'ax':
            status, ax = value
            if status or ax != out['ax']:
                return [f'{label}: C {ax:04X}, original {out["ax"]:04X}']
        compare(label, mem, planes, m, regions(m), fails)
        if fails:
            return fails
    return fails
