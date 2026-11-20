# The Terminator (1991) — decompilation: status

**Goal.** A complete decompilation of the DOS game: every routine translated to C and
proved equal to the original.

Detailed evidence, addresses and format notes: `RE_NOTES.md` (long; newest sections last).
There is one backup at a time, in `out/backup/` (now: sources, tests, tools and the
previous status text as of 2026-11-18, before the readability work); a new backup
replaces it. The project is also under git (`main`, published on GitHub).

## Where it stands (measured 2026-11-19, night)

| | |
|---|---|
| Game data | Every file format the game loads is decoded and exported (meshes, city map, collision, images, cutscenes, sound, music, fonts, save files). The six city OBJ exports were audited against the game's own loader. |
| Game code in C | **Done: 100.0%** of the single-player game code has a C version verified against the original (all 83,511 bytes of segments `0000`, `10BB`, `11BC`, `14A7`, `14B5`, `15AD`, `5776`, `57C5`; 1,128 routines in `tools/names.py` `C_VERSIONS`; `NATIVE` is empty, `DEAD` holds one routine of the music driver that nothing references). That includes the routines that reach the hardware, the BIOS and DOS (through `MachineServices`: ports, software interrupts, and the hardware interrupt that arrives), saving and loading, the program's start with its command line, the sound layer between the game and its drivers, the FM music driver `10BB` (`src/fmdrv.c`, added 2026-11-20), and the 24 routines no path of the game reaches. `python tools/coverage.py` measures it. |
| Verification | 206 test modules, **204,861 comparisons against the original, 0 failures** (`python tools/difftest.py`, about 18 minutes). Ten live runs of walking and turning on different routes (7,500 frames in all, 2026-11-19) produce frames identical to the original (`tools/frame_demo.py --sequence`). The C code compiles warning-free for Windows x64 and Linux x64. |

Out of scope by decision (the C calls them by address through `ProgramServices.call`):

- `151B` serial link play (2,327 bytes): the shipped `TERM.EXE` refuses link mode before
  gameplay; `GAME.EXE` accepts it but stops with Error 25.
- The other sound drivers: `5B67` sample player and the Creative Labs drivers `0FBA` (FM) and
  `101F` (CT-VOICE) (4,880 bytes). The music driver `10BB` (FMDRV) is translated.

## How the C code is built

All game state lives where the original keeps it: a 1 MB copy of real-mode memory with the
main data segment at its original offsets (`Game` in `src/term.h`: `mem`, `ds`, `planes`,
`ds_seg`). Every translated routine reads and writes that image exactly as the original
does, and the EGA screen is four bit planes plus a model of the card's registers. That is
what lets every routine be compared byte for byte with the original in the emulator.

Three kinds of service connect the C code to its host:

- Game-level services (`ImageIO`, `SoundServices`, `MapResources`, `MenuPlatform`, ...):
  files, video modes, waits and the like, by operation.
- `MachineServices`: the machine itself - port input and output, software interrupts with
  every register (`CpuRegs`), and `irq` (the hardware interrupt that arrives now). The
  hardware, BIOS and DOS routines (`src/machine.c`, `src/dos.c`, the sound layer, saving and
  loading, start-up) work through it, register for register.
- `ProgramServices.call`: routines the host owns, by their original address with the
  registers they take - the sound drivers, the serial link, and the screens that need
  services of their own when `program_start` runs them.

## What is left

Nothing in the counted code.

## Known weaknesses of the current state

- The tests depend on 345 MB of recordings in `tests/captures/` and 22 snapshots in
  `out/emu/states/`, which are not published (they are copies of the game's memory). Each
  test file names the command that made its recordings.
- `RE_NOTES.md` is over 3,000 lines in diary order; this file is the summary.
- A few C versions return less than the original leaves in registers no caller reads
  (noted in their comments, e.g. a C-library callee's scratch registers); the tests leave
  exactly those out.
- 1,631 uses of data-segment variables are still raw addresses, each a variable
  whose role is not yet clear (`python tools/dsxref.py --compact --unnamed 40` lists the
  most used). They get names as their routines are studied.
- `tools/check_linux.py` only compiles each file for Linux as a portability check; it does
  not link or run anything.

## Readability (2026-11-18)

All C sources follow one style (`.clang-format`), the 1,409 most common data-segment
addresses are named (`src/dsvars.h`), and the Python tests and tools have one statement per
line. Both C steps were proved behaviour-neutral by building before and after and getting
byte-identical machine code; the Python tidy-up by comparing syntax trees. Two wrong names
of mine from earlier sessions were corrected: the "turret" records are guided projectiles,
and `append_companion` is `append_opponent_and_companion`.

Since then each translation names the variables it touches (107 more uses on 2026-11-19, each
rename again proved by an identical build). Tests of whole screens share one record/replay
method, `tests/boundaries.py` (see RE_NOTES.md, "The M key's map screen in C"); tests of
machine-level routines replay the emulator's trace, `tests/machine.py`.

## How to check

```
python tools/difftest.py                      # all test modules (~17 min)
python tools/difftest.py frame                # whole main-loop frames, C against the original (~1 min)
python tools/difftest.py frames               # live whole-frame comparison (~1 min)
python tools/frame_demo.py --sequence 900 --quiet --keys "2:up:200,210:right:40,260:up:300"
python tools/disasm.py                        # regenerate the listing in disasm/
python tools/coverage.py                      # how much is translated (and any routines left)
```
