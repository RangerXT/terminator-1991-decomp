"""Full original VGA 14B5:000A vs native: real DFB/DFF/optional ATF, palette, timing.
Platform emulation receives only C's own memory/planes. Original outputs are never
replayed into the native game. All DOS and platform input states are compared.
"""
import ctypes, hashlib, os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu, termega
from unicorn import UC_HOOK_CODE
from test_drawlist import make_game, STACK_BYTES
from test_imageload import Files, trace_dos, check_memory, regions, compare
from test_polyfill import planes_of
from test_mapsetupreal import RESOURCE, Resources
from test_camera import Platform
from ai_helpers import prepare
from movie_helpers import MovieServices
from test_travel import CALLBACK, Services
import random
from test_blast import c_events, set_clock
CASES = 0

def run(ctx, opponent=False, losses=False):
    global CASES
    CASES = 0
    root = Path(dosemu.ROOT)
    paths = {p.name.upper():str(p) for d in ['common', 'vga'] for p in (root/'data'/d).iterdir() if p.is_file()}
    fails = []
    present = missing = waited = 0
    for path in sorted((root/'data/vga').glob('*.DFF')):
        if opponent and path.stem != ('DOR' if losses else 'TS'):
            continue
        for variant in range(6 if opponent else 4):
            m = dosemu.Machine()
            m.load(root/'out/emu/states/ingame.pkl')
            m._path = lambda name:paths.get(name.replace(chr(92), '/').split('/')[-1].upper(), str(root/'data/vga'/'NO_SUCH_FILE'))
            if opponent:
                saved = m.ds_read(0, 65536)
                collisionseg = m.rw(m.DATA_SEG, 0x91B2)
                collision = m.rb(collisionseg, 0, 0x9000)
                prepare(m, saved, random.Random(0xB7B6+variant), collision, bytes(0x9000), variant)
                player = m.rw(m.DATA_SEG, 0x03A0)
                actor = m.rw(m.DATA_SEG, 0x04BA)
                m.ds_write(actor+30, struct.pack('<H', m.rw(m.DATA_SEG, player+30)+3))
                m.ds_write(0x04D2, struct.pack('<H', 1))
                m.ds_write(0x97B8, struct.pack('<H', 65535))
                m.ds_write(0x115C, bytes([0]))
                m.ds_write(0xDE3C, bytes([0x80 if variant%2 else 0]))

            def word(o, v):
                m.ds_write(o, struct.pack('<H', v&65535))
            m.ds_write(0xADD0, bytes([0]))
            m.ds_write(0x8200, path.stem.lower().encode('ascii')+bytes([0]))
            word(0x91B8, 0)
            word(0x91BA, 0x2000)
            word(0x91C4, 0)
            word(0x91C6, 0x7000)
            word(0xDE20, 0x7000)
            m.wb(0x7000, 0, bytes(65536))
            m.wb(0x2000, 0, bytes(0x30000))
            m.ds_write(0xDB61, bytes([1 if variant == 2 else 0]))
            word(0x8544, 4)
            if opponent:
                m.ds_write(0xADD0, bytes([1]))
            delay = 2+2*(variant%2)
            flag = variant%2
            for off in [0x0D8D, 0x0DAA]:
                m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
            if losses:
                word(0x03A0, 0x0508)
                word(0x04BA, 0x04D4)
                word(0x04D4+26, 200)
                word(0x04D4+28, 200)
                m.ds_write(0x1152, bytes([0]))
                m.ds_write(0x01DE, bytes([0]))
                m.ds_write(0xAA83, bytes([0]))
                word(0x11CD, [0, 1, 256][variant%3])
            trace_dos(m)
            platform = Platform(ctx, m)
            g, mem, planes = make_game(m)
            logs = [[], []]
            waits = [0, 0]
            first_states = [None, None]
            screen = ctypes.create_string_buffer(bytes(m.vga.chunky), 65536)
            palette = ctypes.create_string_buffer(bytes(m.vga.dac), 768)
            calls = []
            c_events(ctx.lib)
            set_clock(ctx.lib, m)
            class MovieFiles(Files):
                def __init__(self, m):
                    self.video = []
                    super().__init__(m)
                def call(self, *args):
                    self.video.append((screen.raw, palette.raw))
                    return super().call(*args)
            files = MovieFiles(m)
            original_video = []
            logged = m._dos
            def dos_video():
                if m.ax()>>8 in [0x3D, 0x3F, 0x3E, 0x43]:
                    original_video.append((bytes(m.vga.chunky), bytes(m.vga.dac)))
                return logged()
            m._dos = dos_video
            m.wb(dosemu.LOAD_SEG, 0x89A2, bytes([0xC3]))
            at = (dosemu.LOAD_SEG<<4)+0x89A2
            mem[at] = 0xC3
            def sound(uc, address, size, user):
                calls.append((1, m.r(dosemu.UC_X86_REG_AX)&255))
            m.uc.hook_add(UC_HOOK_CODE, sound, None, at, at)
            spans = regions(m)
            def state(raw, card, pixels, dac):
                h = hashlib.sha256()
                for lo, hi in spans:
                    h.update(raw[lo:hi])
                h.update(card)
                h.update(pixels)
                h.update(dac)
                return h.digest()
            def advance(which, op, write):
                if op == 0x0DAA:
                    waits[which] += 1
                    if variant == 1 and waits[which] == 1:
                        write(0x5BD4, struct.pack('<H', 1))
            @RESOURCE
            def callback(gp, op, a, b, user):
                if first_states[0] is None:
                    first_states[0] = (mem.raw, planes.raw, screen.raw, palette.raw)
                logs[0].append((op, a, b, state(mem.raw, planes.raw, screen.raw, palette.raw)))
                if op in [0x0D8D, 0x0DAA]:
                    advance(0, op, lambda o, v:ctypes.memmove(g.ds+o, v, len(v)))
                    return 0
                result = platform.service(gp, op, a, b, user)
                if op == 0xFF10:
                    ctypes.memmove(screen, bytes(platform.vm.vga.chunky), 65536)
                    ctypes.memmove(palette, bytes(platform.vm.vga.dac), 768)
                return result
            def hook(uc, address, size, user):
                cs = m.r(dosemu.UC_X86_REG_CS)
                off = m.r(dosemu.UC_X86_REG_IP)
                if cs == dosemu.LOAD_SEG+0x14B5 and off == 0x005D:
                    op, a, b = 0xFF10, m.r(dosemu.UC_X86_REG_AX), 0
                elif cs == dosemu.LOAD_SEG and off in [0x0D8D, 0x0DAA]:
                    op, a, b = off, 0, 0
                else:
                    return
                if first_states[1] is None:
                    first_states[1] = (bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m), bytes(m.vga.chunky), bytes(m.vga.dac))
                logs[1].append((op, a, b, state(bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m), bytes(m.vga.chunky), bytes(m.vga.dac))))
                advance(1, op, m.ds_write)
            for seg, off in [(0x14B5, 0x005D), (0, 0x0D8D), (0, 0x0DAA)]:
                at = ((dosemu.LOAD_SEG+seg)<<4)+off
                m.uc.hook_add(UC_HOOK_CODE, hook, None, at, at)
            host = Resources(callback, None)
            if opponent:
                scene_logs = [[], []]
                def other_effect(which, op, arg):
                    raw = mem.raw if which == 0 else bytes(m.uc.mem_read(0, 0xA0000))
                    card = planes.raw if which == 0 else planes_of(m)
                    pixels = screen.raw if which == 0 else bytes(m.vga.chunky)
                    dac = palette.raw if which == 0 else bytes(m.vga.dac)
                    scene_logs[which].append((op, arg, state(raw, card, pixels, dac)))
                    return 0
                @CALLBACK
                def other_callback(gp, op, arg, user):
                    return other_effect(0, op, arg)
                other = Services(other_callback, None)
                for seg, off, far in [(0x5776, 0x02C6, True), (0, 0x3B88, False), (0, 0x7A28, False)]:
                    m.wb(dosemu.LOAD_SEG+seg, off, bytes([0xCB if far else 0xC3]))
                    physical = ((dosemu.LOAD_SEG+seg)<<4)+off
                    mem[physical] = 0xCB if far else 0xC3
                    def other_hook(uc, address, size, user, off=off):
                        other_effect(1, off, m.r(dosemu.UC_X86_REG_CX) if off == 0x02C6 else 0)
                    m.uc.hook_add(UC_HOOK_CODE, other_hook, None, physical, physical)
                movie = MovieServices(ctypes.pointer(files.host), ctypes.pointer(host), ctypes.addressof(screen), ctypes.addressof(palette), ctypes.pointer(other))
                @CALLBACK
                def movie_callback(gp, op, arg, user):
                    return ctx.lib.cutscene_opponent_service(gp, op, arg, ctypes.byref(movie))
                native = Services(movie_callback, None)
                if losses:
                    status = ctx.lib.gameplay_check_losses(ctypes.byref(g), ctypes.byref(movie), None)
                    m.call(0, 0x089E, max_instr=500_000_000)
                    CASES += 1
                else:
                    status = ctx.lib.opponent_controller_slow_on_foot(ctypes.byref(g), ctypes.byref(native))
                    m.call(0, 0xB7B6, max_instr=500_000_000)
                    CASES += 1
                if scene_logs[0] != scene_logs[1] or [op for op, arg, h in scene_logs[0]] != [0x02C6, 0x3B88, 0x7A28]:
                    return ['opponent native movie follow-up boundaries']
            else:
                status = ctx.lib.cutscene_vga_play(ctypes.byref(g), 0x8200, delay, flag, screen, palette, ctypes.byref(files.host), ctypes.byref(host))
                m.call(0x14B5, 0x000A, far=True, si=0x8200, ax=40, bx=delay, cx=flag, max_instr=500_000_000)
                CASES += 1
            if status or logs[0] != logs[1] or waits[0] != waits[1]:
                first = next((j for j, (a, b) in enumerate(zip(*logs)) if a != b), None)
                if first == 0:
                    a, b = first_states
                    print('first platform meta', logs[0][0][:3], logs[1][0][:3], 'memory', [(hex(j), a[0][j], b[0][j]) for lo, hi in spans for j in range(lo, hi) if a[0][j] != b[0][j]][:12], 'card/pixels/dac', [a[j] == b[j] for j in range(1, 4)])
                return ['VGA player platform %s/%d status=%d logs=%d/%d first=%s waits=%s'%(path.name, variant, status, len(logs[0]), len(logs[1]), first, waits)]
            if len(files.calls) != len(m.image_calls):
                return ['VGA player DOS count '+path.name]
            for a, b in zip(files.calls, m.image_calls):
                if a[0] != b[0]:
                    return ['VGA player DOS arguments %s/%d: %s != %s'%(path.name, variant, a[0], b[0])]
                error = check_memory(a[1], b[1], spans)
                if error or a[2] != b[2]:
                    return ['VGA player DOS state %s/%d: %s'%(path.name, variant, error)]
            if files.video != original_video:
                return ['VGA movie IO video state '+path.name+'/'+str(variant)]
            if c_events(ctx.lib) != calls:
                return ['VGA movie sound events '+path.name]
            if screen.raw != bytes(m.vga.chunky) or palette.raw != bytes(m.vga.dac):
                return ['VGA movie final screen/palette '+path.name]
            compare('full VGA movie %s/%d'%(path.name, variant), mem, planes, m, spans, fails)
            if fails:
                return fails
            if files.handles:
                return ['VGA player handle leak']
            if platform.vm.vga.mode != m.vga.mode:
                return ['VGA player hardware mode '+path.name]
            name = m.asciiz(m.DATA_SEG, 0xDBA4)
            if os.path.isfile(m._path(name)):
                present += 1
            else:
                missing += 1
            waited += waits[0]
    print('    full VGA movies: ATF present=%d missing=%d retrace pairs=%d'%(present, missing, waited))
    if (not opponent and (not present or not missing)) or not waited:
        return ['missing VGA movie branches']
    return fails
