"""LA.BMP collision records. Run via term3d.py collision <output directory>."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import struct


@dataclass
class Footprint:
    offset: int
    bounds: tuple
    extra: tuple
    mask_header: tuple
    bits: bytes

    def rows(self):
        w, h = self.mask_header[-2:]
        return [[(self.bits[k >> 3] >> (7-(k&7))) & 1 for k in range(y*w, (y+1)*w)]
                for y in range(h)]


def read_footprints(path):
    data = Path(path).read_bytes()
    count, = struct.unpack_from('<H', data)
    at, records = 2, []
    for i in range(count):
        start = at
        size, ident, cx, cz, w, h, n = struct.unpack_from('<HH5h', data, at)
        if size != 14+8*n or ident != i:
            raise ValueError(f'Unexpected bounds header at offset {at} (object {i})')
        extra = tuple(struct.iter_unpack('<4h', data[at+14:at+size]))
        at += size
        present, = struct.unpack_from('<H', data, at)
        at += 2
        if present not in (0, 1):
            raise ValueError(f'Unexpected mask flag at offset {at-2}')
        header, bits = (), b''
        if present:
            header = struct.unpack_from('<6h', data, at)
            mw, mh = header[-2:]
            if not (0 <= mw < 256 and 0 <= mh < 256):
                raise ValueError(f'Invalid mask dimensions on object {i}')
            at += 12
            length = (mw*mh+7)//8
            bits = data[at:at+length]
            if len(bits) != length:
                raise ValueError(f'Truncated mask on object {i}')
            at += length
        records.append(Footprint(start, (cx, cz, w, h), extra, header, bits))
    if at != len(data):
        raise ValueError(f'Unexpected trailing bytes at offset {at}')
    return records


def export_collision(src, meshes, folder):
    from PIL import Image
    folder = Path(folder)
    records = read_footprints(src)
    if len(meshes) != len(records):
        raise ValueError('LA.BMP/LA.DEF object count differs')
    folder.mkdir(parents=True, exist_ok=True)
    objects = []
    for i, (mesh, record) in enumerate(zip(meshes, records)):
        cx, cz, w, h = record.bounds
        obj = dict(id=i, name=mesh.name, source_offset=record.offset,
                   stamp=dict(anchor=[cx, cz], size=[w, h]), extra_words=record.extra, mask=None)
        if record.mask_header:
            first, second, mx, mz, mw, mh = record.mask_header
            safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', mesh.name)
            filename = None
            if mw and mh:
                filename = f'{i:03d}_{safe_name}.png'
                pixels = bytes(255*b for row in reversed(record.rows()) for b in row)
                Image.frombytes('L', (mw, mh), pixels).convert('1').save(folder/filename)
            unused = (-mw*mh)%8
            obj['mask'] = dict(file=filename, size=[mw, mh], origin_pixel=[mx, mh-1-mz],
                               header_words=[first, second], trailing_bits=(record.bits[-1]&((1<<unused)-1)) if unused else 0)
        objects.append(obj)
    manifest = dict(source='LA.BMP', units_per_pixel=16, orientation='unrotated; PNG right=east, down=south; white=solid',
                    stamp='anchor and size are the coarse collision rectangle in grid cells, as stored',
                    origin_pixel='pixel coordinates of the mesh origin, measured from top left',
                    extra_words='four signed words per optional record, preserved as stored',
                    objects=objects)
    (folder/'collision.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    # Read the written artifacts back. The PNGs, bounds and remaining metadata
    # must reconstruct even unused bits and the extended headers byte for byte.
    if restore_bytes(folder) != Path(src).read_bytes(): raise ValueError('Collision export failed round trip')
    print(f'{len(objects)} collision entries, {sum(bool(o["mask"] and o["mask"]["file"]) for o in objects)} PNGs; '
          f'all {Path(src).stat().st_size} source bytes reconstructed')


def restore_bytes(folder):
    from PIL import Image
    folder = Path(folder)
    objects = json.loads((folder/'collision.json').read_text(encoding='utf-8'))['objects']
    data = bytearray(struct.pack('<H', len(objects)))
    for o in objects:
        ext, stamp, mask = o['extra_words'], o['stamp'], o['mask']
        data.extend(struct.pack('<HH5h', 14+8*len(ext), o['id'], *stamp['anchor'], *stamp['size'], len(ext)))
        for words in ext:
            data.extend(struct.pack('<4h', *words))
        data.extend(struct.pack('<H', int(mask is not None)))
        if mask:
            w, h = mask['size']
            x, y = mask['origin_pixel']
            data.extend(struct.pack('<6h', *mask['header_words'], x, h-1-y, w, h))
            if w*h == 0:
                continue
            with Image.open(folder/mask['file']) as image:
                if image.size != (w, h):
                    raise ValueError(f'Mask size mismatch for {o["id"]}')
                pixels = image.convert('L').transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
            raw = bytearray((w*h+7)//8)
            for k, pixel in enumerate(pixels):
                if pixel:
                    raw[k>>3] |= 128>>(k&7)
            raw[-1] |= mask['trailing_bits']
            data.extend(raw)
    return bytes(data)
