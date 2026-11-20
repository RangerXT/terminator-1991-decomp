"""Unaligned executable-page RMW writes must execute once under the SMC guard."""
import dosemu
CASES = 0

def run(ctx):
    global CASES
    cases = [('inc', 'ff060103', 4, 0, 5), ('inc wrap', 'ff060103', 65535, 0, 0),
           ('two inc', 'ff060103ff060103', 4, 0, 6),
           ('adc carry', '8316010300', 0, 1, 1), ('adc clear', '8316010300', 4, 0, 4),
           ('mov', 'c70601030700', 4, 0, 7)]
    for name, code, old, carry, want in cases:
        m = dosemu.Machine()
        m.wb(dosemu.LOAD_SEG, 0x0100, bytes.fromhex(code)+bytes([0x90, 0xC3]))
        m.ww(dosemu.LOAD_SEG, 0x0301, old)
        m.w(dosemu.UC_X86_REG_EFLAGS, 2|carry)
        m.call(0, 0x0100, ds=dosemu.LOAD_SEG, max_instr=20_000_000)
        CASES += 1
        got = m.rw(dosemu.LOAD_SEG, 0x0301)
        if got != want:
            return ['SMC %s: %d != %d'%(name, got, want)]
        if not m.smc_stops:
            return ['SMC fixture did not exercise guard']
    return []
