"""Trace palette changes when a held map-exit key reaches the pause menu."""
import argparse
import os
import dosemu


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--hold', type=int, default=4)
    args = ap.parse_args()
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out/emu/states/local_map.pkl'))
    original_video = m._video
    original_out = m.vga.port_out
    def details():
        ss, sp = m.r(dosemu.UC_X86_REG_SS), m.r(dosemu.UC_X86_REG_SP)
        return f'tick={m.ticks} pc={m.r(dosemu.UC_X86_REG_CS)-dosemu.LOAD_SEG:04X}:{m.r(dosemu.UC_X86_REG_IP):04X} ds={m.r(dosemu.UC_X86_REG_DS):04X} si={m.r(dosemu.UC_X86_REG_SI):04X} stack={m.rb(ss, sp, 24).hex()}'
    def video():
        ax = m.ax()
        es, dx = m.r(dosemu.UC_X86_REG_ES), m.r(dosemu.UC_X86_REG_DX)
        before = list(m.vga.attr[:16])
        payload = m.rb(es, dx, 17).hex() if ax == 0x1002 else ''
        original_video()
        after = m.vga.attr[:16]
        if before != after or ax == 0x1002:
            print('BIOS', hex(ax), details(), 'table', f'{es:04X}:{dx:04X}', payload, 'palette', after, flush=True)
    def out(port, value):
        before = list(m.vga.attr[:16])
        original_out(port, value)
        if m.vga.attr[:16] != before:
            print('PORT', hex(port), hex(value), details(), 'palette', m.vga.attr[:16], flush=True)
    m._video = video
    m.vga.port_out = out
    print('tables before', m.ds_read(0x1510, 33).hex())
    m.press(m.ticks + 2, 'esc', hold=args.hold)
    print(m.run(ticks=20))
    print('final', m.file_addr(), m.vga.attr[:16], 'unknown', m.unknown, 'tables', m.ds_read(0x1510, 33).hex())


if __name__ == '__main__':
    main()