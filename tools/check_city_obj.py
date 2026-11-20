"""Compare the six existing sector OBJs with geometry resident in the DOS executable.

Run from any directory with the project Python. Uses the installed gameplay snapshot
and original 11BC:097E. Does not import the exporter or change any game or OBJ files.
"""
from collections import Counter
from hashlib import sha256
from pathlib import Path
import struct

import dosemu

ROOT = Path(dosemu.ROOT)
U16 = struct.Struct('<H')
VERT = struct.Struct('<3h')
POINT = struct.Struct('<3i')
GROUND = struct.Struct('<3iH')
OBJECT = struct.Struct('<3h3H')


def word(data, at):
    return U16.unpack_from(data, at)[0]


def fingerprint(vertices, faces):
    """Includes ordering, exact integer positions, face indices, primitive and material."""
    h = sha256(U16.pack(len(vertices)))
    for xyz in vertices:
        h.update(POINT.pack(*xyz))
    for primitive, colour, face in faces:
        h.update(struct.pack('<cBH', primitive, colour, len(face)))
        h.update(struct.pack(f'<{len(face)}H', *face))
    return h.digest()


def read_obj(path):
    groups = {'ground': Counter(), 'objects': Counter()}
    vertices, faces, group = [], [], None
    base, colour = 1, None
    for line in path.read_bytes().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith(b'#'):
            continue
        tag = fields[0]
        if tag == b'o':
            if group:
                groups[group][fingerprint(vertices, faces)] += 1
            base += len(vertices)
            vertices, faces = [], []
            group = 'ground' if fields[1].split(b'_')[0][3:].isdigit() and fields[1].startswith(b'big') else 'objects'
        elif tag == b'v':
            vertices.append(tuple(map(int, fields[1:])))
        elif tag == b'usemtl':
            colour = int(fields[1].removeprefix(b'pal_'))
        elif tag in (b'f', b'l', b'p'):
            face = tuple(int(v)-base for v in fields[1:])
            if colour is None or not all(0 <= v < len(vertices) for v in face):
                raise ValueError(f'{path.name}: invalid face in object starting at vertex {base}')
            faces.append((tag, colour, face))
    if group:
        groups[group][fingerprint(vertices, faces)] += 1
    return groups


def resident_mesh(data, size_at):
    start = size_at+2
    _, nf, nv, face_off, vert_off = struct.unpack_from('<5H', data, start)
    vertices = list(VERT.iter_unpack(data[start+vert_off:start+vert_off+nv*6]))
    faces = []
    at = start + face_off
    for _ in range(nf):
        colour, _, _, n = struct.unpack_from('<BBHH', data, at)
        indices = struct.unpack_from(f'<{n}H', data, at+6)
        if any(v%6 or v//6 >= nv for v in indices):
            raise ValueError('bad resident face')
        faces.append((b'f' if n >= 3 else b'l' if n == 2 else b'p', colour, tuple(v//6 for v in indices)))
        at += 6+2*n
    return vertices, faces


def place(mesh, origin, turns, ground):
    ox, oy, oz = origin
    vertices = []
    for x, y, z in mesh[0]:
        # The resident mesh already uses Z north. OBJ uses Z south.
        x, z = ((x, z), (-z, x), (-x, -z), (z, -x))[turns]
        vertices.append((ox+x, -(oy+y), oz-z))
    faces = []
    for tag, colour, indices in mesh[1]:
        reverse = not ground
        if ground and tag == b'f':
            corners = [vertices[v] for v in indices]
            turn = sum(a[2]*b[0] - a[0]*b[2] for a, b in zip(corners, corners[1:] + corners[:1]))
            reverse = turn < 0
        faces.append((tag, colour, indices[::-1] if reverse else indices))
    return fingerprint(vertices, faces)


def original_sector(m, sector_x, sector_z):
    left, top = 64*sector_x, 64*sector_z
    objects, ground, visited, coarse = Counter(), set(), set(), set()
    def ds(off):
        return m.rw(m.DATA_SEG, off)
    actor = ds(0x03A0)
    for dz in (8, 32, 48):
        for dx in (8, 32, 48):
            m.ww(m.DATA_SEG, actor+30, left+dx)
            m.ww(m.DATA_SEG, actor+32, top+dz)
            m.call(0x11BC, 0x097E, far=True, max_instr=100_000_000)
            wx, wz = ds(0x7272), ds(0x7274)
            cells = m.rb(ds(0x91D4), 0, 65536)
            solids = m.rb(ds(0x91D0), 0, 65536)
            land = m.rb(ds(0x91D2), 0, 65536)
            solid_meshes, ground_meshes = {}, {}
            for row in range(24):
                for col in range(24):
                    gx, gz = wx+col-left, wz+row-top
                    if not (0 <= gx < 64 and 0 <= gz < 64) or (gx, gz) in visited:
                        continue
                    visited.add((gx, gz))
                    ptr = word(cells, 2*(row*24+col))
                    for n in range(word(cells, ptr) if ptr else 0):
                        x, y, z, flags, slot, _ = OBJECT.unpack_from(cells, ptr+2+12*n)
                        if slot not in solid_meshes:
                            solid_meshes[slot] = resident_mesh(solids, ds(0x91DA+2*slot))
                        origin = (gx*1024+x, y, (gz+1)*1024-z)
                        objects[place(solid_meshes[slot], origin, flags&3, False)] += 1
            for row in range(3):
                for col in range(3):
                    key = ((wx-left)//8+col, (wz-top)//8+row)
                    if not all(0 <= a < 8 for a in key) or key in coarse:
                        continue
                    coarse.add(key)
                    ptr = word(land, 4*(row*3+col))
                    for n in range(word(land, ptr) if ptr else 0):
                        x, y, z, slot = GROUND.unpack_from(land, ptr+2+14*n)
                        if slot not in ground_meshes:
                            ground_meshes[slot] = resident_mesh(land, ds(0x727E)+ds(0x92DA+2*slot))
                        # BIG placements repeat in each overlapping coarse-cell list.
                        ground.add(place(ground_meshes[slot], (x-left*1024, y, z-top*1024), 0, True))
    if len(visited) != 4096 or len(coarse) != 64:
        raise ValueError('incomplete coverage of sector')
    return objects, ground


def main():
    m = dosemu.Machine()
    m.load(str(ROOT/'out/emu/states/ingame.pkl'))
    failures = 0
    for z in range(2):
        for x in range(3):
            name = f'LA{"AB"[z]}{x+1}'
            objs = read_obj(ROOT/'out/obj'/f'{name}.obj')
            placed, ground = original_sector(m, x, z)
            missing = (objs['objects'] - placed).total()
            extra = (placed - objs['objects']).total()
            gm = len(objs['ground'].keys() - ground)
            ge = len(ground - objs['ground'].keys())
            repeated = objs['ground'].total()-len(objs['ground'])
            print(f'{name}: {placed.total()} shared placements, {len(ground)} distinct ground geometries; '
                  f'OBJ-only/DOS-only shared={missing}/{extra} ground={gm}/{ge}; '
                  f'identical ground groups in OBJ={repeated}', flush=True)
            failures += missing+extra+gm+ge
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
