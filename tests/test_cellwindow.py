"""3B88 from real entries. On misses both implementations read real sector and object files."""
import ctypes
import gzip
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capture
import dosemu
from test_drawlist import make_game
from test_blast import set_clock
from test_imageload import Files, check_memory, compare, regions, trace_dos

CASES = 0


def run(ctx):
    global CASES
    errors, counts, loaded_names = [], {}, set()
    with gzip.open(os.path.join(capture.CAPDIR, 'cell_window_live.pkl.gz'), 'rb') as f:
        states = pickle.load(f)
    jobs = [(s, kind, None) for s in states for kind in ('live', 'unchanged', 'heading', 'neighbor')]
    jobs += [(states[i % len(states)], 'reload', (x, z)) for i, (x, z) in enumerate(
        ((20, 20), (84, 20), (148, 20), (20, 84), (84, 84), (148, 84), (64, 64), (128, 64), (191, 127), (4, 4), (64, 20), (20, 64), (132, 63), (63, 68)))]
    for i, (st, kind, xy) in enumerate(jobs):
        m = capture.restore(st)
        actor = m.rw(m.DATA_SEG, 0x03A0)
        def rw(off):
            return m.rw(m.DATA_SEG, off)
        def ww(off, val):
            m.ww(m.DATA_SEG, off, val & 65535)
        if kind != 'live':
            col, row = rw(actor+30)-rw(0x7272), rw(actor+32)-rw(0x7274)
            ww(0x7242, row*48 + col*2)
            ww(0x04C4, 2*(((rw(actor+6)+rw(actor+8)+32)&511)//64))
            if kind == 'heading':
                ww(actor+8, (rw(actor+8)+64)&511)
            if kind == 'neighbor':
                ww(actor+30, rw(actor+30)+1)
            if kind == 'reload':
                ww(actor+30, xy[0])
                ww(actor+32, xy[1])
                m.ds_write(actor+14, bytes([1 if i%2 else 2]))
                ww(0x7242, 0xFFFF if i%2 else 0xFFFE)
            ww(0x8685, 0xA58F)
            m.ds_write(0x5CD8, bytes(1))
        spans = regions(m)
        g, mem, planes = make_game(m)
        files = Files(m)
        trace_dos(m)
        try:
            capture.run_to_return(m, max_instr=200_000_000)
        except RuntimeError as error:
            return [f'{kind} {i}, cell {xy}, original at {m.file_addr()}: {error}']
        set_clock(ctx.lib, m)
        status = ctx.lib.update_visible_cells(ctypes.byref(g), ctypes.byref(files.host))
        CASES += 1
        names = []
        if status or len(files.calls) != len(m.image_calls) or files.handles or files.next_handle != m.next_handle:
            return [f'{kind} {i} {xy}: status {status}, DOS calls {len(files.calls)}/{len(m.image_calls)}, handles {files.next_handle}/{m.next_handle}']
        for (args, ram, screen), (orig_args, orig_ram, orig_screen) in zip(files.calls, m.image_calls):
            if args != orig_args:
                return [f'{kind} {i} {xy}: DOS args {args}/{orig_args}']
            if args[0] == 0x3D:
                at = args[2]*16+args[3]
                names.append(orig_ram[at:at+64].split(bytes(1))[0].decode('ascii').lower())
            error = check_memory(ram, orig_ram, spans)
            if error or screen != orig_screen:
                return [f'{kind} {i} {xy} before DOS {args} {names[-1:]}: {error or "EGA mismatch"}']
        compare(f'{kind} {i} {xy}', mem, planes, m, spans, errors)
        if errors:
            return errors
        if kind == 'reload' and not {'drop.spn', 'tracer.spn', 'grenade.spn', 'missile.spn', 'la.def', 'la.bmp'} <= set(names):
            return [f'{kind} {i}: missing sector mesh reload: {names}']
        if kind in ('heading', 'neighbor') and not m.ds_read(0x5CD8, 1)[0]:
            return [f'{kind} did not rebuild']
        if kind == 'unchanged' and m.ds_read(0x5CD8, 1)[0]:
            return ['unexpected rebuild']
        counts[kind] = counts.get(kind, 0)+1
        loaded_names.update(names)
    print('    city window:', counts, 'files:', ', '.join(sorted(loaded_names)))
    return errors
