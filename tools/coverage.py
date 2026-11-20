"""How much of the single-player game code is translated: function sizes from
disasm/functions.csv (python tools/disasm.py) against tools/names.py, where C_VERSIONS lists
the routines with a verified C version and NATIVE those that only reach the hardware or DOS
and are left to the host, and DEAD the code proven unreachable. Segments counted: 0000, 11BC, 14A7, 14B5, 15AD, 5776,
57C5 (the serial link 151B and the sound drivers 0FBA, 101F, 10BB, 5B67 are left out, see
PROJECT_STATUS.md).

usage:
  python tools/coverage.py [N]       totals, then the N largest routines left (default 40)
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import names  # noqa: E402

SEGS = {0x0000, 0x11BC, 0x14A7, 0x14B5, 0x15AD, 0x5776, 0x57C5}
native = getattr(names, 'NATIVE', {})
dead = getattr(names, 'DEAD', {})
total = done = host = unreachable = 0
left = []
with open(os.path.join(ROOT, 'disasm', 'functions.csv'), newline='') as f:
    for row in csv.DictReader(f):
        seg, off, size = int(row['segment'], 16), int(row['offset'], 16), int(row['size'])
        if seg not in SEGS:
            continue
        total += size
        if (seg, off) in names.C_VERSIONS:
            done += size
        elif (seg, off) in native:
            host += size
        elif (seg, off) in dead:
            unreachable += size
        else:
            left.append((size, seg, off, row['name'], row['callers'], row['found_by']))
rest = total - done - host - unreachable
print(f'C {done} ({100 * done / total:.1f}%), left to the host {host} ({100 * host / total:.1f}%), '
      f'unreachable {unreachable}, left {rest} ({100 * rest / total:.1f}%) of {total} bytes; '
      f'{len(names.C_VERSIONS)} C versions, {len(native)} native, {len(dead)} unreachable, {len(left)} routines left')
left.sort(reverse=True)
count = int(sys.argv[1]) if len(sys.argv) > 1 else 40
for size, seg, off, name, callers, found in left[:count]:
    print(f'  {seg:04X}:{off:04X} {size:5d} {name} callers {callers} {found}')
