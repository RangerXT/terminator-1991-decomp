"""AFD0 removal with AD37 spawn request intercepted and compared explicitly."""
import ctypes
import os
import random
import struct
import dosemu
from unicorn import UC_HOOK_CODE
CASES = 0

def run(ctx):
    global CASES
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/ingame.pkl'))
    saved = m.ds_read(0, 65536)
    rng = random.Random(0xAFD0)
    requests = []
    def spawn(uc, address, size, user):
        requests.append(m.r(dosemu.UC_X86_REG_AX))
        sp = m.r(dosemu.UC_X86_REG_SP)
        ss = m.r(dosemu.UC_X86_REG_SS)
        uc.reg_write(dosemu.UC_X86_REG_IP, m.rw(ss, sp))
        uc.reg_write(dosemu.UC_X86_REG_SP, (sp+2)&65535)
    addr = (dosemu.LOAD_SEG<<4)+0xAD37
    m.uc.hook_add(UC_HOOK_CODE, spawn, None, addr, addr)
    for i in range(384):
        m.ds_write(0, saved)
        count = [0, 1, 2, 8, 30, 31][i%6]
        index = [0, max(0, count-1), count, count+1][(i//6)%4]
        m.ds_write(0x0B30, bytes(rng.randrange(256) for _ in range(33*22)))
        m.ds_write(0x9000, bytes(rng.randrange(256) for _ in range(33*12)))
        record = 0x9000+index*12
        for off, val in [(0x119A, count), (record+8, index*2), (0x119C, 0), (0x116E, 65535), (0x03A4, 0)]:
            m.ds_write(off, struct.pack('<H', val))
        m.ds_write(0x0B30+index*22, struct.pack('<H', [0, 2, 4, 14][(i//24)%4]))
        m.ds_write(0xB69F, bytes([(i//96)%2]))
        m.ds_write(0x115A, bytes([(i//192)%2]))
        ds = ctypes.create_string_buffer(m.ds_read(0, 65536), 65536)
        request = ctx.lib.figure_remove(ds, record)
        requests.clear()
        m.call(0, 0xAFD0, bx=record, es=m.DATA_SEG)
        CASES += 1
        if requests != ([1] if request else []):
            return ['spawn request %d'%i]
        if ds.raw[:0xEA70] != m.ds_read(0, 0xEA70):
            return ['figure removal state %d'%i]
    return []
