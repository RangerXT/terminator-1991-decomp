/* From the map to the list of visible objects.
 *
 * The map around the player is kept as a window of 24 x 24 cells in its own segment
 * (DS:[91D4]): one word per cell, 0 or the offset of that cell's object list in the same
 * segment. A list is a count followed by 12-byte records (x, y, z, flags, id, extra) with
 * x and z inside the cell (0..1023). Columns run east; rows run south, which is towards
 * smaller z.
 */
#include "term.h"

enum {
    CL_PLAYER = 0x03A0,
    CL_OCTANT = 0x04C4,      /* u16: 2 * (heading sector 0..7) */
    CL_EXTRA_COUNT = 0x04C6, /* u16: number of 14-byte extra entries */
    CL_REMOVED = 0x0F70,     /* 32 x 12 bytes: objects that have been removed */
    CL_EXTRA_PTR = 0x1200,   /* far pointer to the extra entries */
    CL_OUTPUT = 0x5F80,      /* the visible-object records */
    CL_COLUMN = 0x5EDF,      /* i8: window column of the cell being read */
    CL_COLUMN_BASE = 0x5EE0,
    CL_ROW = 0x5EE1, /* i8: window row */
    CL_ROW_START = 0x5EE2,
    CL_COUNT = 0x7240,      /* u16: number of visible-object records */
    CL_CELL = 0x7242,       /* u16: the cell the list was built for */
    CL_WINDOW_COL = 0x7272, /* u16: map column of the window's first column */
    CL_WINDOW_ROW = 0x7274,
    CL_SOURCE_PTR = 0x72DA,   /* u16: next free slot of the source list below */
    CL_SOURCES = 0x72DC,      /* u16[]: for each record, where it came from in the cell segment */
    CL_MESH_NUMBERS = 0x72CA, /* u16[]: mesh numbers for the extra entries */
    CL_ROW_COUNT0 = 0x74B2,
    CL_ROW_OUTPUT0 = 0x74B4,
    CL_VIEW_PTR = 0x74B6,
    CL_VIEW_TABLES = 0x74B8, /* u16[8]: per heading sector, offset of its list of rows */
    CL_RAW_EXTRAS = 0x7A18,
    CL_OUTPUT_END = 0x9156,
    CL_SEG_CELLS = 0x91D4,
    CL_DETAIL = 0xABCA,
};

static inline uint16_t far_u16(const Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(*far_ptr(g, seg, off) | (*far_ptr(g, seg, (uint16_t)(off + 1)) << 8));
}

static inline void far_set_u16(Game *g, uint16_t seg, uint16_t off, uint16_t v)
{
    *far_ptr(g, seg, off) = (uint8_t)v;
    *far_ptr(g, seg, (uint16_t)(off + 1)) = (uint8_t)(v >> 8);
}

/* orig 0000:45B8   is the cell record at seg:si on the list of removed objects?
 * If so its extra word is set to FFFF, which hides it for good. */
static int record_removed(Game *g, uint16_t seg, uint16_t si)
{
    uint8_t *ds = g->ds;
    uint16_t entry = CL_REMOVED;
    for (int i = 0; i < 0x20; i++, entry = (uint16_t)(entry + 12)) {
        int same = 1;
        for (int k = 0; k < 8 && same; k += 2)
            same = far_u16(g, seg, (uint16_t)(si + k)) == DS_U16(ds, (uint16_t)(entry + k));
        if (same) {
            far_set_u16(g, seg, (uint16_t)(si + 10), 0xFFFF);
            return 1;
        }
    }
    return 0;
}

/* orig 0000:3D87   in ES:SI = a cell's list, AX = x of the cell's west edge, BP = z of its
 * south edge (both relative to the player's cell), DI = where to write   out DI
 *
 * Copies the cell's records to the output with their positions made relative to the
 * player's cell. A record whose extra word is negative is not kept.
 *
 * Quirk kept: when a record is on the removed list the original does not step past it, so
 * the rest of that cell's list is skipped as well, for as long as the entry stays there. */
static uint16_t collect_cell_objects(Game *g, uint16_t seg, uint16_t si, uint16_t x_base, uint16_t z_base, uint16_t di)
{
    uint8_t *ds = g->ds;
    uint16_t count = far_u16(g, seg, si);
    si = (uint16_t)(si + 2);
    for (; count; count--) {
        if (record_removed(g, seg, si))
            continue;
        uint16_t slot = DS_U16(ds, CL_SOURCE_PTR);
        DS_U16(ds, slot) = si;
        DS_U16(ds, CL_SOURCE_PTR) = (uint16_t)(slot + 2);
        DS_U16(ds, CL_COUNT)++;
        DS_U16(ds, di) = (uint16_t)(far_u16(g, seg, si) + x_base);
        DS_U16(ds, (uint16_t)(di + 2)) = far_u16(g, seg, (uint16_t)(si + 2));
        DS_U16(ds, (uint16_t)(di + 4)) = (uint16_t)(far_u16(g, seg, (uint16_t)(si + 4)) + z_base);
        DS_U16(ds, (uint16_t)(di + 6)) = far_u16(g, seg, (uint16_t)(si + 6));
        DS_U16(ds, (uint16_t)(di + 8)) = far_u16(g, seg, (uint16_t)(si + 8));
        uint16_t extra = far_u16(g, seg, (uint16_t)(si + 10));
        DS_U16(ds, (uint16_t)(di + 10)) = extra;
        si = (uint16_t)(si + 12);
        di = (uint16_t)(di + 12);
        if (extra & 0x8000) {
            DS_U16(ds, CL_SOURCE_PTR) = (uint16_t)(DS_U16(ds, CL_SOURCE_PTR) - 2);
            DS_U16(ds, CL_COUNT)--;
            di = (uint16_t)(di - 12);
        }
    }
    DS_U16(ds, CL_OUTPUT_END) = di;
    return di;
}

/* orig 0000:42C0 (with 42EF and 41F8)   in DI = where to write   out DI
 * Objects that are not part of the map files (14-byte entries behind the far pointer at
 * DS:1200: cell, x, z, mesh index, extra, flags) and lie in the current cell are appended. */
uint16_t collect_cell_extras(Game *g, uint16_t di)
{
    uint8_t *ds = g->ds;
    uint16_t count = DS_U16(ds, CL_EXTRA_COUNT);
    if (count == 0)
        return di;
    uint8_t col = (uint8_t)(DS_U8(ds, CL_COLUMN) + DS_U8(ds, CL_WINDOW_COL));
    uint8_t row = (uint8_t)(DS_U8(ds, CL_ROW) + DS_U8(ds, CL_WINDOW_ROW));
    uint16_t key = (uint16_t)(col | (row << 8));
    uint16_t bx = DS_U16(ds, CL_EXTRA_PTR), seg = DS_U16(ds, CL_EXTRA_PTR + 2);
    for (; count; count--, bx = (uint16_t)(bx + 0x0E)) {
        if (far_u16(g, seg, bx) != key)
            continue;
        uint16_t x = far_u16(g, seg, (uint16_t)(bx + 2)), z = far_u16(g, seg, (uint16_t)(bx + 4));
        if (!DS_U8(ds, CL_RAW_EXTRAS)) {
            uint16_t player = DS_U16(ds, CL_PLAYER);
            x = (uint16_t)((uint16_t)(col - DS_U16(ds, (uint16_t)(player + 0x1E))) * 0x400 + x);
            z = (uint16_t)((uint16_t)(0 - (uint16_t)(row - DS_U16(ds, (uint16_t)(player + 0x20)))) * 0x400 + z);
        }
        DS_U16(ds, di) = x;
        DS_U16(ds, (uint16_t)(di + 2)) = 0;
        DS_U16(ds, (uint16_t)(di + 4)) = z;
        DS_U16(ds, (uint16_t)(di + 8)) = DS_U16(ds, (uint16_t)(far_u16(g, seg, (uint16_t)(bx + 6)) + CL_MESH_NUMBERS));
        DS_U16(ds, (uint16_t)(di + 10)) = far_u16(g, seg, (uint16_t)(bx + 8)) & 0x37F;
        DS_U16(ds, (uint16_t)(di + 6)) = far_u16(g, seg, (uint16_t)(bx + 0x0A));
        di = (uint16_t)(di + 12);
        DS_U16(ds, CL_COUNT)++;
    }
    return di;
}

/* orig 0000:3C18 - 3D61 (the second half of update_visible_cells, 0000:3B88)
 * in AX = identifier of the player's cell, CX = its window column, DX = its window row
 *
 * Rebuilds the visible-object list at DS:5F80. The cells to read come from a table chosen by
 * the player's heading sector (DS:74B8): for each of the 9 rows from 4 north of the player
 * to 4 south, a first column (relative to 4 west of the player) and a number of cells, ended
 * by FFFF. So the list covers a wedge of the 9 x 9 cells around the player.
 *
 * Objects more than 3 cells away in both directions (2 with reduced detail) get record
 * flag 0x80. Quirk kept: the test uses the column after the one just read, and marks every
 * record gathered so far in that row, not just the new ones.
 */
void collect_visible_objects(Game *g, uint16_t cell_id, uint16_t column, uint16_t row)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, CL_SEG_CELLS);
    uint16_t di = CL_OUTPUT;
    uint16_t x_base = 0xF000, z_base = 0x1000;

    DS_U16(ds, CL_COUNT) = 0;
    DS_U16(ds, CL_CELL) = cell_id;
    column = (uint16_t)(column - 4);
    row = (uint16_t)(row - 4);
    DS_U8(ds, CL_COLUMN) = (uint8_t)column;
    DS_U8(ds, CL_COLUMN_BASE) = (uint8_t)column;
    DS_U8(ds, CL_ROW) = (uint8_t)row;
    uint16_t si = (uint16_t)(0x30 * row + column * 2);
    DS_U8(ds, CL_RAW_EXTRAS) = 0;
    DS_U16(ds, CL_VIEW_PTR) = DS_U16(ds, (uint16_t)(DS_U16(ds, CL_OCTANT) + CL_VIEW_TABLES));
    DS_U16(ds, CL_SOURCE_PTR) = CL_SOURCES;

    for (;;) {
        uint16_t entry = DS_U16(ds, CL_VIEW_PTR);
        uint16_t first = DS_U16(ds, entry);
        if (first == 0xFFFF)
            break;
        DS_U8(ds, CL_ROW_START) = (uint8_t)first;
        uint16_t x = (uint16_t)(x_base + (uint16_t)(0x400 * first));
        uint16_t cell = (uint16_t)(si + first + first);
        uint16_t cells = DS_U16(ds, (uint16_t)(entry + 2));
        DS_U16(ds, CL_VIEW_PTR) = (uint16_t)(entry + 4);
        if (cells != 0) {
            DS_U8(ds, CL_COLUMN) = (uint8_t)(DS_U8(ds, CL_COLUMN_BASE) + DS_U8(ds, CL_ROW_START));
            DS_U16(ds, CL_ROW_OUTPUT0) = di;
            DS_U16(ds, CL_ROW_COUNT0) = DS_U16(ds, CL_COUNT);
            do {
                if (!(DS_U8(ds, CL_COLUMN) & 0x80) && !(DS_U8(ds, CL_ROW) & 0x80)) {
                    uint16_t list = far_u16(g, seg, cell);
                    if (list != 0)
                        di = collect_cell_objects(g, seg, list, x, z_base, di);
                    di = collect_cell_extras(g, di);
                }
                DS_U8(ds, CL_COLUMN)++;
                x = (uint16_t)(x + 0x400);
                cell = (uint16_t)(cell + 2);

                uint16_t added = (uint16_t)(DS_U16(ds, CL_COUNT) - DS_U16(ds, CL_ROW_COUNT0));
                if (added != 0) {
                    uint8_t limit = DS_U16(ds, CL_DETAIL) ? 2 : 3;
                    uint16_t player = DS_U16(ds, CL_PLAYER);
                    int8_t dc = (int8_t)((uint8_t)(DS_U16(ds, (uint16_t)(player + 0x1E)) - DS_U16(ds, CL_WINDOW_COL))
                                         - DS_U8(ds, CL_COLUMN));
                    if (dc < 0)
                        dc = (int8_t)-dc;
                    if ((uint8_t)dc > limit) {
                        int8_t dr =
                            (int8_t)((uint8_t)(DS_U16(ds, (uint16_t)(player + 0x20)) - DS_U16(ds, CL_WINDOW_ROW))
                                     - DS_U8(ds, CL_ROW));
                        if (dr < 0)
                            dr = (int8_t)-dr;
                        if ((uint8_t)dr > limit) {
                            uint16_t rec = DS_U16(ds, CL_ROW_OUTPUT0);
                            do {
                                DS_U16(ds, (uint16_t)(rec + 6)) |= 0x80;
                                rec = (uint16_t)(rec + 12);
                            } while (--added);
                        }
                    }
                }
            } while (--cells);
        }
        z_base = (uint16_t)(z_base - 0x400);
        si = (uint16_t)(si + 0x30);
        DS_U8(ds, CL_ROW)++;
    }
    if (DS_U16(ds, CL_COUNT) > 0xC8)
        DS_U16(ds, CL_COUNT) = 0xC8;
}

/* ---------------------------------------------------------------- the ground list */

enum {
    GL_LIST = 0x2836, /* 12-byte ground records, drawn before the objects */
    GL_COUNT = 0x91D8,
    GL_COARSE_ROW = 0x5F7C, /* which of the window's 3 x 3 coarse cells the player is in */
    GL_COARSE_COL = 0x5F7A,
    GL_LAYER_TABLE = 0x5EE6, /* u8[]: drawing layer of a ground mesh, by its first face's colour */
    GL_ORIGIN_X = 0x7244,    /* i32: player column * 1024 */
    GL_ORIGIN_Z = 0x7248,    /* i32: (player row + 1) * 1024 */
    GL_MESH_OFFSETS = 0x92DA,
    GL_MESH_BASE = 0x727E,
    GL_SEG_GROUND = 0x91D2,
};

/* Offset of a stored ground mesh (its size word) in the ground segment. */
static uint16_t ground_mesh_at(const uint8_t *ds, uint16_t number)
{
    return (uint16_t)(DS_U16(ds, (uint16_t)((uint16_t)(number * 2) + GL_MESH_OFFSETS)) + DS_U16(ds, GL_MESH_BASE));
}

/* orig 0000:3F4D   in AX = ground mesh number, DI = just past its new record   out: carry
 * Returns 1 if the mesh reaches too far from the player to be transformed safely: any
 * vertex, widened by 1024, more than 16383 from the player cell's corner in x or z. */
static int ground_mesh_too_far(Game *g, uint16_t seg, uint16_t number, uint16_t di)
{
    uint8_t *ds = g->ds;
    uint16_t mesh = ground_mesh_at(ds, number);
    uint16_t count = far_u16(g, seg, (uint16_t)(mesh + 6));
    uint16_t v = (uint16_t)(far_u16(g, seg, (uint16_t)(mesh + 0x0A)) + mesh + 2);
    int carry;
    do {
        for (int axis = 0; axis < 2; axis++) {
            int16_t c = (int16_t)far_u16(g, seg, (uint16_t)(v + 4 * axis));
            if (c < 0) {
                c = (int16_t)(c - 0x400);
                if (c >= 0)
                    return 1;
            } else {
                c = (int16_t)(c + 0x400);
                if (c < 0)
                    return 1;
            }
            c = (int16_t)(c + DS_I16(ds, (uint16_t)(di - (axis ? 8 : 12))));
            if (c >= 0x4000 || c < -0x4000)
                return 1;
        }
        carry = v > 0xFFF9;
        v = (uint16_t)(v + 6);
    } while (--count);
    return carry;
}

/* orig 0000:3E8F   in DI = where to write   out DI
 * One coarse cell (8 x 8 map cells) of the ground: each placement there (i32 x, i32 y,
 * i32 z, mesh number; x east, z south, in window coordinates) becomes a ground record
 * relative to the south-west corner of the player's cell: x - column * 1024, y,
 * (row + 1) * 1024 - z, flags 0, mesh number. The record's last word is left as it was. */
static uint16_t ground_cell_records(Game *g, uint16_t di)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, GL_SEG_GROUND);
    uint16_t si = (uint16_t)(0x0C * DS_U16(ds, GL_COARSE_ROW) + 4 * DS_U16(ds, GL_COARSE_COL));
    si = far_u16(g, seg, si);
    if (si == 0)
        return di;
    uint16_t count = far_u16(g, seg, si);
    si = (uint16_t)(si + 2);
    if (count == 0)
        return di;
    do {
        DS_U16(ds, di) = (uint16_t)(far_u16(g, seg, si) - DS_U16(ds, GL_ORIGIN_X));
        DS_U16(ds, (uint16_t)(di + 2)) = far_u16(g, seg, (uint16_t)(si + 4));
        DS_U16(ds, (uint16_t)(di + 4)) =
            (uint16_t)(0 - (uint16_t)(far_u16(g, seg, (uint16_t)(si + 8)) - DS_U16(ds, GL_ORIGIN_Z)));
        DS_U16(ds, (uint16_t)(di + 6)) = 0;
        uint16_t number = far_u16(g, seg, (uint16_t)(si + 12));
        DS_U16(ds, (uint16_t)(di + 8)) = number;
        si = (uint16_t)(si + 14);
        di = (uint16_t)(di + 12);
        DS_U16(ds, GL_COUNT)++;
        if (ground_mesh_too_far(g, seg, number, di)) {
            di = (uint16_t)(di - 12);
            DS_U16(ds, GL_COUNT)--;
        }
    } while (--count);
    return di;
}

/* orig 0000:3E5E   the coarse cells west of, at and east of the player's, in one row.
 * (The original raises the byte at DS:5CDD around the middle call; nothing reads it there.) */
static uint16_t ground_row_records(Game *g, uint16_t di)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, GL_COARSE_COL) != 0) {
        DS_U16(ds, GL_COARSE_COL)--;
        di = ground_cell_records(g, di);
        DS_U16(ds, GL_COARSE_COL)++;
    }
    di = ground_cell_records(g, di);
    if (DS_U16(ds, GL_COARSE_COL) != 2) {
        DS_U16(ds, GL_COARSE_COL)++;
        di = ground_cell_records(g, di);
        DS_U16(ds, GL_COARSE_COL)--;
    }
    return di;
}

/* Drawing layer of the ground record at `rec`: looked up from the colour of the first face
 * of its mesh (grass 1, water 2, roads 3, ...; DS:5EE6). */
static uint8_t ground_layer(Game *g, uint16_t seg, uint16_t rec)
{
    uint8_t *ds = g->ds;
    uint16_t mesh = ground_mesh_at(ds, DS_U16(ds, (uint16_t)(rec + 8)));
    uint16_t face = (uint16_t)(mesh + far_u16(g, seg, (uint16_t)(mesh + 8)) + 2);
    return DS_U8(ds, (uint16_t)(GL_LAYER_TABLE + *far_ptr(g, seg, face)));
}

/* orig 11BC:14D3 (far)   bubble sort of the ground records by layer, lowest first, so that
 * roads are drawn over grass. (With fewer than two records the loop counter of the original
 * wraps and it compares 65536 pairs; kept.) */
static void ground_sort_layers(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, GL_SEG_GROUND);
    uint16_t dx = DS_U16(ds, GL_COUNT);
    for (;;) {
        dx--;
        uint16_t cx = dx, si = GL_LIST, di = GL_LIST + 12, swaps = 0;
        do {
            if (ground_layer(g, seg, si) > ground_layer(g, seg, di)) {
                for (int i = 0; i < 12; i++) {
                    uint8_t t = DS_U8(ds, (uint16_t)(si + i));
                    DS_U8(ds, (uint16_t)(si + i)) = DS_U8(ds, (uint16_t)(di + i));
                    DS_U8(ds, (uint16_t)(di + i)) = t;
                }
                swaps++;
            }
            si = (uint16_t)(si + 12);
            di = (uint16_t)(di + 12);
        } while (--cx);
        if (dx == 1 || swaps == 0)
            break;
    }
}

/* orig 0000:3FAB (with 3FCD, 3FF5)   remove records that are exact copies of an earlier one
 * (a mesh lying across several coarse cells is listed in each). All 12 bytes are compared,
 * including the last word that ground_cell_records never writes. */
static void ground_remove_duplicates(uint8_t *ds)
{
    uint16_t si = GL_LIST;
    uint16_t end = (uint16_t)(GL_LIST + DS_U8(ds, GL_COUNT) * 12);
    do {
        uint16_t di = (uint16_t)(si + 12);
        do {
            int same = 1;
            for (int i = 0; i < 12 && same; i++)
                same = DS_U8(ds, (uint16_t)(si + i)) == DS_U8(ds, (uint16_t)(di + i));
            if (same) {
                uint16_t from = (uint16_t)(di + 12), to = di;
                for (uint16_t words = (uint16_t)((uint16_t)(end - from) >> 1); words; words--) {
                    uint8_t lo = DS_U8(ds, from), hi = DS_U8(ds, (uint16_t)(from + 1));
                    DS_U8(ds, to) = lo;
                    DS_U8(ds, (uint16_t)(to + 1)) = hi;
                    from = (uint16_t)(from + 2);
                    to = (uint16_t)(to + 2);
                }
                di = (uint16_t)(di - 12);
                DS_U16(ds, GL_COUNT)--;
                end = (uint16_t)(end - 12);
            }
            di = (uint16_t)(di + 12);
        } while (di < end);
        si = (uint16_t)(si + 12);
    } while (si < (uint16_t)(end - 12));
}

/* orig 0000:3D62 - 3D80 (inside update_visible_cells) with 0000:3DE7
 *
 * Rebuilds the ground list at DS:2836: the ground meshes of the up to nine coarse cells
 * around the player, without those reaching too far away, sorted by layer and with
 * duplicates removed. At most 220 records.
 */
void build_ground_list(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t player = DS_U16(ds, CL_PLAYER);
    uint16_t col = DS_U16(ds, (uint16_t)(player + 0x1E)), row = DS_U16(ds, (uint16_t)(player + 0x20));

    DS_U16(ds, GL_COUNT) = 0;
    uint32_t x0 = (uint32_t)col * 0x400, z0 = (uint32_t)(uint16_t)(row + 1) * 0x400;
    DS_U16(ds, GL_ORIGIN_X) = (uint16_t)x0;
    DS_U16(ds, GL_ORIGIN_X + 2) = (uint16_t)(x0 >> 16);
    DS_U16(ds, GL_ORIGIN_Z) = (uint16_t)z0;
    DS_U16(ds, GL_ORIGIN_Z + 2) = (uint16_t)(z0 >> 16);
    DS_U16(ds, GL_COARSE_ROW) = (uint16_t)((uint16_t)(row - DS_U16(ds, CL_WINDOW_ROW)) >> 3);
    DS_U16(ds, GL_COARSE_COL) = (uint16_t)((uint16_t)(col - DS_U16(ds, CL_WINDOW_COL)) >> 3);

    uint16_t di = GL_LIST;
    if (DS_U16(ds, GL_COARSE_ROW) != 0) {
        DS_U16(ds, GL_COARSE_ROW)--;
        di = ground_row_records(g, di);
        DS_U16(ds, GL_COARSE_ROW)++;
    }
    di = ground_row_records(g, di);
    if (DS_U16(ds, GL_COARSE_ROW) != 2) {
        DS_U16(ds, GL_COARSE_ROW)++;
        di = ground_row_records(g, di);
        DS_U16(ds, GL_COARSE_ROW)--;
    }
    ground_sort_layers(g);
    ground_remove_duplicates(ds);
    if (DS_U16(ds, GL_COUNT) > 0xDC)
        DS_U16(ds, GL_COUNT) = 0xDC;
}
