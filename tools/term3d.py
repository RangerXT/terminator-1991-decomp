"""The Terminator (Bethesda, 1991) - 3D mesh and city map reader.

Formats handled (all little-endian, uncompressed):

  mesh container  LA.DEF, LA??.BIG, *.CSF   (*.SPN is one bare record: u16 size; body)
      u16 count
      count x { u16 size; body[size] }
      body:  u16 name_off   (0 = unnamed, else offset of 8-char name)
             u16 n_faces
             u16 n_verts
             u16 face_off
             u16 vert_off
             u16 tabA_off   n_faces bytes telling the back-face test what to do (code at 11BC:159C):
                            0 = test this face, N = use the result of face N-1 (coplanar detail
                            such as a window on its wall), FF = two-sided (never hidden; drawn
                            with reversed vertex order when seen from behind)
             u16 order      draw-order control (code at 0000:2D2A): 0 = file order, N < n_faces =
                            pivot on face N-1 (if it is hidden the face groups are drawn in
                            reverse). Values >= n_faces, including FFFF, do nothing; in every BIG and some
                            DEF/CSF/SPN records the word points just after the facing table.
             u16 foot_off   (0 or offset of 4 x (i16 x, i16 z) footprint corners)
             faces: { u8 colour; u8 outline_colour; u16 flags; u16 n; u16 vert_byte_off[n] }
                    colour 0-15 = EGA colour, 16-135 = 50% dither of two (see dither_pair)
                    flags bit 0 = filled, bit 1 = also draw its outline in outline_colour
                    (code at 0000:482B; the shipped data only uses 1 and 3)
                    n = 1 is a point, n = 2 a line, n >= 3 a polygon
             verts: n_verts x (i16 x, i16 y, i16 z)      right-handed: x east, y DOWN, z north.
                    Exception: the meshes in LA??.BIG are stored with z SOUTH; the game
                    negates their z when it loads them (seen by comparing memory with
                    the files; LA.DEF and .CSF meshes are loaded unchanged).
             winding: solids (LA.DEF, .SPN) are clockwise seen from outside in the game's
                    frame; the flat figures in .CSF are counter-clockwise seen from the
                    viewer (the game reverses them when it draws, 11BC:157C); ground
                    meshes are not culled and have no consistent winding.
      every offset is relative to the start of the body.

  LA??.BIG tail   (after the mesh records) - where the sector's unique meshes (roads...) go
      u16 w, u16 h (8 x 8); w*h pairs of u16 offsets relative to tail start (0 = empty).
      The first offset is the placement list. 11BC:0E83 handles a separate second list;
      all 384 second offsets in the installed sectors are zero. Each secondary list holds
      a count and tail-relative u16 record offsets. Each fresh record has 22 opaque header
      bytes, a u16 entry count, and 10 bytes per entry. The info command prints their bytes.
      list: u16 n; n x { i32 x; i32 y; i32 z; u16 mesh_index }   sector-global coordinates,
      x east, z SOUTH, like the vertices of these files: a vertex is at east = x + vx,
      south = z + vz. (At run time the placement becomes z_local = (row + 1) * 1024 - z,
      code at 0000:3EB5-3EE4, and the already negated vertex z is added to that.)
      a mesh that overlaps several coarse cells is listed in each of them.

  LA??.SCT        - placement of shared LA.DEF objects
      u16 w, u16 h (64 x 64); u16 list_off[w*h] absolute file offsets (0 = empty)
      list: u16 n; n x { u16 x; u16 y(0); u16 z; u16 rot(0-3); u16 def_index; u16 0 }
      (when loading, the game replaces def_index by a slot number and fills the last word:
      low byte = the object's strength, table DS:5EFA; high byte = car colour variant)
      rot = quarter turns counter-clockwise seen from above (see rot_xz)
      x/z are 0..1023 inside the cell; one cell = 1024 units, one sector = 65536 units.
      Columns run east and rows run south, but z inside a cell is measured NORTH from the
      cell's south edge: an object is at east = col*1024 + x, south = (row+1)*1024 - z
      (the cell walk at 0000:3C18-3D4D steps z by -1024 per row; see also 0000:41F8).

  LA.BMP          - collision footprint of each LA.DEF object (loader 11BC:12E7)
      u16 count (117, same order as LA.DEF)
      per object: u16 header_bytes; i16 def_index, anchor_x, anchor_z, w, h, n_extra
                  followed by n_extra groups of 4 signed words; sizes in 16-unit cells.
                  u16 has_bitmap
                  if has_bitmap: i16 reserved, height_like, centre_x, centre_z, w, h;
                                 then ceil(w*h/8) bytes. The first word is always zero.
                                 The second matches a rounded mesh vertex height in 112 of
                                 113 masks. Its precise authoring rule is unconfirmed.
                                 one bit per 16x16-unit cell, row-major, MSB first (1 = solid).
                                 Rows run from SOUTH to NORTH (row index grows with the
                                 game's z), columns west to east; the cell under the
                                 object's origin is (centre_x, centre_z). Code: 11BC:20CE-2166.

  *.CSF pose order (frame selection code at 0000:B0A6-B186; people are 22-byte records at DS:0B30)
      dir = (8 - (((heading - angle_from_viewer) & 511) >> 6)) & 7        8 view directions
      MANWOM.CSF: man = meshes 0-39, woman = 40-79; within each
          0-7    standing, one per dir
          8-39   walking, 8 + dir*4 + frame (frame 0-3)
      COP.CSF / SOL.CSF (25 each): only 5 poses, pose = [0,1,2,3,0,1,3,4][dir]
          0-4    standing, one per pose
          5-24   walking, 5 + pose*4 + frame
      ENEMIES.CSF = SOL + COP + MANWOM in one file (two meshes differ slightly); no code loads it.

  World frame of everything this tool writes (OBJ files and the map picture):
      x = east, y = up, z = south, right-handed. A game vertex (x, y, z) becomes
      (x, -y, -z): a half turn about the x axis, not a mirror image. (For .BIG meshes
      that is (x, -y, z) of the file's numbers.) Faces are written counter-clockwise
      seen from their front. Figures face +z, towards the viewer of a front view.

usage:
  python tools/term3d.py info <file>...
  python tools/term3d.py obj  <container> <out.obj>          every mesh, laid out in a row
  python tools/term3d.py sector <LAA1> <out.obj>             whole sector, objects instanced
  python tools/term3d.py map <out.png>                       top-down plot of all six sectors
  python tools/term3d.py collision <folder>                  north-up masks and LA.DEF index
"""
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', 'data', 'common')
CELL = 1024
SECTOR = 65536
SECTORS = ['LAA1', 'LAA2', 'LAA3', 'LAB1', 'LAB2', 'LAB3']


class Mesh:
    __slots__ = ('name', 'verts', 'faces', 'tab_a', 'foot', 'hdr')


def parse_mesh(b):
    name_off, nf, nv, fo, vo, ta, tb, ft = struct.unpack_from('<8H', b, 0)
    m = Mesh()
    m.hdr = (name_off, nf, nv, fo, vo, ta, tb, ft)
    m.name = b[name_off:name_off + 8].split(b'\0')[0].decode('latin1') if name_off else ''
    m.verts = [struct.unpack_from('<3h', b, vo + 6 * i) for i in range(nv)]
    m.faces = []
    q = fo
    for _ in range(nf):
        col, col2, unk, n = struct.unpack_from('<BBHH', b, q)
        idx = struct.unpack_from(f'<{n}H', b, q + 6)
        if any(i % 6 or i // 6 >= nv for i in idx):
            raise ValueError('bad vertex reference')
        m.faces.append((col, col2, unk, tuple(i // 6 for i in idx)))
        q += 6 + 2 * n
    m.tab_a = bytes(b[ta:ta + nf]) if ta else b''
    m.foot = [struct.unpack_from('<2h', b, ft + 4 * i) for i in range(4)] if ft else None
    return m


def read_container(path):
    """Return (meshes, offset_after_last_mesh, raw_bytes)."""
    d = open(path, 'rb').read()
    n = struct.unpack_from('<H', d, 0)[0]
    pos = 2
    out = []
    if n + 2 == len(d):  # .SPN: a single bare record, the first word is its size
        return [parse_mesh(d[2:])], len(d), d
    for _ in range(n):
        sz = struct.unpack_from('<H', d, pos)[0]
        out.append(parse_mesh(d[pos + 2:pos + 2 + sz]))
        pos += 2 + sz
    return out, pos, d


def read_big_secondary(tail):
    """Return cell references and opaque record bodies, keyed by tail-relative offsets."""
    if len(tail) < 4:
        raise ValueError('Truncated BIG directory')
    width, height = struct.unpack_from('<HH', tail)
    directory_end = 4 + width * height * 4
    if directory_end > len(tail):
        raise ValueError('Truncated BIG directory')
    cells, records = {}, {}
    directory = struct.iter_unpack('<HH', tail[4:directory_end])
    for cell, (_, offset) in enumerate(directory):
        if not offset:
            continue
        if offset < directory_end or offset + 2 > len(tail):
            raise ValueError(f'Invalid secondary list offset {offset:#x}')
        count, = struct.unpack_from('<H', tail, offset)
        if not count or offset + 2 + 2*count > len(tail):
            raise ValueError(f'Invalid secondary list length at {offset:#x}')
        refs = struct.unpack_from(f'<{count}H', tail, offset + 2)
        cells[cell % width, cell // width] = refs
        for ref in refs:
            if ref in records:
                continue
            if ref < directory_end or ref + 24 > len(tail):
                raise ValueError(f'Invalid secondary record offset {ref:#x}')
            if tail[ref + 1] & 0x80:
                raise ValueError(f'Secondary record at {ref:#x} has a resident reuse marker')
            n, = struct.unpack_from('<H', tail, ref + 22)
            end = ref + 24 + 10*n
            if end > len(tail):
                raise ValueError(f'Truncated secondary record at {ref:#x}')
            entries = tuple(tail[i:i+10] for i in range(ref+24, end, 10))
            records[ref] = tail[ref:ref+22], entries
    return cells, records


def read_big(path):
    """Return (meshes, placements) with placements = sorted unique (x, y, z, mesh_index)."""
    meshes, pos, d = read_container(path)
    t = d[pos:]
    w, h = struct.unpack_from('<2H', t, 0)
    seen = set()
    read_big_secondary(t)  # Validate the optional records. Only primary placements have known geometry.
    for off, _ in struct.iter_unpack('<HH', t[4:4 + 4*w*h]):
        if not off:
            continue
        n = struct.unpack_from('<H', t, off)[0]
        for k in range(n):
            seen.add(struct.unpack_from('<3iH', t, off + 2 + 14 * k))
    return meshes, sorted(seen)


def read_sct(path):
    """Return list of (east, south, rot, def_index): where each object's origin is, in sector
    coordinates (see the module text for why south is (row + 1) * 1024 - z)."""
    d = open(path, 'rb').read()
    w, h = struct.unpack_from('<2H', d, 0)
    grid = struct.unpack_from(f'<{w * h}H', d, 4)
    out = []
    for i, off in enumerate(grid):
        if not off:
            continue
        cx, cz = i % w, i // w
        n = struct.unpack_from('<H', d, off)[0]
        for k in range(n):
            x, _, z, rot, obj, _ = struct.unpack_from('<6H', d, off + 2 + 12 * k)
            out.append((cx * CELL + x, (cz + 1) * CELL - z, rot, obj))
    return out


def read_bmp(path):
    """LA.BMP -> list of (w, h, rows) per LA.DEF object, rows as lists of 0/1; None if no bitmap."""
    if __package__:
        from .termcollision import read_footprints
    else:
        from termcollision import read_footprints
    return [(*r.mask_header[-2:], r.rows()) if r.mask_header else None for r in read_footprints(path)]


def rot_xz(x, z, rot):
    """Apply an .SCT object's quarter turns to a local (x, z), in the game's own frame.

    One turn maps (x, z) -> (-z, x). The game's frame is x east, z north, so that is 90
    degrees counter-clockwise seen from above. Taken from the game's vertex transform at
    0000:29EC-2A23, which reads the turn count from the placement record's word +6
    (copied at 0000:3DB5-3DC1, masked to 2 bits at 0000:27E3)."""
    for _ in range(rot & 3):
        x, z = -z, x
    return x, z


# ---------------------------------------------------------------- commands

def cmd_info(paths):
    for p in paths:
        meshes, pos, d = read_container(p)
        nf = sum(len(m.faces) for m in meshes)
        nv = sum(len(m.verts) for m in meshes)
        print(f'{os.path.basename(p)}: {len(meshes)} meshes, {nf} faces, {nv} verts, '
              f'{len(d) - pos} bytes after meshes')
        if os.path.splitext(p)[1].upper() == '.BIG':
            cells, records = read_big_secondary(d[pos:])
            print(f'  distinct secondary records {len(records)}, populated coarse cells {len(cells)}')
            for (col, row), refs in cells.items():
                print(f'  cell ({col},{row}) references', ' '.join(hex(ref) for ref in refs))
            for ref, (header, entries) in records.items():
                print(f'  record {ref:#x} header {header.hex()} entries {len(entries)}')
                for entry in entries:
                    print('   ', entry.hex())
        for i, m in enumerate(meshes):
            if m.name:
                xs = [v[0] for v in m.verts]
                ys = [v[1] for v in m.verts]
                zs = [v[2] for v in m.verts]
                print(f'  {i:3} {m.name:8} faces {len(m.faces):3} verts {len(m.verts):3} '
                      f'size x{max(xs) - min(xs)} y{max(ys) - min(ys)} z{max(zs) - min(zs)}')


class ObjWriter:
    def __init__(self, path):
        self.f = open(path, 'w')
        self.mtl = os.path.splitext(path)[0] + '.mtl'
        self.f.write(f'mtllib {os.path.basename(self.mtl)}\n')
        self.base = 1
        self.colours = set()

    def add(self, name, mesh, ox=0, oy=0, oz=0, rot=0, kind='solid'):
        """Write one mesh. (ox, oz) = where its origin is, east and south; oy = the game's
        (downward) y of its origin; rot = quarter turns. kind:

        'solid'   LA.DEF / .SPN: game vertex (x, y, z) -> (x, -y, -z); faces reversed, because
                  the game winds solids clockwise seen from outside and OBJ viewers expect
                  counter-clockwise.
        'figure'  .CSF: same vertex mapping, faces in file order (they already run
                  counter-clockwise seen from the front).
        'ground'  .BIG: the file's z already points south, so (x, -y, z); each face is turned
                  so that its normal points up."""
        f = self.f
        f.write(f'o {name}\n')
        pts = []
        for x, y, z in mesh.verts:
            if kind == 'ground':
                z = -z                      # into the game's frame, as the loader does
            x, z = rot_xz(x, z, rot)
            pts.append((x + ox, -(y + oy), oz - z))
            f.write(f'v {pts[-1][0]} {pts[-1][1]} {pts[-1][2]}\n')
        cur = None
        for col, _, _, idx in mesh.faces:
            if col != cur:
                f.write(f'usemtl pal_{col:03d}\n')
                cur = col
                self.colours.add(col)
            n = len(idx)
            tag = 'f' if n >= 3 else 'l' if n == 2 else 'p'
            if kind == 'solid':
                idx = idx[::-1]
            elif kind == 'ground' and n >= 3:
                # y component of the Newell normal of the face as written
                ny = sum((pts[idx[k]][2] - pts[idx[(k + 1) % n]][2]) * (pts[idx[k]][0] + pts[idx[(k + 1) % n]][0])
                         for k in range(n))
                if ny < 0:
                    idx = idx[::-1]
            f.write(tag + ' ' + ' '.join(str(self.base + i) for i in idx) + '\n')
        self.base += len(mesh.verts)

    def close(self):
        self.f.close()
        with open(self.mtl, 'w') as m:
            for c in sorted(self.colours):
                r, g, b = placeholder_rgb(c)
                m.write(f'newmtl pal_{c:03d}\nKd {r / 255:.3f} {g / 255:.3f} {b / 255:.3f}\n')


EGA16 = [(0, 0, 0), (0, 0, 170), (0, 170, 0), (0, 170, 170), (170, 0, 0), (170, 0, 170), (170, 85, 0),
         (170, 170, 170), (85, 85, 85), (85, 85, 255), (85, 255, 85), (85, 255, 255), (255, 85, 85),
         (255, 85, 255), (255, 255, 85), (255, 255, 255)]


def dither_pair(c):
    """Face colour -> (a, b) EGA colour pair. 0-15 are solid; 16-135 are the 120 two-colour
    dithers, enumerated a = 0..14, b = a+1..15 (table built at 0000:1F50 in the exe)."""
    if c < 16:
        return c, c
    k = c - 16
    for a in range(15):
        n = 15 - a
        if k < n:
            return a, a + 1 + k
        k -= n
    return 0, 0  # out of range; not used by the shipped data


def placeholder_rgb(c):
    """RGB for a face colour: the EGA colour, or the average of the dithered pair.

    The 3D view runs in BIOS mode 0Dh (320x200, 16 colours) with the default palette,
    even on VGA, so these are the true colours."""
    a, b = dither_pair(c)
    return tuple((x + y) // 2 for x, y in zip(EGA16[a], EGA16[b]))


COP_POSE_FOR_DIR = [0, 1, 2, 3, 0, 1, 3, 4]


def pose_names(filename, count):
    """Names for the meshes of a .CSF file, or None if it is not a character file."""
    def civilian(who):
        return [f'{who}_stand_dir{d}' for d in range(8)] +                [f'{who}_walk_dir{d}_f{f}' for d in range(8) for f in range(4)]

    def armed(who):
        return [f'{who}_stand_pose{p}' for p in range(5)] +                [f'{who}_walk_pose{p}_f{f}' for p in range(5) for f in range(4)]

    base = os.path.basename(filename).upper()
    names = {'MANWOM.CSF': civilian('man') + civilian('woman'),
             'COP.CSF': armed('cop'), 'SOL.CSF': armed('soldier'),
             'ENEMIES.CSF': armed('soldier') + armed('cop') + civilian('man') + civilian('woman')}.get(base)
    return names if names and len(names) == count else None


def cmd_obj(src, dst):
    meshes, _, _ = read_container(src)
    poses = pose_names(src, len(meshes))
    ext = os.path.splitext(src)[1].upper()
    kind = 'ground' if ext == '.BIG' else 'figure' if ext == '.CSF' else 'solid'
    w = ObjWriter(dst)
    x = 0
    for i, m in enumerate(meshes):
        xs = [v[0] for v in m.verts] or [0]
        x -= min(xs)
        w.add(f'{i:03d}_{poses[i] if poses else (m.name or "mesh")}', m, ox=x, kind=kind)
        x += max(xs) + 64
    w.close()
    print(f'{dst}: {len(meshes)} meshes')


def cmd_sector(name, dst):
    defs, _, _ = read_container(os.path.join(DATA, 'LA.DEF'))
    bigs, bplace = read_big(os.path.join(DATA, name + '.BIG'))
    w = ObjWriter(dst)
    for n, (x, y, z, idx) in enumerate(bplace):
        w.add(f'big{idx:03d}_{n}', bigs[idx], x, y, z, kind='ground')
    place = read_sct(os.path.join(DATA, name + '.SCT'))
    for n, (x, z, rot, idx) in enumerate(place):
        w.add(f'{defs[idx].name}_{n}', defs[idx], x, 0, z, rot)
    w.close()
    print(f'{dst}: {len(bplace)} unique meshes + {len(place)} LA.DEF objects')


def cmd_map(dst, px_per_sector=1536):
    from PIL import Image, ImageDraw
    defs, _, _ = read_container(os.path.join(DATA, 'LA.DEF'))
    s = px_per_sector / SECTOR
    img = Image.new('RGB', (px_per_sector * 3, px_per_sector * 2), (16, 24, 16))
    dr = ImageDraw.Draw(img)
    for si, name in enumerate(SECTORS):
        ox, oz = (si % 3) * px_per_sector, (si // 3) * px_per_sector
        bigs, bplace = read_big(os.path.join(DATA, name + '.BIG'))
        for x, y, z, idx in bplace:
            m = bigs[idx]
            for col, _, _, vi in m.faces:
                pts = [(ox + (x + m.verts[i][0]) * s, oz + (z + m.verts[i][2]) * s) for i in vi]
                if len(pts) >= 3:
                    dr.polygon(pts, fill=placeholder_rgb(col))
                elif len(pts) == 2:
                    dr.line(pts, fill=placeholder_rgb(col))
                else:
                    dr.point(pts, fill=placeholder_rgb(col))
        for x, z, rot, idx in read_sct(os.path.join(DATA, name + '.SCT')):
            m = defs[idx]
            n = m.name.lower()
            col = ((60, 200, 60) if any(k in n for k in ('tree', 'pine', 'palm', 'shrub')) else
                   (255, 220, 0) if any(k in n for k in ('car', 'van', 'pckup', 'semi', 'bus', 'sport')) else
                   (120, 160, 255) if any(k in n for k in ('light', 'stop', 'yield', 'hydr', 'mail', 'bench', 'turn', 'xrd', 'flag')) else
                   (230, 120, 90))
            xs = [v[0] for v in m.verts]
            zs = [v[2] for v in m.verts]
            c = [rot_xz(a, b, rot) for a, b in ((min(xs), min(zs)), (max(xs), min(zs)), (max(xs), max(zs)), (min(xs), max(zs)))]
            pts = [(ox + (x + a) * s, oz + (z - b) * s) for a, b in c]
            if max(xs) - min(xs) < 80:
                dr.point(pts[0], fill=col)
            else:
                dr.polygon(pts, fill=col)
        dr.rectangle([ox, oz, ox + px_per_sector - 1, oz + px_per_sector - 1], outline=(90, 90, 90))
        dr.text((ox + 6, oz + 4), name, fill=(255, 255, 255))
    img.save(dst)
    print(dst, img.size)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'info':
        cmd_info(a[1:])
    elif a[0] == 'obj':
        cmd_obj(a[1], a[2])
    elif a[0] == 'sector':
        cmd_sector(a[1], a[2])
    elif a[0] == 'map':
        cmd_map(a[1])
    elif a[0] == 'collision':
        from termcollision import export_collision
        meshes, _, _ = read_container(os.path.join(DATA, 'LA.DEF'))
        export_collision(os.path.join(DATA, 'LA.BMP'), meshes, a[1])
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
