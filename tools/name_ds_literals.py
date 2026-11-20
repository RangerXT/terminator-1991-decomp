"""Replace literal data-segment addresses in src/ with the names in src/dsvars.h.

  python tools/name_ds_literals.py            rewrite src/*.c and src/*.h
  python tools/name_ds_literals.py --check    only report what would change

Only exact accesses of the form DS_U8(ds, 0x1234), DS_U16(g->ds, 0x1234) and so on are
touched, so the generated code cannot change: the names are enum constants with the same
values. Key-table entries (0x5BD9 + scancode) become KEY_DOWN(SC_...). Run it again after
adding names to src/dsvars.h; prove the result with an identical build (see
PROJECT_STATUS.md, "How to check").
"""
import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ACCESS = re.compile(r'\b(DS_(?:U8|U16|I16|I8|U32)\(\s*(?:g->)?ds\s*,\s*)(0x[0-9A-Fa-f]{1,4})(\s*\))')


def load_names():
    text = open(os.path.join(ROOT, 'src', 'dsvars.h'), encoding='utf-8').read()
    names = {}
    for m in re.finditer(r'\b(DS_[A-Z0-9_]+)\s*=\s*0x([0-9A-Fa-f]+)', text):
        off = int(m.group(2), 16)
        if off in names:
            raise SystemExit(f'two names for 0x{off:04X}: {names[off]} and {m.group(1)}')
        names[off] = m.group(1)
    key_base = int(re.search(r'#define DS_KEY_DOWN\s+0x([0-9A-Fa-f]+)', text).group(1), 16)
    scancodes = {int(m.group(2), 16): m.group(1) for m in re.finditer(r'\b(SC_[A-Z0-9_]+)\s*=\s*0x([0-9A-Fa-f]+)', text)}
    return names, key_base, scancodes


def main():
    check = '--check' in sys.argv
    names, key_base, scancodes = load_names()
    total = 0
    unknown_keys = set()
    for path in sorted(glob.glob(os.path.join(ROOT, 'src', '*.c')) + [os.path.join(ROOT, 'src', 'term.h')]):
        text = open(path, encoding='utf-8').read()
        count = 0

        def replace(m):
            nonlocal count
            off = int(m.group(2), 16)
            if off in names:
                count += 1
                return m.group(1) + names[off] + m.group(3)
            if key_base <= off < key_base + 0x80:
                sc = off - key_base
                if sc in scancodes:
                    count += 1
                    return m.group(1) + f'KEY_DOWN({scancodes[sc]})' + m.group(3)
                unknown_keys.add(sc)
            return m.group(0)

        new = ACCESS.sub(replace, text)
        if count:
            total += count
            print(f'{os.path.basename(path)}: {count}')
            if not check:
                open(path, 'w', encoding='utf-8', newline='\n').write(new)
    print(f'{total} accesses named' + (' (check only)' if check else ''))
    if unknown_keys:
        print('key-table entries without a scancode name:', ', '.join(f'{k:02X}' for k in sorted(unknown_keys)))


if __name__ == '__main__':
    main()
