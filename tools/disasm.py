"""Recursive-descent disassembler for exe/TERM_unpacked.exe.

Builds a database of instructions, functions, labels and data cross-references and writes

  disasm/seg_XXXX.asm     annotated listing per segment that contains code
  disasm/functions.csv    every function: address, size, callers, how it was found, name
  disasm/vars.csv         every directly addressed DS variable with its readers/writers
  disasm/db.pkl           the database, for other tools (emulator coverage, diff tests)

Addresses are "file" segment:offset pairs (segment values before load-address fixup).

How code is found
  1. program entry, plus every seed in names.py (interrupt handlers, pointers stored as
     immediates, routines only reached through tables)
  2. direct near/far calls and jumps; far targets are confirmed by the relocation table
  3. `jmp/call word [reg+table]` tables whose entries all land inside the segment
  4. coverage recorded by the emulator (tools/dosemu.py --coverage), if disasm/coverage.txt exists
  5. gaps that decode cleanly from a boundary to a return are added as "orphan" functions
Each function records which of these found it, so guesses can be told from facts.

usage:
  python tools/disasm.py            rebuild everything
"""
import collections
import csv
import os
import pickle
import struct
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from capstone import x86_const as X

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
EXE = os.path.join(ROOT, 'exe', 'TERM_unpacked.exe')
OUT = os.path.join(ROOT, 'disasm')
DS = 0x5C27

sys.path.insert(0, HERE)
import names as NAMES  # noqa: E402


def load_exe():
    d = open(EXE, 'rb').read()
    nrel, hdrpar = struct.unpack_from('<HH', d, 6)
    reloff = struct.unpack_from('<H', d, 0x18)[0]
    relocs = set()
    for i in range(nrel):
        off, seg = struct.unpack_from('<HH', d, reloff + 4 * i)
        relocs.add(seg * 16 + off)
    return d[hdrpar * 16:], relocs


IMG, RELOCS = load_exe()
MD = Cs(CS_ARCH_X86, CS_MODE_16)
MD.detail = True

# Segment starts, from relocation targets and far-call operands. A near address belongs to
# the segment it was reached in; this list only bounds how far a segment's code may extend.
SEG_STARTS = [0x0000, 0x0FBA, 0x101F, 0x10BB, 0x11BC, 0x14A7, 0x14B5, 0x151B, 0x15AD, 0x1609,
              0x1720, 0x5776, 0x57C5, 0x5819, 0x5A4D, 0x5B0D, 0x5B1D, 0x5B48, 0x5B67, 0x5C01, 0x5C27, 0x6ACE]


# Creative Labs drivers linked into the exe (CT-VOICE, FMDRV and a wrapper). They keep their own
# data in their code segment, so the DS-relative heuristics below do not apply to them.
THIRD_PARTY = {0x0FBA, 0x101F, 0x10BB}


def seg_end(seg):
    """Linear end of the segment that starts at seg (next known segment start)."""
    nxt = [s for s in SEG_STARTS if s > seg]
    return (min(nxt) if nxt else 0x6ACE) * 16


class Ins:
    __slots__ = ('seg', 'off', 'size', 'mnem', 'ops', 'bytes', 'targets', 'flow', 'mem')


class DB:
    def __init__(self):
        self.ins = {}            # linear -> Ins
        self.covered = bytearray(len(IMG))
        self.funcs = {}          # linear -> {'seg','off','how':set,'callers':set}
        self.labels = {}         # linear -> set of referrers (jump targets)
        self.var_refs = collections.defaultdict(lambda: {'r': set(), 'w': set(), 'size': 0})
        self.indirect = []       # (linear, text) unresolved indirect transfers
        self.bad = []            # (linear, why)
        self.tables = {}         # linear table address -> list of target linear


def lin(seg, off):
    return seg * 16 + (off & 0xFFFF)


COND = {X.X86_INS_JAE, X.X86_INS_JA, X.X86_INS_JBE, X.X86_INS_JB, X.X86_INS_JCXZ, X.X86_INS_JE,
        X.X86_INS_JGE, X.X86_INS_JG, X.X86_INS_JLE, X.X86_INS_JL, X.X86_INS_JNE, X.X86_INS_JNO,
        X.X86_INS_JNP, X.X86_INS_JNS, X.X86_INS_JO, X.X86_INS_JP, X.X86_INS_JS, X.X86_INS_LOOP,
        X.X86_INS_LOOPE, X.X86_INS_LOOPNE}
STOP = {X.X86_INS_RET, X.X86_INS_RETF, X.X86_INS_IRET, X.X86_INS_HLT}


def decode(seg, off):
    a = lin(seg, off)
    if a >= len(IMG):
        return None
    it = next(MD.disasm(IMG[a:a + 16], off), None)
    return it


def table_targets(db, seg, table_seg, disp):
    """Read a near jump/call table at table_seg:disp. Returns target offsets (possibly empty)."""
    base = lin(table_seg, disp)
    lo, hi = seg * 16, seg_end(seg)
    out = []
    limit = NAMES.EXTRA_TABLES.get((seg, disp), 96) if table_seg == DS else 96
    for i in range(limit):
        a = base + 2 * i
        if a + 2 > len(IMG) or a in RELOCS:
            break
        t = struct.unpack_from('<H', IMG, a)[0]
        tl = seg * 16 + t
        if not (lo <= tl < hi) or t < 0x200:
            break
        # must look like the start of an instruction that is not obviously padding
        it = decode(seg, t)
        if it is None or IMG[tl] == 0 and IMG[tl + 1] == 0:
            break
        out.append(t)
    return out


def explore(db, seeds):
    """seeds: iterable of (seg, off, how, is_function, referrer_linear)."""
    work = collections.deque(seeds)
    while work:
        seg, off, how, is_func, ref = work.popleft()
        a = lin(seg, off)
        if a >= len(IMG):
            continue
        if is_func:
            f = db.funcs.setdefault(a, {'seg': seg, 'off': off, 'how': set(), 'callers': set()})
            f['how'].add(how)
            if ref is not None:
                f['callers'].add(ref)
        elif how != 'executed':
            # (executed block starts are only decoding seeds: emulation slices cut blocks at
            # arbitrary instructions, so they are not meaningful labels)
            db.labels.setdefault(a, set())
            if ref is not None:
                db.labels[a].add(ref)
        while True:
            a = lin(seg, off)
            if a in db.ins:
                break
            if db.covered[a]:
                db.bad.append((a, 'lands inside another instruction'))
                break
            it = decode(seg, off)
            if it is None:
                db.bad.append((a, 'undecodable'))
                break
            if any(db.covered[a + k] for k in range(it.size)):
                db.bad.append((a, 'overlaps decoded code'))
                break
            ins = Ins()
            ins.seg, ins.off, ins.size = seg, off, it.size
            ins.mnem, ins.ops, ins.bytes = it.mnemonic, it.op_str, bytes(it.bytes)
            ins.targets, ins.flow, ins.mem = [], 'next', None
            db.ins[a] = ins
            for k in range(it.size):
                db.covered[a + k] = 1
            nxt = (off + it.size) & 0xFFFF
            iid = it.id
            ops = it.operands
            # ---- data references through a plain [disp16] operand
            for op in ops:
                if op.type == X.X86_OP_MEM and op.mem.base == 0 and op.mem.index == 0:
                    sreg = op.mem.segment
                    if sreg in (0, X.X86_REG_DS):
                        v = db.var_refs[op.mem.disp & 0xFFFF]
                        v['size'] = max(v['size'], op.size)
                        (v['w'] if (op.access & 2) else v['r']).add(a)
                        ins.mem = op.mem.disp & 0xFFFF
            # ---- control flow
            if iid in (X.X86_INS_JMP, X.X86_INS_CALL, X.X86_INS_LJMP, X.X86_INS_LCALL):
                iscall = iid in (X.X86_INS_CALL, X.X86_INS_LCALL)
                op = ops[0] if ops else None
                first = it.bytes[0]
                curated = NAMES.INDIRECT_TARGETS.get((seg, off))
                if curated is not None:
                    ins.targets.extend(curated)
                    for tseg, toff in curated:
                        work.append((tseg, toff, 'indirect call', True, a))
                elif first in (0x9A, 0xEA):                    # far ptr16:16
                    toff, tseg = struct.unpack_from('<HH', it.bytes, 1)
                    if (a + 3) in RELOCS:
                        ins.targets.append((tseg, toff))
                        work.append((tseg, toff, 'far call' if iscall else 'far jump', True, a))
                    else:
                        db.bad.append((a, 'far transfer without relocation'))
                elif op is not None and op.type == X.X86_OP_IMM:
                    toff = op.imm & 0xFFFF
                    ins.targets.append((seg, toff))
                    work.append((seg, toff, 'call' if iscall else 'jump', iscall, a))
                elif op is not None and op.type == X.X86_OP_MEM:
                    m = op.mem
                    resolved = False
                    if op.size == 2 and m.disp and (m.base or m.index) and not (m.base and m.index)                             and seg not in THIRD_PARTY:
                        tseg_reg = m.segment
                        tbl_seg = seg if tseg_reg == X.X86_REG_CS else DS
                        ts = table_targets(db, seg, tbl_seg, m.disp & 0xFFFF)
                        if len(ts) >= 2:
                            resolved = True
                            db.tables[lin(tbl_seg, m.disp & 0xFFFF)] = [lin(seg, t) for t in ts]
                            for t in ts:
                                ins.targets.append((seg, t))
                                work.append((seg, t, 'table', iscall, a))
                    if not resolved:
                        db.indirect.append((a, f'{it.mnemonic} {it.op_str}'))
                else:
                    db.indirect.append((a, f'{it.mnemonic} {it.op_str}'))
                if iscall:
                    if a in NAMES.NORETURN_CALLS:
                        ins.flow = 'stop'
                        break
                    off = nxt
                    continue
                ins.flow = 'stop'
                break
            if iid in COND:
                toff = ops[0].imm & 0xFFFF
                ins.targets.append((seg, toff))
                work.append((seg, toff, 'jump', False, a))
                off = nxt
                continue
            if iid in STOP:
                ins.flow = 'stop'
                break
            if iid == X.X86_INS_INT and ops and ops[0].imm == 0x20:
                ins.flow = 'stop'
                break
            if iid == X.X86_INS_INT and ops and ops[0].imm == 0x21:
                prev = db.ins.get(a - 2)
                if prev is not None and prev.bytes == b'\xb4\x4c':
                    ins.flow = 'stop'
                    break
            off = nxt


def pointer_seeds(db):
    """Code pointers passed as immediates: `mov bp, imm` before a routine that does `call bp`,
    and `mov word [var], imm` where var is later called through."""
    out = []
    called_vars = set()
    for a, txt in db.indirect:
        ins = db.ins[a]
        if ins.mem is not None:
            called_vars.add(ins.mem)
    uses_call_bp = any(t.endswith('call bp') for _, t in db.indirect)
    for a, ins in list(db.ins.items()):
        if ins.seg in THIRD_PARTY:
            continue
        b = ins.bytes
        tgt = None
        if uses_call_bp and len(b) == 3 and b[0] == 0xBD:                     # mov bp, imm16
            tgt, why = struct.unpack_from('<H', b, 1)[0], 'callback (mov bp)'
        elif len(b) == 6 and b[0] == 0xC7 and b[1] == 0x06:                   # mov word [disp16], imm16
            disp, imm = struct.unpack_from('<HH', b, 2)
            if disp in called_vars:
                tgt, why = imm, 'stored pointer'
        if tgt is None or tgt < 0x10:
            continue
        seg = ins.seg
        tl = lin(seg, tgt)
        if not (seg * 16 <= tl < seg_end(seg)) or tl in db.funcs:
            continue
        if db.covered[tl] and tl not in db.ins:
            continue
        out.append((seg, tgt, why, True, a))
    return out


def orphan_pass(db):
    """Look for uncovered runs inside code areas that decode cleanly to a return."""
    found = []
    code_segs = sorted({f['seg'] for f in db.funcs.values()})
    for seg in code_segs:
        lo, hi = seg * 16, seg_end(seg)
        last_code = max((a for a in db.ins if lo <= a < hi), default=lo)
        a = lo
        while a < last_code:
            if db.covered[a]:
                a += 1
                continue
            # start of a gap; only consider it if the previous byte ends an instruction
            start = a
            while a < last_code and not db.covered[a]:
                a += 1
            gap_end = a
            # skip padding
            s = start
            while s < gap_end and IMG[s] in (0x00, 0x90):
                s += 1
            if gap_end - s < 3:
                continue
            # trial decode
            p = s
            n = 0
            ok = False
            while p < gap_end:
                it = next(MD.disasm(IMG[p:p + 16], p - lo), None)
                if it is None:
                    break
                n += 1
                p += it.size
                if it.id in STOP or it.id in (X.X86_INS_JMP, X.X86_INS_LJMP):
                    ok = n >= 2
                    break
            if ok:
                found.append((seg, s - lo))
    return found


def build():
    db = DB()
    seeds = [(0x0000, 0x0000, 'entry', True, None)]
    for (seg, off), why in NAMES.SEEDS.items():
        seeds.append((seg, off, why, True, None))
    for (seg, tbl), count in NAMES.EXTRA_TABLES.items():
        for i in range(count):
            t = struct.unpack_from('<H', IMG, DS * 16 + tbl + 2 * i)[0]
            if t:
                seeds.append((seg, t, 'table', True, None))
    cov = os.path.join(OUT, 'coverage.txt')
    if os.path.exists(cov):
        for line in open(cov):
            line = line.strip()
            if line and not line.startswith('#'):
                s, o = line.split(':')
                seeds.append((int(s, 16), int(o, 16), 'executed', False, None))
    explore(db, seeds)
    for _ in range(4):
        extra = pointer_seeds(db)
        if not extra:
            break
        explore(db, extra)
    for _ in range(6):
        orphans = [(s, o) for s, o in orphan_pass(db) if lin(s, o) not in db.funcs]
        if not orphans:
            break
        explore(db, [(s, o, 'orphan', True, None) for s, o in orphans])
    return db


def name_of(db, a, seg, off):
    n = NAMES.FUNCS.get((seg, off))
    if n:
        return n
    if a in db.funcs:
        return f'sub_{seg:04X}_{off:04X}'
    return f'loc_{seg:04X}_{off:04X}'


def var_name(disp, size=0):
    n = NAMES.VARS.get(disp)
    if n:
        return n
    return f'{"b" if size == 1 else "w" if size == 2 else "d" if size == 4 else "v"}_{disp:04X}'


def func_extents(db):
    """Assign each instruction to the nearest preceding function start in its segment."""
    starts = sorted(db.funcs)
    sizes = {}
    import bisect
    for a, ins in db.ins.items():
        i = bisect.bisect_right(starts, a) - 1
        if i < 0:
            continue
        f = starts[i]
        if db.funcs[f]['seg'] != ins.seg:
            continue
        sizes[f] = max(sizes.get(f, 0), a + ins.size - f)
    return sizes


def range_seg(a):
    """The known segment whose address range contains linear address a."""
    return max(s for s in SEG_STARTS if s * 16 <= a)


def write_listing(db):
    os.makedirs(OUT, exist_ok=True)
    sizes = func_extents(db)
    by_range = collections.defaultdict(list)
    for a in db.ins:
        by_range[range_seg(a)].append(a)
    for seg in sorted(by_range):
        lo = seg * 16
        addrs = sorted(by_range[seg])
        end = addrs[-1] + db.ins[addrs[-1]].size
        with open(os.path.join(OUT, f'seg_{seg:04X}.asm'), 'w', encoding='utf-8') as f:
            f.write(f'; The Terminator (1991) v1.00B - segment {seg:04X}, generated by tools/disasm.py\n')
            f.write(f'; {len(addrs)} instructions, {sum(db.ins[a].size for a in addrs)} code bytes '
                    f'of {end - lo} up to the last instruction\n\n')
            a = lo
            while a < end:
                ins = db.ins.get(a)
                if ins is None:
                    b = a
                    while b < end and b not in db.ins:
                        b += 1
                    chunk = IMG[a:b]
                    if len(chunk) > 16 and not any(chunk):
                        f.write(f'{seg:04X}:{a - lo:04X}                    ; {len(chunk)} zero bytes\n')
                    else:
                        for o in range(0, len(chunk), 16):
                            part = chunk[o:o + 16]
                            txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in part)
                            f.write(f'{seg:04X}:{a - lo + o:04X}  db {", ".join(f"0x{c:02x}" for c in part)}'
                                    f'    ; {txt}\n')
                    a = b
                    continue
                iseg = ins.seg
                if a in db.funcs:
                    fn = db.funcs[a]
                    f.write(f'\n; ======== {name_of(db, a, iseg, ins.off)}   size {sizes.get(a, 0)}   '
                            f'found by: {", ".join(sorted(fn["how"]))}   callers: {len(fn["callers"])}\n')
                    cver = NAMES.C_VERSIONS.get((iseg, ins.off))
                    if cver:
                        f.write(f';   C version (verified by tests/): {cver}\n')
                    native = getattr(NAMES, 'NATIVE', {}).get((iseg, ins.off))
                    if native:
                        f.write(f';   not translated, left to the host: {native}\n')
                    dead = getattr(NAMES, 'DEAD', {}).get((iseg, ins.off))
                    if dead:
                        f.write(f';   not translated, unreachable: {dead}\n')
                    note = NAMES.NOTES.get((iseg, ins.off))
                    if note:
                        for ln in note.strip().splitlines():
                            f.write(f';   {ln}\n')
                    f.write(f'{name_of(db, a, iseg, ins.off)}:\n')
                elif a in db.labels:
                    f.write(f'{name_of(db, a, iseg, ins.off)}:\n')
                ops = ins.ops
                cmt = ''
                if (iseg, ins.off) in NAMES.INDIRECT_TARGETS:
                    cmt = 'targets: ' + ', '.join(name_of(db, lin(ts, to), ts, to) for ts, to in ins.targets)
                elif len(ins.targets) == 1:
                    ts, to = ins.targets[0]
                    ops = name_of(db, lin(ts, to), ts, to)
                elif ins.targets:
                    cmt = 'table: ' + ', '.join(name_of(db, lin(s_, o_), s_, o_) for s_, o_ in ins.targets[:12]) + (
                        ' ...' if len(ins.targets) > 12 else '')
                if ins.mem is not None:
                    vn = var_name(ins.mem, db.var_refs[ins.mem]['size'])
                    ops = ops.replace(f'[0x{ins.mem:x}]', f'[{vn}]').replace(f'[{ins.mem}]', f'[{vn}]')
                line = f'{iseg:04X}:{ins.off:04X}  {ins.bytes.hex():<16} {ins.mnem} {ops}'
                if cmt:
                    line = f'{line:<70} ; {cmt}'
                f.write(line + '\n')
                if ins.flow == 'stop':
                    f.write('\n')
                a += ins.size
    with open(os.path.join(OUT, 'functions.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['segment', 'offset', 'name', 'size', 'callers', 'found_by'])
        for a in sorted(db.funcs):
            fn = db.funcs[a]
            w.writerow([f'{fn["seg"]:04X}', f'{fn["off"]:04X}', name_of(db, a, fn['seg'], fn['off']),
                        sizes.get(a, 0), len(fn['callers']), '+'.join(sorted(fn['how']))])
    with open(os.path.join(OUT, 'vars.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['ds_offset', 'name', 'size', 'readers', 'writers', 'initial_value'])
        for disp in sorted(db.var_refs):
            v = db.var_refs[disp]
            a = DS * 16 + disp
            init = IMG[a:a + max(1, min(4, v['size'] or 2))].hex() if a < len(IMG) else ''
            w.writerow([f'{disp:04X}', var_name(disp, v['size']), v['size'], len(v['r']), len(v['w']), init])
    with open(os.path.join(OUT, 'db.pkl'), 'wb') as f:
        pickle.dump({'ins': {a: (i.seg, i.off, i.size, i.mnem, i.ops, i.flow, i.targets) for a, i in db.ins.items()},
                     'funcs': db.funcs, 'labels': {a: sorted(v) for a, v in db.labels.items()},
                     'vars': {k: {'r': sorted(v['r']), 'w': sorted(v['w']), 'size': v['size']}
                              for k, v in db.var_refs.items()},
                     'indirect': db.indirect, 'bad': db.bad, 'tables': db.tables}, f)


def report(db):
    code_bytes = sum(i.size for i in db.ins.values())
    how = collections.Counter()
    for fn in db.funcs.values():
        for h in fn['how']:
            how[h] += 1
    print(f'instructions {len(db.ins)}, code bytes {code_bytes}, functions {len(db.funcs)}')
    print('functions by discovery:', dict(how))
    print(f'unresolved indirect transfers {len(db.indirect)}, decode problems {len(db.bad)}, '
          f'jump tables {len(db.tables)}, DS variables {len(db.var_refs)}')
    per = collections.Counter()
    for i in db.ins.values():
        per[i.seg] += i.size
    for seg in sorted(per):
        lo = seg * 16
        last = max(a + db.ins[a].size for a in db.ins if db.ins[a].seg == seg)
        print(f'   seg {seg:04X}: {per[seg]:6} code bytes, span {last - lo:6}, '
              f'{100 * per[seg] / max(1, last - lo):5.1f}% of span decoded')


if __name__ == '__main__':
    db = build()
    write_listing(db)
    report(db)
