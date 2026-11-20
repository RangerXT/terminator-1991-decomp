"""Record real external-call effects while executing a captured fast-travel request.

No service stubs: simulation, loading and encounters run in the original machine.
The resulting trace lets tests check the C controller at every service boundary.
"""
import gzip
import os
import pickle
import sys
from unicorn import UC_HOOK_CODE
import capture
import dosemu

ENTRIES = [(0, off, False) for off in [0xB588, 0x3B88, 0xC42F, 0xBBF1, 0xC35F, 0xDC7B, 0x057C]]
ENTRIES += [(0x11BC, 0x1FCC, True)]


def memory(m):
    return bytes(m.uc.mem_read(0, 0xA0000))


def record(index=0, capture_name='travel', output_name='travel_realtrace', entries=None, arguments=None, stop=None, inline=(), changes=None, result_registers=None):
    st = pickle.load(gzip.open(os.path.join(capture.CAPDIR, capture_name + '.pkl.gz'), 'rb'))[index]
    m = capture.restore(st)
    if changes:
        for off, data in changes.items():
            m.ds_write(off, data)
        st = capture.state_of(m)
    stack = m.r(dosemu.UC_X86_REG_SS) << 4
    result = dict(state=st, calls=[], stack=stack)
    pending = []
    hooked = set()

    def returned(uc, addr, size, ud):
        if not pending:
            return
        entry = pending[-1]
        if addr != entry['return'] or m.r(dosemu.UC_X86_REG_SP) != entry['sp']:
            return
        entry['after'] = memory(m)
        entry['screen_after'] = m.vga.card_state(), [bytes(p) for p in m.vga.planes]
        result_reg = (result_registers or {}).get(entry['service'])
        value = m.r(m.REG_BY_NAME[result_reg]) if result_reg else (m.r(dosemu.UC_X86_REG_CX) if entry['service'] == 0xB588 else 0)
        entry['result'] = value | (0x10000 if m.r(dosemu.UC_X86_REG_EFLAGS) & 1 else 0)
        pending.pop()
        print('returned', hex(entry['service']), 'result', hex(entry['result']), flush=True)

    def entered(uc, addr, size, spec):
        if pending:
            return
        seg, off, far = spec
        ss, sp = m.r(dosemu.UC_X86_REG_SS), m.r(dosemu.UC_X86_REG_SP)
        ret_off = m.rw(ss, sp)
        ret_seg = m.rw(ss, sp + 2) if far else m.r(dosemu.UC_X86_REG_CS)
        ret = (ret_seg << 4) + ret_off
        arg = m.r(dosemu.UC_X86_REG_CX) if off == 0xB588 else (m.r(dosemu.UC_X86_REG_BX) if off == 0x1FCC else 0)
        arg2 = 0
        if arguments and off in arguments:
            names = arguments[off]
            arg = m.r(m.REG_BY_NAME[names[0]]) if names else 0
            arg2 = m.r(m.REG_BY_NAME[names[1]]) if len(names) > 1 else 0
        entry = dict(service=off, argument=arg, argument2=arg2, before=memory(m),
                     screen_before=(m.vga.card_state(), [bytes(p) for p in m.vga.planes]),
                     sp=(sp + (4 if far else 2)) & 65535, **{'return': ret})
        pending.append(entry)
        result['calls'].append(entry)
        if ret not in hooked:
            m.uc.hook_add(UC_HOOK_CODE, returned, None, ret, ret)
            hooked.add(ret)
        print('entered', hex(off), 'argument', arg, flush=True)

    def entered_inline(uc, addr, size, spec):
        if pending:
            return
        off, next_off, service, names = spec
        ret = (dosemu.LOAD_SEG << 4) + next_off
        arg = m.r(m.REG_BY_NAME[names[0]]) if names else 0
        arg2 = m.r(m.REG_BY_NAME[names[1]]) if len(names) > 1 else 0
        entry = dict(service=service, argument=arg, argument2=arg2, before=memory(m),
                     screen_before=(m.vga.card_state(), [bytes(p) for p in m.vga.planes]),
                     sp=m.r(dosemu.UC_X86_REG_SP), **{'return': ret})
        pending.append(entry)
        result['calls'].append(entry)
        if ret not in hooked:
            m.uc.hook_add(UC_HOOK_CODE, returned, None, ret, ret)
            hooked.add(ret)
        print('entered inline', hex(service), 'argument', arg, flush=True)

    for spec in inline:
        addr = (dosemu.LOAD_SEG << 4) + spec[0]
        m.uc.hook_add(UC_HOOK_CODE, entered_inline, spec, addr, addr)

    for seg, off, far in (entries or ENTRIES):
        addr = ((seg + dosemu.LOAD_SEG) << 4) + off
        m.uc.hook_add(UC_HOOK_CODE, entered, (seg, off, far), addr, addr)
    if stop is None:
        capture.run_to_return(m, max_instr=500_000_000)
    else:
        target = (dosemu.LOAD_SEG << 4) + stop
        m.uc.reg_write(dosemu.UC_X86_REG_EFLAGS, m.r(dosemu.UC_X86_REG_EFLAGS) & ~dosemu.IF_)
        for _ in range(500):
            m.step(target, 1_000_000)
            if m.pending is not None:
                m._apply_pending()
            if (m.cs << 4) + m.ip == target:
                break
        else:
            raise RuntimeError('Did not reach requested stop')
    if pending:
        raise RuntimeError('Unfinished external call')
    result['after'] = memory(m)
    result['display_after'] = {k: v for k, v in m.vga.__dict__.items() if k not in ('planes', 'clock')}
    result['screen_after'] = m.vga.card_state(), [bytes(p) for p in m.vga.planes]
    path = os.path.join(capture.CAPDIR, output_name + '.pkl.gz')
    with gzip.open(path, 'wb') as f:
        pickle.dump(result, f)
    print(len(result['calls']), 'actual external calls ->', path)


if __name__ == '__main__':
    record(int(sys.argv[1]) if len(sys.argv) > 1 else 0)