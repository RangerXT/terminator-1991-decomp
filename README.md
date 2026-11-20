# The Terminator (1991, DOS) — a decompilation in C

A complete translation into C of *The Terminator*, Bethesda Softworks' 1991 DOS game
(version 1.00B, `TERM.EXE`), every routine checked against the original program running in
an emulator.

**No game files are included.** This repository holds only the C code, the tools and tests
that verify it, and the research notes. To run the tests you need your own copy of the game.

## Status

| | |
|---|---|
| The game code in C | **Complete.** All 80,987 bytes of the single-player code (segments `0000`, `11BC`, `14A7`, `14B5`, `15AD`, `5776`, `57C5`; 1,069 routines) have a C version verified against the original, including the parts that reach the hardware, the BIOS and DOS, saving and loading, the start-up, the sound layer, and the routines no path of the game reaches. |
| Verification | 205 test modules, 201,317 comparisons against the original, 0 failures. Live runs of whole frames (7,500 frames over ten routes) match the original byte for byte. |
| Out of scope | The serial-link game (segment `151B`) and the sound drivers (the sample player `5B67` and the Creative Labs drivers `0FBA`, `101F`, `10BB`); the C calls them by address. |

The details are in [PROJECT_STATUS.md](PROJECT_STATUS.md); the evidence for every routine,
data format and quirk is in [RE_NOTES.md](RE_NOTES.md) (long, in the order the work was done).

## How it works

All game state lives where the original keeps it: a 1 MB image of real-mode memory with the
data segment at its original offsets (`Game` in `src/term.h`), and the EGA screen as four bit
planes plus a model of the card's registers. Every C routine reads and writes that image
exactly as the original does, so each one can be compared byte for byte with the original.

The C code talks to its host through three kinds of service:

- game-level services (`ImageIO`, `SoundServices`, `MapResources`, `MenuPlatform`, ...) for
  files, video modes, waits and the like;
- `MachineServices`, the machine itself: port input and output, software interrupts with
  every register (`CpuRegs`), and the hardware interrupts that arrive; the routines that
  reach the hardware, the BIOS and DOS work through it register for register;
- `ProgramServices.call`: routines the host owns, by their original address (the sound
  drivers, the serial link, screens that need services of their own).

The original's quirks are kept, not fixed: a divide-error handler that resumes in the middle
of an instruction, return addresses dropped from the stack to close menus, a save format that
carries part of the interrupt vector table, and many more (see RE_NOTES.md).

## Verification

`tools/dosemu.py` is a headless PC (Unicorn CPU emulation plus just enough DOS, BIOS, timer,
keyboard and EGA/VGA) that runs the original game deterministically. Each test in `tests/`
runs a routine of the original in it and the C version on the same state, then compares
memory, the screen and the registers. Whole screens are tested by recording the original's
calls into the routines around them and replaying those to the C code
(`tests/boundaries.py`); machine-level routines by replaying the emulator's trace of ports,
interrupts and IRQs (`tests/machine.py`).

## Layout

- `src/` — the C code (one header, `term.h`; `dsvars.h` names the data-segment variables)
- `tools/` — the emulator, the differential test runner, the disassembler, coverage
  accounting (`names.py` lists every routine and its C version), format decoders and
  exporters
- `tests/` — one test module per area, each comparing C against the original

## Building and testing

Python 3 with the packages in `tools/requirements.txt` (Unicorn, Capstone, Pillow, and Zig's
C compiler through the `ziglang` package):

```
pip install -r tools/requirements.txt
python tools/difftest.py              # builds build/term.dll from src/ and runs every test
python tools/difftest.py savegame     # only the tests whose name contains "savegame"
python tools/coverage.py              # how much of the game is translated
python tools/check_linux.py           # compile every C file for Linux x64
```

The tests need what this repository leaves out: the installed game (`run_vga/`, and the data
under `data/`), the emulator snapshots in `out/emu/states/` (made with
`python tools/dosemu.py run ... --save`) and the recordings in `tests/captures/` (made with
`tools/capture.py`; each test file names the command that made its recordings). They are
copies of the game's memory, so they are not published.

## License

This project's own work — the C code, tools, tests and notes — is released into the public
domain under [The Unlicense](LICENSE): use it for anything, with no conditions. That covers
only what this repository contains; it gives no rights to the original game or its files.

## Disclaimer

*The Terminator* (1991) was developed and published by Bethesda Softworks; the film's names
and characters belong to their owners. This is an independent study of the program for
preservation and interoperability, not affiliated with or endorsed by any of them. It
contains none of the game's files.
