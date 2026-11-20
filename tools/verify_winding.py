"""Executable-backed front-face convention and actual OBJ-writer orientation.
Well-conditioned triangles avoid the original quantized-slope/degenerate ambiguity.
Writes a repeatable evidence artifact without changing the asset exports.
"""
import json, random, tempfile
from pathlib import Path
import dosemu, term3d

def main():
    root = Path(dosemu.ROOT)
    m = dosemu.Machine()
    m.load(root/'out/emu/states/ingame.pkl')
    rng = random.Random(0x168B)
    rows = []
    m.ds_write(0x114D, bytes([0]))
    m.ds_write(0x114F, bytes([0]))
    m.ds_write(0x00BB, bytes([0]))
    with tempfile.TemporaryDirectory(dir=root/'out/verification') as tmp:
        while len(rows) < 256:
            points = [(rng.randrange(-80, 81), rng.randrange(-80, 81), 256) for _ in range(3)]
            projected = []
            for x, y, z in points:
                r = m.call(0, 0x4772, ax=x, bx=y, cx=z+40)
                projected.append(tuple(v if v < 32768 else v-65536 for v in [r['ax'], r['bx']]))
            a, b, c = projected
            area = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(area) < 2000:
                continue
            for kind in ['solid', 'figure']:
                indices = [0, 1, 2] if kind == 'solid' else [2, 1, 0]
                a, b, c = [projected[j] for j in indices]
                r = m.call(0x11BC, 0x168B, ax=a[0]-b[0], bx=a[1]-b[1], cx=c[0]-b[0], dx=c[1]-b[1])
                hidden = r['ax']&255
                source_area = area if kind == 'solid' else -area
                if hidden != (source_area < 0):
                    raise RuntimeError('unexpected source culling sign')
                mesh = term3d.Mesh()
                mesh.verts = points
                mesh.faces = [(1, 0, 1, (0, 1, 2))]
                path = Path(tmp)/'face.obj'
                writer = term3d.ObjWriter(path)
                writer.add('triangle', mesh, kind=kind)
                writer.close()
                vertices = []
                face = None
                for line in path.read_text().splitlines():
                    if line.startswith('v '):
                        vertices.append(tuple(map(float, line.split()[1:])))
                    elif line.startswith('f '):
                        face = [int(s)-1 for s in line.split()[1:]]
                p, q, s = [vertices[j] for j in face]
                u = [q[j]-p[j] for j in range(3)]
                v = [s[j]-p[j] for j in range(3)]
                normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
                view = [-sum(t[j] for t in [p, q, s])/3 for j in range(3)]
                toward = sum(normal[j]*view[j] for j in range(3))
                if (toward > 0) != (not hidden):
                    raise RuntimeError('OBJ facing disagrees with source')
                rows.append(dict(kind=kind, projected_area2=source_area, hidden=hidden, obj_normal_toward_viewer=toward))
    output = dict(scope='256 well-conditioned synthetic triangle cases through original projection/culling and actual ObjWriter; no claim about degenerate/quantized-slope edge cases', screen_axes='x right, y down', source_front='positive signed projected area; clockwise on screen', source_front_cross='(v0-v1) x (v2-v1) is negative', obj_transform='solid/figure vertices (x,-y,-z); determinant +1', obj_solid='face order reversed', obj_figure='file face order; native cut-out drawing reverses file winding', cases=rows)
    (root/'out/verification/obj_winding.json').write_text(json.dumps(output, indent=2))
    print('Original projection/culling and exported OBJ fronts match:', len(rows), 'cases')
if __name__ == '__main__':
    main()
