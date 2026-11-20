"""Helpers for poking at exe/TERM_unpacked.exe (16-bit real-mode MZ).

usage:
  python tools/exe.py dis  <seg:off | linear> [count]     disassemble
  python tools/exe.py str  <regex>                        find strings (offset shown as DS-relative when inside DS)
  python tools/exe.py xref <ds_offset_hex>                code that loads this 16-bit immediate
  python tools/exe.py find <hex bytes>                    raw byte search
  python tools/exe.py dump <seg:off | linear> [len]       hex dump
"""
import os
import re
import struct
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_16

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(HERE, '..', 'exe', 'TERM_unpacked.exe')
DS = 0x5C27
CODE_SEGS = [0x0000, 0x0FBA, 0x101F, 0x10BB, 0x11BC, 0x14A7, 0x14B5, 0x151B, 0x15AD, 0x1609, 0x1720]
CODE_END = 0x17200


def load():
    d = open(EXE, 'rb').read()
    hdr = struct.unpack_from('<H', d, 8)[0] * 16
    return d[hdr:]


IMG = load()
MD = Cs(CS_ARCH_X86, CS_MODE_16)


def addr(s):
    if ':' in s:
        a, b = s.split(':')
        return int(a, 16) * 16 + int(b, 16)
    return int(s, 16)


def seg_of(lin):
    """Return the code segment containing a linear address."""
    best = 0
    for s in CODE_SEGS:
        if s * 16 <= lin:
            best = s
    return best


def dis(lin, count=40, stop_at_ret=False):
    seg = seg_of(lin)
    out = []
    for i, ins in enumerate(MD.disasm(IMG[lin:lin + count * 8], lin - seg * 16)):
        if i >= count:
            break
        out.append(f'{seg:04x}:{ins.address:04x}  {ins.bytes.hex():<14} {ins.mnemonic} {ins.op_str}')
        if stop_at_ret and ins.mnemonic in ('ret', 'retf', 'iret'):
            break
    return out


def strings(pat, minlen=4):
    rx = re.compile(pat.encode(), re.I)
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, IMG):
        if rx.search(m.group()):
            o = m.start()
            rel = f'ds:{o - DS * 16:04x}' if DS * 16 <= o < DS * 16 + 0x10000 else '       '
            yield o, rel, m.group().decode('latin1')


def xref(val):
    """Find instructions in the code area with val as a 16-bit immediate/displacement."""
    pat = struct.pack('<H', val)
    out = []
    start = 0
    code = IMG[:CODE_END]
    while True:
        i = code.find(pat, start)
        if i < 0:
            break
        start = i + 1
        # try to decode an instruction ending at or containing this immediate
        for back in range(1, 6):
            s = i - back
            if s < 0:
                continue
            ins = next(MD.disasm(code[s:s + 8], s - seg_of(s) * 16), None)
            if ins and s + ins.size >= i + 2 and s + ins.size <= i + 4 and hex(val) in ins.op_str:
                out.append((s, f'{seg_of(s):04x}:{ins.address:04x}  {ins.mnemonic} {ins.op_str}'))
                break
    return out


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'dis':
        print('\n'.join(dis(addr(a[1]), int(a[2]) if len(a) > 2 else 40)))
    elif a[0] == 'str':
        for o, rel, s in strings(a[1]):
            print(f'{o:06x} {rel} {s}')
    elif a[0] == 'xref':
        for s, t in xref(int(a[1], 16)):
            print(f'{s:06x} {t}')
    elif a[0] == 'find':
        pat = bytes.fromhex(''.join(a[1:]))
        i = IMG.find(pat)
        while i >= 0:
            print(f'{i:06x}')
            i = IMG.find(pat, i + 1)
    elif a[0] == 'dump':
        lin = addr(a[1])
        n = int(a[2], 0) if len(a) > 2 else 256
        for o in range(lin, lin + n, 16):
            b = IMG[o:o + 16]
            print(f'{o:06x}  {b.hex(" "):<47}  {"".join(chr(c) if 32 <= c < 127 else "." for c in b)}')


if __name__ == '__main__':
    main()
