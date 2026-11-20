"""Original sample cache/groups/requests vs native C, with actual RS file bytes.
Stat metadata, completion wait and device submit are identical explicit host stubs.
No sample playback backend/IRQ timing is claimed. DOS byte IO boundaries are checked.
"""
import ctypes, os, random, struct, sys
from unicorn import UC_HOOK_CODE
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu
from test_drawlist import make_game, compare
from test_imageload import Files, trace_dos, check_memory, ImageIO
from test_mapsetupreal import RESOURCE, Resources
CASES = 0

class SoundServices(ctypes.Structure):
    _fields_ = [('files', ctypes.POINTER(ImageIO)), ('platform', ctypes.POINTER(Resources))]


def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0x8B1E)
    fails = []
    active = [None]
    counts = {0xF6B3:0, 0x0100:0, 0x0818:0}
    trace_dos(m)
    stack = m.r(dosemu.UC_X86_REG_SS)<<4
    spans = [(0, stack), (stack+1024, 0xA0000)]
    m.wb(dosemu.LOAD_SEG, 0xF6B3, bytes([0xC3]))
    at = (dosemu.LOAD_SEG<<4)+0xF6B3
    def stat(uc, address, size, user):
        active[0](0xF6B3, m.r(dosemu.UC_X86_REG_SI), 0)
        m.w(dosemu.UC_X86_REG_EFLAGS, m.r(dosemu.UC_X86_REG_EFLAGS)|0x40)
    m.uc.hook_add(UC_HOOK_CODE, stat, None, at, at)
    for off in [0x8AA5, 0x8AC5, 0x8AE5, 0x8B05]:
        at = (dosemu.LOAD_SEG<<4)+off
        def wait(uc, address, size, user):
            if m.ds_read(0xAA83, 1)[0]:
                active[0](0x0100, 0, 0)
        m.uc.hook_add(UC_HOOK_CODE, wait, None, at, at)
    m.wb(dosemu.LOAD_SEG+0x5B67, 0x0818, bytes([0xCB]))
    at = ((dosemu.LOAD_SEG+0x5B67)<<4)+0x0818
    def play(uc, address, size, user):
        if m.r(dosemu.UC_X86_REG_SI):
            raise AssertionError('sample pointer offset')
        active[0](0x0818, m.r(dosemu.UC_X86_REG_ES), m.r(dosemu.UC_X86_REG_CX))
    m.uc.hook_add(UC_HOOK_CODE, play, None, at, at)
    def word(o, v):
        m.ds_write(o, struct.pack('<H', v&65535))
    def run_case(i, request=None):
        g, mem, planes = make_game(m)
        files = Files(m)
        m.image_calls.clear()
        logs = [[], []]
        errors = []
        def effect(which, read, write, op, a, b):
            logs[which].append((op, a, b, read(0xA6E9, 2), read(0xA743, 48), read(0x80E9, 1)))
            if which == 1:
                counts[op] += 1
            if op == 0x0100:
                write(0xAA83, bytes([0]))
            elif op == 0xF6B3:
                name = read(a, 64).split(bytes([0]))[0].decode('ascii')
                size = os.path.getsize(m._path(name))
                dta = bytearray(43)
                struct.pack_into('<I', dta, 26, size)
                encoded = os.path.basename(name).upper().encode('ascii')[:12]
                dta[30:30+len(encoded)] = encoded
                write(0x77E5, bytes(dta))
            elif op != 0x0818:
                raise AssertionError('unknown sound host service')
            return 0
        active[0] = lambda op, a, b:effect(1, m.ds_read, m.ds_write, op, a, b)
        @RESOURCE
        def callback(gp, op, a, b, user):
            try:
                return effect(0, lambda o, n:ctypes.string_at(g.ds+o, n), lambda o, v:ctypes.memmove(g.ds+o, v, len(v)), op, a, b)
            except Exception as exc:
                errors.append(repr(exc))
                return -1
        platform = Resources(callback, None)
        host = SoundServices(ctypes.pointer(files.host), ctypes.pointer(platform))
        if request is None:
            mode = [1, 3, 4, 6][i%4]
            entry = {1:0x8A9E, 3:0x8ABE, 4:0x8ADE, 6:0x8AFE}[mode]
            status = ctx.lib.sound_group_select(ctypes.byref(g), ctypes.byref(host), mode)
            m.call(0, entry, es=m.DATA_SEG, max_instr=5_000_000)
        else:
            status = ctx.lib.sound_request(ctypes.byref(g), ctypes.byref(host), request)
            m.call(0, 0x89A2, ax=request, es=m.DATA_SEG)
        if status or errors or logs[0] != logs[1]:
            return ['sound boundary %d status=%d errors=%s'%(i, status, errors)]
        if len(files.calls) != len(m.image_calls):
            return ['sound file IO count %d'%i]
        for a, b in zip(files.calls, m.image_calls):
            if a[0] != b[0]:
                return ['sound DOS inputs %d'%i]
            err = check_memory(a[1], b[1], spans)
            if err:
                return ['sound DOS state %d %s'%(i, err)]
        compare('sound cache/request %d'%i, mem, planes, m, fails)
        if files.handles:
            return ['sound handles leaked']
        return fails
    for i in range(128):
        m.ds_write(0, saved)
        word(0xA743, 0x8000)
        word(0xA75F, [0, 1, 16, 256, 512, 0xD74, 0x7FFF, 64][i//4%8])
        m.ds_write(0xA6E9, bytes([[1, 3, 4, 6][i%4] if i%7 == 0 else 0]))
        m.ds_write(0xAA83, bytes([i%5 == 0]))
        error = run_case(i)
        CASES += 1
        if error:
            return error
    for i in range(512):
        m.ds_write(0, saved)
        m.ds_write(0x0361, bytes([i%5 != 0]))
        m.ds_write(0x80E9, bytes([i%3 == 0]))
        m.ds_write(0xA763, bytes((j+i)%32 for j in range(14)))
        word(0xA771, 0xA763)
        for j in range(14):
            word(0xA743+j*2, 0 if (i+j)%7 == 0 else 0x8000+j*0x20)
        request = (rng.randrange(256)<<8)|([i%32, 99][i%2])
        error = run_case(i, request)
        CASES += 1
        if error:
            return error
    print('    native sound boundaries:', {('%04X'%op):n for op, n in counts.items()})
    if any(not n for n in counts.values()):
        return ['missing sound-group/request branches']
    return fails
