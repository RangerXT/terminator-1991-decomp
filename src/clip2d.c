/* Clipping a projected mesh against the four edges of the view window. */
#include "term.h"

/* Scratch variables shared with the near-plane clipper, at their original offsets. */
enum {
    C2_STATE = 0x4B6F, /* u8: 1 = first point of a face, 0 = later ones, FF = closing edge */
    C2_PREV_X = 0x4B72,
    C2_PREV_Y = 0x4B74,
    C2_FIRST_X = 0x4B78,
    C2_FIRST_Y = 0x4B7A,
    C2_NEXT_REF = 0x4B7E, /* u16: reference (byte offset) for the next new point */
    C2_FLAG_PTR = 0x4B80,
    C2_CUR_REF = 0x4B82,
    C2_COUNT_PTR = 0x4B84,
    C2_EDGE = 0x4B94,    /* u16: which edge last produced a crossing (1 right, 2 left, 3 top, 4 bottom) */
    C2_PROD_HI = 0x4B96, /* debug copies of the last intersection's operands */
    C2_PROD_LO = 0x4B98,
    C2_OPERAND_A = 0x4B9A,
    C2_OPERAND_B = 0x4B9C,
    C2_CUR_X = 0x4B9E,
    C2_CUR_Y = 0x4BA0,
    C2_OTHER_X = 0x4BA2,
    C2_OTHER_Y = 0x4BA4,
    C2_TOGGLE = 0x4BA6,    /* u16: 0 or 2, selects one of the two work buffers */
    C2_OUT_PTR = 0x4BA8,   /* u16: write position in the clipped face list */
    C2_FACE_PTR = 0x4BAA,  /* u16: where the current version of the face is */
    C2_BUFFERS = 0x4BAC,   /* u16[2]: addresses of the two work buffers */
    C2_FACE_LIST = 0x4BFC, /* the clipped face list that replaces the mesh's own */
};

typedef enum {
    EDGE_RIGHT = 1,
    EDGE_LEFT = 2,
    EDGE_TOP = 3,
    EDGE_BOTTOM = 4
} Edge;

/* orig 0000:2370 (right) and 0000:23CB (left)
 * (ax, bx) = current point, (*cx, *dx) = the other end of the edge.
 * If the edge crosses x = limit, replaces (*cx, *dx) with the crossing point and returns 1.
 * `si` is only recorded in a debug variable. */
static int cross_x(uint8_t *ds, Edge edge, int16_t ax, int16_t bx, int16_t *cx, int16_t *dx, uint16_t si)
{
    int16_t limit = DS_I16(ds, edge == EDGE_RIGHT ? DS_VIEW_RIGHT : DS_VIEW_LEFT);
    if ((((int16_t)(ax - limit)) ^ ((int16_t)(*cx - limit))) >= 0)
        return 0;
    DS_I16(ds, C2_CUR_X) = ax;
    DS_I16(ds, C2_CUR_Y) = bx;
    DS_I16(ds, C2_OTHER_X) = *cx;
    DS_I16(ds, C2_OTHER_Y) = *dx;
    int16_t run = (int16_t)(*cx - ax);
    if (run == 0) {
        /* cannot happen for a real crossing; the left-edge routine even loads the right limit here */
        *dx = bx;
        *cx = DS_I16(ds, DS_VIEW_RIGHT);
        return 1;
    }
    int16_t rise = (int16_t)(*dx - bx);
    int32_t prod = (int32_t)(int16_t)(limit - ax) * rise;
    DS_U16(ds, C2_PROD_HI) = (uint16_t)((uint32_t)prod >> 16);
    DS_U16(ds, C2_PROD_LO) = (uint16_t)prod;
    DS_I16(ds, C2_OPERAND_A) = run;
    DS_U16(ds, C2_OPERAND_B) = si;
    DS_U16(ds, C2_EDGE) = (uint16_t)edge;
    *dx = (int16_t)(bx + idiv_or_skip(prod, run));
    *cx = limit;
    return 1;
}

/* orig 0000:2426 (top) and 0000:2488 (bottom): the same for a horizontal limit. */
static int cross_y(uint8_t *ds, Edge edge, int16_t ax, int16_t bx, int16_t *cx, int16_t *dx)
{
    int16_t limit = DS_I16(ds, edge == EDGE_TOP ? DS_VIEW_TOP : DS_VIEW_BOTTOM);
    if ((((int16_t)(bx - limit)) ^ ((int16_t)(*dx - limit))) >= 0)
        return 0;
    DS_I16(ds, C2_CUR_X) = ax;
    DS_I16(ds, C2_CUR_Y) = bx;
    DS_I16(ds, C2_OTHER_X) = *cx;
    DS_I16(ds, C2_OTHER_Y) = *dx;
    int16_t rise = (int16_t)(*dx - bx);
    if (rise == 0) {
        *cx = ax;
        *dx = limit;
        return 1;
    }
    int32_t prod = (int32_t)(int16_t)(*cx - ax) * (int16_t)(limit - bx);
    DS_U16(ds, C2_PROD_HI) = (uint16_t)((uint32_t)prod >> 16);
    DS_U16(ds, C2_PROD_LO) = (uint16_t)prod;
    DS_I16(ds, C2_OPERAND_A) = *cx;
    DS_I16(ds, C2_OPERAND_B) = rise;
    DS_U16(ds, C2_EDGE) = (uint16_t)edge;
    *cx = (int16_t)(ax + idiv_or_skip(prod, rise));
    *dx = limit;
    return 1;
}

static int inside(const uint8_t *ds, Edge edge, int16_t x, int16_t y)
{
    switch (edge) {
    case EDGE_RIGHT:
        return x <= DS_I16(ds, DS_VIEW_RIGHT);
    case EDGE_LEFT:
        return x >= DS_I16(ds, DS_VIEW_LEFT);
    case EDGE_TOP:
        return y >= DS_I16(ds, DS_VIEW_TOP);
    default:
        return y <= DS_I16(ds, DS_VIEW_BOTTOM);
    }
}

/* Appends a crossing point to the 2D point buffer (only x and y are written; the third word
 * of the slot keeps whatever was there) and emits a reference to it. */
static void emit_new_point(uint8_t *ds, int16_t x, int16_t y, uint16_t *out)
{
    uint16_t end = DS_U16(ds, DS_VERTEX_BUFFER_END);
    DS_I16(ds, end) = x;
    DS_I16(ds, (uint16_t)(end + 2)) = y;
    DS_U16(ds, DS_VERTEX_BUFFER_END) = (uint16_t)(end + 6);
    DS_U16(ds, *out) = DS_U16(ds, C2_NEXT_REF);
    *out = (uint16_t)(*out + 2);
    DS_U16(ds, C2_NEXT_REF) = (uint16_t)(DS_U16(ds, C2_NEXT_REF) + 6);
    DS_U16(ds, DS_U16(ds, C2_COUNT_PTR))++;
}

static void emit_current(uint8_t *ds, uint16_t *out)
{
    DS_U16(ds, DS_U16(ds, C2_COUNT_PTR))++;
    DS_U16(ds, *out) = DS_U16(ds, C2_CUR_REF);
    *out = (uint16_t)(*out + 2);
}

/* orig 0000:20DC / 2181 / 2226 / 22CB   one point of a face against one edge */
static void stage_point(uint8_t *ds, Edge edge, int16_t x, int16_t y, uint16_t si, uint16_t *out)
{
    uint8_t state = DS_U8(ds, C2_STATE);
    int16_t cx, dx;
    int crossed;
    if (state & 0x80) { /* closing edge: last point back to first */
        cx = DS_I16(ds, C2_FIRST_X);
        dx = DS_I16(ds, C2_FIRST_Y);
        crossed = (edge == EDGE_RIGHT || edge == EDGE_LEFT) ? cross_x(ds, edge, x, y, &cx, &dx, si)
                                                            : cross_y(ds, edge, x, y, &cx, &dx);
        if (crossed)
            emit_new_point(ds, cx, dx, out);
        return;
    }
    if (state != 0) { /* first point */
        DS_I16(ds, C2_FIRST_X) = x;
        DS_I16(ds, C2_FIRST_Y) = y;
        DS_I16(ds, C2_PREV_X) = x;
        DS_I16(ds, C2_PREV_Y) = y;
        if (inside(ds, edge, x, y))
            emit_current(ds, out);
        return;
    }
    cx = DS_I16(ds, C2_PREV_X);
    dx = DS_I16(ds, C2_PREV_Y);
    crossed = (edge == EDGE_RIGHT || edge == EDGE_LEFT) ? cross_x(ds, edge, x, y, &cx, &dx, si)
                                                        : cross_y(ds, edge, x, y, &cx, &dx);
    if (crossed)
        emit_new_point(ds, cx, dx, out);
    DS_I16(ds, C2_PREV_X) = x;
    DS_I16(ds, C2_PREV_Y) = y;
    if (inside(ds, edge, x, y))
        emit_current(ds, out);
}

/* orig 0000:208F   clips the face at `src` against one edge into `dst` */
static void clip_face_edge(uint8_t *ds, Edge edge, uint16_t src, uint16_t dst)
{
    DS_U8(ds, C2_STATE) = 1;
    DS_U16(ds, dst) = DS_U16(ds, src);
    DS_U16(ds, (uint16_t)(dst + 2)) = DS_U16(ds, (uint16_t)(src + 2));
    uint16_t count_at = (uint16_t)(dst + 4);
    DS_U16(ds, C2_COUNT_PTR) = count_at;
    DS_U16(ds, count_at) = 0;
    uint16_t out = (uint16_t)(dst + 6);
    uint16_t count = DS_U16(ds, (uint16_t)(src + 4));
    if (count == 0)
        return;
    uint16_t ref_at = (uint16_t)(src + 6);
    uint16_t ref = 0, p;
    for (uint16_t i = 0; i < count; i++) {
        ref = DS_U16(ds, ref_at);
        ref_at = (uint16_t)(ref_at + 2);
        DS_U16(ds, C2_CUR_REF) = ref;
        p = (uint16_t)(ref + DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR));
        stage_point(ds, edge, DS_I16(ds, p), DS_I16(ds, (uint16_t)(p + 2)), ref_at, &out);
        DS_U8(ds, C2_STATE) = 0;
    }
    DS_U8(ds, C2_STATE) = 0xFF;
    DS_U16(ds, C2_CUR_REF) = ref;
    p = (uint16_t)(ref + DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR));
    stage_point(ds, edge, DS_I16(ds, p), DS_I16(ds, (uint16_t)(p + 2)), ref_at, &out);
}

/* orig 0000:1FFE   clips the face at DS:[4BAA] against every edge some point lies beyond,
 * ping-ponging between two work buffers. Returns the resulting vertex count. */
static uint16_t clip_face_window(uint8_t *ds)
{
    static const struct {
        uint8_t bit;
        Edge edge;
    } order[4] = {{2, EDGE_RIGHT}, {1, EDGE_LEFT}, {4, EDGE_TOP}, {8, EDGE_BOTTOM}};
    for (int i = 0; i < 4; i++) {
        if (DS_U8(ds, DS_OUTCODE_UNION) & order[i].bit) {
            DS_U16(ds, C2_TOGGLE) ^= 2;
            uint16_t dst = DS_U16(ds, (uint16_t)(C2_BUFFERS + DS_U16(ds, C2_TOGGLE)));
            uint16_t src = DS_U16(ds, C2_FACE_PTR);
            DS_U16(ds, C2_FACE_PTR) = dst;
            clip_face_edge(ds, order[i].edge, src, dst);
        }
    }
    return DS_U16(ds, DS_U16(ds, C2_COUNT_PTR));
}

/* orig 0000:1F6A   in BX = mesh (working copy in DS)
 *
 * If any projected point lies outside the view window (DS:4B70, set by project_vertices),
 * clips every face to the window with a Sutherland-Hodgman pass per edge. Crossing points
 * are appended to the 2D point buffer; faces left with no vertices get their hidden flag
 * set; the mesh is pointed at the clipped face list.
 */
void mesh_clip_window(uint8_t *ds, uint16_t mesh)
{
    if (DS_U8(ds, DS_OUTCODE_UNION) == 0)
        return;
    DS_U16(ds, C2_EDGE) = 0;
    uint16_t bytes = DS_U16(ds, C2_NEXT_REF);
    if (DS_U8(ds, DS_ANY_VERT_BEHIND) == 0) {
        bytes = (uint16_t)(DS_U16(ds, (uint16_t)(mesh + 4)) * 6);
        DS_U16(ds, C2_NEXT_REF) = bytes;
    }
    DS_U16(ds, DS_VERTEX_BUFFER_END) = (uint16_t)(DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR) + bytes);

    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 2));
    DS_U16(ds, C2_FLAG_PTR) = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    DS_U16(ds, C2_OUT_PTR) = C2_FACE_LIST;

    do {
        DS_U16(ds, C2_TOGGLE) = 0;
        DS_U16(ds, C2_FACE_PTR) = face;
        if (clip_face_window(ds) == 0)
            DS_U8(ds, DS_U16(ds, C2_FLAG_PTR)) = 1;
        /* orig 0000:1FE9: copy the final version of the face to the output list */
        uint16_t src = DS_U16(ds, C2_FACE_PTR), dst = DS_U16(ds, C2_OUT_PTR);
        uint16_t n = DS_U16(ds, (uint16_t)(src + 4));
        for (uint16_t i = 0; i < (uint16_t)(3 + n); i++) {
            DS_U16(ds, dst) = DS_U16(ds, src);
            src = (uint16_t)(src + 2);
            dst = (uint16_t)(dst + 2);
        }
        DS_U16(ds, C2_OUT_PTR) = dst;
        face = (uint16_t)(face + 6 + 2 * DS_U16(ds, (uint16_t)(face + 4)));
        DS_U16(ds, C2_FLAG_PTR)++;
    } while (--count);

    DS_U16(ds, (uint16_t)(mesh + 6)) = C2_FACE_LIST;
    DS_U16(ds, C2_EDGE) = 0;
}
