"""Compile each native translation as a Linux object; this is build portability proof,
not a runnable Linux game or live platform validation.
"""
import concurrent.futures, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def main():
    target = ROOT/'build/linux'
    target.mkdir(parents=True, exist_ok=True)
    def compile_one(src):
        command = [sys.executable, '-m', 'ziglang', 'cc', '-target', 'x86_64-linux-gnu', '-c', '-O2', '-std=c99', '-Wall', '-Wextra', '-Wno-unused-parameter', '-o', str(target/(src.stem+'.o')), str(src)]
        result = subprocess.run(command, capture_output=True, text=True)
        return src.name, result.returncode, result.stdout+result.stderr
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(compile_one, sorted((ROOT/'src').glob('*.c'))))
    lines = []
    for name, code, output in rows:
        lines.append(name+(': FAIL' if code else ': PASS'))
        if output.strip():
            lines.append(output.strip())
    failures = sum(bool(row[1]) for row in rows)
    lines.append('%d sources, %d failures'%(len(rows), failures))
    report = ROOT/'out/verification/linux_objects.txt'
    report.write_text(chr(10).join(lines)+chr(10))
    print(chr(10).join(lines))
    return bool(failures)
if __name__ == '__main__':
    sys.exit(main())
