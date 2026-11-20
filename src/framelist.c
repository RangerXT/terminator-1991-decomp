/* Collecting everything that is to be drawn this frame into one list of object records. */
#include "term.h"

enum {
    FL_LIST = 0x1576,
    FL_COUNT = 0x50AC,
    FL_COUNT_BEFORE_SORT = 0x020E,
    FL_LIST_PTR = 0x01FE,
    FL_WRITE_PTR = 0x9156,
    FL_PLAYER = 0x03A0,
    FL_VEHICLE = 0x04BA,
    FL_VISIBLE = 0x5F80,
    FL_VISIBLE_COUNT = 0x7240,
    FL_SPECIAL_ID = 0x9A64, /* u16: mesh number shared by pickups and the timed object */
    FL_MESH_NUMBERS = 0x72CA,
    FL_SEG_DEBRIS = 0x96DC,
};

static inline uint16_t far_u16(const Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(*far_ptr(g, seg, off) | (*far_ptr(g, seg, (uint16_t)(off + 1)) << 8));
}

/* Append one record at the write pointer and count it. */
static void append(uint8_t *ds, uint16_t x, uint16_t y, uint16_t z, uint16_t flags, uint16_t id, uint16_t extra)
{
    uint16_t di = DS_U16(ds, FL_WRITE_PTR);
    DS_U16(ds, di) = x;
    DS_U16(ds, (uint16_t)(di + 2)) = y;
    DS_U16(ds, (uint16_t)(di + 4)) = z;
    DS_U16(ds, (uint16_t)(di + 6)) = flags;
    DS_U16(ds, (uint16_t)(di + 8)) = id;
    DS_U16(ds, (uint16_t)(di + 10)) = extra;
    DS_U16(ds, FL_WRITE_PTR) = (uint16_t)(di + 12);
    DS_U16(ds, FL_COUNT)++;
}

/* REP MOVSW of `words` words from seg:si to the write pointer (not counted). */
static void append_block(Game *g, uint16_t seg, uint16_t si, uint16_t words)
{
    uint8_t *ds = g->ds;
    uint16_t di = DS_U16(ds, FL_WRITE_PTR);
    for (; words; words--) {
        uint16_t w = far_u16(g, seg, si);
        DS_U8(ds, di) = (uint8_t)w;
        DS_U8(ds, (uint16_t)(di + 1)) = (uint8_t)(w >> 8);
        si = (uint16_t)(si + 2);
        di = (uint16_t)(di + 2);
    }
    DS_U16(ds, FL_WRITE_PTR) = di;
}

/* orig 0000:5E62   in AX,BX = point A (x, z), CX,DX = point B   out AX = 0..511
 * Direction between two points as a heading, by linear interpolation inside each octant
 * (64 * smaller difference / larger difference) instead of an arctangent. */
uint16_t angle_between(uint8_t *ds, int16_t ax_, int16_t az, int16_t bx_, int16_t bz)
{
    int16_t dx = (int16_t)(ax_ - bx_), dz = (int16_t)(az - bz);
    int x_not_negative = dx >= 0, z_not_negative = dz >= 0;
    uint16_t ux = (uint16_t)(dx < 0 ? -dx : dx), uz = (uint16_t)(dz < 0 ? -dz : dz);
    uint16_t a;
    if (ux < uz) {
        a = (uint16_t)(((uint32_t)ux << 6) / uz);
    } else {
        a = (uint16_t)(((uint32_t)uz << 6) / (ux ? ux : 1));
        a = (uint16_t)(0x80 - a);
    }
    if (z_not_negative)
        a = (uint16_t)(0x100 - a);
    if (x_not_negative)
        a = (uint16_t)(0x200 - a);
    DS_U16(ds, 0x4B94) = 0;
    return a & 0x1FF;
}

/* orig 0000:D9FB (with DA96)   the up to [11A0] guided projectiles (missiles), 18-byte
 * entries at DS:10F0. An active one gives a record with flag 0x0800, its heading as id
 * and y = 30; the mesh is the one in DS:E3D2.
 * Quirk kept: the count is raised by the number of entries, active or not. */
static void append_guided_projectiles(uint8_t *ds)
{
    uint16_t count = DS_U16(ds, DS_GUIDED_COUNT);
    if (count == 0)
        return;
    DS_U16(ds, FL_COUNT) = (uint16_t)(DS_U16(ds, FL_COUNT) + count);
    uint16_t si = 0x10F0;
    for (; count; count--, si = (uint16_t)(si + 0x12)) {
        if (DS_U16(ds, (uint16_t)(si + 0x10)) == 0)
            continue;
        DS_U16(ds, 0xE3D4) = DS_U16(ds, si);
        DS_U16(ds, 0xE3D6) = 0x1E;
        DS_U16(ds, 0xE3D8) = DS_U16(ds, (uint16_t)(si + 4));
        DS_U16(ds, 0xE3DA) = 0x800;
        DS_U16(ds, 0xE3DC) = DS_U16(ds, (uint16_t)(si + 6));
        DS_U16(ds, 0xE3DE) = 0x64;
        uint16_t di = DS_U16(ds, FL_WRITE_PTR);
        for (int i = 0; i < 12; i++)
            DS_U8(ds, (uint16_t)(di + i)) = DS_U8(ds, (uint16_t)(0xE3D4 + i));
        DS_U16(ds, FL_WRITE_PTR) = (uint16_t)(di + 12);
    }
}

/* orig 0000:87FC (with 88A3, 881F)   20 entries of 13 bytes at DS:0253: map column, row,
 * x and z inside the cell, ..., an "in use" byte at +10. One that is in the player's cell or
 * a neighbouring one gives a record with the special mesh. (The original also measures the
 * distance to the player here; the result only decides which of two equivalent paths
 * advances to the next entry.) */
static void append_pickups(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, FL_PLAYER);
    uint16_t si = 0x253;
    for (int n = 0; n < 0x14; n++, si = (uint16_t)(si + 0x0D)) {
        if (DS_U8(ds, (uint16_t)(si + 0x0A)) == 0)
            continue;
        int16_t d = (int16_t)(DS_U16(ds, si) - DS_U16(ds, (uint16_t)(player + 0x1E)));
        if (d == 0) {
            DS_U16(ds, 0x9A5C) = 0;
        } else {
            DS_U16(ds, 0x9A5C) = 0x400;
            if (d < 0) {
                d = (int16_t)-d;
                DS_U16(ds, 0x9A5C) = 0xFC00;
            }
            if ((uint16_t)d > 1)
                continue;
        }
        d = (int16_t)(DS_U16(ds, (uint16_t)(si + 2)) - DS_U16(ds, (uint16_t)(player + 0x20)));
        if (d == 0) {
            DS_U16(ds, 0x9A5E) = 0;
        } else {
            DS_U16(ds, 0x9A5E) = 0xFC00;
            if (d < 0) {
                d = (int16_t)-d;
                DS_U16(ds, 0x9A5E) = 0x400;
            }
            if ((uint16_t)d > 1)
                continue;
        }
        DS_U16(ds, 0x9A5C) = (uint16_t)(DS_U16(ds, 0x9A5C) + DS_U16(ds, (uint16_t)(si + 4)));
        DS_U16(ds, 0x9A5E) = (uint16_t)(DS_U16(ds, 0x9A5E) + DS_U16(ds, (uint16_t)(si + 6)));
        append(ds, DS_U16(ds, 0x9A5C), 0, DS_U16(ds, 0x9A5E), 0, DS_U16(ds, FL_SPECIAL_ID), 0);
    }
}

/* orig 0000:9FB2   30 entries of 10 bytes at DS:B520 (x, y, z, state, extra): things in
 * flight. One that has got 4096 or more away from the player is switched off (state FFFF);
 * the others give a record with the mesh number in DS:B51E. */
static void append_projectiles(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, FL_PLAYER);
    uint16_t si = 0xB520;
    for (int n = 0; n < 0x1E; n++, si = (uint16_t)(si + 0x0A)) {
        if (DS_U16(ds, (uint16_t)(si + 6)) & 0x8000)
            continue;
        int16_t d = (int16_t)approx_distance(DS_I16(ds, si), DS_I16(ds, (uint16_t)(si + 4)), DS_I16(ds, player),
                                             DS_I16(ds, (uint16_t)(player + 4)));
        if (d < 0x1000)
            append(ds, DS_U16(ds, si), DS_U16(ds, (uint16_t)(si + 2)), DS_U16(ds, (uint16_t)(si + 4)), 0,
                   DS_U16(ds, 0xB51E), DS_U16(ds, (uint16_t)(si + 8)));
        else
            DS_U16(ds, (uint16_t)(si + 6)) = 0xFFFF;
    }
}

/* orig 0000:BE47   in SI = a moving thing's record, DI = its 8-byte animation record
 * Stores the direction from the player to it, and how many frames each walk step lasts. */
static void animation_bearing(uint8_t *ds, uint16_t si, uint16_t di)
{
    DS_U8(ds, (uint16_t)(di + 3)) = DS_U16(ds, (uint16_t)(si + 0x0A)) == 3 ? 4 : 3;
    uint16_t player = DS_U16(ds, FL_PLAYER);
    DS_U16(ds, di) = angle_between(ds, DS_I16(ds, si), DS_I16(ds, (uint16_t)(si + 4)), DS_I16(ds, player),
                                   DS_I16(ds, (uint16_t)(player + 4)));
}

/* The walk cycle of an animation record: every [di+3] frames the step advances by 2, mod 8.
 * `whole_word` = the original masks the whole word (BECE) rather than its low byte (BE68). */
static void animation_step(uint8_t *ds, uint16_t di, int whole_word)
{
    if (--DS_U8(ds, (uint16_t)(di + 2)) != 0)
        return;
    DS_U8(ds, (uint16_t)(di + 2)) = DS_U8(ds, (uint16_t)(di + 3));
    uint16_t step = (uint16_t)(DS_U16(ds, (uint16_t)(di + 4)) + 2);
    DS_U16(ds, (uint16_t)(di + 4)) = whole_word ? (uint16_t)(step & 7) : (uint16_t)((step & 0xFF00) | (step & 7));
}

/* Which of 8 directions the thing is seen from: its own heading against the bearing. */
static uint16_t seen_from(const uint8_t *ds, uint16_t si, uint16_t di)
{
    uint16_t turn = (uint16_t)(((uint16_t)(DS_U16(ds, di) - DS_U16(ds, (uint16_t)(si + 6))) & 0x1FF) >> 6);
    return (uint16_t)((8 - turn) & 7);
}

/* orig 0000:BE68   out AX = mesh for the figure, also stored at [di+6]
 * A figure with 5 poses for the 8 directions (3..5 go through the table at DS:B69A, 6 and 7
 * reuse 3 and 4); standing meshes first in the table at DS:B8D0, then 4 walk frames each. */
static uint16_t figure_mesh_5(uint8_t *ds, uint16_t si, uint16_t di)
{
    uint16_t bx = seen_from(ds, si, di);
    if (bx > 2) {
        if (bx >= 6)
            bx = (uint16_t)(bx - 3);
        else
            bx = DS_U8(ds, (uint16_t)(bx - 3 + 0xB69A));
    }
    bx = (uint16_t)(bx + bx);
    if (DS_U16(ds, (uint16_t)(si + 0x0A)) != 0) {
        bx = (uint16_t)(bx * 4 + 0x0A);
        animation_step(ds, di, 0);
        bx = (uint16_t)(bx + DS_U16(ds, (uint16_t)(di + 4)));
    }
    uint16_t mesh = DS_U16(ds, (uint16_t)(bx + 0xB8D0));
    DS_U16(ds, (uint16_t)(di + 6)) = mesh;
    return mesh;
}

/* orig 0000:BECE   the same for a figure with a mesh for each of the 8 directions; BP = its
 * table (8 standing meshes, then 4 walk frames per direction) */
static uint16_t figure_mesh_8(uint8_t *ds, uint16_t si, uint16_t di, uint16_t table)
{
    uint16_t bx = (uint16_t)(seen_from(ds, si, di) * 2);
    if (DS_U16(ds, (uint16_t)(si + 0x0A)) != 0) {
        bx = (uint16_t)(bx * 4 + 0x10);
        animation_step(ds, di, 1);
        bx = (uint16_t)(bx + DS_U16(ds, (uint16_t)(di + 4)));
    }
    uint16_t mesh = DS_U16(ds, (uint16_t)(bx + table));
    DS_U16(ds, (uint16_t)(di + 6)) = mesh;
    return mesh;
}

/* orig 0000:BD64   the opponent (and what it rides in) and the companion.
 * With the opponent in the scene (DS:1153): at its position DS:DE52/DE54 either a vehicle
 * (flags 1020, mesh from the list at DS:72CA) or, in a single-player game or when the
 * vehicle record says so, a figure (flags 4020) with the mesh picked for its direction and
 * walk step. With the companion in the scene (DS:1154, and some further conditions) a
 * figure at the companion's position DS:E3EC/E3EE with flags 4024. */
static void append_opponent_and_companion(uint8_t *ds)
{
    if (DS_U8(ds, DS_PRACTICE_MODE))
        return;
    int second_figure_forced = 0;
    if (DS_U8(ds, DS_OPPONENT_ACTIVE)) {
        if (DS_U8(ds, 0x1152)) {
            DS_U16(ds, DS_COMPANION_X) = DS_U16(ds, DS_OPPONENT_X);
            DS_U16(ds, DS_COMPANION_Z) = DS_U16(ds, DS_OPPONENT_Z);
            second_figure_forced = 1;
        } else {
            uint16_t vehicle = DS_U16(ds, FL_VEHICLE);
            if (DS_U8(ds, DS_LINK_GAME) && !(DS_U8(ds, (uint16_t)(vehicle + 0x0E)) & 1)) {
                append(ds, DS_U16(ds, DS_OPPONENT_X), 0, DS_U16(ds, DS_OPPONENT_Z), 0x1020,
                       DS_U16(ds, (uint16_t)(DS_U16(ds, 0xAF86) + FL_MESH_NUMBERS)),
                       DS_U16(ds, (uint16_t)(vehicle + 0x30)));
            } else {
                /* the record is written field by field around the mesh choice, as in the original */
                uint16_t di = DS_U16(ds, FL_WRITE_PTR);
                DS_U16(ds, di) = DS_U16(ds, DS_OPPONENT_X);
                DS_U16(ds, (uint16_t)(di + 2)) = 0;
                DS_U16(ds, (uint16_t)(di + 4)) = DS_U16(ds, DS_OPPONENT_Z);
                DS_U16(ds, (uint16_t)(di + 6)) = 0x4020;
                animation_bearing(ds, vehicle, 0x5A0);
                DS_U16(ds, (uint16_t)(di + 8)) = figure_mesh_5(ds, vehicle, 0x5A0);
                DS_U16(ds, (uint16_t)(di + 10)) = 5;
                DS_U16(ds, FL_WRITE_PTR) = (uint16_t)(di + 12);
                DS_U16(ds, FL_COUNT)++;
            }
        }
    }
    if (!second_figure_forced) {
        if (!DS_U8(ds, DS_COMPANION_ACTIVE))
            return;
        if (DS_U16(ds, DS_COMPANION_ORDER) == 2 && !(DS_U8(ds, (uint16_t)(DS_U16(ds, FL_PLAYER) + 0x0E)) & 1))
            return;
    }
    uint16_t di = DS_U16(ds, FL_WRITE_PTR);
    DS_U16(ds, di) = DS_U16(ds, DS_COMPANION_X);
    DS_U16(ds, (uint16_t)(di + 2)) = 0;
    DS_U16(ds, (uint16_t)(di + 4)) = DS_U16(ds, DS_COMPANION_Z);
    DS_U16(ds, (uint16_t)(di + 6)) = 0x4024;
    animation_bearing(ds, 0x53C, 0x5A8);
    DS_U16(ds, (uint16_t)(di + 8)) = figure_mesh_8(ds, 0x53C, 0x5A8, 0xB880);
    DS_U16(ds, (uint16_t)(di + 10)) = 5;
    DS_U16(ds, FL_WRITE_PTR) = (uint16_t)(di + 12);
    DS_U16(ds, FL_COUNT)++;
}

/* orig 0000:036E
 *
 * Builds the frame's object list at DS:1576 and has it culled and sorted:
 *   the map objects in view (the visible-object list), guided projectiles, pickups, things in flight,
 *   one special object (DS:0373), a timed object (DS:0B08), the figures (DS:0DF0, already
 *   made into records elsewhere), the opponent and the companion, debris records.
 * DS:01FE receives the address of the sorted list, DS:50AC the number of records (at most
 * 199), DS:020E the number before sorting.
 *
 * When the timed object's countdown ends in this call it goes off (explosion_damage) in the
 * middle of the list being built, as in the original.
 *
 * Always returns 0.
 */
int build_frame_draw_list(Game *g)
{
    uint8_t *ds = g->ds;

    DS_U16(ds, FL_COUNT) = 0;
    DS_U16(ds, FL_WRITE_PTR) = FL_LIST;
    uint16_t visible = DS_U16(ds, FL_VISIBLE_COUNT);
    DS_U16(ds, FL_COUNT) = (uint16_t)(DS_U16(ds, FL_COUNT) + visible);
    if (visible != 0)
        append_block(g, g->ds_seg, FL_VISIBLE, (uint16_t)(6 * (uint8_t)visible));

    append_guided_projectiles(ds);
    append_pickups(ds);
    append_projectiles(ds);

    /* orig 11BC:1BBC */
    if (DS_U8(ds, 0x0373))
        append(ds, DS_U16(ds, 0x0367), DS_U16(ds, 0x0369), DS_U16(ds, 0x036B), 0, DS_U16(ds, 0x80EE), 0x32);

    /* orig 0000:95F2 (with 9625) */
    uint16_t timer = DS_U16(ds, 0x0B08 + 6);
    if (timer != 0) {
        append(ds, DS_U16(ds, 0x0B08), 0, DS_U16(ds, 0x0B08 + 2), 0x2000, DS_U16(ds, FL_SPECIAL_ID), 0x33);
        uint16_t di = (uint16_t)(DS_U16(ds, FL_WRITE_PTR) - 12);
        for (int i = 0; i < 12; i++)
            DS_U8(ds, (uint16_t)(0xAAF2 + i)) = DS_U8(ds, (uint16_t)(di + i));
        if (!(timer & 0x8000) && --DS_U16(ds, 0x0B08 + 6) == 0)
            explosion_damage(g, 0xAAF2); /* orig 0000:960F: it goes off */
    }

    /* orig 0000:B1F1 */
    uint16_t figures = DS_U16(ds, DS_FIGURE_COUNT);
    if (figures != 0) {
        DS_U16(ds, FL_COUNT) = (uint16_t)(DS_U16(ds, FL_COUNT) + figures);
        append_block(g, g->ds_seg, 0x0DF0, (uint16_t)(6 * (uint8_t)figures));
    }

    append_opponent_and_companion(ds);

    /* orig 0000:7EC8 */
    uint16_t debris = DS_U16(ds, 0x117A);
    if (debris != 0) {
        DS_U16(ds, FL_COUNT) = (uint16_t)(DS_U16(ds, FL_COUNT) + debris);
        append_block(g, DS_U16(ds, FL_SEG_DEBRIS), 0, (uint16_t)((uint8_t)debris * 6));
    }

    DS_U16(ds, FL_COUNT_BEFORE_SORT) = DS_U16(ds, FL_COUNT);
    DS_U16(ds, FL_LIST_PTR) = sort_draw_list(g);
    if (DS_U16(ds, FL_COUNT) >= 0xC8)
        DS_U16(ds, FL_COUNT) = 0xC7;
    return 0;
}

/* The angle routine also leaves DX as the unsigned octant-division remainder.
 * This register is an input to C21F's new-burst probability, not scratch to discard. */
uint32_t angle_between_state(uint8_t *ds, int16_t ax, int16_t az, int16_t bx, int16_t bz)
{
    int16_t dx = (uint16_t)(ax - bx), dz = (uint16_t)(az - bz);
    uint16_t ux = dx < 0 ? -dx : dx, uz = dz < 0 ? -dz : dz;
    uint16_t small = ux < uz ? ux : uz, large = ux < uz ? uz : ux;
    uint16_t remainder = ((uint32_t)small * 64) % (large ? large : 1);
    return angle_between(ds, ax, az, bx, bz) | ((uint32_t)remainder << 16);
}
