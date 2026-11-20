/* The city window and the visible lists derived from it (0000:3B88). */
#include "term.h"

static uint16_t mesh_word(Game *g, uint16_t seg, uint16_t off)
{
    return *far_ptr(g, seg, off) | ((uint16_t)*far_ptr(g, seg, (uint16_t)(off + 1)) << 8);
}

/* 7B00: append a length-prefixed SPN and remember its resident mesh slot. */
static int append_mesh(Game *g, const ImageIO *files, uint16_t name, uint16_t result)
{
    uint8_t *ds = g->ds;
    uint16_t dest = DS_U16(ds, 0x94DA);
    uint16_t seg = g->ds_seg - 0x5C27 + 0x1F5A;
    uint32_t size = file_load(g, files, name, seg, dest);
    if (size == UINT32_MAX)
        return -1;
    uint16_t slot = DS_U16(ds, DS_LOADED_DEF_COUNT)++;
    DS_U16(ds, 0x94DA) += (uint16_t)size;
    DS_U16(ds, 0x91DA + 2 * slot) = dest;
    DS_U16(ds, result) = slot;
    return 0;
}

/* 7ABE then D88C: measure resident DEF and the first three SPN meshes. The
 * missile is appended later, so it has no entry in this pass's minimum-Y table. */
static int refresh_meshes(Game *g, const ImageIO *files)
{
    if (append_mesh(g, files, 0x99E4, 0x9A64) || append_mesh(g, files, 0xB513, 0xB51E)
        || append_mesh(g, files, 0x80CE, 0x80EE))
        return -1;
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DS_SEG_OBJECTS), off = 0;
    for (unsigned i = 0; i < DS_U16(ds, DS_LOADED_DEF_COUNT); ++i) {
        uint16_t size = mesh_word(g, seg, off);
        off += 2;
        uint16_t vertices = mesh_word(g, seg, off + 4);
        uint16_t v = off + mesh_word(g, seg, off + 8);
        int16_t lowest = 0;
        do {
            int16_t y = mesh_word(g, seg, v + 2);
            if (y < lowest)
                lowest = y;
            v += 6;
        } while (--vertices);
        DS_U16(ds, 0x94E4 + 2 * i) = lowest;
        off += size;
    }
    return append_mesh(g, files, 0xE3C6, 0xE3D2);
}

/* 3F0F: the cell identifier is a byte offset in the 24-column pointer table. */
static uint16_t window_cell(uint8_t *ds, uint16_t *col, uint16_t *row)
{
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    *col = DS_U16(ds, actor + 30) - DS_U16(ds, 0x7272);
    *row = DS_U16(ds, actor + 32) - DS_U16(ds, 0x7274);
    return *row * 48 + *col * 2;
}

/* 097E: six-cell thresholds at the origin have the special zero-edge rule. */
static uint16_t window_axis(uint8_t *ds, uint16_t coord, uint16_t max, uint16_t axis)
{
    uint16_t origin = (coord & 0xFFF8) - 8;
    if ((int16_t)origin < 0)
        origin = 0;
    uint16_t low = origin ? origin + 6 : 0, high = low + 14;
    DS_U16(ds, 0x5F7A + 2 * axis) = coord >> 3;
    DS_U16(ds, 0x7272 + 2 * axis) = origin;
    DS_U16(ds, 0x7276 + 4 * axis) = low;
    DS_U16(ds, 0x7278 + 4 * axis) = high < max ? high : max;
    DS_U16(ds, 0x7280 + 2 * axis) = origin >> 3;
    return origin;
}

static int load_window(Game *g, const ImageIO *files)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    uint32_t x = window_axis(ds, DS_U16(ds, actor + 30), 192, 0) * 1024u;
    uint32_t z = window_axis(ds, DS_U16(ds, actor + 32), 128, 1) * 1024u;
    if (load_window_ground_and_cells(g, files))
        return -1;
    DS_U16(ds, 0x72D6) = (uint16_t)z;
    DS_U16(ds, 0x72D8) = z >> 16;
    DS_U16(ds, 0x72D2) = (uint16_t)x;
    DS_U16(ds, 0x72D4) = x >> 16;
    return load_window_objects(g, files);
}

int update_visible_cells(Game *g, const ImageIO *files)
{
    uint8_t *ds = g->ds;
    uint16_t col, row, cell = window_cell(ds, &col, &row);
    uint16_t previous = DS_U16(ds, DS_VISIBLE_CELL), actor = DS_U16(ds, DS_PLAYER);
    uint16_t sector = ((DS_U16(ds, actor + 6) + DS_U16(ds, actor + 8) + 32) & 511) >> 6;
    uint16_t x = DS_U16(ds, actor + 30), z = DS_U16(ds, actor + 32);
    int changed = cell != previous;
    if (!changed && DS_U16(ds, 0x04C4) == 2 * sector) {
        DS_U16(ds, 0x8685) = 0;
        return 0;
    }
    uint16_t left = DS_U16(ds, 0x7276);
    if ((int16_t)previous <= 0 && previous != 0xFFFE)
        left = 5000;
    int reload = x <= left || x >= DS_U16(ds, 0x7278) || z <= DS_U16(ds, 0x727A) || z >= DS_U16(ds, 0x727C);
    if (reload && (!files || !files->call))
        return -1;
    DS_U16(ds, 0x8685) = changed ? 0xFFFF : 0;
    DS_U16(ds, 0x04C4) = 2 * sector;
    DS_U16(ds, 0x7276) = left;
    if (reload) {
        if (load_window(g, files))
            return -1;
        DS_U16(ds, 0x8685) = 0xFFFF;
        cell = window_cell(ds, &col, &row);
        if (horizon_load(g, files) || refresh_meshes(g, files))
            return -1;
        actor = DS_U16(ds, DS_PLAYER);
        if (DS_U8(ds, actor + 14) & 2) {
            if (vehicle_hud_load(g, files))
                return -1;
        } else if (character_resources_load(g, files))
            return -1;
    }
    DS_U8(ds, 0x5CD8) = 255;
    collect_visible_objects(g, cell, col, row);
    build_ground_list(g);
    collision_map_build(g);
    return 0;
}
