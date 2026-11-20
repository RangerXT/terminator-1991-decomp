"""Record real calls of a game routine, to replay as test vectors.

The game is run from a snapshot; every time execution reaches the routine's entry the whole
machine state is saved. A test later restores each state, lets the original routine run to
its return, and compares the result with the C rewrite given the same starting memory.

  python tools/capture.py <seg:off> <name> [--count 12] [--skip 7] [--from ingame] [--ticks 400]
                          [--keys "t:key[:hold],..."]

writes tests/captures/<name>.pkl.gz  (a list of machine states taken at the routine entry)

In a test:
    from capture import replay
    for before, after, regs_in, regs_out in replay('transform', 0x0000, 0x29C4): ...
`before`/`after` are Machine objects positioned at entry and at return.
"""
import gzip
import os
import pickle
import sys

from unicorn import UC_HOOK_CODE

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import dosemu  # noqa: E402

CAPDIR = os.path.join(ROOT, 'tests', 'captures')
STATES = os.path.join(ROOT, 'out', 'emu', 'states')


def state_of(m):
    """Machine state as a plain dict (same content as Machine.save)."""
    import io
    tmp = os.path.join(CAPDIR, '_tmp_state.pkl')
    m.save(tmp)
    st = pickle.load(open(tmp, 'rb'))
    os.remove(tmp)
    return st


def restore(st):
    m = dosemu.Machine()
    tmp = os.path.join(CAPDIR, f'_tmp_restore_{os.getpid()}.pkl')
    with open(tmp, 'wb') as f:
        pickle.dump(st, f)
    m.load(tmp)
    os.remove(tmp)
    return m


def record(seg, off, name, count=12, skip=7, start='ingame', ticks=400, keys=''):
    os.makedirs(CAPDIR, exist_ok=True)
    m = dosemu.Machine()
    m.load(os.path.join(STATES, start + '.pkl'))
    base = m.ticks
    for item in filter(None, keys.split(',')):
        parts = item.split(':')
        m.press(base + int(parts[0]), parts[1], hold=int(parts[2]) if len(parts) > 2 else 6)
    addr = ((seg + dosemu.LOAD_SEG) << 4) + off
    hits = {'n': 0, 'resume_entry': False, 'frames': 0}
    caps = []

    def on_code(uc, address, size, ud):
        # emu_stop leaves IP at the unexecuted entry instruction. Let that
        # instruction execute once on resume rather than recording it again.
        if hits['resume_entry']:
            hits['resume_entry'] = False
            return
        hits['n'] += 1
        if hits['n'] % (skip + 1) == 1 or skip == 0:
            m._capture_now = True
            uc.emu_stop()

    m.uc.hook_add(UC_HOOK_CODE, on_code, None, addr, addr)
    # Count actual frame-list entries as an independent recording-progress marker.
    # If this is also the capture entry, do not count its stopped, unexecuted visit.
    def on_frame(uc, address, size, ud):
        if not m._capture_now:
            hits['frames'] += 1
    frame_addr = (dosemu.LOAD_SEG << 4) + 0x036E
    m.uc.hook_add(UC_HOOK_CODE, on_frame, None, frame_addr, frame_addr)
    end = m.ticks + ticks
    while m.ticks < end and len(caps) < count:
        m._capture_now = False
        m.run(ticks=1, until=lambda mm: mm._capture_now)
        if m._capture_now:
            # the hook fired before the first instruction of the routine executed
            m.cs, m.ip = m.r(dosemu.UC_X86_REG_CS), m.r(dosemu.UC_X86_REG_IP)
            if ((m.cs << 4) + m.ip) == addr:
                st = state_of(m)
                st['trace_frame'] = hits['frames']
                caps.append(st)
                hits['resume_entry'] = True
            m._capture_now = False
    path = os.path.join(CAPDIR, name + '.pkl.gz')
    with gzip.open(path, 'wb', compresslevel=6) as f:
        pickle.dump(caps, f)
    print(f'{name}: {len(caps)} captures of {seg:04X}:{off:04X} ({hits["n"]} calls seen) -> {path} '
          f'({os.path.getsize(path) // 1024} KB)')
    return len(caps)


REG_NAMES = ['ax', 'bx', 'cx', 'dx', 'si', 'di', 'bp', 'sp', 'ds', 'es', 'ss', 'flags']


def run_to_return(m, far=False, max_instr=50_000_000):
    """Run machine `m`, which stands at the entry of a routine with its return address on the
    stack, until that routine returns (interrupts off). Returns the registers afterwards."""
    ss, sp = m.r(dosemu.UC_X86_REG_SS), m.r(dosemu.UC_X86_REG_SP)
    ret_ip = m.rw(ss, sp)
    ret_cs = m.rw(ss, sp + 2) if far else m.cs
    until = ((ret_cs << 4) + ret_ip) & 0xFFFFF
    want_sp = (sp + (4 if far else 2)) & 0xFFFF
    uc = m.uc
    uc.reg_write(dosemu.UC_X86_REG_EFLAGS, uc.reg_read(dosemu.UC_X86_REG_EFLAGS) & ~dosemu.IF_ & 0xFFFF)
    budget = max_instr
    m.pending = None
    while True:
        step = min(budget, 1_000_000)
        m.step(until, step)
        budget -= step
        if m.pending is not None:
            m._apply_pending()
            if m.blocked:
                raise RuntimeError(m.blocked)
            continue
        if ((m.cs << 4) + m.ip) & 0xFFFFF == until and m.r(dosemu.UC_X86_REG_SP) == want_sp:
            break
        if budget <= 0:
            raise RuntimeError('routine did not return')
    return {n: m.r(m.REG_BY_NAME[n]) for n in REG_NAMES}


def replay(name, far=False, max_instr=50_000_000):
    """Yield (before, after, regs_in, regs_out): Machines at routine entry and at its return."""
    path = os.path.join(CAPDIR, name + '.pkl.gz')
    caps = pickle.load(gzip.open(path, 'rb'))
    for st in caps:
        before = restore(st)
        after = restore(st)
        regs_in = {n: before.r(before.REG_BY_NAME[n]) for n in REG_NAMES}
        regs_out = run_to_return(after, far, max_instr)
        yield before, after, regs_in, regs_out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('addr')
    ap.add_argument('name')
    ap.add_argument('--count', type=int, default=12)
    ap.add_argument('--skip', type=int, default=7)
    ap.add_argument('--from', dest='start', default='ingame')
    ap.add_argument('--ticks', type=int, default=400)
    ap.add_argument('--keys', default='')
    a = ap.parse_args()
    seg, off = (int(x, 16) for x in a.addr.split(':'))
    record(seg, off, a.name, a.count, a.skip, a.start, a.ticks, a.keys)


if __name__ == '__main__':
    main()
