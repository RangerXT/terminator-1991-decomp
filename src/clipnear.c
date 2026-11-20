/* Clipping a mesh against the plane of the camera (z = 0), in camera space. */
#include "term.h"

/* Scratch variables of the clipper, at their original offsets. */
enum {
    CLIP_STATE = 0x4B6F,     /* u8: 1 = first vertex of a face, 0 = later ones, FF = closing edge */
    CLIP_PREV = 0x4B72,      /* i16[3]: previous vertex */
    CLIP_FIRST = 0x4B78,     /* i16[3]: first vertex of the face */
    CLIP_NEXT_REF = 0x4B7E,  /* u16: vertex reference (byte offset) for the next new vertex */
    CLIP_FLAG_PTR = 0x4B80,  /* u16: hidden-flag address of the face being clipped */
    CLIP_CUR_REF = 0x4B82,   /* u16: reference of the vertex being processed */
    CLIP_COUNT_PTR = 0x4B84, /* u16: address of the output face's vertex count */
    CLIP_P = 0x4B88,         /* i16[3]: intersection scratch, start point */
    CLIP_Q = 0x4B8E,         /* i16[3]: intersection scratch, end point */
    CLIP_BUSY = 0x4B94,      /* u16: 0x68 while clipping */
    CLIP_OUT_PTR = 0x4BA8,   /* u16: write position in the clipped face list */
    CLIP_TEMP_FACE = 0x4BB0, /* one clipped face is built here first */
    CLIP_FACE_LIST = 0x4E54, /* the clipped face list that replaces the mesh's own */
};

/* orig 0000:2673   in BX = current vertex; previous vertex in CLIP_PREV
 * Point where the edge previous->current crosses z = 0. out AX = x, BX = y, CX = 1 (its z). */
static void clip_intersect(uint8_t *ds, uint16_t cur, int16_t *x, int16_t *y)
{
    DS_I16(ds, CLIP_P + 0) = DS_I16(ds, CLIP_PREV + 0);
    DS_I16(ds, CLIP_P + 2) = DS_I16(ds, CLIP_PREV + 2);
    DS_I16(ds, CLIP_P + 4) = DS_I16(ds, CLIP_PREV + 4);
    DS_I16(ds, CLIP_Q + 0) = DS_I16(ds, cur);
    DS_I16(ds, CLIP_Q + 2) = DS_I16(ds, (uint16_t)(cur + 2));
    DS_I16(ds, CLIP_Q + 4) = DS_I16(ds, (uint16_t)(cur + 4));

    int16_t t = (int16_t)-DS_I16(ds, CLIP_P + 4);
    int16_t dx = (int16_t)(DS_I16(ds, CLIP_Q + 0) - DS_I16(ds, CLIP_P + 0));
    int16_t dy = (int16_t)(DS_I16(ds, CLIP_Q + 2) - DS_I16(ds, CLIP_P + 2));
    int16_t dz = (int16_t)(DS_I16(ds, CLIP_Q + 4) - DS_I16(ds, CLIP_P + 4));
    int16_t nx = (int16_t)(idiv_or_skip((int32_t)t * dx, dz) + DS_I16(ds, CLIP_P + 0));
    DS_I16(ds, CLIP_Q + 0) = nx;
    int16_t ny = (int16_t)(idiv_or_skip((int32_t)t * dy, dz) + DS_I16(ds, CLIP_P + 2));
    *x = nx;
    *y = ny;
}

/* Appends the crossing point as a new vertex and emits a reference to it. */
static void clip_emit_crossing(uint8_t *ds, uint16_t cur, uint16_t *out)
{
    int16_t x, y;
    clip_intersect(ds, cur, &x, &y);
    uint16_t end = DS_U16(ds, DS_VERTEX_BUFFER_END);
    DS_I16(ds, end) = x;
    DS_I16(ds, (uint16_t)(end + 2)) = y;
    DS_I16(ds, (uint16_t)(end + 4)) = 1;
    DS_U16(ds, DS_VERTEX_BUFFER_END) = (uint16_t)(end + 6);
    DS_U16(ds, *out) = DS_U16(ds, CLIP_NEXT_REF);
    *out = (uint16_t)(*out + 2);
    DS_U16(ds, CLIP_NEXT_REF) = (uint16_t)(DS_U16(ds, CLIP_NEXT_REF) + 6);
    DS_U16(ds, DS_U16(ds, CLIP_COUNT_PTR))++;
}

static void clip_emit_current(uint8_t *ds, uint16_t *out)
{
    DS_U16(ds, DS_U16(ds, CLIP_COUNT_PTR))++;
    DS_U16(ds, *out) = DS_U16(ds, CLIP_CUR_REF);
    *out = (uint16_t)(*out + 2);
}

static void copy3(uint8_t *ds, uint16_t dst, uint16_t src)
{
    DS_I16(ds, dst) = DS_I16(ds, src);
    DS_I16(ds, (uint16_t)(dst + 2)) = DS_I16(ds, (uint16_t)(src + 2));
    DS_I16(ds, (uint16_t)(dst + 4)) = DS_I16(ds, (uint16_t)(src + 4));
}

/* orig 0000:25B3   in BX = vertex, DI = output position; state in CLIP_STATE */
static void clip_vertex(uint8_t *ds, uint16_t v, uint16_t *out)
{
    uint8_t state = DS_U8(ds, CLIP_STATE);
    if (state & 0x80) { /* closing edge: last vertex back to first */
        if (((DS_I16(ds, CLIP_FIRST + 4) ^ DS_I16(ds, (uint16_t)(v + 4))) & 0x8000) == 0)
            return;
        copy3(ds, CLIP_PREV, CLIP_FIRST);
        clip_emit_crossing(ds, v, out);
        return;
    }
    if (state != 0) { /* first vertex */
        copy3(ds, CLIP_FIRST, v);
        copy3(ds, CLIP_PREV, v);
        if (DS_I16(ds, (uint16_t)(v + 4)) >= 0)
            clip_emit_current(ds, out);
        return;
    }
    if ((DS_I16(ds, (uint16_t)(v + 4)) ^ DS_I16(ds, CLIP_PREV + 4)) & 0x8000)
        clip_emit_crossing(ds, v, out);
    copy3(ds, CLIP_PREV, v);
    if (DS_I16(ds, (uint16_t)(v + 4)) >= 0)
        clip_emit_current(ds, out);
}

/* orig 0000:2564   in SI = face, DI = where to build the clipped face
 * Returns the clipped face's vertex count (the original returns "zero flag set" for 0). */
static uint16_t clip_face(uint8_t *ds, uint16_t face, uint16_t dst)
{
    DS_U8(ds, CLIP_STATE) = 1;
    DS_U16(ds, dst) = DS_U16(ds, face);
    DS_U16(ds, (uint16_t)(dst + 2)) = DS_U16(ds, (uint16_t)(face + 2));
    uint16_t count = DS_U16(ds, (uint16_t)(face + 4));
    uint16_t count_at = (uint16_t)(dst + 4);
    DS_U16(ds, CLIP_COUNT_PTR) = count_at;
    DS_U16(ds, count_at) = 0;
    uint16_t out = (uint16_t)(dst + 6);
    if (count == 0)
        return 0;
    uint16_t ref_at = (uint16_t)(face + 6);
    uint16_t ref = 0;
    for (uint16_t i = 0; i < count; i++) {
        ref = DS_U16(ds, ref_at);
        ref_at = (uint16_t)(ref_at + 2);
        DS_U16(ds, CLIP_CUR_REF) = ref;
        clip_vertex(ds, (uint16_t)(DS_U16(ds, DS_VERTEX_BUFFER_PTR) + ref), &out);
        DS_U8(ds, CLIP_STATE) = 0;
    }
    DS_U8(ds, CLIP_STATE) = 0xFF;
    DS_U16(ds, CLIP_CUR_REF) = ref; /* the last vertex again */
    clip_vertex(ds, (uint16_t)(DS_U16(ds, DS_VERTEX_BUFFER_PTR) + ref), &out);
    return DS_U16(ds, DS_U16(ds, CLIP_COUNT_PTR));
}

/* orig 0000:24EA   in BX = mesh (working copy in DS)
 *
 * Always records where the 3D vertex buffer ends. If any vertex is behind the camera
 * (DS:4B6E, set by object_transform_vertices) every face is clipped against z = 0:
 * crossing points become new vertices with z = 1 appended to the buffer, faces left with no
 * vertices get their hidden flag set, and the mesh is pointed at the clipped face list.
 */
void mesh_clip_near(uint8_t *ds, uint16_t mesh)
{
    uint16_t bytes = (uint16_t)(DS_U16(ds, (uint16_t)(mesh + 4)) * 6);
    DS_U16(ds, CLIP_NEXT_REF) = bytes;
    DS_U16(ds, DS_VERTEX_BUFFER_END) = (uint16_t)(DS_U16(ds, DS_VERTEX_BUFFER_PTR) + bytes);
    if (DS_U8(ds, DS_ANY_VERT_BEHIND) == 0)
        return;

    DS_U16(ds, CLIP_BUSY) = 0x68;
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 2));
    DS_U16(ds, CLIP_FLAG_PTR) = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    DS_U16(ds, CLIP_OUT_PTR) = CLIP_FACE_LIST;

    do {
        if (clip_face(ds, face, CLIP_TEMP_FACE) == 0)
            DS_U8(ds, DS_U16(ds, CLIP_FLAG_PTR)) = 1;
        /* copy the temporary face to the output list: colour, flags, count, references */
        uint16_t src = CLIP_TEMP_FACE, dst = DS_U16(ds, CLIP_OUT_PTR);
        uint16_t n = DS_U16(ds, (uint16_t)(src + 4));
        for (uint16_t i = 0; i < (uint16_t)(3 + n); i++) {
            DS_U16(ds, dst) = DS_U16(ds, src);
            src = (uint16_t)(src + 2);
            dst = (uint16_t)(dst + 2);
        }
        DS_U16(ds, CLIP_OUT_PTR) = dst;
        face = (uint16_t)(face + 6 + 2 * DS_U16(ds, (uint16_t)(face + 4)));
        DS_U16(ds, CLIP_FLAG_PTR)++;
    } while (--count);

    DS_U16(ds, (uint16_t)(mesh + 6)) = CLIP_FACE_LIST;
    DS_U16(ds, CLIP_BUSY) = 0;
}
