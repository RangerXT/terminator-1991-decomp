"""FAAF/FACE file helpers including success, open failure and read-failure handle leak."""
import ctypes
import os
import struct
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_drawlist import make_game
from test_imageload import Files, trace_dos, check_memory, regions, compare
import dosemu

CASES = 0


def run(ctx):
    global CASES
    fails = []
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    trace_dos(m)
    logged = m._dos
    def failure():
        if getattr(m, 'fail_read', False) and m.ax() >> 8 == 0x3F:
            # Log the same real service input, then fail before any file bytes are read.
            args = (0x3F, m.r(dosemu.UC_X86_REG_BX), m.r(dosemu.UC_X86_REG_DS),
                    m.r(dosemu.UC_X86_REG_DX), m.r(dosemu.UC_X86_REG_CX))
            from test_polyfill import planes_of
            m.image_calls.append((args, bytes(m.uc.mem_read(0, 0xA0000)), planes_of(m)))
            return m._err(5)
        return logged()
    m._dos = failure
    spans = regions(m)
    ctx.lib.file_load.restype = ctypes.c_uint32
    for i in range(30):
        m.ds_write(0, saved)
        far = i % 2
        filename = ['BINOS.IMG', 'SCOPES.IMG', 'MAPMASK.IMG', 'DOES_NOT_EXIST.IMG', 'FRAME.IMG'][i % 5]
        m.ds_write(0x8000, filename.encode('ascii') + b'\0')
        segment = 0x8000 if far else m.DATA_SEG
        dest = [0x100, 0xF800, 0xFFFE][(i // 2) % 3]
        native = Files(m)
        native.fail_read = m.fail_read = i >= 20 and i % 5 != 3
        m.image_calls.clear()
        g, mem, planes = make_game(m)
        result = ctx.lib.file_load(ctypes.byref(g), ctypes.byref(native.host), 0x8000, segment, dest)
        out = m.call(0, 0xFACE if far else 0xFAAF, dx=0x8000, es=segment, bx=dest)
        CASES += 1
        if result != out['ax'] | ((out['flags'] & 1) << 16):
            return [f'file helper {i}: AX/carry differs']
        if len(native.calls) != len(m.image_calls):
            return [f'file helper {i}: call count differs']
        for c, original in zip(native.calls, m.image_calls):
            if c[0] != original[0]:
                return [f'file helper {i}: service arguments differ']
            error = check_memory(c[1], original[1], spans)
            if error:
                return [f'file helper {i} before DOS: {error}']
        if native.next_handle != m.next_handle:
            return [f'file helper {i}: next handle differs']
        if bool(native.handles) != bool(native.fail_read):
            return [f'file helper {i}: read-error handle behavior differs']
        compare(f'file helper {i}', mem, planes, m, spans, fails)
        if fails:
            return fails
        # Explicit cleanup of handles the reference leaves open on failed reads.
        for handle in native.handles:
            stream, name = m.files.pop(handle)
            stream.close()
    return fails
