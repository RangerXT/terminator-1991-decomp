"""Produce whole frames of the 3D view with the C rewrite and compare them with the original.

The real game is run in the emulator, with interrupts. In each frame to be checked four
moments are recorded (memory, screen planes, card registers):

    A  0000:06DE   about to draw the background (ground colour, horizon, sun)
    L  0000:01E8   about to gather this frame's object records into one list
    B  0000:06FF   about to draw the scene
    C  0000:0752   the scene has been drawn (before the HUD and the page flip)

The C code then produces the same frame on a screen of its own, each step checked against
the original, and nothing is copied from the original's screen or memory after A and L:

    1. draw_background on the memory of A               -> the screen must equal L's
       (the game logic between A and L reads the screen, so the card's latches and selected
       register index - not its other registers, and no pixels - are taken from L here)
    2. on the memory of L:
         build_frame_draw_list                          -> the list must equal B's
         map_page_update (redraws the overhead-map page in frames where the lists were
         rebuilt, otherwise does nothing)               -> the screen must equal B's
         the ground list and the object list with draw_object_list
                                                        -> screen and card registers must equal C's

Still done by the original: moving things (game logic between A and L) and, when the
player enters a new cell or turns far enough, rebuilding the visible-object and ground
lists (those rebuilds are in C too and tested on their own, see tests/). Between the two
lists the original also runs two routines that draw nothing; the C path skips them.

  python tools/frame_demo.py [out.png] [--from ingame] [--frames-ahead N] [--keys "t:key[:hold],..."]
        one frame; writes a side-by-side PNG: original | C | differences (in red)

  python tools/frame_demo.py --sequence N [--from ingame] [--keys ...] [--quiet]
        the next N frames; prints one line per frame (only the unusual ones with --quiet)
        and a total; exit status 1 if any frame differs
"""
import ctypes
import os
import sys

from unicorn import UC_HOOK_CODE

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import difftest  # noqa: E402
import dosemu  # noqa: E402

BACKGROUND = 0x06DE
LISTS = 0x01E8
SCENE = 0x06FF
SCENE_DONE = 0x0752
FRAME_START = 0x01DC
PLANE_BYTES = 4 * 0x10000


class Game(ctypes.Structure):
    _fields_ = [('mem', ctypes.c_void_p), ('ds', ctypes.c_void_p), ('planes', ctypes.c_void_p),
                ('ds_seg', ctypes.c_uint16)]


def planes_of(m):
    """The four bit planes followed by the card's registers and latches (see EgaRegs in
    src/term.h): the C code needs both."""
    return b''.join(bytes(p) for p in m.vga.planes) + m.vga.card_state()


def record_frames(start='ingame', first=1, count=1, keys=(), max_ticks=3000, on_complete=None):
    """Run the game; returns (machine, {frame number: {'A': (mem, screen), 'L': .., 'B': .., 'C': ..}})
    for frames first .. first+count-1 (frame 0 is the one in progress at the snapshot).
    With on_complete(machine, frame, shots), each frame is handed over as soon as it is
    complete and not kept, so long runs do not fill memory."""
    m = dosemu.Machine()
    m.load(os.path.join(ROOT, 'out', 'emu', 'states', start + '.pkl'))
    for t, k, hold in keys:
        m.press(m.ticks + t, k, hold=hold)
    base = dosemu.LOAD_SEG << 4
    st = {'frame': -1, 'stop': False}
    frames = {}
    last = first + count - 1

    def on_frame(uc, address, size, ud):
        st['frame'] += 1
        if st['frame'] > last:
            st['stop'] = True
            uc.emu_stop()

    def shot(name):
        def hook(uc, address, size, ud):
            f = st['frame']
            if first <= f <= last and name not in frames.setdefault(f, {}):
                frames[f][name] = (bytes(uc.mem_read(0, 0xA0000)), planes_of(m))
                if name == 'C' and on_complete is not None:
                    on_complete(m, f, frames.pop(f))
        return hook

    m.uc.hook_add(UC_HOOK_CODE, on_frame, None, base + FRAME_START, base + FRAME_START)
    for name, addr in (('A', BACKGROUND), ('L', LISTS), ('B', SCENE), ('C', SCENE_DONE)):
        m.uc.hook_add(UC_HOOK_CODE, shot(name), None, base + addr, base + addr)
    m.run(ticks=max_ticks, until=lambda mm: st['stop'])
    return m, frames


def image_of(planes, page, view):
    """RGB bytes of the view window from four bit planes."""
    left, top, right, bottom = view
    w, h = right - left + 1, bottom - top + 1
    out = bytearray(w * h * 3)
    o = 0
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            a = (page + y * 40 + (x >> 3)) & 0xFFFF
            bit = 0x80 >> (x & 7)
            c = sum((1 << p) for p in range(4) if planes[(p << 16) + a] & bit)
            out[o:o + 3] = bytes(dosemu.ega_rgb(dosemu.DEFAULT_ATTR[c]))
            o += 3
    return w, h, bytes(out)


def word(mem, ds, off):
    return int.from_bytes(mem[ds + off:ds + off + 2], 'little')


def differing(a, b, n=PLANE_BYTES):
    return 0 if a[:n] == b[:n] else sum(1 for i in range(n) if a[i] != b[i])


def c_frame(lib, m, shots):
    """Produce the frame in C. Returns (screen bytes, stats)."""
    ds = m.DATA_SEG << 4
    a, l, b, c = (shots[k] for k in 'ALBC')
    screen = ctypes.create_string_buffer(a[1], len(a[1]))

    def game_on(mem_bytes):
        mem = ctypes.create_string_buffer(mem_bytes, 0x100000 + 16)
        g = Game(ctypes.addressof(mem), ctypes.addressof(mem) + ds, ctypes.addressof(screen), m.DATA_SEG)
        return g, mem

    # 1. background
    g, mem = game_on(a[0])
    lib.draw_background(ctypes.byref(g))
    background_diff = differing(screen.raw, l[1])
    # The game logic between A and L reads the screen, which loads the card's latches and
    # leaves another register selected. So only the plane mask and the nine graphics
    # controller registers are compared here, and the latches and selected index for the
    # next step are taken from the original at L.
    background_regs_differ = screen.raw[PLANE_BYTES:PLANE_BYTES + 10] != l[1][PLANE_BYTES:PLANE_BYTES + 10]
    ctypes.memmove(ctypes.addressof(screen) + PLANE_BYTES + 10, l[1][PLANE_BYTES + 10:], len(l[1]) - PLANE_BYTES - 10)

    # 2. the frame's object list
    g, mem = game_on(l[0])
    statuses = [lib.build_frame_draw_list(ctypes.byref(g))]
    mine = mem.raw
    count_c, count_o = word(mine, ds, 0x50AC), word(b[0], ds, 0x50AC)
    at_c, at_o = word(mine, ds, 0x01FE), word(b[0], ds, 0x01FE)
    list_same = (count_c == count_o and at_c == at_o and word(mine, ds, 0x020E) == word(b[0], ds, 0x020E)
                 and mine[ds + at_c:ds + at_c + 12 * count_c] == b[0][ds + at_o:ds + at_o + 12 * count_o])

    # the overhead-map page (only does something when the lists were rebuilt this frame)
    map_redrawn = bool(l[0][ds + 0x5CD8])
    statuses.append(lib.map_page_update(ctypes.byref(g)))
    map_diff = differing(screen.raw, b[1])
    map_regs_differ = screen.raw[PLANE_BYTES:] != b[1][PLANE_BYTES:]

    # 3. the scene, on the same memory
    ground = word(mem.raw, ds, 0x91D8)
    if ground:
        mem[ds + 0x00BB] = 1
        statuses.append(lib.draw_object_list(ctypes.byref(g), ctypes.c_uint16(0x2836), ctypes.c_uint16(ground)))
    mem[ds + 0x00BB] = 0
    if count_c:
        statuses.append(lib.draw_object_list(ctypes.byref(g), ctypes.c_uint16(at_c), ctypes.c_uint16(count_c)))

    player = word(b[0], ds, 0x03A0)
    stats = {'ground_records': ground, 'object_records': count_o, 'statuses': statuses,
             'gathered': word(b[0], ds, 0x020E),
             'page': word(b[0], ds, 0x1234), 'heading': word(b[0], ds, player + 6),
             'cell': (word(b[0], ds, player + 0x1E), word(b[0], ds, player + 0x20)),
             'view': tuple(int.from_bytes(b[0][ds + o:ds + o + 2], 'little', signed=True)
                           for o in (0x3F4, 0x3F6, 0x3F8, 0x3FA)),
             'background_diff': background_diff, 'background_regs_differ': background_regs_differ,
             'list_same': list_same, 'map_redrawn': map_redrawn, 'map_diff': map_diff,
             'map_regs_differ': map_regs_differ,
             'differing_plane_bytes': differing(screen.raw, c[1]),
             'registers_differ': c[1][PLANE_BYTES:] != screen.raw[PLANE_BYTES:]}
    stats['identical'] = (background_diff == 0 and not background_regs_differ and list_same
                          and map_diff == 0 and not map_regs_differ
                          and stats['differing_plane_bytes'] == 0
                          and not stats['registers_differ'] and all(x == 0 for x in statuses))
    return screen.raw, stats


def complete(shots):
    return all(k in shots for k in 'ALBC')


def prepare(lib):
    lib.draw_object_list.restype = ctypes.c_int
    lib.build_frame_draw_list.restype = ctypes.c_int
    lib.map_page_update.restype = ctypes.c_int
    return lib


def compare(start='ingame', frames_ahead=1, keys=()):
    """One frame. Returns (stats dict, (w, h, original_rgb, c_rgb))."""
    m, frames = record_frames(start, frames_ahead, 1, keys)
    shots = frames.get(frames_ahead, {})
    if not complete(shots):
        raise SystemExit('that frame did not pass through all four points: not a normal 3D frame')
    screen, stats = c_frame(prepare(difftest.Ctx().lib), m, shots)
    w, h, a = image_of(shots['C'][1], stats['page'], stats['view'])
    _, _, b = image_of(screen, stats['page'], stats['view'])
    stats['pixels'] = w * h
    stats['differing_pixels'] = sum(1 for i in range(0, w * h * 3, 3) if a[i:i + 3] != b[i:i + 3])
    return stats, (w, h, a, b)


def sequence(start='ingame', count=20, keys=(), lib=None):
    """The next `count` frames. Returns a list of (frame, stats or None)."""
    lib = prepare(lib or difftest.Ctx().lib)
    done = {}

    def on_complete(m, f, shots):
        done[f] = c_frame(lib, m, shots)[1] if complete(shots) else None

    record_frames(start, 1, count, keys, max_ticks=400000, on_complete=on_complete)
    return [(f, done.get(f)) for f in range(1, count + 1)]


def describe(s):
    """One-line verdict for a frame's stats."""
    if s['identical']:
        text = 'identical'
    else:
        parts = []
        if s['background_diff'] or s['background_regs_differ']:
            parts.append(f'background: {s["background_diff"]} plane bytes'
                         + (', card registers' if s['background_regs_differ'] else ''))
        if not s['list_same']:
            parts.append('object list differs')
        if s['map_diff'] or s['map_regs_differ']:
            parts.append(f'map page: {s["map_diff"]} plane bytes' + (', card registers' if s['map_regs_differ'] else ''))
        if s['differing_plane_bytes']:
            parts.append(f'scene: {s["differing_plane_bytes"]} plane bytes')
        if s['registers_differ']:
            parts.append('card registers differ at the end')
        if any(s['statuses']):
            parts.append(f'statuses {s["statuses"]}')
        text = 'DIFFERENT: ' + ', '.join(parts)
    if s['map_redrawn']:
        text += ' (lists rebuilt this frame: overhead-map page redrawn too)'
    return text


def main():
    argv = sys.argv[1:]
    quiet = '--quiet' in argv
    argv = [a for a in argv if a != '--quiet']
    opts = {'--frames-ahead': '1', '--from': 'ingame', '--keys': '', '--sequence': ''}
    args = []
    i = 0
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    keys = []
    for item in filter(None, opts['--keys'].split(',')):
        parts = item.split(':')
        keys.append((int(parts[0]), parts[1], int(parts[2]) if len(parts) > 2 else 6))

    if opts['--sequence']:
        results = sequence(opts['--from'], int(opts['--sequence']), keys)
        bad = skipped = other = 0
        cells = set()
        for f, s in results:
            if s is None:
                skipped += 1
                print(f'frame {f:3}: not a normal 3D frame, skipped')
                continue
            bad += not s['identical']
            other += s['map_redrawn']
            cells.add(s['cell'])
            if not quiet or not s['identical']:
                print(f'frame {f:3}: cell {s["cell"]} heading {s["heading"]:3}  gathered {s["gathered"]:3} -> '
                      f'{s["object_records"]:3} objects, {s["ground_records"]:3} ground   {describe(s)}')
        print(f'{len(results) - skipped - bad} of {len(results) - skipped} frames identical to the original'
              + (f' ({skipped} skipped)' if skipped else '')
              + f'; {len(cells)} map cells visited'
              + (f'; the overhead-map page was redrawn in {other} of them' if other else ''))
        return 1 if bad else 0

    from PIL import Image
    out = args[0] if args else os.path.join(ROOT, 'out', 'emu', 'frame_c_vs_original.png')
    stats, (w, h, a, b) = compare(opts['--from'], int(opts['--frames-ahead']), keys)
    diff = bytearray(w * h * 3)
    for i in range(0, w * h * 3, 3):
        diff[i:i + 3] = b'\xff\x00\x00' if a[i:i + 3] != b[i:i + 3] else bytes(v // 3 for v in a[i:i + 3])
    scale = 2
    sheet = Image.new('RGB', (3 * w * scale + 16, h * scale), (40, 0, 40))
    for k, data in enumerate((a, b, bytes(diff))):
        im = Image.frombytes('RGB', (w, h), data).resize((w * scale, h * scale), Image.NEAREST)
        sheet.paste(im, (k * (w * scale + 8), 0))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    print(f'C drew the background, built the object list ({stats["gathered"]} gathered, {stats["object_records"]} kept), '
          f'and drew {stats["ground_records"]} ground records and the objects (statuses {stats["statuses"]})')
    print(f'view window {stats["view"]}: {stats["differing_pixels"]} of {stats["pixels"]} pixels differ; whole frame: '
          + describe(stats))
    print('wrote', out)
    return 0 if stats['identical'] else 1


if __name__ == '__main__':
    sys.exit(main())
