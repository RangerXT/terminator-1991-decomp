/* 11BC:0A16. Stitch a three-by-three coarse window from up to four DOS
 * sectors. Ground and street files use different grids and list formats. */
#include "term.h"
#include <string.h>

typedef struct {
    Game *game;
    const ImageIO *files;
    uint8_t *cs, *ground, *cells, *source;
    unsigned size;
} SectorWindow;

/* Loader scratch is visible to the DOS program, including the per-quadrant
 * mesh dictionary and the running maxima of the three resident buffers. */
enum {
    PACKED = 0x4F8,
    PACK_SEG = 0x4FA,
    LOCAL_COUNT = 0x4FC,
    LIST_END = 0x4FE,
    NEXT_ID = 0x500,
    LOCAL_IDS = 0x502,
    SOURCE_MESH = 0x702,
    TAIL = 0x928,
    WORLD_X = 0x92A,
    WORLD_Z = 0x92E,
    X_ORIGINS = 0x932,
    Z_ORIGINS = 0x93A,
    COL_STRIDE = 0x942,
    ROW_STRIDE = 0x944,
    ADDED = 0x946,
    FIRST_SLOT = 0x948,
    MAX_CELLS = 0x94A,
    MAX_GROUND = 0x94E
};

static uint32_t read32(const uint8_t *p, unsigned at)
{
    return DS_U16(p, at) | ((uint32_t)DS_U16(p, at + 2) << 16);
}

static void write32(uint8_t *p, unsigned at, uint32_t value)
{
    DS_U16(p, at) = (uint16_t)value;
    DS_U16(p, at + 2) = value >> 16;
}

/* 0AE7. At the east and south city limits the window can end in a
 * partially populated row or column. Those missing cells stay zero. */
static void split_axis(SectorWindow *w, unsigned axis)
{
    uint8_t *ds = w->game->ds;
    unsigned coarse = DS_U16(ds, 0x7280 + 2 * axis);
    unsigned sector = coarse / 8, first = coarse % 8;
    unsigned ids = 0x5CDE + 2 * axis, widths = 0x725A + 4 * axis;
    unsigned origins = axis ? Z_ORIGINS : X_ORIGINS;
    unsigned table = axis ? 0x7290 : 0x7284;
    DS_U8(ds, ids) = sector + 1;
    DS_U8(ds, ids + 1) = 255;
    DS_U16(ds, 0x7256 + 2 * axis) = first;
    DS_U16(ds, widths) = 3;
    write32(w->cs, origins, read32(ds, table + 4 * sector));
    if (first + 3 <= 8)
        return;
    DS_U16(ds, widths) = 8 - first;
    DS_U16(ds, widths + 2) = first + 3 - 8;
    if (sector + 1 >= (axis ? 2u : 3u))
        return;
    DS_U8(ds, ids + 1) = sector + 2;
    write32(w->cs, origins + 4, read32(ds, table + 4 * (sector + 1)));
}

/* 0FEA, 10BB, 10CB and 10C6. The game issues one 60,000-byte read. */
static int read_sector(SectorWindow *w, unsigned extension)
{
    Game *g = w->game;
    uint8_t *ds = g->ds;
    DS_U16(ds, 0x5E4C) = DS_U16(ds, 0x726A) + 0x3060;
    memcpy(ds + 0x5E4E, ds + extension, 5); /* ".big" or ".sct", including NUL */
    const ImageIO *io = w->files;
    uint32_t handle = io->call(g, IMG_OPEN, 0, g->ds_seg, 0x5E4A, 0, io->user);
    if (handle > UINT16_MAX)
        return -1;
    DS_U16(ds, 0x7270) = (uint16_t)handle;
    uint32_t size = io->call(g, IMG_READ, handle, DS_U16(ds, 0x94DE), 0, 60000, io->user);
    uint32_t closed = io->call(g, IMG_CLOSE, handle, 0, 0, 0, io->user);
    if (size > 60000 || closed > UINT16_MAX)
        return -1;
    w->size = size;
    return 0;
}

/* 0EA8. Mesh slots are local to this window. Repeated placements of
 * the same sector mesh all point to its first copy. */
static int resident_slot(SectorWindow *w, unsigned id)
{
    uint8_t *cs = w->cs;
    unsigned count = DS_U16(cs, LOCAL_COUNT);
    unsigned slot = 0;
    while (slot < count && DS_U16(cs, LOCAL_IDS + 2 * slot) != id)
        ++slot;
    if (slot == count) {
        if (id >= DS_U16(w->source, 0) || count >= (SOURCE_MESH - LOCAL_IDS) / 2)
            return -1;
        unsigned source = DS_U16(cs, SOURCE_MESH + 2 * id);
        unsigned dest = DS_U16(cs, PACKED), size = 2 + DS_U16(w->source, source);
        if (dest + size > UINT16_MAX)
            return -1;
        memcpy(w->cells + dest, w->source + source, size);
        DS_U16(cs, PACKED) = dest + size;
        DS_U16(cs, LOCAL_IDS + 2 * slot) = id;
        DS_U16(cs, NEXT_ID) += 2;
        ++DS_U16(cs, LOCAL_COUNT);
        ++DS_U16(cs, ADDED);
    }
    return DS_U16(cs, FIRST_SLOT) + slot;
}

/* 0E2D. The 32-bit positions in a BIG are relative to the sector. */
static int ground_list(SectorWindow *w, unsigned relative, unsigned cell)
{
    uint8_t *cs = w->cs, *source = w->source, *ground = w->ground;
    unsigned list = DS_U16(cs, TAIL) + relative, dest = DS_U16(cs, LIST_END);
    if (list + 2 > w->size)
        return -1;
    unsigned count = DS_U16(source, list), size = 2 + 14 * count;
    if (!count || list + size > w->size || dest + size > UINT16_MAX)
        return -1;
    DS_U16(ground, cell) = dest;
    memcpy(ground + dest, source + list, size);
    DS_U16(cs, LIST_END) = dest + size;
    for (unsigned i = 0, at = dest + 2; i < count; ++i, at += 14) {
        write32(ground, at, read32(ground, at) + read32(cs, WORLD_X));
        write32(ground, at + 8, read32(ground, at + 8) + read32(cs, WORLD_Z));
        int slot = resident_slot(w, DS_U16(ground, at + 12));
        if (slot < 0)
            return -1;
        DS_U16(ground, at + 12) = slot;
    }
    return 0;
}

static int ground_quadrant(SectorWindow *w)
{
    uint8_t *cs = w->cs, *ds = w->game->ds;
    DS_U16(cs, LOCAL_COUNT) = 0;
    DS_U16(cs, NEXT_ID) = LOCAL_IDS;
    if (read_sector(w, 0x5E40) || w->size < 2)
        return -1;
    unsigned count = DS_U16(w->source, 0), tail = 2;
    if (count > (TAIL - SOURCE_MESH) / 2)
        return -1;
    for (unsigned i = 0; i < count; ++i) {
        if (tail + 2 > w->size)
            return -1;
        DS_U16(cs, SOURCE_MESH + 2 * i) = tail;
        tail += 2 + DS_U16(w->source, tail);
    }
    if (tail + 260 > w->size)
        return -1;
    DS_U16(cs, TAIL) = tail;
    unsigned grid = tail + 4 + 32 * DS_U16(ds, 0x726E) + 4 * DS_U16(ds, 0x726C);
    unsigned dest = DS_U16(ds, 0x7266) + DS_U16(ds, 0x7268);
    for (unsigned row = 0; row < DS_U16(ds, 0x7264); ++row) {
        for (unsigned col = 0; col < DS_U16(ds, 0x7262); ++col) {
            unsigned entry = grid + 32 * row + 4 * col, cell = dest + 12 * row + 4 * col;
            unsigned relative = DS_U16(w->source, entry);
            if (relative && ground_list(w, relative, cell))
                return -1;
            /* 0E83 is a second, independent list format. No installed
             * sector uses it (all 384 pointers are zero). */
            if (DS_U16(w->source, entry + 2))
                return -1;
        }
    }
    return 0;
}

static int street_quadrant(SectorWindow *w)
{
    uint8_t *ds = w->game->ds, *cs = w->cs;
    if (read_sector(w, 0x5E45) || w->size < 4 + 8192)
        return -1;
    unsigned grid = 4 + 1024 * DS_U16(ds, 0x726E) + 16 * DS_U16(ds, 0x726C);
    unsigned dest = DS_U16(ds, 0x7266) + DS_U16(ds, 0x7268);
    unsigned end = DS_U16(cs, LIST_END);
    for (unsigned row = 0; row < 8u * DS_U16(ds, 0x7264); ++row) {
        for (unsigned col = 0; col < 8u * DS_U16(ds, 0x7262); ++col) {
            unsigned list = DS_U16(w->source, grid + 128 * row + 2 * col);
            if (!list)
                continue;
            if (list + 2 > w->size)
                return -1;
            unsigned size = 2 + 12 * w->source[list]; /* 107F uses MUL CL */
            if (list + size > w->size || end + size > UINT16_MAX)
                return -1;
            DS_U16(w->cells, dest + 48 * row + 2 * col) = end;
            memcpy(w->cells + end, w->source + list, size);
            end += size;
        }
    }
    DS_U16(cs, LIST_END) = end;
    if (end > DS_U16(cs, MAX_CELLS))
        DS_U16(cs, MAX_CELLS) = end;
    return 0;
}

/* 0BE0 visits NW, NE, SW, SE in that order for each file type. */
static int pack_quadrants(SectorWindow *w, int streets)
{
    uint8_t *ds = w->game->ds, *cs = w->cs;
    split_axis(w, 0);
    split_axis(w, 1);
    DS_U16(cs, COL_STRIDE) = streets ? 16 : 4;
    DS_U16(cs, ROW_STRIDE) = streets ? 384 : 12;
    DS_U16(cs, PACK_SEG) = DS_U16(ds, DS_SEG_CELLS);
    DS_U16(cs, PACKED) = DS_U16(cs, ADDED) = 0;
    for (unsigned south = 0; south < 2; ++south) {
        unsigned z = DS_U8(ds, 0x5CE0 + south);
        if (z == 255)
            continue;
        for (unsigned east = 0; east < 2; ++east) {
            unsigned x = DS_U8(ds, 0x5CDE + east);
            if (x == 255)
                continue;
            DS_U16(cs, FIRST_SLOT) += DS_U16(cs, ADDED);
            DS_U16(cs, ADDED) = 0;
            write32(cs, WORLD_X, read32(cs, X_ORIGINS + 4 * east));
            write32(cs, WORLD_Z, read32(cs, Z_ORIGINS + 4 * south));
            DS_U16(ds, 0x726C) = east ? 0 : DS_U16(ds, 0x7256);
            DS_U16(ds, 0x726E) = south ? 0 : DS_U16(ds, 0x7258);
            DS_U16(ds, 0x7262) = DS_U16(ds, 0x725A + 2 * east);
            DS_U16(ds, 0x7264) = DS_U16(ds, 0x725E + 2 * south);
            DS_U16(ds, 0x7266) = east * DS_U16(ds, 0x725A) * DS_U16(cs, COL_STRIDE);
            DS_U16(ds, 0x7268) = south * DS_U16(ds, 0x725E) * DS_U16(cs, ROW_STRIDE);
            DS_U16(ds, 0x726A) = (x << 8) | z;
            if (streets ? street_quadrant(w) : ground_quadrant(w))
                return -1;
        }
    }
    return 0;
}

int load_window_ground_and_cells(Game *g, const ImageIO *files)
{
    if (!files || !files->call)
        return -1;
    uint8_t *ds = g->ds;
    SectorWindow w = {g,
                      files,
                      far_ptr(g, g->ds_seg - 0x5C27 + 0x11BC, 0),
                      far_ptr(g, DS_U16(ds, DS_SEG_GROUND), 0),
                      far_ptr(g, DS_U16(ds, DS_SEG_CELLS), 0),
                      far_ptr(g, DS_U16(ds, 0x94DE), 0),
                      0};
    memset(w.ground, 0, 36);
    DS_U16(w.cs, FIRST_SLOT) = 0;
    DS_U16(w.cs, LIST_END) = 36;
    if (pack_quadrants(&w, 0))
        return -1;
    unsigned base = DS_U16(w.cs, LIST_END), packed = DS_U16(w.cs, PACKED);
    if (base + packed > UINT16_MAX)
        return -1;
    DS_U16(ds, 0x727E) = base;
    memcpy(w.ground + base, w.cells, packed);
    /* 0AC6/10D4. Only the final ground copy changes Z convention. The
     * lookup table stores offsets from the mesh base, before the SCT pass
     * reuses the temporary buffer for the 24x24 street grid. */
    for (unsigned at = 0, i = 0; at < packed; ++i) {
        unsigned size = DS_U16(w.cells, at) + 2, n = DS_U16(w.cells, at + 6);
        unsigned vertices = 2 + DS_U16(w.cells, at + 10);
        if (size < 18 || at + size > packed || vertices + 6 * n > size)
            return -1;
        DS_U16(ds, 0x92DA + 2 * i) = at;
        for (unsigned j = 0; j < n; ++j) {
            unsigned z = base + at + vertices + 6 * j + 4;
            DS_U16(w.ground, z) = -DS_U16(w.ground, z);
        }
        at += size;
    }
    if (base + packed > DS_U16(w.cs, MAX_GROUND))
        DS_U16(w.cs, MAX_GROUND) = base + packed;
    memset(w.cells, 0, 1152);
    DS_U16(w.cs, LIST_END) = 1152;
    return pack_quadrants(&w, 1);
}
