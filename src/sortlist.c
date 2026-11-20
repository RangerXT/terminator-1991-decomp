/* Ordering the frame's object list: nearest last, with objects that cannot be seen removed.
 *
 * There is no depth buffer, so the order of the list is what makes near objects cover far
 * ones. The original keeps a linked list of 16-byte nodes at DS:C552, one per visible record:
 *
 *    +0 next   +2 screen x of the centre   +4 depth of the centre
 *    +6 left screen x   +8 depth there   +A right screen x   +C depth there   +E record
 *
 * The registers the original juggles are kept as local variables of the same names where
 * the logic depends on what happens to be left in them.
 */
#include "term.h"

enum {
    SL_LIST = 0x1576, /* the unsorted 12-byte records */
    SL_COUNT = 0x50AC,
    SL_PLAYER = 0x03A0,
    SL_ZOOM_A = 0x114D,
    SL_ZOOM_B = 0x114F,
    SL_MIN_DEPTH = 0x5F7E,  /* u16: nearest corner of the current building */
    SL_OTHER_MESH = 0x5EE3, /* u8: a mesh number that never hides anything */
    SL_PLAYER_MESH = 0x72CA,
    SL_HEIGHTS = 0x75EC, /* i16[]: height of each building mesh (negative = up) */
    SL_OBJECT_OFFSETS = 0x91DA,
    SL_SEG_OBJECTS = 0x91D0,
    SL_DETAIL = 0xABCA, /* u16: 0 = draw everything, 1 = nothing beyond 3072, else 2048 */
    SL_ANY_INSIDE = 0xC54B,
    SL_ANY_IN_FRONT = 0xC54C,
    SL_SIDES = 0xC54D, /* bit 0 = a corner right of the window, bit 1 = one left of it */
    SL_TURNS = 0xC54E, /* u8: low byte of the record's flags */
    SL_HEAD = 0xC550,
    SL_NODES = 0xC552,
    SL_OUTPUT_END = 0xDB26, /* the sorted list is written downwards from here */
    SL_NODE = 0xDB32,       /* u16: node being filled */
    SL_CUR = 0xDB34,
    SL_CUR_PREV = 0xDB36,
    SL_OTHER = 0xDB38,
    SL_OTHER_PREV = 0xDB3A,
    SL_POINT_COUNT = 0xDB3C,
    SL_POINT_PTR = 0xDB3E,
    SL_POINTS = 0xDB40, /* (screen x, depth) of up to four corners */
};

static inline uint16_t far_u16(const Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(*far_ptr(g, seg, off) | (*far_ptr(g, seg, (uint16_t)(off + 1)) << 8));
}

/* orig 15AD:034F   in AX = value, CX = depth   out AX, CX
 * value * 256 / depth for sorting purposes: depth halved per active zoom and at least 40.
 * A result with the wrong sign (the divide overflowed and was skipped) becomes +-30000. */
static int16_t sort_project(const uint8_t *ds, int16_t v, uint16_t *depth)
{
    uint16_t cx = *depth;
    if (DS_U8(ds, SL_ZOOM_A))
        cx >>= 1;
    if (DS_U8(ds, SL_ZOOM_B))
        cx >>= 1;
    if (cx < 0x28)
        cx = 0x28;
    *depth = cx;
    /* the same oddly built dividend as the projection proper: v * 256 + (v & 0xFF) */
    int32_t num = (int32_t)(((uint32_t)(v < 0 ? 0xFFu : 0u) << 24) | ((uint32_t)(uint8_t)((uint16_t)v >> 8) << 16)
                            | ((uint32_t)(uint8_t)v << 8) | (uint32_t)(uint8_t)v);
    int16_t q = idiv_or_skip(num, (int16_t)cx);
    if (v < 0) {
        if (q > 0)
            q = (int16_t)0x8AD0;
    } else if (q < 0) {
        q = 0x7530;
    }
    return q;
}

/* orig 15AD:0582   screen x and depth of the record's position, into the node */
static void node_centre(uint8_t *ds, int16_t x, int16_t z)
{
    uint16_t player = DS_U16(ds, SL_PLAYER);
    uint16_t node = DS_U16(ds, SL_NODE);
    x = (int16_t)(x - DS_I16(ds, player));
    z = (int16_t)(z - DS_I16(ds, (uint16_t)(player + 4)));
    /* heading + head turn, not reduced to 0..511 here */
    rotate_xz(ds, &x, &z, (uint16_t)(DS_U16(ds, (uint16_t)(player + 6)) + DS_U16(ds, (uint16_t)(player + 8))));
    if (z < 0) {
        DS_U16(ds, (uint16_t)(node + 4)) = 0;
        DS_I16(ds, (uint16_t)(node + 2)) = x;
        return;
    }
    uint16_t depth = (uint16_t)z;
    int16_t sx = (int16_t)(sort_project(ds, x, &depth) + DS_I16(ds, DS_VIEW_CENTRE_X));
    DS_U16(ds, (uint16_t)(node + 4)) = (uint16_t)(depth - 0x28);
    DS_I16(ds, (uint16_t)(node + 2)) = sx;
}

/* The detail setting hides everything beyond a distance. Returns 1 if `depth` is too far. */
static int beyond_detail_range(const uint8_t *ds, uint16_t depth)
{
    uint16_t detail = DS_U16(ds, SL_DETAIL);
    if (detail == 0)
        return 0;
    return depth >= (detail == 1 ? 0xC00 : 0x800);
}

/* orig 15AD:0426 (with 046C)   a cut-out figure: 24 units to either side of its centre.
 * Returns 1 if it can be seen. */
static int cutout_extent(uint8_t *ds)
{
    uint16_t node = DS_U16(ds, SL_NODE);
    uint16_t depth = DS_U16(ds, (uint16_t)(node + 4));
    int16_t half = sort_project(ds, 0x18, &depth);
    int16_t right = (int16_t)(half + DS_I16(ds, (uint16_t)(node + 2)));
    int16_t left = (int16_t)(DS_I16(ds, (uint16_t)(node + 2)) - half);
    depth = DS_U16(ds, (uint16_t)(node + 4));
    if (right <= DS_I16(ds, DS_VIEW_LEFT) || left >= DS_I16(ds, DS_VIEW_RIGHT))
        return 0;
    DS_I16(ds, (uint16_t)(node + 6)) = left;
    DS_I16(ds, (uint16_t)(node + 0x0A)) = right;
    DS_U16(ds, (uint16_t)(node + 8)) = depth;
    DS_U16(ds, (uint16_t)(node + 0x0C)) = depth;
    return !beyond_detail_range(ds, depth);
}

static void store_point(uint8_t *ds, int16_t x, uint16_t depth)
{
    uint16_t p = DS_U16(ds, SL_POINT_PTR);
    DS_I16(ds, p) = x;
    DS_U16(ds, (uint16_t)(p + 2)) = depth;
    DS_U16(ds, SL_POINT_PTR) = (uint16_t)(p + 4);
    DS_U16(ds, SL_POINT_COUNT)++;
}

/* orig 15AD:024F   in ES:SI = four (x, z) footprint corners of a building mesh
 * Projects the corners that are in front of the camera, pinned to the window's left and
 * right edges. Returns 1 if the footprint can be on screen.
 *
 * Quirk kept: the quarter turn is taken from the whole low byte of the record's flags, so
 * any record with another low flag bit set (0x08, 0x80, ...) is treated as three turns. */
static int footprint_corners(Game *g, uint16_t seg, uint16_t si)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, SL_SIDES) = 0;
    DS_U8(ds, SL_ANY_INSIDE) = 0;
    DS_U8(ds, SL_ANY_IN_FRONT) = 0;
    for (int corner = 0; corner < 4; corner++) {
        int16_t x = (int16_t)far_u16(g, seg, si), z = (int16_t)far_u16(g, seg, (uint16_t)(si + 2));
        si = (uint16_t)(si + 4);
        uint16_t player = DS_U16(ds, SL_PLAYER);
        uint16_t heading =
            (uint16_t)((DS_U16(ds, (uint16_t)(player + 8)) + DS_U16(ds, (uint16_t)(player + 6))) & 0x1FF);
        uint8_t turns = DS_U8(ds, SL_TURNS);
        if (turns == 1) {
            int16_t t = x;
            x = (int16_t)-z;
            z = t;
        } else if (turns == 2) {
            z = (int16_t)-z;
            x = (int16_t)-x;
        } else if (turns != 0) {
            int16_t t = x;
            x = z;
            z = (int16_t)-t;
        }
        x = (int16_t)(x + DS_I16(ds, DS_OBJ_X) - DS_I16(ds, player));
        z = (int16_t)(z + DS_I16(ds, DS_OBJ_Z) - DS_I16(ds, (uint16_t)(player + 4)));
        rotate_xz(ds, &x, &z, heading);
        if (z < 0)
            continue;
        uint16_t depth = (uint16_t)z;
        if (DS_U16(ds, SL_MIN_DEPTH) >= depth)
            DS_U16(ds, SL_MIN_DEPTH) = depth;
        depth = (uint16_t)(depth + 0x1E);
        DS_U8(ds, SL_ANY_IN_FRONT) = 1;
        int16_t sx = (int16_t)(sort_project(ds, x, &depth) + DS_I16(ds, DS_VIEW_CENTRE_X));
        if (sx <= DS_I16(ds, DS_VIEW_LEFT)) {
            DS_U8(ds, SL_SIDES) |= 2;
            store_point(ds, DS_I16(ds, DS_VIEW_LEFT), depth);
        } else if (sx < DS_I16(ds, DS_VIEW_RIGHT)) {
            DS_U8(ds, SL_ANY_INSIDE) = 1;
            store_point(ds, sx, depth);
        } else {
            store_point(ds, DS_I16(ds, DS_VIEW_RIGHT), depth);
            DS_U8(ds, SL_SIDES) |= 1;
        }
    }
    if (DS_U8(ds, SL_ANY_INSIDE) || DS_U8(ds, SL_SIDES) == 3)
        return DS_U8(ds, SL_ANY_IN_FRONT) != 0;
    return 0;
}

/* orig 15AD:0386   leftmost and rightmost stored corner, with their depths, into the node.
 * With fewer than two corners the node keeps whatever it held before. */
static void node_extent_from_points(uint8_t *ds)
{
    uint16_t count = DS_U16(ds, SL_POINT_COUNT);
    if (count <= 1)
        return;
    uint16_t p = SL_POINTS;
    int16_t max_x = (int16_t)0x8300, min_x = 0x7D00;
    uint16_t max_depth = 0, min_depth = 0;
    do {
        if (!(max_x > DS_I16(ds, p))) {
            max_x = DS_I16(ds, p);
            max_depth = DS_U16(ds, (uint16_t)(p + 2));
        }
        if (!(min_x < DS_I16(ds, p))) {
            min_x = DS_I16(ds, p);
            min_depth = DS_U16(ds, (uint16_t)(p + 2));
        }
        p = (uint16_t)(p + 4);
    } while (--count);
    uint16_t node = DS_U16(ds, SL_NODE);
    DS_I16(ds, (uint16_t)(node + 6)) = min_x;
    DS_U16(ds, (uint16_t)(node + 8)) = min_depth;
    DS_I16(ds, (uint16_t)(node + 0x0A)) = max_x;
    DS_U16(ds, (uint16_t)(node + 0x0C)) = max_depth;
}

/* orig 15AD:01FA   in BX = offset of the stored mesh in the building segment
 * A building: its extent comes from the footprint in the mesh (header word 7).
 * Returns 1 if it can be seen. */
static int building_extent(Game *g, uint16_t mesh_at)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, SL_POINT_COUNT) = 0;
    DS_U16(ds, SL_POINT_PTR) = SL_POINTS;
    DS_U16(ds, SL_MIN_DEPTH) = 0xEA60;
    uint16_t seg = DS_U16(ds, SL_SEG_OBJECTS);
    uint16_t corners = (uint16_t)(far_u16(g, seg, (uint16_t)(mesh_at + 0x10)) + 2 + mesh_at);
    if (!footprint_corners(g, seg, corners))
        return 0;
    if (beyond_detail_range(ds, DS_U16(ds, SL_MIN_DEPTH)))
        return 0;
    node_extent_from_points(ds);
    return 1;
}

/* orig 15AD:0049   one node per record that can be seen; the others get record flag 0x40 */
static void build_nodes(Game *g, uint16_t si, uint16_t count)
{
    uint8_t *ds = g->ds;
    if (count >= 0xC8) {
        count = 0xC7;
        DS_U16(ds, SL_COUNT) = count;
    }
    uint16_t di = SL_NODES, bx = 0;
    for (; count; count--) {
        DS_U16(ds, DS_OBJ_X) = DS_U16(ds, si);
        DS_U16(ds, DS_OBJ_Z) = DS_U16(ds, (uint16_t)(si + 4));
        uint16_t flags = DS_U16(ds, (uint16_t)(si + 6));
        DS_U8(ds, SL_TURNS) = (uint8_t)flags;
        uint16_t mesh_at = DS_U16(ds, (uint16_t)((uint16_t)(DS_U16(ds, (uint16_t)(si + 8)) * 2) + SL_OBJECT_OFFSETS));
        DS_U16(ds, SL_NODE) = di;
        DS_U16(ds, (uint16_t)(di + 0x0E)) = si;
        node_centre(ds, DS_I16(ds, si), DS_I16(ds, (uint16_t)(si + 4)));
        int visible = (DS_U16(ds, (uint16_t)(si + 6)) & 0x4000) ? cutout_extent(ds) : building_extent(g, mesh_at);
        if (visible) {
            DS_U16(ds, (uint16_t)(di + 0x0E)) = si;
            bx = di;
            DS_U16(ds, SL_CUR) = bx;
            di = (uint16_t)(di + 0x10);
            DS_U16(ds, bx) = di;
        } else {
            DS_U16(ds, (uint16_t)(si + 6)) |= 0x40;
            bx = di;
            if (count == 1)
                bx = DS_U16(ds, SL_CUR); /* stale if nothing at all was visible */
        }
        si = (uint16_t)(si + 12);
    }
    DS_U16(ds, bx) = 0;
}

/* orig 15AD:00CE   bubble sort of the list by centre depth, nearest first */
static void sort_by_depth(uint8_t *ds)
{
    DS_U16(ds, SL_HEAD) = SL_NODES;
    uint8_t swapped;
    do {
        uint16_t si = DS_U16(ds, SL_HEAD), bx = 0;
        uint8_t index = 0;
        swapped = 0;
        for (;;) {
            uint16_t di = DS_U16(ds, si);
            if (di == 0)
                break;
            if (DS_U16(ds, (uint16_t)(si + 4)) > DS_U16(ds, (uint16_t)(di + 4))) {
                if (index != 0)
                    DS_U16(ds, bx) = di;
                DS_U16(ds, si) = DS_U16(ds, di);
                DS_U16(ds, di) = si;
                swapped = 1;
                if (index == 0)
                    DS_U16(ds, SL_HEAD) = di;
                si = di;
            }
            bx = si;
            si = DS_U16(ds, si);
            index++;
            if (si == 0)
                break;
        }
    } while (swapped);
}

/* orig 15AD:04FA (with 053F)   returns 1 if the node's object never hides others: cut-outs
 * and debris, two special mesh numbers, and meshes whose name starts with "TR" or "PAl"
 * (trees and palms; the first two letters are compared without regard to case). */
static int never_hides(Game *g, uint16_t node)
{
    uint8_t *ds = g->ds;
    uint16_t record = DS_U16(ds, (uint16_t)(node + 0x0E));
    if (DS_U16(ds, (uint16_t)(record + 6)) & 0x4100)
        return 1;
    uint8_t number = DS_U8(ds, (uint16_t)(record + 8));
    if (number == DS_U8(ds, SL_OTHER_MESH) || number == DS_U8(ds, SL_PLAYER_MESH))
        return 1;
    uint16_t seg = DS_U16(ds, SL_SEG_OBJECTS);
    uint16_t mesh =
        (uint16_t)(DS_U16(ds, (uint16_t)((uint16_t)(DS_U16(ds, (uint16_t)(record + 8)) * 2) + SL_OBJECT_OFFSETS)) + 2);
    uint16_t name = (uint16_t)(far_u16(g, seg, mesh) + mesh);
    uint16_t two = far_u16(g, seg, name) & 0xDFDF;
    if (two == 0x5254)
        return 1;
    if (two == 0x4150 && *far_ptr(g, seg, (uint16_t)(name + 2)) == 0x6C)
        return 1;
    return 0;
}

/* orig 15AD:0480   in SI = farther node, DI = nearer node
 * Returns 1, and drops the farther object (record flag 0x40, node record cleared), if the
 * nearer one spans it left to right and rises at least as high on screen. */
static int hidden_behind(Game *g, uint16_t si, uint16_t di)
{
    uint8_t *ds = g->ds;
    if (never_hides(g, di))
        return 0;
    if (DS_I16(ds, (uint16_t)(si + 6)) < DS_I16(ds, (uint16_t)(di + 6)))
        return 0;
    if (DS_I16(ds, (uint16_t)(si + 0x0A)) > DS_I16(ds, (uint16_t)(di + 0x0A)))
        return 0;
    if (DS_U16(ds, (uint16_t)(si + 4)) == 0 || DS_U16(ds, (uint16_t)(di + 4)) == 0)
        return 0;
    uint16_t far_record = DS_U16(ds, (uint16_t)(si + 0x0E));
    uint16_t near_record = DS_U16(ds, (uint16_t)(di + 0x0E));
    uint16_t depth = DS_U16(ds, (uint16_t)(di + 4));
    int16_t near_top = sort_project(
        ds, DS_I16(ds, (uint16_t)((uint16_t)(DS_U16(ds, (uint16_t)(near_record + 8)) * 2) + SL_HEIGHTS)), &depth);
    int16_t height;
    if (DS_U16(ds, (uint16_t)(far_record + 6)) & 0x4000)
        height = -40;
    else
        height = DS_I16(ds, (uint16_t)((uint16_t)(DS_U16(ds, (uint16_t)(far_record + 8)) * 2) + SL_HEIGHTS));
    depth = DS_U16(ds, (uint16_t)(si + 4));
    int16_t far_top = sort_project(ds, height, &depth);
    if (near_top > far_top)
        return 0;
    DS_U16(ds, (uint16_t)(far_record + 6)) |= 0x40;
    DS_U16(ds, (uint16_t)(si + 0x0E)) = 0;
    return 1;
}

/* orig 15AD:01BC   unlink every node that is hidden behind a nearer one.
 * (If the head node were ever removed the original would stop there; it cannot be, since
 * nothing is nearer than the head.) */
static void remove_hidden(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t bx = 0, si = DS_U16(ds, SL_HEAD);
    do {
        uint16_t di = DS_U16(ds, SL_HEAD);
        while (di != 0 && si != di) {
            if (hidden_behind(g, si, di)) {
                if (bx == 0) {
                    DS_U16(ds, SL_HEAD) = DS_U16(ds, si);
                    return;
                }
                DS_U16(ds, bx) = DS_U16(ds, si);
                si = bx;
                break;
            }
            di = DS_U16(ds, di);
        }
        bx = si;
        si = DS_U16(ds, si);
    } while (si != 0);
}

/* orig 15AD:054F   in SI = left/right extent of a node (x, depth, x, depth), AX = x offset
 * from its left end, BX = its smaller depth, CX = depth to compare.
 * Depth of that extent at the given x, by a slope in 1/16 steps; returns 1 (carry) if it is
 * less than CX. (The original shifts the depth difference left after sign-extending it,
 * and a divide that overflows is skipped; both kept.) */
static int extent_nearer_at(const uint8_t *ds, uint16_t extent, int16_t x_offset, uint16_t base, uint16_t depth)
{
    int16_t dd = (int16_t)(DS_U16(ds, (uint16_t)(extent + 6)) - DS_U16(ds, (uint16_t)(extent + 2)));
    int16_t dx = (int16_t)(DS_I16(ds, (uint16_t)(extent + 4)) - DS_I16(ds, extent));
    if (dx == 0)
        dx = 1;
    int32_t dividend = (int32_t)(((uint32_t)(dd < 0 ? 0xFFFFu : 0u) << 16) | (uint16_t)((uint16_t)dd << 4));
    int16_t slope = idiv_or_skip(dividend, dx);
    uint32_t product = (uint32_t)((int32_t)slope * (int32_t)x_offset);
    uint16_t at = (uint16_t)((uint16_t)(product >> 4) + base);
    return at < depth;
}

/* orig 15AD:03C6   in SI, DI = two nodes
 * 3 = they do not overlap on screen (or DI was dropped); 1 = DI is in front of SI;
 * 2 = DI is behind SI. */
static uint8_t compare_nodes(const uint8_t *ds, uint16_t si, uint16_t di)
{
    if (DS_U16(ds, (uint16_t)(di + 0x0E)) == 0)
        return 3;
    if (DS_I16(ds, (uint16_t)(di + 0x0A)) < DS_I16(ds, (uint16_t)(si + 6)))
        return 3;
    if (DS_I16(ds, (uint16_t)(di + 6)) > DS_I16(ds, (uint16_t)(si + 0x0A)))
        return 3;
    uint16_t d_near = DS_U16(ds, (uint16_t)(di + 8)), d_far = DS_U16(ds, (uint16_t)(di + 0x0C));
    if (!(d_near < d_far)) {
        uint16_t t = d_near;
        d_near = d_far;
        d_far = t;
    }
    uint16_t s_near = DS_U16(ds, (uint16_t)(si + 8)), s_far = DS_U16(ds, (uint16_t)(si + 0x0C));
    if (!(s_near < s_far)) {
        uint16_t t = s_near;
        s_near = s_far;
        s_far = t;
    }
    if (d_far < s_near)
        return 1;
    if (d_near >= s_far)
        return 2;
    int16_t x_offset = (int16_t)(DS_I16(ds, (uint16_t)(di + 2)) - DS_I16(ds, (uint16_t)(si + 6)));
    uint16_t base = DS_U16(ds, (uint16_t)(si + 8));
    if (!(base < DS_U16(ds, (uint16_t)(si + 0x0C))))
        base = DS_U16(ds, (uint16_t)(si + 0x0C));
    if (!extent_nearer_at(ds, (uint16_t)(si + 6), x_offset, base, DS_U16(ds, (uint16_t)(di + 4))))
        return 1;
    return 2;
}

/* orig 15AD:014A   one step of the fix-up pass. SI = current node, DI = a later node,
 * BX = the node before SI (0 at the head), DX = the node before DI. */
static void fix_order_step(uint8_t *ds, uint16_t si, uint16_t di, uint16_t bx, uint16_t dx)
{
    for (;;) {
        uint8_t result = compare_nodes(ds, si, di);
        if (result == 2)
            break;
        if (result == 1) {
            /* DI belongs in front of SI: exchange the two nodes' places */
            if (bx != 0)
                DS_U16(ds, bx) = di;
            if (DS_U16(ds, SL_HEAD) == si)
                DS_U16(ds, SL_HEAD) = di;
            uint16_t after_si = DS_U16(ds, si);
            DS_U16(ds, si) = DS_U16(ds, di);
            if (after_si == di) {
                DS_U16(ds, di) = si;
                DS_U16(ds, SL_CUR) = di;
                DS_U16(ds, SL_CUR_PREV) = bx;
                DS_U16(ds, SL_OTHER_PREV) = si;
                DS_U16(ds, SL_OTHER) = DS_U16(ds, si);
            } else {
                DS_U16(ds, di) = after_si;
                DS_U16(ds, SL_CUR_PREV) = bx;
                DS_U16(ds, SL_CUR) = di;
                DS_U16(ds, dx) = si;
                DS_U16(ds, SL_OTHER_PREV) = si;
                DS_U16(ds, SL_OTHER) = DS_U16(ds, si);
            }
            return;
        }
        dx = di;
        di = DS_U16(ds, di);
        if (di == 0)
            break;
    }
    /* nothing later belongs in front of SI: move on to the next node */
    DS_U16(ds, SL_CUR_PREV) = si;
    si = DS_U16(ds, si);
    DS_U16(ds, SL_CUR) = si;
    DS_U16(ds, SL_OTHER_PREV) = si;
    DS_U16(ds, SL_OTHER) = DS_U16(ds, si);
}

/* orig 15AD:010F   centre depth alone orders wide buildings wrongly; walk the list and pull
 * forward any later node that overlaps the current one on screen and is in front of it */
static void fix_order(uint8_t *ds)
{
    DS_U8(ds, 0xC54F) = 0;
    uint16_t si = DS_U16(ds, SL_HEAD);
    DS_U16(ds, SL_CUR) = si;
    si = DS_U16(ds, si);
    DS_U16(ds, SL_OTHER) = si;
    DS_U16(ds, SL_CUR_PREV) = 0;
    DS_U16(ds, SL_OTHER_PREV) = si;
    for (unsigned guard = 0; guard < 1000000; guard++) {
        si = DS_U16(ds, SL_CUR);
        if (si == 0)
            return;
        uint16_t di = DS_U16(ds, SL_OTHER);
        if (di == 0)
            return;
        fix_order_step(ds, si, di, DS_U16(ds, SL_CUR_PREV), DS_U16(ds, SL_OTHER_PREV));
    }
}

/* orig 15AD:001F   write the records out, last node first, so the list ends up farthest
 * first. Returns the offset of the first record. */
static uint16_t write_sorted(uint8_t *ds)
{
    DS_U16(ds, SL_COUNT) = 0;
    uint16_t di = SL_OUTPUT_END, bx = DS_U16(ds, SL_HEAD);
    do {
        uint16_t si = DS_U16(ds, (uint16_t)(bx + 0x0E));
        if (si != 0) {
            for (int i = 0; i < 12; i += 2) {
                uint8_t lo = DS_U8(ds, (uint16_t)(si + i)), hi = DS_U8(ds, (uint16_t)(si + i + 1));
                DS_U8(ds, (uint16_t)(di + i)) = lo;
                DS_U8(ds, (uint16_t)(di + i + 1)) = hi;
            }
            di = (uint16_t)(di - 12);
            DS_U16(ds, SL_COUNT)++;
        }
        bx = DS_U16(ds, bx);
    } while (bx != 0);
    return (uint16_t)(di + 12);
}

/* orig 15AD:0006 (far)   out SI = first record of the sorted list (returned)
 *
 * Takes the frame's object records at DS:1576 (count DS:50AC) and produces the list the
 * renderer draws: records that cannot be seen are dropped (off to the side, behind the
 * camera, beyond the detail range, or hidden behind a nearer building), and the rest are
 * ordered farthest first. DS:50AC becomes the new count.
 */
uint16_t sort_draw_list(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t count = DS_U16(ds, SL_COUNT);
    if (count == 0)
        return SL_LIST;
    build_nodes(g, SL_LIST, count);
    sort_by_depth(ds);
    remove_hidden(g);
    fix_order(ds);
    return write_sorted(ds);
}
