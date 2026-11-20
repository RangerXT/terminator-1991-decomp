"""02B5 native resource/HUD/control composition; real files and independent BIOS model.
First 24 cases stub audio-group bodies; last 24 execute native and original groups,
with only stat metadata external. Native C receives asset bytes from
Files and platform operations from an independent machine fed only its own C state.
"""
import ctypes, os, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game
from test_imageload import Files, trace_dos, regions, compare, check_memory, ImageIO
from test_mapsetupreal import Resources, RESOURCE
from test_sound import SoundServices
from test_camera import Platform
from test_travel import CALLBACK, Services
from test_blast import GameEvent, set_clock
CASES = 0

class VehicleServices(ctypes.Structure):
    _fields_ = [('display', ctypes.POINTER(Resources)), ('images', ctypes.POINTER(ImageIO)), ('audio', ctypes.POINTER(Services))]


def run(ctx, caller="transition"):
    global CASES
    fails = []
    for i in range(144 if caller == "transition" else 48):
        native_sound = i >= 24
        m = dosemu.Machine()
        m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
        mode = (1 if i >= 48 else i%3) if caller == "transition" else (2 if caller == "entry" else (1 if i%4 < 2 else 2))
        p = [0x04D4, 0x0508][i//3%2]
        def word(o, v):
            m.ds_write(o, struct.pack('<H', v&65535))
        word(0x03A0, p)
        m.ds_write(p+14, bytes([2 if mode == 1 else 1]))
        word(p+26, 0)
        word(p+28, 1000)
        word(p+48, 100)
        m.ds_write(0x5BD9, bytes(0x59))
        m.ds_write(0x5EF7, bytes([i//6%2]))
        m.ds_write(0x11CA, bytes([0 if i%24 < 12 else 2]))
        m.ds_write(0x1155, bytes([0]))
        m.ds_write(0x8096, bytes([0]))
        m.ds_write(0xAA98, bytes([0]))
        word(0x5F76, 100)
        if i >= 48:
            m.ds_write(0x11CA, bytes([i%3]))
            word(p+6, (i*37)%512)
            m.ds_write(0xAA96, bytes([i//3%2]))
            m.ds_write(0x7AC5, bytes([i//24%2]))
            for j, o in enumerate([0x8096, 0x1155, 0x5BF6]):
                m.ds_write(o, bytes([255 if i//6%4 == j+1 else 0]))
        word(0x11CD, i%2)
        word(0x9948, 0x97B8)
        word(0x994A, 0x9948)
        m.ds_write(0x97B8, bytes(400))
        trace_dos(m)
        spans = regions(m)
        stream_logs = [[], []]
        if caller == "entry":
            word(0x72B0, 1)
            m.ds_write(0x5CE3, bytes([255]))
            m.ds_write(0x5BEB, bytes([255]))
            word(0x72C8, i%4)
            word(0x03A6, 0x0F70)
            word(0x5F74, 0x0200 if i%2 else 65535)
            word(0x5F78, 0)
            word(0x04C6, 2)
            word(0x1204, 28)
            word(0x1200, 0)
            word(0x1202, 0x9000)
            word(0x1206, 0x9000)
            m.wb(0x9000, 0, bytes(56))
            m.wb(m.rw(m.DATA_SEG, 0x91D4), 0x0200, struct.pack('<6H', 500, 0, 600, i%4, i%117*2, 0x2060))
            word(0x5F70, 0x1020)
            word(0x5F72, 0x3040)
        elif caller == "control":
            m.ds_write(p+14, bytes([1 if i%4 == 1 else 2]))
            m.ds_write(0x5BEA, bytes([255 if i%4 == 0 else 0]))
            m.ds_write(0x5BF9, bytes([255]))
            word(0x1204, i%14*14)
            word(0x1206, 0x9000)
            word(0x04C6, i%14)
            m.wb(m.rw(m.DATA_SEG, 0x91B2), 0, bytes(65536))
            word(0x11BE, 0)
            word(p+10, [0, 7, 8, 16, 32, 64][i//4%6])
            m.ds_write(0x1153, bytes([0]))
            m.ds_write(0x1154, bytes([0]))
            for off in [0x3B88, 0x057C]:
                m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
                at = (dosemu.LOAD_SEG<<4)+off
                def stream_event(uc, address, size, user, off=off):
                    stream_logs[1].append((off, m.ds_read(p, 52), m.ds_read(0x8683, 1), m.ds_read(0x1200, 8)))
                m.uc.hook_add(UC_HOOK_CODE, stream_event, None, at, at)
        elif caller == "predraw":
            # Force an actual collision-map miss or a blocking 0x80 footprint.
            m.ds_write(p+14, bytes([1 if i%4 < 2 else 2]));m.ds_write(0x8683, bytes([255]))
            m.wb(m.rw(m.DATA_SEG, 0x91B2), 0, bytes([0 if i%4 == 0 else 128])*65536)
            word(0x03F0, i%7)
            m.ds_write(0x80E9, bytes([0]))
        audio_logs = [[], []]
        calls = []
        def effect(which, read, write, op, arg):
            audio_logs[which].append((op, arg, read(p, 52), read(0x8540, 4)))
            write(0xA6E9, bytes([3 if op == 0x8ABE else 1]))
            return 0
        stat_logs = [[], []]
        def stat_effect(which, read, write, filename):
            stat_logs[which].append((filename, read(0xA743, 48)))
            name = read(filename, 64).split(bytes([0]))[0].decode('ascii')
            size = os.path.getsize(m._path(name))
            dta = bytearray(43)
            struct.pack_into('<I', dta, 26, size)
            text = os.path.basename(name).upper().encode('ascii')[:12]
            dta[30:30+len(text)] = text
            write(0x77E5, bytes(dta))
            return 0
        if native_sound:
            word(0xA743, 0x8000)
            word(0xA75F, 0xD74)
            m.ds_write(0xA6E9, bytes([0]))
            m.ds_write(0xAA83, bytes([0]))
            m.wb(dosemu.LOAD_SEG, 0xF6B3, bytes([0xC3]))
            at = (dosemu.LOAD_SEG<<4)+0xF6B3
            def stat(uc, address, size, user):
                stat_effect(1, m.ds_read, m.ds_write, m.r(dosemu.UC_X86_REG_SI))
                m.w(dosemu.UC_X86_REG_EFLAGS, m.r(dosemu.UC_X86_REG_EFLAGS)|0x40)
            m.uc.hook_add(UC_HOOK_CODE, stat, None, at, at)
        else:
            for off in [0x8ABE, 0x8A9E]:
                m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
                at = (dosemu.LOAD_SEG<<4)+off
                def audio(uc, address, size, user, off=off):
                    effect(1, m.ds_read, m.ds_write, off, 0)
                m.uc.hook_add(UC_HOOK_CODE, audio, None, at, at)
        for kind, off, reg in [(1, 0x89A2, dosemu.UC_X86_REG_AX), (5, 0x0A4F, dosemu.UC_X86_REG_BX)]:
            m.wb(dosemu.LOAD_SEG, off, bytes([0xC3]))
            at = (dosemu.LOAD_SEG<<4)+off
            def event(uc, address, size, user, kind=kind, reg=reg):
                calls.append((kind, uc.reg_read(reg)&255, m.ds_read(0x80E9, 1)[0] if kind == 1 else 0))
            m.uc.hook_add(UC_HOOK_CODE, event, None, at, at)
        platform = Platform(ctx, m)
        files = Files(m)
        platform.files = files
        g, mem, planes = make_game(m)
        m.image_calls.clear()
        @RESOURCE
        def sound_platform_call(gp, op, a, b, user):
            if op == 0xF6B3:
                return stat_effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), a)
            if op == 0x0100:
                ctypes.memset(g.ds+0xAA83, 0, 1)
                return 0
            return -1
        sound_platform = Resources(sound_platform_call, None)
        sound_host = SoundServices(ctypes.pointer(files.host), ctypes.pointer(sound_platform))
        @CALLBACK
        def audio_call(gp, op, arg, user):
            if native_sound:
                return ctx.lib.sound_group_service(gp, op, arg, ctypes.byref(sound_host))
            return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, b:ctypes.memmove(g.ds+o, b, len(b)), op, arg)
        audio_host = Services(audio_call, None)
        host = VehicleServices(ctypes.pointer(platform.host), ctypes.pointer(files.host), ctypes.pointer(audio_host))
        buf = (GameEvent*512)()
        ctx.lib.game_events(buf, 512)
        set_clock(ctx.lib, m)
        @CALLBACK
        def stream_call(gp, op, arg, user):
            if op not in [0x3B88, 0x057C] or arg:
                return 0xFFFFFFFF
            stream_logs[0].append((op, ctypes.string_at(g.ds+p, 52), ctypes.string_at(g.ds+0x8683, 1), ctypes.string_at(g.ds+0x1200, 8)))
            return 0
        stream_host = Services(stream_call, None)
        if caller == "entry":
            status = ctx.lib.vehicle_interaction_native(ctypes.byref(g), ctypes.byref(host))
        elif caller == "control":
            status = ctx.lib.player_control_step(ctypes.byref(g), ctypes.byref(host), ctypes.byref(stream_host))
        elif caller == "predraw":
            status = ctx.lib.player_pre_draw_collision(ctypes.byref(g), ctypes.byref(host))
        elif mode == 1:
            bx = ctx.lib.vehicle_exit_state(ctypes.byref(g), ctypes.byref(host))
            status = -1 if bx < 0 else 0
        else:
            status = ctx.lib.vehicle_transition(ctypes.byref(g), mode, ctypes.byref(host))
        entry = {"entry":0x400E, "control":0x0255, "transition":0x02B5, "predraw":0x0641}[caller]
        out = m.call(0, entry, bx=mode, es=m.DATA_SEG, max_instr=100_000_000)
        CASES += 1
        if caller == "transition" and mode == 1 and bx != out['bx']:
            return ['vehicle exit BX %d: %04x != %04x'%(i, bx, out['bx'])]
        if stream_logs[0] != stream_logs[1]:
            return ['player-control stream input %d'%i]
        n = ctx.lib.game_events(buf, 512)
        events = [(e.kind, e.a, e.b if e.kind == 1 else 0) for e in buf[:n]]
        if status or audio_logs[0] != audio_logs[1] or stat_logs[0] != stat_logs[1] or events != calls:
            return [f'{caller} {i}: status {status}, native events {events}, original events {calls}']
        if len(files.calls) != len(m.image_calls):
            return ['transition DOS count %d: %d != %d'%(i, len(files.calls), len(m.image_calls))]
        for a, b in zip(files.calls, m.image_calls):
            if a[0] != b[0]:
                return ['transition DOS args %d'%i]
            error = check_memory(a[1], b[1], spans)
            if error:
                return ['transition DOS state %d: %s'%(i, error)]
        compare('native vehicle transition %d mode %d'%(i, mode), mem, planes, m, spans, fails)
        if fails:
            return fails
        if files.handles:
            return ['transition file handles leaked']
    return fails
