/* Back-face handling for a mesh whose vertices have been projected to the screen. */
#include "term.h"

/* A face in the working copy of a mesh:
 *   +0 u8 colour, +1 u8 second colour, +2 u16 flags, +4 u16 n, +6 u16 vertex_ref[n]
 * vertex_ref is a byte offset (a multiple of 6) into the vertex buffers. */
static uint16_t face_next(const uint8_t *ds, uint16_t face)
{
    return (uint16_t)(face + 6 + 2 * DS_U16(ds, face + 4));
}

/* orig 11BC:161B   in SI = face.  Reverses the order of the face's vertex references. */
void face_reverse_winding(uint8_t *ds, uint16_t face)
{
    uint16_t lo = (uint16_t)(face + 6);
    uint16_t hi = (uint16_t)(lo + 2 * DS_U16(ds, face + 4) - 2);
    do { /* the original swaps once even for a 1-vertex face */
        uint16_t t = DS_U16(ds, hi);
        DS_U16(ds, hi) = DS_U16(ds, lo);
        DS_U16(ds, lo) = t;
        lo = (uint16_t)(lo + 2);
        hi = (uint16_t)(hi - 2);
    } while (lo < hi);
}

/* orig 11BC:157C (far)   in BX = mesh.  Reverses every face and clears its hidden flag;
 * used for objects drawn mirrored (object flag 0x4000). Synthetic whole-mesh tests cover points, lines and polygons. */
void mesh_reverse_all_faces(uint8_t *ds, uint16_t mesh)
{
    uint16_t face = DS_U16(ds, mesh + 6);
    uint16_t count = DS_U16(ds, mesh + 2);
    uint16_t flag = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    do {
        face_reverse_winding(ds, face);
        DS_U8(ds, flag) = 0;
        flag++;
        face = face_next(ds, face);
    } while (--count);
}

/* orig 11BC:163D   in SI = face.  Stores the screen positions of the face's first three
 * vertices in the scratch words at DS:7746.. and returns the edge vectors from vertex 1. */
void face_edge_vectors(uint8_t *ds, uint16_t face, int16_t *x01, int16_t *y01, int16_t *x21, int16_t *y21)
{
    uint16_t pts = DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR);
    uint16_t r;
    r = DS_U16(ds, face + 0x0A); /* vertex 2 */
    DS_I16(ds, 0x774C) = DS_I16(ds, (uint16_t)(r + pts + 2));
    DS_I16(ds, 0x7748) = DS_I16(ds, (uint16_t)(r + pts));
    r = DS_U16(ds, face + 6); /* vertex 0 */
    DS_I16(ds, 0x774A) = DS_I16(ds, (uint16_t)(r + pts + 2));
    DS_I16(ds, 0x7746) = DS_I16(ds, (uint16_t)(r + pts));
    r = DS_U16(ds, face + 8); /* vertex 1 */
    DS_I16(ds, 0x7750) = DS_I16(ds, (uint16_t)(r + pts + 2));
    DS_I16(ds, 0x774E) = DS_I16(ds, (uint16_t)(r + pts));
    *x01 = (int16_t)(DS_I16(ds, 0x7746) - DS_I16(ds, 0x774E));
    *x21 = (int16_t)(DS_I16(ds, 0x7748) - DS_I16(ds, 0x774E));
    *y01 = (int16_t)(DS_I16(ds, 0x774A) - DS_I16(ds, 0x7750));
    *y21 = (int16_t)(DS_I16(ds, 0x774C) - DS_I16(ds, 0x7750));
}

/* orig 11BC:159C (far)   in BX = mesh, AL = see below.
 *
 * Fills the per-face hidden flags (buffer at DS:[40E0]) for faces not already flagged.
 * The mesh's facing table (header word 5) has one byte per face:
 *   0    test the face: hidden = face_is_hidden(v1->v0, v1->v2) on its first three vertices
 *   N    1..7F: copy the flag of face N-1 (coplanar detail shares its parent's result)
 *   FF   two-sided: test it, and if it faces away show it anyway with reversed vertex order
 *
 * Far objects (record flag 0x80) lose their detail: a face with N in 1..7F is then not given
 * its parent's result but whatever is in AL, and that is the low byte of the size of the
 * face before it (2 * its vertex count + 6, left there by the code that steps to the next
 * face), which is practically never zero - so the face is hidden. Only for the very first
 * face is AL what the caller left in it; `al_in` is that value.
 */
void mesh_face_visibility(uint8_t *ds, uint16_t mesh, uint8_t al_in)
{
    uint16_t flags = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    uint16_t table = DS_U16(ds, mesh + 0x0A);
    uint16_t count = DS_U16(ds, mesh + 2);
    uint16_t face = DS_U16(ds, mesh + 6);
    uint16_t index = 0;
    uint8_t al = al_in;

    do {
        if (DS_U8(ds, (uint16_t)(flags + index)) == 0) {
            uint8_t how = DS_U8(ds, table);
            int two_sided = 0, store = 1;
            DS_U8(ds, 0x76DF) = 0;
            if (how != 0 && !(how & 0x80)) {
                if (!(DS_U16(ds, DS_OBJ_FLAGS) & 0x80)) {
                    al = DS_U8(ds, (uint16_t)(flags + (uint8_t)(how - 1)));
                    DS_U8(ds, (uint16_t)(flags + index)) = al;
                    store = 0;
                }
            } else {
                if (how & 0x80) {
                    DS_U8(ds, 0x76DF) = 0xFF;
                    two_sided = 1;
                }
                int16_t x01, y01, x21, y21;
                face_edge_vectors(ds, face, &x01, &y01, &x21, &y21);
                al = face_is_hidden(x01, y01, x21, y21);
            }
            if (store) {
                DS_U8(ds, (uint16_t)(flags + index)) = al;
                if (al != 0 && two_sided) {
                    DS_U8(ds, (uint16_t)(flags + index)) = 0;
                    face_reverse_winding(ds, face);
                }
            }
        }
        al = (uint8_t)(2 * DS_U16(ds, face + 4) + 6); /* AX after stepping over this face */
        face = face_next(ds, face);
        table++;
        index++;
    } while (--count);
}
