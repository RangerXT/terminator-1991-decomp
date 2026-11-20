"""RATINGS.RSE/TRM: fixed 207 bytes = u16 count + five 41-byte records.
Each record is ten little-endian stat words (first is signed rating) and a 21-byte
NUL-padded CP437 name. Source D628 decodes with ((byte + remaining)&255)^A5;
D5FA encodes its fixed-capacity buffer using (byte^A5)-remaining.
Exports are copies; installed score files are never changed.
Usage: python tools/termratings.py [out/tables]
"""
import csv, hashlib, json, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def decode(data):
    return bytes((((value+len(data)-i)&255)^0xA5) for i, value in enumerate(data))
def encode(data):
    return bytes(((value^0xA5)-(len(data)-i))&255 for i, value in enumerate(data))


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT/'out/tables'
    out.mkdir(parents=True, exist_ok=True)
    tables = []
    rows = []
    for name, actor in [('RATINGS.RSE', 0x04D4), ('RATINGS.TRM', 0x0508)]:
        data = (ROOT/'data/common'/name).read_bytes()
        plain = decode(data)
        if len(data) != 207 or encode(plain) != data:
            raise ValueError('ratings length/round-trip')
        count = struct.unpack_from('<H', plain)[0]
        if not 0 <= count <= 5:
            raise ValueError('ratings record count')
        records = []
        for index in range(count):
            rec = plain[2+index*41:2+(index+1)*41]
            words = struct.unpack('<10H', rec[:20])
            score = struct.unpack_from('<h', rec)[0]
            text = rec[20:].split(bytes([0]), 1)[0].decode('cp437')
            record = dict(index=index, score=score, name=text, stat_words=list(words))
            records.append(record)
            rows.append(dict(file=name, player_record='%04X'%actor, index=index, score=score, name=text, **{'stat_%d'%i:word for i, word in enumerate(words)}))
        tables.append(dict(file=name, player_record='%04X'%actor, sha256=hashlib.sha256(data).hexdigest(), records=records))
    (out/'ratings.json').write_text(json.dumps(dict(source_decode='0000:D628', source_encode='0000:D5FA', record_bytes=41, tables=tables), indent=2)+'\n')
    with (out/'ratings.csv').open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print('Exported %d rating records from %d tables'%(len(rows), len(tables)))

if __name__ == '__main__':
    main()
