"""Original VGA message windows: independent input polls, native pixels/state."""
import ctypes, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, compare, STACK_BYTES
from test_polyfill import planes_of
from test_textmodal import Poll, Platform
CASES = 0

def run(ctx):
    global CASES
    root = Path(dosemu.ROOT)
    fails = []
    phases = set()
    for i in range(96):
        m = dosemu.Machine()
        m.load(root/'out/emu/states/ingame.pkl')
        m.w(dosemu.UC_X86_REG_AX, 19)
        m._video()
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        m.ds_write(0xADCF, bytes([1]))
        word(0x91BC, 0x100)
        word(0x91BE, 0x9000)
        m.ds_write(0xAE04, bytes([0]))
        m.ds_write(0x5A4E, bytes([255 if i >= 72 else 0]))
        word(0x0200, i%2)
        m.ds_write(0x8096, bytes([i//2%2]))
        m.ds_write(0x5BDA, bytes([i%2]))
        m.ds_write(0x5BF5, bytes([i//2%2]))
        m.vga.chunky[:] = bytes((j*19+i)&255 for j in range(65536))
        g, mem, planes = make_game(m)
        screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
        logs = [[], []]
        counts = [[0, 0, 0], [0, 0, 0]]
        def effect(which, phase, write):
            phases.add(phase)
            counts[which][phase] += 1
            n = counts[which][phase]
            if phase == 0 and n >= 2:
                write(0x5BDA, bytes([0]))
                write(0x5BF5, bytes([0]))
            elif phase == 1 and n >= 2+i%3:
                write(0x5BF5 if i%2 else 0x5BDA, bytes([255]))
            elif phase == 2 and n >= 2+i%2:
                write(0x5BDA, bytes([0]))
                write(0x5BF5, bytes([0]))
        @Poll
        def poll(gp, phase, ticks, user):
            logs[0].append((phase, ticks, mem.raw[:0xA0000], planes.raw, screen.raw))
            effect(0, phase, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)))
            return 0
        def hook(uc, address, size, user):
            off = m.r(dosemu.UC_X86_REG_IP)
            if off == 0x2C27:
                if not (m.ds_read(0x5BDA, 1)[0] or m.ds_read(0x5BF5, 1)[0]):
                    return
                phase = 0
            elif off == 0x2C35:
                if m.ds_read(0x5BDA, 1)[0] or m.ds_read(0x5BF5, 1)[0]:
                    return
                phase = 1
            elif off == 0x2C45:
                if not (m.ds_read(0x5BDA, 1)[0] or m.ds_read(0x5BF5, 1)[0]):
                    return
                phase = 2
            else:
                return
            logs[1].append((phase, 0, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m), bytes(m.vga.chunky)))
            effect(1, phase, m.ds_write)
        for off in [0x2C27, 0x2C35, 0x2C45]:
            at = ((dosemu.LOAD_SEG+0x11BC)<<4)+off
            m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
        host = Platform(poll, None)
        status = ctx.lib.textbox_vga_draw(ctypes.byref(g), screen, 0x0729, 6, 4, 13, 3, ctypes.byref(host))
        m.call(0, 0x5032, si=0x0729, ax=6, bx=4, cx=13, dx=3, max_instr=100_000_000)
        CASES += 1
        if status or counts[0] != counts[1] or len(logs[0]) != len(logs[1]):
            return ['VGA message poll status/counts %d %s'%(i, counts)]
        stack = m.r(dosemu.UC_X86_REG_SS)<<4
        for a, b in zip(*logs):
            if a[:2] != b[:2] or a[3:] != b[3:] or any(a[2][lo:hi] != b[2][lo:hi] for lo, hi in [(0, stack), (stack+STACK_BYTES, 0xA0000)]):
                return ['VGA message poll state %d phase %d'%(i, a[0])]
        if screen.raw != bytes(m.vga.chunky):
            return ['VGA message pixels %d'%i]
        compare('VGA message %d'%i, mem, planes, m, fails)
        if fails:
            return fails
    if phases != {0, 1, 2}:
        return ['VGA message missing input phases']
    return fails
