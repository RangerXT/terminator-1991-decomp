"""Differential testing: original routine in the emulator vs. the C rewrite in src/.

  python tools/difftest.py            build src/*.c and run every tests/test_*.py
  python tools/difftest.py rotate     run only tests whose file name contains "rotate"

A test module defines  run(ctx) -> list of failure strings  and may set  CASES  for the report.
ctx.lib is the compiled C library (ctypes), ctx.game() a Machine restored from the in-game
snapshot (tables initialised), ctx.boot() a freshly booted Machine (lots of free memory).
"""
import ctypes
import glob
import importlib.util
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import dosemu  # noqa: E402

DLL = os.path.join(ROOT, 'build', 'term.dll')
SNAP = os.path.join(ROOT, 'out', 'emu', 'states', 'ingame.pkl')


def build():
    srcs = sorted(glob.glob(os.path.join(ROOT, 'src', '*.c')))
    deps = srcs + glob.glob(os.path.join(ROOT, 'src', '*.h'))
    if os.path.exists(DLL) and all(os.path.getmtime(DLL) >= os.path.getmtime(d) for d in deps):
        return
    os.makedirs(os.path.dirname(DLL), exist_ok=True)
    cmd = [sys.executable, '-m', 'ziglang', 'cc', '-shared', '-O2', '-std=c99', '-Wall', '-Wextra',
           '-Wno-unused-parameter', '-o', DLL] + srcs
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit('C build failed')
    if r.stderr.strip():
        print(r.stderr)


class Ctx:
    def __init__(self):
        build()
        self.lib = ctypes.CDLL(DLL)
        self._game = None

    def game(self):
        """Machine restored from the in-game snapshot. Shared between tests; callers must not
        rely on registers, and should restore any data they overwrite."""
        if self._game is None:
            self._game = dosemu.Machine()
            self._game.load(SNAP)
        return self._game

    def boot(self):
        return dosemu.Machine()

    def ds_copy(self):
        """A writable copy of the game's 64 KB data segment as a ctypes buffer."""
        return ctypes.create_string_buffer(self.game().ds_read(0, 0x10000), 0x10000)


def main():
    pat = sys.argv[1] if len(sys.argv) > 1 else ''
    ctx = Ctx()
    total_fail = 0
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, 'tests', 'test_*.py'))):
        name = os.path.basename(path)[5:-3]
        if pat and pat not in name:
            continue
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        t0 = time.time()
        fails = mod.run(ctx)
        rows.append((name, getattr(mod, 'CASES', '?'), len(fails), time.time() - t0))
        total_fail += len(fails)
        for f in fails[:8]:
            print(f'  FAIL {name}: {f}')
    print(f'{"test":28} {"cases":>8} {"failed":>7} {"seconds":>8}')
    for name, cases, nf, secs in rows:
        print(f'{name:28} {cases!s:>8} {nf:>7} {secs:>8.1f}')
    print('ALL PASSED' if total_fail == 0 else f'{total_fail} FAILURES')
    return 1 if total_fail else 0


if __name__ == '__main__':
    sys.exit(main())
