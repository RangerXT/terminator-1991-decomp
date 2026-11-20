"""The Terminator (1991) sound effects: .RS -> .WAV

  .RS  (RealSound-style 6-bit samples; player in segment 5B67 of the unpacked exe, entry 5B67:0818)
      char tag[5]      "CRAIG" or "STEVE" (who digitised it; not checked by the game)
      u8  rate_code    always 3 in the shipped files: each sample lasts 3 ticks of the
                       16,572 Hz PC-speaker carrier (PIT divisor 72) = about 5,524 Hz.
                       The Sound Blaster path uses the matching table 60/120/181/241 microseconds.
      u8  unknown      0x00 (CRAIG) or 0x48 (STEVE); not read by the player
      u16 length       sample count
      zero padding to 32 bytes
      u8  sample[length]   unsigned, 0..63

  SONG1.CMF is a standard Creative Music File (AdLib/OPL2); any CMF player handles it.

usage:
  python tools/termsnd.py info
  python tools/termsnd.py all <out_dir>
"""
import os
import struct
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
COMMON = os.path.join(HERE, '..', 'data', 'common')
PIT_HZ = 1193182
CARRIER_DIVISOR = 72


def read_rs(path):
    d = open(path, 'rb').read()
    tag = d[:5].decode('latin1')
    rate_code = d[5]
    length = struct.unpack_from('<H', d, 7)[0]
    samples = d[32:32 + length]
    rate = PIT_HZ / CARRIER_DIVISOR / max(1, rate_code)
    return tag, rate_code, rate, samples


def to_wav(samples, rate, dst):
    with wave.open(dst, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(round(rate))
        w.writeframes(bytes(min(255, s * 4 + 2) for s in samples))


def files():
    return sorted(f for f in os.listdir(COMMON) if f.endswith('.RS'))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'info':
        for f in files():
            tag, code, rate, s = read_rs(os.path.join(COMMON, f))
            print(f'{f:13} {tag} rate_code {code} ({rate:.0f} Hz) {len(s)} samples = {len(s) / rate:.2f} s')
    elif a[0] == 'all':
        os.makedirs(a[1], exist_ok=True)
        for f in files():
            tag, code, rate, s = read_rs(os.path.join(COMMON, f))
            to_wav(s, rate, os.path.join(a[1], f[:-3] + '.wav'))
        print(len(files()), 'sounds written to', a[1])


if __name__ == '__main__':
    main()
