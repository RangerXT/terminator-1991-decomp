"""Unpack a PKLITE-compressed DOS MZ executable by emulating its stub.

The stub is run twice at two different load segments; every word that differs
by exactly the load-segment delta is a relocation, which lets us rebuild a
clean, relocatable MZ file that Ghidra / IDA / DOSBox can load directly.

usage:  python tools/unpack_exe.py term.exe exe/TERM_unpacked.exe
needs:  pip install unicorn
"""
import struct
import sys

from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_16, UC_HOOK_BLOCK, UC_HOOK_INTR
from unicorn.x86_const import (UC_X86_REG_CS, UC_X86_REG_IP, UC_X86_REG_SS, UC_X86_REG_SP,
                               UC_X86_REG_DS, UC_X86_REG_ES)

MEM_TOP = 0xA000  # top-of-conventional-memory segment reported in the PSP


def parse_mz(data):
    f = struct.unpack_from('<2s13H', data, 0)
    keys = 'sig lastpg pages nrel hdrpar minal maxal ss sp csum ip cs reloff ovl'.split()
    h = dict(zip(keys, f))
    h['hdr'] = h['hdrpar'] * 16
    h['size'] = h['pages'] * 512 - ((512 - h['lastpg']) if h['lastpg'] else 0)
    return h


def load_image(data, load_seg):
    """Return the load image with MZ relocations applied for load_seg."""
    h = parse_mz(data)
    img = bytearray(data[h['hdr']:h['size']])
    for i in range(h['nrel']):
        off, seg = struct.unpack_from('<HH', data, h['reloff'] + i * 4)
        a = seg * 16 + off
        struct.pack_into('<H', img, a, (struct.unpack_from('<H', img, a)[0] + load_seg) & 0xffff)
    return h, img


def run_stub(data, psp_seg):
    """Emulate until control leaves the stub (3rd distinct CS value). Returns (mem, regs)."""
    load = psp_seg + 0x10
    h, img = load_image(data, load)
    mu = Uc(UC_ARCH_X86, UC_MODE_16)
    mu.mem_map(0, 0x110000)
    mu.mem_write(load * 16, bytes(img))
    psp = bytearray(256)
    psp[0:2] = b'\xcd\x20'
    struct.pack_into('<H', psp, 2, MEM_TOP)
    psp[0x81] = 0x0d
    mu.mem_write(psp_seg * 16, bytes(psp))
    mu.mem_write(0xF0000, b'\xcf')  # IRET for every interrupt vector
    for i in range(256):
        mu.mem_write(i * 4, struct.pack('<HH', 0, 0xF000))
    mu.reg_write(UC_X86_REG_DS, psp_seg)
    mu.reg_write(UC_X86_REG_ES, psp_seg)
    mu.reg_write(UC_X86_REG_SS, (h['ss'] + load) & 0xffff)
    mu.reg_write(UC_X86_REG_SP, h['sp'])
    cs0 = (h['cs'] + load) & 0xffff
    mu.reg_write(UC_X86_REG_CS, cs0)
    mu.reg_write(UC_X86_REG_IP, h['ip'])
    seen = [cs0]
    done = []

    def on_block(uc, addr, size, user):
        c = uc.reg_read(UC_X86_REG_CS)
        if c not in seen:
            seen.append(c)
            if len(seen) > 2:  # stub start -> relocated stub -> original program
                done.append(True)
                uc.emu_stop()

    def on_intr(uc, intno, user):
        raise RuntimeError(f'stub raised INT {intno:02x}h - not a plain PKLITE stub?')

    mu.hook_add(UC_HOOK_BLOCK, on_block)
    mu.hook_add(UC_HOOK_INTR, on_intr)
    try:
        mu.emu_start(cs0 * 16 + h['ip'], 0, count=500_000_000)
    except UcError as e:
        raise RuntimeError(f'emulation failed: {e}')
    if not done:
        raise RuntimeError('stub never transferred control to the unpacked program')
    regs = {
        'cs': (mu.reg_read(UC_X86_REG_CS) - load) & 0xffff,
        'ip': mu.reg_read(UC_X86_REG_IP),
        'ss': (mu.reg_read(UC_X86_REG_SS) - load) & 0xffff,
        'sp': mu.reg_read(UC_X86_REG_SP),
    }
    mem = bytes(mu.mem_read(load * 16, MEM_TOP * 16 - load * 16))
    return mem, regs


def unpack(data):
    seg_a, seg_b = 0x1000, 0x2000
    a, ra = run_stub(data, seg_a)
    b, rb = run_stub(data, seg_b)
    assert ra == rb, (ra, rb)
    limit = ra['ss'] * 16  # program image ends where the stack segment starts
    delta = seg_b - seg_a
    relocs = []
    i = 0
    while i < limit - 1:
        if a[i] != b[i] or a[i + 1] != b[i + 1]:
            wa = a[i] | a[i + 1] << 8
            wb = b[i] | b[i + 1] << 8
            if (wb - wa) & 0xffff != delta:
                raise RuntimeError(f'unexplained difference at image offset {i:#x}')
            relocs.append(i)
            i += 2
        else:
            i += 1
    img = bytearray(a[:limit])
    for r in relocs:
        v = (struct.unpack_from('<H', img, r)[0] - (seg_a + 0x10)) & 0xffff
        struct.pack_into('<H', img, r, v)
    hdrsz = (0x1c + 4 * len(relocs) + 511) // 512 * 512
    total = hdrsz + len(img)
    hdr = struct.pack('<2s13H', b'MZ', total % 512, (total + 511) // 512, len(relocs), hdrsz // 16,
                      (ra['sp'] + 15) // 16, 0xffff, ra['ss'], ra['sp'], 0, ra['ip'], ra['cs'], 0x1c, 0)
    tbl = b''.join(struct.pack('<HH', r & 0xf, r >> 4) for r in relocs)
    return (hdr + tbl).ljust(hdrsz, b'\0') + bytes(img), ra, relocs, a, b


def main():
    src, dst = sys.argv[1], sys.argv[2]
    data = open(src, 'rb').read()
    out, regs, relocs, dump_a, dump_b = unpack(data)
    open(dst, 'wb').write(out)
    print(f'{dst}: {len(out)} bytes, {len(relocs)} relocations, '
          f'entry {regs["cs"]:04x}:{regs["ip"]:04x}, stack {regs["ss"]:04x}:{regs["sp"]:04x}')
    # self-check: loading the rebuilt file at either segment must reproduce the emulated memory
    for psp, dump in ((0x1000, dump_a), (0x2000, dump_b)):
        h, img = load_image(out, psp + 0x10)
        assert bytes(img) == dump[:len(img)], f'rebuilt image mismatch at load seg {psp + 0x10:#x}'
    print('self-check OK: rebuilt exe reproduces the unpacked memory image at two load addresses')


if __name__ == '__main__':
    main()
