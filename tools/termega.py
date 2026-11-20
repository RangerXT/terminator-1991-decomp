"""The Terminator EGA cinematics: DBI background + DCF deltas.

Source: 0000:B36D background, B3BC delta. DBI has four {u16 length, ByteKiller}
planes; 8000/16000 unpacked bytes identify 320/640 x 200. DCF starts with u16
frame count then {u16 length, ByteKiller}. Each decoded frame has four sections:
u16 section length INCLUDING its word, then {u16 screen offset, u8 count,
u8 bytes[count]}. Runs advance vertically by width/8 bytes (source B423+1).

Usage: python tools/termega.py info
       python tools/termega.py all out/anim/ega [preview_ms=100]
Preview duration is chosen for viewing; timing is not stored in these files.
"""
import json, os, struct, sys
from pathlib import Path
import bytekiller
ROOT = Path(__file__).resolve().parent.parent
EGA = ROOT/'data/ega'


def background(path):
    data = Path(path).read_bytes()
    at = 0
    planes = []
    records = []
    for plane in range(4):
        size = struct.unpack_from('<H', data, at)[0]
        at += 2
        raw, ok = bytekiller.decode(data, at, size)
        if not ok:
            raise ValueError('DBI checksum '+str(path))
        planes.append(raw)
        records.append(dict(plane=plane, packed_offset=at, packed_bytes=size, unpacked_bytes=len(raw)))
        at += size
    if at != len(data) or len(set(map(len, planes))) != 1 or len(planes[0]) not in [8000, 16000]:
        raise ValueError('DBI shape/tail '+str(path))
    width = len(planes[0])*8//200
    return planes, width, records


def packets(path):
    data = Path(path).read_bytes()
    count = struct.unpack_from('<H', data)[0]
    at = 2
    result = []
    for frame in range(count):
        size = struct.unpack_from('<H', data, at)[0]
        result.append(data[at:at+2+size])
        at += 2+size
    if at != len(data):
        raise ValueError('DCF unparsed tail '+str(path))
    return result


def delta(packet):
    size = struct.unpack_from('<H', packet)[0]
    raw, ok = bytekiller.decode(packet, 2, size)
    if not ok:
        raise ValueError('DCF checksum')
    at = 0
    sections = []
    for plane in range(4):
        size = struct.unpack_from('<H', raw, at)[0]
        end = at+size
        at += 2
        runs = []
        if size < 2 or end > len(raw):
            raise ValueError('DCF section bounds')
        while at < end:
            off, count = struct.unpack_from('<HB', raw, at)
            at += 3
            if not count or at+count > end:
                raise ValueError('DCF run bounds')
            runs.append((off, raw[at:at+count]))
            at += count
        if at != end:
            raise ValueError('DCF section tail')
        sections.append(runs)
    if at != len(raw):
        raise ValueError('DCF decoded tail')
    return sections


def apply(planes, sections, stride):
    for plane, runs in zip(planes, sections):
        for start, data in runs:
            for value in data:
                plane[start] = value
                start = (start+stride)&65535


def image_of(planes, width):
    from PIL import Image, ImageChops
    from termanim import EGA16
    image = Image.new('L', (width, 200), 0)
    size = width//8*200
    for bit, plane in enumerate(planes):
        mask = Image.frombytes('1', (width, 200), bytes(plane[:size])).convert('L').point([0]*255+[1<<bit])
        image = ImageChops.add(image, mask)
    out = Image.frombytes('P', image.size, image.tobytes())
    out.putpalette(bytes(v for rgb in EGA16 for v in rgb))
    return out


def decode(path, images=False):
    path = Path(path)
    raw, width, records = background(path)
    planes = [bytearray(p)+bytearray(65536-len(p)) for p in raw]
    frames = [image_of(planes, width)] if images else []
    count = 0
    runs = 0
    outside = 0
    for packet in packets(path.with_suffix('.DCF')):
        sections = delta(packet)
        runs += sum(map(len, sections))
        for entries in sections:
            for start, data in entries:
                outside += sum(((start+j*(width//8))&65535) >= len(raw[0]) for j in range(len(data)))
        apply(planes, sections, width//8)
        count += 1
        if images:
            frames.append(image_of(planes, width))
    return dict(name=path.stem, width=width, height=200, delta_frames=count, total_images=count+1, runs=runs, bytes_outside_visible_plane=outside, background_planes=records), frames


def main():
    args = sys.argv[1:]
    mode = args[0] if args else 'info'
    out = Path(args[1]) if len(args) > 1 else ROOT/'out/anim/ega'
    ms = int(args[2]) if len(args) > 2 else 100
    if mode not in ['info', 'all']:
        raise SystemExit(__doc__)
    rows = []
    if mode == 'all':
        out.mkdir(parents=True, exist_ok=True)
    for path in sorted(EGA.glob('*.DBI')):
        row, frames = decode(path, mode == 'all')
        rows.append(row)
        if frames:
            frames[0].save(out/(path.stem+'_background.png'))
            frames[0].save(out/(path.stem+'.gif'), save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=False, disposal=1)
        print('%s: %dx200, %d delta frames, %d runs, %d off-screen bytes'%(row['name'], row['width'], row['delta_frames'], row['runs'], row['bytes_outside_visible_plane']), flush=True)
    if mode == 'all':
        (out/'index.json').write_text(json.dumps(dict(preview_frame_ms=ms, timing_note='Preview timing chosen; not an encoded file field.', clips=rows), indent=2)+'\n')
    print('TOTAL:', len(rows), 'clips,', sum(r['delta_frames'] for r in rows), 'delta frames')

if __name__ == '__main__':
    main()
