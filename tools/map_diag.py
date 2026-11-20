"""Inspect map exit without relying on the visible page alone."""
import os
import argparse
import dosemu


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--hold', type=int, default=1, help='Escape hold in virtual ticks; 4 also reaches menu flow')
    ap.add_argument('--from', dest='start', default='local_map', choices=['local_map', 'area_map'])
    ap.add_argument('--ticks', type=int, default=30)
    args = ap.parse_args()
    m = dosemu.Machine()
    m.load(os.path.join(dosemu.ROOT, 'out', 'emu', 'states', args.start + '.pkl'))
    m.press(m.ticks + 2, 'esc', hold=args.hold)
    for tick in range(0, args.ticks, 10):
        m.run(ticks=min(10, args.ticks - tick))
        v = m.vga
        nz = [sum(b != 0 for p in v.planes for b in p[a:a + 8000])
              for a in (0, 0x2000, 0x4000, 0x6000)]
        print('tick', m.ticks, 'pc', m.file_addr(), 'instr', m.instr,
              'dx', hex(m.r(dosemu.UC_X86_REG_DX)), 'bda_port', hex(m.rw(0x40, 0x63)),
              'start', hex((v.crtc[12] << 8) | v.crtc[13]), 'nonzero/page', nz,
              'pages', m.ds_read(0x122A, 4).hex(), 'offset', m.ds_read(0x1234, 4).hex(),
              'attr', v.attr[:16], 'dac_nonzero', sum(bool(x) for x in v.dac), flush=True)
    m.save(os.path.join(dosemu.ROOT, 'out', 'emu', 'states', 'map_exit_diag.pkl'))


if __name__ == '__main__':
    main()
