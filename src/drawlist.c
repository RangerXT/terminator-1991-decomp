/* The frame level of the renderer: walking a draw list and drawing every record on it. */
#include "term.h"

enum {
    DL_PLAYER = 0x03A0,      /* u16: offset of the player record (x, y, z, heading, head turn..) */
    DL_VEHICLE = 0x04BA,     /* u16: offset of the vehicle record in use; word +6 = its heading */
    DL_MODEL_TABLE = 0x0B30, /* 22-byte records; byte +0 flags, word +6 heading, word +0x14 mesh offset */
    DL_CAMERA_MODE = 0x11CA, /* u8: 0 or 2 (1 is handled by the code but never set) */
    DL_WORK_MESH = 0x50B2,   /* the mesh being drawn is copied here */
    DL_FORCE_REDO = 0x50B0,  /* u8: non-zero = ignore the "already off screen" record flag */
    DL_SCRATCH_X = 0x57D6,
    DL_SCRATCH_Z = 0x57D8,
    DL_RECORD_ID = 0x57C4, /* u16: word +8 of the record: mesh number, or an angle */
    DL_ORDER_BUFFER = 0x57DA,
    DL_RECORD_EXTRA = 0x59E4, /* u16: word +10 of the record */
    DL_MAP_VIEW_Y = 0x59E0,
    DL_STAGE = 0x59E2,
    DL_PLAYER_MESH = 0x72CA, /* u16: mesh number used for the player's own vehicle */
    DL_GROUND_BASE = 0x727E, /* u16: added to ground mesh offsets */
    DL_COLOUR_TABLE = 0x7756,
    DL_MAP_VIEW = 0x7AB6,       /* u8: non-zero while the overhead map view is drawn */
    DL_SEG_MODELS = 0x91CE,     /* u16: segment of the vehicle/character meshes */
    DL_SEG_OBJECTS = 0x91D0,    /* u16: segment of the building meshes (LA.DEF) */
    DL_SEG_GROUND = 0x91D2,     /* u16: segment of the ground meshes (.BIG) */
    DL_OBJECT_OFFSETS = 0x91DA, /* u16[]: offset of each building mesh in its segment */
    DL_GROUND_OFFSETS = 0x92DA, /* u16[]: offset of each ground mesh in its segment */
    DL_SEG_DEBRIS = 0x96DC,     /* u16: segment of the debris tables */
    DL_SPECIAL_ID = 0x9A64,
    DL_TARGET_COUNT = 0xB64E,
    DL_LAST_VEHICLE_A = 0xDE4C,
    DL_LAST_VEHICLE_B = 0xDE4E,
    DL_GUIDED_MESH = 0xE3D2,
    DL_ANY_INSIDE = 0xE5FC,
    DL_DEINDEX_BUFFER = 0xE5FD,
};

static inline uint16_t far_u16(const Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(*far_ptr(g, seg, off) | (*far_ptr(g, seg, (uint16_t)(off + 1)) << 8));
}

/* REP MOVSW from seg:si to DS:di, one word at a time with 16-bit offset wrap. */
static void copy_words(Game *g, uint16_t seg, uint16_t *si, uint16_t *di, uint16_t count)
{
    while (count--) {
        uint16_t w = far_u16(g, seg, *si);
        DS_U8(g->ds, *di) = (uint8_t)w;
        DS_U8(g->ds, (uint16_t)(*di + 1)) = (uint8_t)(w >> 8);
        *si = (uint16_t)(*si + 2);
        *di = (uint16_t)(*di + 2);
    }
}

/* orig 0000:7E28   in BX = 2 * debris number
 *
 * Builds a one-face mesh for a piece of debris from the tables in the debris segment:
 * a 16-byte header at 1900 + 16 * number, a face (colours, flags, count, vertex references)
 * at the offset in header word 3, and vertices at 3580 + reference. The vertices go straight
 * into the vertex buffer and the face's references are renumbered 0, 6, 12, ...
 */
static void debris_fetch(Game *g, uint16_t bx)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DL_SEG_DEBRIS);
    uint16_t header = (uint16_t)(0x1900 + (uint8_t)bx * 8);
    uint16_t si = header, di = DL_WORK_MESH;

    copy_words(g, seg, &si, &di, 8);
    si = far_u16(g, seg, (uint16_t)(header + 6));
    DS_U16(ds, DL_WORK_MESH + 6) = di;
    copy_words(g, seg, &si, &di, 2);
    uint16_t count = far_u16(g, seg, si);
    si = (uint16_t)(si + 2);
    DS_U16(ds, di) = count;
    di = (uint16_t)(di + 2);

    uint16_t offset = 0;
    do { /* LOOP: a count of 0 means 65536 */
        uint16_t ref = far_u16(g, seg, si);
        si = (uint16_t)(si + 2);
        DS_U16(ds, di) = offset;
        di = (uint16_t)(di + 2);
        uint16_t to = (uint16_t)(offset + DS_U16(ds, DS_VERTEX_BUFFER_PTR));
        if (offset == 0)
            DS_U16(ds, DL_WORK_MESH + 8) = to;
        uint16_t from = (uint16_t)(ref + 0x3580);
        copy_words(g, seg, &from, &to, 3);
        offset = (uint16_t)(offset + 6);
    } while (--count);
}

/* orig 0000:2BFF   in BX = mesh number (meaning depends on the record's flags)
 *
 * Copies the mesh a draw record refers to into the work buffer at DS:50B2, turns the
 * offsets in its header into data-segment offsets, and copies its vertices into the vertex
 * buffer. Where the mesh comes from:
 *
 *   flags == 0x100             debris: built from tables (debris_fetch)
 *   0x4000 without 0x20        a model: offset from the 22-byte model record number BX/2
 *   0x20 with 0x04 or 0x4000   a model: BX is the offset itself
 *   0x20 alone                 the player's vehicle mesh (DS:72CA), then as a building
 *   anything else              a building (object pass) or ground mesh (ground pass), by
 *                              number through the offset tables at DS:91DA / DS:92DA
 *
 * It also selects a colour translation table for some of them (DS:7756).
 * Stored meshes are preceded by a word giving their size in bytes.
 */
void mesh_fetch(Game *g, uint16_t bx)
{
    uint8_t *ds = g->ds;
    uint16_t flags = DS_U16(ds, DS_OBJ_FLAGS);
    uint16_t si, seg, di = DL_WORK_MESH;

    if (flags == 0x100) {
        debris_fetch(g, (uint16_t)(bx + bx));
        return;
    }
    if ((flags & 0x4000) && !(flags & 0x20)) {
        uint16_t model = (uint16_t)((uint8_t)(bx >> 1) * 0x16 + DL_MODEL_TABLE);
        si = DS_U16(ds, (uint16_t)(model + 0x14));
        if (DS_U8(ds, model) & 8)
            DS_U16(ds, DL_COLOUR_TABLE) = 0x76E0;
        seg = DS_U16(ds, DL_SEG_MODELS);
    } else if ((flags & 0x20) && (flags & (4 | 0x4000))) {
        if (flags & 4)
            DS_U16(ds, DL_COLOUR_TABLE) = 0x76F0;
        else
            DS_U16(ds, DL_COLOUR_TABLE) = DS_U16(ds, DL_VEHICLE) == 0x508 ? 0x7710 : 0x7700;
        si = bx;
        seg = DS_U16(ds, DL_SEG_MODELS);
    } else {
        if (flags & 0x20)
            bx = DS_U16(ds, DL_PLAYER_MESH);
        if (!DS_U8(ds, DS_GROUND_PASS) && bx == DS_U16(ds, DL_PLAYER_MESH)) {
            /* the player's vehicle: two entries of its colour table depend on the record */
            uint8_t c = DS_U8(ds, (uint16_t)(0x7740 + DS_U8(ds, DL_RECORD_EXTRA + 1)));
            DS_U8(ds, 0x7734) = c;
            DS_U8(ds, 0x773C) = (uint8_t)(c ^ 8);
            DS_U16(ds, DL_COLOUR_TABLE) = 0x7730;
        }
        bx = (uint16_t)(bx + bx);
        if (DS_U8(ds, DS_GROUND_PASS)) {
            si = (uint16_t)(DS_U16(ds, (uint16_t)(bx + DL_GROUND_OFFSETS)) + DS_U16(ds, DL_GROUND_BASE));
            seg = DS_U16(ds, DL_SEG_GROUND);
        } else {
            si = DS_U16(ds, (uint16_t)(bx + DL_OBJECT_OFFSETS));
            seg = DS_U16(ds, DL_SEG_OBJECTS);
        }
    }

    uint16_t size = far_u16(g, seg, si);
    si = (uint16_t)(si + 2);
    copy_words(g, seg, &si, &di, (uint16_t)((uint16_t)(size + 1) >> 1));

    const uint16_t m = DL_WORK_MESH;
    DS_U16(ds, m) += m;
    DS_U16(ds, m + 6) += m;
    DS_U16(ds, DL_ORDER_BUFFER) = DS_U16(ds, m + 6);
    DS_U16(ds, m + 8) += m;
    DS_U16(ds, m + 0x0A) += m;
    DS_U16(ds, m + 0x0E) += m;

    uint16_t from = DS_U16(ds, m + 8), to = DS_U16(ds, DS_VERTEX_BUFFER_PTR);
    copy_words(g, g->ds_seg, &from, &to, (uint16_t)(DS_U16(ds, m + 4) * 3));
    DS_U16(ds, DS_VERTEX_BUFFER_END) = to;
}

/* orig 0000:DA6E and 0000:7921 (the same code twice)   in BX = mesh, angle in AX / DX
 * Turns every vertex in the vertex buffer about the vertical axis. */
static void rotate_vertices(uint8_t *ds, uint16_t mesh, uint16_t angle)
{
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 4));
    uint16_t v = DS_U16(ds, DS_VERTEX_BUFFER_PTR);
    do {
        int16_t x = DS_I16(ds, v), z = DS_I16(ds, (uint16_t)(v + 4));
        rotate_xz_inverse(ds, &x, &z, angle);
        DS_I16(ds, v) = x;
        DS_I16(ds, (uint16_t)(v + 4)) = z;
        v = (uint16_t)(v + 6);
    } while (--count);
}

/* orig 0000:7E86   in AX = debris number, BX = mesh
 * Tumbles a piece of debris: three rotations by the angles in its 20-byte record. */
static void debris_rotate(Game *g, uint16_t mesh, uint16_t number)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DL_SEG_DEBRIS);
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 4));
    uint16_t v = DS_U16(ds, (uint16_t)(mesh + 8));
    uint16_t rec = (uint16_t)(0x960 + (uint8_t)number * 0x14);
    do {
        int16_t a = DS_I16(ds, v), b = DS_I16(ds, (uint16_t)(v + 2)), c = DS_I16(ds, (uint16_t)(v + 4));
        rotate_bc(ds, &b, &c, far_u16(g, seg, (uint16_t)(rec + 0x0E)));
        rotate_xz(ds, &a, &c, far_u16(g, seg, (uint16_t)(rec + 0x10)));
        rotate_ab(ds, &a, &b, far_u16(g, seg, (uint16_t)(rec + 0x12)));
        DS_I16(ds, v) = a;
        DS_I16(ds, (uint16_t)(v + 2)) = b;
        DS_I16(ds, (uint16_t)(v + 4)) = c;
        v = (uint16_t)(v + 6);
    } while (--count);
}

/* orig 0000:285A   in BX = mesh
 * Object pass only: gives objects that have a heading of their own their rotation before
 * the usual transform. Which angle is used depends on the record's flags. */
void mesh_prepare(Game *g, uint16_t mesh)
{
    uint8_t *ds = g->ds;
    uint16_t flags = DS_U16(ds, DS_OBJ_FLAGS);

    if (DS_U8(ds, DS_GROUND_PASS))
        return;
    if (flags & 0x800) {
        rotate_vertices(ds, mesh, DS_U16(ds, DL_RECORD_ID));
    } else if (flags & 0x100) {
        debris_rotate(g, mesh, DS_U16(ds, DL_RECORD_ID));
    } else if (flags & 0x1000) {
        rotate_vertices(ds, mesh, DS_U16(ds, (uint16_t)(DS_U16(ds, DL_VEHICLE) + 6)));
    } else if (flags & 0x2000) {
        DS_U16(ds, DL_COLOUR_TABLE) = 0x7720;
        uint16_t id = DS_U16(ds, DL_RECORD_ID);
        if (id == DS_U16(ds, DL_SPECIAL_ID))
            return;
        uint16_t model = (uint16_t)(DL_MODEL_TABLE + (uint16_t)(0x16 * (uint8_t)(id >> 1)));
        rotate_vertices(ds, DL_WORK_MESH, DS_U16(ds, (uint16_t)(model + 6)));
    } else if ((flags & 0x20) && !(flags & 0x4000)) {
        rotate_vertices(ds, DL_WORK_MESH, DS_U16(ds, (uint16_t)(DS_U16(ds, DL_VEHICLE) + 6)));
    }
}

/* orig 0000:2A99   in BX = mesh
 * For objects that always face the camera (record flag 0x4000: the flat cut-out figures):
 * only the object's position is rotated into camera space, and the vertices are added to
 * it unrotated. Counts the vertices behind the camera. */
void object_translate_only(uint8_t *ds, uint16_t mesh)
{
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 4));
    uint16_t v = DS_U16(ds, DS_VERTEX_BUFFER_PTR);
    int16_t px = (int16_t)(DS_I16(ds, DS_OBJ_X) - DS_I16(ds, DS_CAM_X));
    int16_t pz = (int16_t)(DS_I16(ds, DS_OBJ_Z) - DS_I16(ds, DS_CAM_Z));
    rotate_xz(ds, &px, &pz, DS_U16(ds, DS_CAM_HEADING));
    DS_I16(ds, DL_SCRATCH_X) = px;
    DS_I16(ds, DL_SCRATCH_Z) = pz;

    uint16_t behind = 0;
    do {
        int16_t x = DS_I16(ds, v);
        DS_I16(ds, (uint16_t)(v + 2)) =
            (int16_t)(DS_I16(ds, (uint16_t)(v + 2)) + DS_I16(ds, DS_OBJ_Y) + DS_I16(ds, DS_CAM_Y));
        int16_t z = (int16_t)(DS_I16(ds, (uint16_t)(v + 4)) + DS_I16(ds, DL_SCRATCH_Z));
        if (z < 0)
            behind++;
        DS_I16(ds, v) = (int16_t)(x + DS_I16(ds, DL_SCRATCH_X));
        DS_I16(ds, (uint16_t)(v + 4)) = z;
        v = (uint16_t)(v + 6);
    } while (--count);
    DS_U16(ds, DS_VERTS_BEHIND) = behind;
    DS_U8(ds, DS_ANY_VERT_BEHIND) = (uint8_t)behind;
}

/* ---------------------------------------------------------------- one-face meshes
 * A mesh with a single face (the ground polygons, debris, and anything else flat) skips the
 * general pipeline: no hidden-face table, no ordering, its own transform and projection. */

/* orig 0000:E8B9   make the face's vertices consecutive in the vertex buffer when the face
 * does not use every vertex of the mesh once. (The original copies back twice as many
 * words as it gathered; kept.) */
static void flat_gather_vertices(uint8_t *ds, uint16_t mesh)
{
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    uint16_t n = DS_U16(ds, (uint16_t)(face + 4));
    if (n == DS_U16(ds, (uint16_t)(mesh + 4)))
        return;
    DS_U16(ds, (uint16_t)(mesh + 4)) = n;

    uint16_t buffer = DS_U16(ds, DS_VERTEX_BUFFER_PTR);
    uint16_t ref = (uint16_t)(face + 6), di = DL_DEINDEX_BUFFER, offset = 0, count = n;
    do {
        uint16_t from = (uint16_t)(buffer + DS_U16(ds, ref));
        for (int i = 0; i < 6; i++)
            DS_U8(ds, (uint16_t)(di + i)) = DS_U8(ds, (uint16_t)(from + i));
        di = (uint16_t)(di + 6);
        DS_U16(ds, ref) = offset;
        offset = (uint16_t)(offset + 6);
        ref = (uint16_t)(ref + 2);
    } while (--count);

    uint16_t si = DL_DEINDEX_BUFFER;
    di = buffer;
    for (uint16_t words = (uint16_t)(n * 6); words; words--) {
        uint8_t lo = DS_U8(ds, si), hi = DS_U8(ds, (uint16_t)(si + 1));
        DS_U8(ds, di) = lo;
        DS_U8(ds, (uint16_t)(di + 1)) = hi;
        si = (uint16_t)(si + 2);
        di = (uint16_t)(di + 2);
    }
}

/* orig 0000:E903   out: carry (returned), DH (*far_count)
 * Camera-space transform without quarter turns. Returns 1 if the record is already known to
 * be off screen or every vertex is behind the camera. *far_count = number of vertices with
 * z outside 0..4095 (behind or far away), as a byte. */
static int flat_transform(uint8_t *ds, uint16_t mesh, uint8_t *far_count)
{
    if (!DS_U8(ds, DL_FORCE_REDO) && (DS_U16(ds, DS_OBJ_FLAGS) & 8))
        return 1;
    uint16_t record = DS_U16(ds, DS_DRAW_RECORD);
    DS_U16(ds, (uint16_t)(record + 6)) &= 0xFFF7;

    uint16_t n = DS_U16(ds, (uint16_t)(mesh + 4)), count = n;
    uint16_t v = DS_U16(ds, DS_VERTEX_BUFFER_PTR);
    uint16_t behind = 0;
    uint8_t beyond = 0;
    do {
        DS_I16(ds, (uint16_t)(v + 2)) =
            (int16_t)(DS_I16(ds, (uint16_t)(v + 2)) + (int16_t)(DS_I16(ds, DS_OBJ_Y) + DS_I16(ds, DS_CAM_Y)));
        int16_t x = (int16_t)(DS_I16(ds, v) + DS_I16(ds, DS_OBJ_X) - DS_I16(ds, DS_CAM_X));
        int16_t z = (int16_t)(DS_I16(ds, (uint16_t)(v + 4)) + DS_I16(ds, DS_OBJ_Z) - DS_I16(ds, DS_CAM_Z));
        rotate_xz(ds, &x, &z, DS_U16(ds, DS_CAM_HEADING));
        DS_I16(ds, v) = x;
        DS_I16(ds, (uint16_t)(v + 4)) = z;
        if ((uint16_t)z >= 0x1000)
            beyond++;
        if (z < 0)
            behind++;
        v = (uint16_t)(v + 6);
    } while (--count);
    DS_U8(ds, DS_ANY_VERT_BEHIND) = (uint8_t)behind;
    *far_count = beyond;
    return (uint16_t)(n - 1) < behind;
}

/* orig 0000:E978   out: DH = DS:E5FC (returned)
 * Projects the face's vertices and collects their outcodes. Unlike project_vertices, a
 * screen x that overflows is pinned to +32000 / -32256. Returns 0xFF if some point is
 * inside the view window. */
static int flat_project(uint8_t *ds, uint16_t mesh, uint8_t *any_inside)
{
    DS_U8(ds, DL_ANY_INSIDE) = 0;
    DS_U8(ds, DS_OUTCODE_UNION) = 0;
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 4));
    uint16_t si = DS_U16(ds, DS_VERTEX_BUFFER_PTR), di = DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR);
    uint8_t all = 0;
    do {
        unsigned guard = 0;
        while (DS_I16(ds, (uint16_t)(si + 4)) < 0) { /* vertices behind the camera are skipped */
            si = (uint16_t)(si + 6);
            di = (uint16_t)(di + 6);
            if (++guard > 0x10000)
                return -3; /* the original would never come back */
        }
        int16_t x = DS_I16(ds, si), y = DS_I16(ds, (uint16_t)(si + 2));
        uint16_t depth = (uint16_t)(DS_I16(ds, (uint16_t)(si + 4)) + 0x28);
        si = (uint16_t)(si + 6);
        project_point(ds, &x, &y, depth);

        int32_t wide = (int32_t)x + DS_I16(ds, DS_VIEW_CENTRE_X);
        int16_t sx = (int16_t)wide;
        if (wide != sx)
            sx = (int16_t)(sx < 0 ? 0x7D00 : 0x8200);
        int16_t sy = (int16_t)(y + DS_I16(ds, DS_VIEW_CENTRE_Y));
        DS_I16(ds, di) = sx;
        DS_I16(ds, (uint16_t)(di + 2)) = sy;
        di = (uint16_t)(di + 6);

        uint8_t code = 0;
        if (sx < DS_I16(ds, DS_VIEW_LEFT))
            code |= 1;
        if (sx > DS_I16(ds, DS_VIEW_RIGHT))
            code |= 2;
        if (sy < DS_I16(ds, DS_VIEW_TOP))
            code |= 4;
        if (sy > DS_I16(ds, DS_VIEW_BOTTOM))
            code |= 8;
        all |= code;
        if (code == 0)
            DS_U8(ds, DL_ANY_INSIDE) = 0xFF;
    } while (--count);
    DS_U8(ds, DS_OUTCODE_UNION) = all;
    *any_inside = DS_U8(ds, DL_ANY_INSIDE);
    return 0;
}

/* orig 0000:EA3E   a two-sided face (facing table entry with bit 7) that faces away is
 * turned round so the fill still sees it the right way. */
static void flat_two_sided(uint8_t *ds, uint16_t mesh)
{
    if (!(DS_U8(ds, DS_U16(ds, (uint16_t)(mesh + 0x0A))) & 0x80))
        return;
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    int16_t x01, y01, x21, y21;
    face_edge_vectors(ds, face, &x01, &y01, &x21, &y21);
    if (face_is_hidden(x01, y01, x21, y21))
        face_reverse_winding(ds, face);
}

/* orig 0000:EA68   fill the face, then outline it if face flag bit 1 is set. No colour
 * translation, and the outline is drawn whether or not the fill found anything to draw. */
static void flat_draw(uint8_t *ds, uint8_t *planes, uint16_t mesh)
{
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    DS_U16(ds, DS_FILL_COLOUR) = DS_U16(ds, face);
    uint16_t flags = DS_U16(ds, (uint16_t)(face + 2));
    fill_polygon(ds, planes, (uint16_t)(face + 4));
    if (flags & 2) {
        DS_U8(ds, DS_FILL_COLOUR) = DS_U8(ds, DS_OUTLINE_COLOUR);
        polygon_outline(ds, planes);
    }
}

/* orig 0000:E83E   in BX = mesh.  Returns 0, or -3 where the original would hang. */
int draw_flat_mesh(uint8_t *ds, uint8_t *planes, uint16_t mesh)
{
    uint8_t far_count, any_inside;

    flat_gather_vertices(ds, mesh);
    if (flat_transform(ds, mesh, &far_count)) {
        uint16_t record = DS_U16(ds, DS_DRAW_RECORD);
        DS_U16(ds, (uint16_t)(record + 6)) |= 8;
        return 0;
    }
    if (far_count == DS_U8(ds, (uint16_t)(mesh + 4)))
        return 0;
    mesh_clip_near(ds, mesh);
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    uint16_t n = DS_U16(ds, (uint16_t)(face + 4));
    DS_U16(ds, (uint16_t)(mesh + 4)) = n;
    if (n == 0)
        return 0;
    if (flat_project(ds, mesh, &any_inside))
        return -3;

    if (!DS_U8(ds, DS_GROUND_PASS)) {
        /* Off to one side only and above or below only, with no point inside: not drawn. */
        uint8_t sides = DS_U8(ds, DS_OUTCODE_UNION) & 3, ends = DS_U8(ds, DS_OUTCODE_UNION) & 0x0C;
        if ((sides == 1 || sides == 2) && !any_inside && (ends == 4 || ends == 8))
            return 0;
        flat_two_sided(ds, mesh);
    }
    if (DS_U8(ds, DS_OUTCODE_UNION)) {
        mesh_clip_window(ds, mesh);
        face = DS_U16(ds, (uint16_t)(mesh + 6));
        if (DS_U16(ds, (uint16_t)(face + 4)) == 0)
            return 0;
    }
    flat_draw(ds, planes, mesh);
    return 0;
}

/* ---------------------------------------------------------------- the draw list */

/* orig 0000:2921 (with 0000:2986 and 0000:DAE9)
 * Sets the camera for the list from the player record: position, and heading = body
 * heading + head turn. In the overhead map view the camera sits at the origin instead.
 *
 * Camera mode 1 (a camera following one of four records at DS:10F0) is handled by the
 * original but nothing ever selects it; note that it overwrites SI, the list pointer. */
static void draw_list_camera(uint8_t *ds, uint16_t *si)
{
    if (DS_U8(ds, DL_CAMERA_MODE) == 1) {
        uint16_t e = 0x10F0;
        for (unsigned guard = 0; DS_U16(ds, (uint16_t)(e + 0x10)) == 0 && guard < 0x10000; guard++)
            e = (uint16_t)(e + 0x12);
        *si = e;
        DS_I16(ds, DS_CAM_X) = DS_I16(ds, e);
        DS_I16(ds, DS_CAM_Y) = 0x1E;
        DS_I16(ds, DS_CAM_Z) = DS_I16(ds, (uint16_t)(e + 4));
        uint16_t a = (uint16_t)(((DS_U16(ds, DL_RECORD_ID) + 0x100) & 0x1FF) * 2);
        DS_I16(ds, DS_CAM_X) = (int16_t)(DS_I16(ds, DS_CAM_X) + mul_hi(0x32, DS_I16(ds, (uint16_t)(a + 0x4188))));
        DS_I16(ds, DS_CAM_Z) = (int16_t)(DS_I16(ds, DS_CAM_Z) + mul_hi(0x32, DS_I16(ds, (uint16_t)(a + 0x4288))));
        return;
    }
    if (DS_U8(ds, DL_MAP_VIEW)) {
        DS_U16(ds, DS_CAM_Y) = DS_U16(ds, DL_MAP_VIEW_Y);
        DS_U16(ds, DS_CAM_X) = 0;
        DS_U16(ds, DS_CAM_Z) = 0;
        DS_U16(ds, DS_CAM_HEADING) = 0;
        return;
    }
    uint16_t player = DS_U16(ds, DL_PLAYER);
    DS_U16(ds, DS_CAM_Y) = DS_U16(ds, (uint16_t)(player + 2));
    DS_U16(ds, DS_CAM_X) = DS_U16(ds, player);
    DS_U16(ds, DS_CAM_Z) = DS_U16(ds, (uint16_t)(player + 4));
    DS_U16(ds, DS_CAM_HEADING) =
        (uint16_t)((DS_U16(ds, (uint16_t)(player + 6)) + DS_U16(ds, (uint16_t)(player + 8))) & 0x1FF);
}

/* orig 0000:28E4   in AX = record flags, SI = address of record word 4   out AX
 * Reads the record's id word (into DS:57C4) and decides which mesh number it means. */
uint16_t record_mesh_number(uint8_t *ds, uint16_t flags, uint16_t id_at)
{
    uint16_t id = DS_U16(ds, id_at);
    if (!DS_U8(ds, DS_GROUND_PASS) && (flags & 0x800)) {
        DS_U16(ds, DL_RECORD_ID) = id; /* here the id is an angle */
        return DS_U16(ds, DL_GUIDED_MESH);
    }
    if (flags & 0x2000) {
        DS_U16(ds, DL_RECORD_ID) = id;
        return id == DS_U16(ds, DL_SPECIAL_ID) ? id : DS_U16(ds, DL_PLAYER_MESH);
    }
    if ((flags & 0x20) && !(flags & 0x4000))
        return DS_U16(ds, DL_PLAYER_MESH); /* DS:57C4 keeps its old value */
    DS_U16(ds, DL_RECORD_ID) = id;
    return id;
}

/* orig 0000:271E   in SI = first record, CX = number of records
 *
 * Draws a list of 12-byte records:
 *     +0 x   +2 y   +4 z   +6 flags   +8 id (mesh number or angle)   +10 extra
 * A record is skipped if its extra word is negative, if flag 0x40 is set, or if it is the
 * second kind of vehicle record (0x20 with 0x04) while the player is not in a vehicle.
 * Flag bit 3 (0x08) is written back: set when the object turned out to be off screen.
 * In the object pass y is negated (the records store height upwards).
 *
 * Returns 0; -1 if an untranslated path was needed; -2 or -3 where the original would have
 * stopped or hung.
 */
int draw_object_list(Game *g, uint16_t si, uint16_t count)
{
    uint8_t *ds = g->ds;

    DS_U16(ds, DL_STAGE) = 0xD2;
    DS_U16(ds, DL_TARGET_COUNT) = 0;
    draw_list_camera(ds, &si);

    do {
        uint16_t record = si;
        uint16_t flags = DS_U16(ds, (uint16_t)(record + 6));
        si = (uint16_t)(record + 12);
        DS_U16(ds, DL_STAGE) = 0xD3;

        if (flags & 0x20) {
            if (!(flags & 4)) {
                DS_U16(ds, DL_LAST_VEHICLE_A) = record;
            } else {
                DS_U16(ds, DL_LAST_VEHICLE_B) = record;
                if (!(DS_U8(ds, (uint16_t)(DS_U16(ds, DL_PLAYER) + 0x0E)) & 1))
                    goto next;
            }
        }
        DS_U8(ds, DS_ANY_VERT_BEHIND) = 0;
        if (DS_I16(ds, (uint16_t)(record + 10)) < 0)
            goto next;

        DS_U16(ds, DS_DRAW_RECORD) = record;
        DS_U16(ds, DS_OBJ_X) = DS_U16(ds, record);
        DS_U16(ds, DS_OBJ_Y) = DS_U16(ds, (uint16_t)(record + 2));
        DS_U16(ds, DS_OBJ_Z) = DS_U16(ds, (uint16_t)(record + 4));
        DS_U16(ds, DS_OBJ_FLAGS) = flags;
        if (!DS_U8(ds, DS_GROUND_PASS))
            DS_I16(ds, DS_OBJ_Y) = (int16_t)-DS_I16(ds, DS_OBJ_Y);
        DS_U16(ds, DL_STAGE) = 0xD4;
        uint16_t number = record_mesh_number(ds, flags, (uint16_t)(record + 8));
        DS_U16(ds, DL_RECORD_EXTRA) = DS_U16(ds, (uint16_t)(record + 10));
        if (flags & 0x40)
            goto next;

        DS_U16(ds, DL_STAGE) = 0xD5;
        mesh_fetch(g, number);
        const uint16_t mesh = DL_WORK_MESH;
        if (pipeline_sanity_failed(ds))
            return -2;
        if (!DS_U8(ds, DL_MAP_VIEW) && DS_U16(ds, mesh + 2) == 1) {
            DS_U16(ds, DL_STAGE) = 0xD6;
            if (draw_flat_mesh(ds, g->planes, mesh))
                return -3;
            DS_U16(ds, DL_STAGE) = 0xD7;
            goto next;
        }
        mesh_prepare(g, mesh);
        DS_U16(ds, DL_STAGE) = 0xD8;
        DS_U8(ds, DS_OBJ_QUARTER_TURNS) = (uint8_t)(DS_U8(ds, DS_OBJ_FLAGS) & 3);
        if (DS_U16(ds, DS_OBJ_FLAGS) & 0x4000) {
            DS_U16(ds, DL_STAGE) = 0xD9;
            object_translate_only(ds, mesh);
            if (pipeline_sanity_failed(ds))
                return -2;
            DS_U16(ds, DL_STAGE) = 0xDA;
        } else {
            DS_U16(ds, DL_STAGE) = 0xDB;
            if (object_transform_vertices(ds, mesh))
                return -1;
            if (pipeline_sanity_failed(ds))
                return -2;
            DS_U16(ds, DL_STAGE) = 0xDC;
        }
        if (DS_U16(ds, mesh + 4) == DS_U16(ds, DS_VERTS_BEHIND)) {
            if (DS_U8(ds, DS_GROUND_PASS))
                DS_U16(ds, (uint16_t)(DS_U16(ds, DS_DRAW_RECORD) + 6)) |= 8;
            goto next;
        }
        DS_U16(ds, DL_STAGE) = 0xDD;
        if (draw_object(ds, g->planes, mesh, (uint8_t)g->ds_seg) < 0)
            return -2;
    next:
        DS_U16(ds, DL_COLOUR_TABLE) = 0;
        DS_U16(ds, DL_STAGE) = 0xDE;
    } while (--count);
    return 0;
}
