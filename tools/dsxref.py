"""Cross-reference of the main data segment: for each variable, which routines read it and
which write it, how the C code uses it, and its value in a live game.

  python tools/dsxref.py 1153 DE52 ...       one report per address (hex)
  python tools/dsxref.py --unnamed 60        the 60 most-used addresses in src/ that have
                                             no name in src/dsvars.h yet
  python tools/dsxref.py --uses              usage counts of literal addresses in src/
  python tools/dsxref.py --compact --unnamed 40 80   shorter report, addresses 81..120

Reads disasm/seg_*.asm (run tools/disasm.py first), src/*.c and the in-game snapshot.
"""
import collections
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)

WRITE_FIRST = {'mov', 'inc', 'dec', 'add', 'sub', 'adc', 'sbb', 'or', 'and', 'xor', 'not', 'neg', 'shl', 'shr',
               'sar', 'sal', 'rol', 'ror', 'rcl', 'rcr', 'pop', 'xchg'}
READ_MODIFY = {'inc', 'dec', 'add', 'sub', 'adc', 'sbb', 'or', 'and', 'xor', 'not', 'neg', 'shl', 'shr', 'sar',
               'sal', 'rol', 'ror', 'rcl', 'rcr', 'xchg'}
LITERAL = re.compile(r'\bDS_(?:U8|U16|I16|I8|U32)\(\s*(?:g->)?ds\s*,\s*(0x[0-9A-Fa-f]{1,4})\s*\)')


def var_names():
    """Offset -> name used in the listing (names.VARS plus the listing's w_/b_ placeholders)."""
    import names
    return dict(names.VARS)


def listing_xref():
    """{offset: {'r': set(functions), 'w': set(functions)}} for direct [var] operands in the
    main code segments (DS-relative memory operands without a segment override)."""
    import names
    by_name = {v: k for k, v in names.VARS.items()}
    ref = collections.defaultdict(lambda: {'r': set(), 'w': set()})
    for path in sorted(glob.glob(os.path.join(ROOT, 'disasm', 'seg_*.asm'))):
        func = '?'
        for line in open(path, encoding='utf-8', errors='replace'):
            if line.startswith('; ======== '):
                func = line.split()[2]
                continue
            m = re.match(r'^([0-9A-F]{4}):([0-9A-F]{4})\s+[0-9a-f]+\s+(\w+)\s+(.*)$', line.rstrip())
            if not m:
                continue
            mnem, ops = m.group(3), m.group(4)
            if re.search(r'\b(cs|es|ss):\[', ops):
                continue
            parts = [p.strip() for p in re.split(r',(?![^\[]*\])', ops)]
            for i, part in enumerate(parts):
                mm = re.search(r'\[(\w+)\]', part)
                if not mm:
                    continue
                name = mm.group(1)
                if re.fullmatch(r'[wbd]_[0-9A-F]{4}', name):
                    off = int(name[2:], 16)
                elif name in by_name:
                    off = by_name[name]
                else:
                    continue
                where = f'{m.group(1)}:{func}'
                if i == 0 and mnem in WRITE_FIRST:
                    ref[off]['w'].add(where)
                    if mnem in READ_MODIFY or mnem == 'xchg':
                        ref[off]['r'].add(where)
                else:
                    ref[off]['r'].add(where)
    return ref


def c_uses():
    uses = collections.Counter()
    files = collections.defaultdict(set)
    for path in glob.glob(os.path.join(ROOT, 'src', '*.c')):
        for m in LITERAL.finditer(open(path, encoding='utf-8').read()):
            off = int(m.group(1), 16)
            uses[off] += 1
            files[off].add(os.path.basename(path)[:-2])
    return uses, files


def named_in_header():
    path = os.path.join(ROOT, 'src', 'dsvars.h')
    if not os.path.exists(path):
        return {}
    out = {}
    for m in re.finditer(r'\b(D_[A-Z0-9_]+)\s*=\s*0x([0-9A-Fa-f]{4})', open(path, encoding='utf-8').read()):
        out[int(m.group(2), 16)] = m.group(1)
    return out


def snapshot_values(offsets):
    try:
        import dosemu
        m = dosemu.Machine()
        m.load(os.path.join(ROOT, 'out', 'emu', 'states', 'ingame.pkl'))
        return {o: m.ds_read(o, 4) for o in offsets}
    except Exception:
        return {}


def c_lines(off, limit):
    """A few C lines that use the literal address, with their file."""
    out = []
    pat = re.compile(r'DS_(?:U8|U16|I16|I8|U32)\(\s*(?:g->)?ds\s*,\s*0x0*%X\s*\)' % off, re.I)
    for path in sorted(glob.glob(os.path.join(ROOT, 'src', '*.c'))):
        for line in open(path, encoding='utf-8'):
            if pat.search(line):
                out.append(f'{os.path.basename(path)}: {line.strip()[:150]}')
                if len(out) >= limit:
                    return out
    return out


def report(offsets, ref, uses, files, compact=False):
    vals = snapshot_values(offsets)
    names = var_names()
    for o in offsets:
        r, w = ref.get(o, {'r': set(), 'w': set()})['r'], ref.get(o, {'r': set(), 'w': set()})['w']
        v = vals.get(o)
        vtxt = f'bytes {v.hex(" ")}' if v else ''
        if compact:
            short = lambda fs: ', '.join(sorted(f.split(':')[1] for f in fs)[:9]) or '-'
            print(f'{o:04X} {names.get(o, "")} uses {uses.get(o, 0)} val {vtxt}')
            print(f'   W: {short(w)}')
            print(f'   R: {short(r - w)}')
            for line in c_lines(o, 3):
                print(f'   c: {line}')
            continue
        print(f'{o:04X}  {names.get(o, "")}  C uses {uses.get(o, 0)} in {", ".join(sorted(files.get(o, ())))}  in-game {vtxt}')
        print(f'   written by: {", ".join(sorted(w)) or "-"}')
        print(f'   read by:    {", ".join(sorted(r - w)) or "-"}')


def main():
    args = sys.argv[1:]
    ref = listing_xref()
    uses, files = c_uses()
    if args and args[0] == '--uses':
        for o, c in uses.most_common():
            print(f'{o:04X} {c}')
        return
    compact = '--compact' in args
    args = [a for a in args if a != '--compact']
    if args and args[0] == '--unnamed':
        n = int(args[1]) if len(args) > 1 else 50
        skip = int(args[2]) if len(args) > 2 else 0
        done = named_in_header()
        offsets = [o for o, _ in uses.most_common() if o not in done][skip:skip + n]
    else:
        offsets = [int(a, 16) for a in args]
    report(offsets, ref, uses, files, compact)


if __name__ == '__main__':
    main()
