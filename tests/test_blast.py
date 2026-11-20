"""Explosions (src/blast.c) against the original: random_word (0000:80EE), debris_start
(0000:7B28), debris_update (0000:7D2B), explosion_damage (0000:7EF0), blast_queue_step
(0000:80B6), and the drawing of debris records, which also exercises debris_fetch and
debris_rotate in src/drawlist.c.

No recordings: nothing blows up in the snapshots, so every case is set up from the in-game
snapshot by calling the routines directly on objects of the current frame list.

Four routines the blast code calls belong to parts of the game that are not translated
(sound, damage to the player, killing a figure, bookkeeping for a blown-up object). In the
emulator they are replaced by an immediate return and their calls are logged; the C code
reports the same calls as events. The two logs must be equal, as must all conventional
memory except the stack and, where something is drawn, the screen and card registers.
"""
import ctypes
import os
import struct
import sys

from unicorn import UC_HOOK_CODE

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dosemu  # noqa: E402
from test_drawlist import compare, make_game  # noqa: E402

CASES = 0
SEEN = {}        # calls into untranslated code, by kind
SNAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'out', 'emu', 'states', 'ingame.pkl')

EV_SOUND, EV_PLAYER_HIT, EV_FIGURE_KILLED, EV_OBJECT_BLOWN = 1, 2, 3, 4
STUBS = [   # kind, file segment, offset, return opcode, register holding the argument
    (EV_SOUND, 0x0000, 0x89A2, 0xC3, dosemu.UC_X86_REG_AX),
    (EV_PLAYER_HIT, 0x0000, 0x6386, 0xC3, dosemu.UC_X86_REG_AX),
    (EV_FIGURE_KILLED, 0x0000, 0xAFD0, 0xC3, dosemu.UC_X86_REG_BX),
    (EV_OBJECT_BLOWN, 0x151B, 0x02DE, 0xCB, dosemu.UC_X86_REG_SI),
]


class GameEvent(ctypes.Structure):
    _fields_ = [('kind', ctypes.c_uint16), ('a', ctypes.c_uint16), ('b', ctypes.c_uint16)]


def stub(m):
    """Replace the untranslated routines in machine `m` by immediate returns and log their
    calls in m.calls as (kind, argument). Returns m."""
    m.calls = []
    for kind, seg, off, opcode, reg in STUBS:
        m.wb((seg + dosemu.LOAD_SEG) & 0xFFFF, off, bytes([opcode]))
        addr = ((seg + dosemu.LOAD_SEG) << 4) + off

        def hook(uc, address, size, ud, kind=kind, reg=reg):
            value = uc.reg_read(reg)
            m.calls.append((kind, value & 0xFF if kind == EV_SOUND else value & 0xFFFF))
        m.uc.hook_add(UC_HOOK_CODE, hook, None, addr, addr)
    return m


def fresh():
    """A machine at the in-game snapshot with the untranslated routines stubbed and logged."""
    m = dosemu.Machine()
    m.load(SNAP)
    return stub(m)


def set_clock(lib, m):
    t = m.ticks * 10000 // 182
    lib.game_set_clock(ctypes.c_uint16(((t // 360000) % 24) << 8 | (t // 6000) % 60),
                       ctypes.c_uint16(((t // 100) % 60) << 8 | t % 100))


def c_events(lib):
    buf = (GameEvent * 512)()
    n = lib.game_events(buf, 512)
    return [(buf[i].kind, buf[i].a) for i in range(min(n, 512))]


def word(m, off):
    return m.rw(m.DATA_SEG, off)


def visible_records(m):
    """Offsets of the records of the sorted list of the last frame: things on screen."""
    first, count = word(m, 0x01FE), word(m, 0x50AC)
    return [(first + 12 * i) & 0xFFFF for i in range(count)]


class Pair:
    """The original (a machine) and the C code (a copy of its memory) side by side."""

    def __init__(self, lib, m):
        self.lib, self.m = lib, m
        self.g, self.mem, self.planes = make_game(m)
        set_clock(lib, m)
        lib.game_events((GameEvent * 512)(), 512)
        m.calls.clear()

    def check(self, label, fails):
        """Compare events, memory and screen. Returns True if all equal."""
        global CASES
        CASES += 1
        mine, theirs = c_events(self.lib), list(self.m.calls)
        self.m.calls.clear()
        for kind, _ in theirs:
            SEEN[kind] = SEEN.get(kind, 0) + 1
        if mine != theirs:
            fails.append(f'{label}: calls into untranslated code differ: C {mine[:8]}, original {theirs[:8]}')
            return False
        return compare(label, self.mem, self.planes, self.m, fails)


def run(ctx):
    lib = ctx.lib
    lib.random_word.restype = ctypes.c_uint16
    lib.record_mesh_number.restype = ctypes.c_uint16
    lib.build_frame_draw_list.restype = ctypes.c_int
    lib.draw_object_list.restype = ctypes.c_int
    fails = []

    # ---- random numbers, across a refill of the buffer
    m = fresh()
    p = Pair(lib, m)
    ds = ctypes.cast(p.g.ds, ctypes.POINTER(ctypes.c_uint8))
    for i in range(450):
        want = m.call(0x0000, 0x80EE)['ax']
        got = lib.random_word(ds)
        if got != want:
            fails.append(f'random_word call {i}: {got:04X}, original {want:04X}')
            return fails
    if not p.check('random_word, 450 calls', fails):
        return fails

    # ---- debris: start on two objects, update for 50 frames, draw along the way
    pieces = drawn_frames = 0
    for first in (0, 3, 6):
        m = fresh()
        p = Pair(lib, m)
        recs = visible_records(m)
        for k in (first, first + 1):
            rec = recs[k % len(recs)]
            number = word(m, rec + 8)
            m.call(0x0000, 0x7B28, si=rec, bx=number)
            lib.debris_start(ctypes.byref(p.g), ctypes.c_uint16(rec), ctypes.c_uint16(number))
            if not p.check(f'debris_start on visible record {k}', fails):
                return fails
        pieces += word(m, 0x117A)
        for frame in range(50):
            m.call(0x0000, 0x7D2B)
            lib.debris_update(ctypes.byref(p.g))
            if not p.check(f'debris_update, objects {first}/{first + 1}, frame {frame}', fails):
                return fails
            if frame % 6 == 2 and word(m, 0x117A):
                # this frame's list with the debris in it, and the object pass
                m.call(0x0000, 0x036E)
                lib.build_frame_draw_list(ctypes.byref(p.g))
                if not p.check(f'frame list with debris, frame {frame}', fails):
                    return fails
                m.ds_write(0x00BB, b'\0')
                p.mem[(m.DATA_SEG << 4) + 0x00BB] = 0
                si, cx = word(m, 0x01FE), word(m, 0x50AC)
                if cx:
                    m.call(0x0000, 0x271E, si=si, cx=cx)
                    status = lib.draw_object_list(ctypes.byref(p.g), ctypes.c_uint16(si), ctypes.c_uint16(cx))
                    if status != 0:
                        fails.append(f'drawing debris, frame {frame}: C returned {status}')
                        return fails
                    if not p.check(f'drawing debris, objects {first}/{first + 1}, frame {frame}', fails):
                        return fails
                    drawn_frames += 1

    # ---- blast damage, with the list arranged so that every branch is taken
    blasts = queued = 0
    for variant in range(12):
        m = fresh()
        recs = visible_records(m)
        every = [0x1576 + 12 * i for i in range(word(m, 0x020E))]
        # In this snapshot DS:9A64 does not name a loaded mesh (nothing of that kind is
        # about); give it one, or a special object that blows up would fetch garbage.
        m.ds_write(0x9A64, struct.pack('<H', 2))
        car, special = word(m, 0x72CA + 2 * (variant % 3)), word(m, 0x9A64)
        source = recs[variant % len(recs)] if variant % 4 else every[variant % len(every)]
        sx, sz = struct.unpack('<h2xh', m.ds_read(source, 6))
        explosive_near = 0
        for i, rec in enumerate(every):
            flags, ident, extra = struct.unpack('<HHH', m.ds_read(rec + 6, 6))
            # Bring some of the list close to the blast. Things that go off themselves are
            # queued again by every later blast for as long as they stay in this (stale)
            # list, and the original's queue has room for 16 and no overflow check, so only
            # three of those are brought close and the queue is stepped a few times only.
            near = rec != source and i % 3 and i < 24
            if near and (i + variant) % 8 in (1, 4):
                explosive_near += 1
                near = explosive_near <= 3
            if near:
                m.ds_write(rec, struct.pack('<h', sx + (i * 37) % 500 - 250))
                m.ds_write(rec + 4, struct.pack('<h', sz + (i * 53) % 500 - 250))
            kind = (i + variant) % 8
            if kind == 1:
                ident, extra = car, (extra & 0xFF00) | (5 + 9 * (i % 7))      # a car: goes off when destroyed
            elif kind == 2:
                flags, ident = 0x4000, 2 * (i % 10)                           # a figure
            elif kind == 3:
                flags, ident = 0x4020 if i % 2 else 0x4024, ident             # the companion
            elif kind == 4:
                flags, ident = 0x2000, special                                # special object
            elif kind == 5:
                extra = (extra & 0xFF00) | (0xFF if i % 2 else 0x14)          # indestructible / weak
            elif kind == 6:
                extra = 0xFFFF                                                # already gone
            m.ds_write(rec + 6, struct.pack('<HHH', flags, ident, extra))
        strength = (20, 60, 150, 255, 90, 40)[variant % 6]
        m.ds_write(source + 10, struct.pack('<H', strength))
        if variant % 5 == 0:                                                  # the player well away
            player = word(m, 0x03A0)
            m.ds_write(player, struct.pack('<H', (word(m, player) + 3000) & 0xFFFF))
        p = Pair(lib, m)
        m.call(0x0000, 0x7EF0, stack=(source,))
        lib.explosion_damage(ctypes.byref(p.g), ctypes.c_uint16(source))
        if not p.check(f'explosion_damage, arrangement {variant}', fails):
            return fails
        blasts += 1
        queued += word(m, 0x97B6)
        for step in range(6):                     # the queued secondary blasts, one per call
            if not word(m, 0x97B6):
                break
            m.ds_write(0x020C, bytes([(step % 3 == 2) * 1]))      # sometimes not a "fourth frame"
            p.mem[(m.DATA_SEG << 4) + 0x020C] = (step % 3 == 2) * 1
            lib.blast_queue_step(ctypes.byref(p.g))
            try:
                m.call(0x0000, 0x80B6)
            except Exception as e:
                fails.append(f'blast_queue_step, arrangement {variant}, step {step}: original: {e} '
                             f'(queue {word(m, 0x97B6)}, debris {word(m, 0x117A)})')
                return fails
            if not p.check(f'blast_queue_step, arrangement {variant}, step {step}', fails):
                return fails
            blasts += 1
    print(f'    blast: {pieces} pieces of debris started, {drawn_frames} frames drawn with debris; '
          f'{blasts} blast steps, {queued} secondary blasts queued')
    names = {EV_SOUND: 'sound', EV_PLAYER_HIT: 'player hit', EV_FIGURE_KILLED: 'figure killed', EV_OBJECT_BLOWN: 'object blown'}
    print('    blast: calls into untranslated code seen: ' + ', '.join(f'{names[k]} {v}' for k, v in sorted(SEEN.items())))
    return fails
