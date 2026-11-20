/* Build the resident object meshes and gameplay lists for a 24x24 city window. */
#include "term.h"

static uint16_t get_word(Game *g, uint16_t seg, uint16_t off)
{
    return *far_ptr(g, seg, off) | ((uint16_t)*far_ptr(g, seg, (uint16_t)(off + 1)) << 8);
}

static void put_word(Game *g, uint16_t seg, uint16_t off, uint16_t v)
{
    *far_ptr(g, seg, off) = (uint8_t)v;
    *far_ptr(g, seg, (uint16_t)(off + 1)) = v >> 8;
}

static void put_long(Game *g, uint16_t seg, uint16_t off, uint32_t value)
{
    put_word(g, seg, off, (uint16_t)value);
    put_word(g, seg, off + 2, (uint16_t)(value >> 16));
}

static uint32_t origin(Game *g, uint16_t at)
{
    return DS_U16(g->ds, at) | ((uint32_t)DS_U16(g->ds, at + 2) << 16);
}

/* 1386: register the three drivable models and four shop markers. */
static void special_object(Game *g, uint16_t seg, uint16_t rec, uint16_t id)
{
    uint8_t *ds = g->ds;
    uint16_t x = get_word(g, seg, rec), z = get_word(g, seg, rec + 4);
    uint32_t east = origin(g, 0x72D2) + x, south = origin(g, 0x72D6) + (uint16_t)(1024 - z);
    if (id == 10 || id == 100 || id == 74) {
        if ((int16_t)get_word(g, seg, rec + 10) < 0 || DS_U16(ds, DS_VEHICLE_COUNT) >= 249)
            return;
        *far_ptr(g, seg, rec + 11) = ((x >> 2) | (x >> 9) | (z >> 2)) & 3;
        uint16_t table = DS_U16(ds, 0x72B8), dest = DS_U16(ds, 0x72B6);
        put_word(g, table, dest + 12, id == 10 ? 0 : id == 100 ? 2 : 4);
        put_long(g, table, dest, east);
        put_long(g, table, dest + 4, south);
        put_word(g, table, dest + 10, rec);
        uint16_t flags = *far_ptr(g, seg, rec + 6) | ((uint16_t)*far_ptr(g, seg, rec + 10) << 8);
        if (!(random_word(ds) & 7))
            flags |= 0x8000;
        put_word(g, table, dest + 8, flags);
        DS_U16(ds, 0x72B6) += 14;
        ++DS_U16(ds, DS_VEHICLE_COUNT);
        return;
    }
    uint16_t kind;
    switch (id) {
    case 31:
        kind = 1;
        break;
    case 24:
        kind = 2;
        break;
    case 89:
        kind = 3;
        break;
    case 113:
        kind = 4;
        break;
    default:
        return;
    }
    uint16_t dest = DS_U16(ds, 0x72BE);
    put_long(g, g->ds_seg, dest, east);
    put_long(g, g->ds_seg, dest + 4, south);
    DS_U16(ds, dest + 8) = kind;
    DS_U8(ds, dest + 10) = random_word(ds) >= DS_U16(ds, 0x74AC + 2 * DS_U16(ds, DS_DIFFICULTY));
    dest += 11;
    for (unsigned k = 0; k < 8; k += 2)
        DS_U16(ds, dest + k) = 0;
    DS_U16(ds, 0x72BE) = dest;
    ++DS_U16(ds, DS_SHOP_COUNT);
}

static void prepare_records(Game *g, uint16_t seg, uint16_t list)
{
    if (!list)
        return;
    uint8_t *ds = g->ds;
    uint16_t n = get_word(g, seg, list), rec = list + 2;
    for (; n; --n, rec += 12) {
        uint16_t id = get_word(g, seg, rec + 8);
        *far_ptr(g, seg, rec + 10) = DS_U8(ds, 0x5EFA + (uint8_t)id);
        special_object(g, seg, rec, id);
        uint16_t count = DS_U16(ds, DS_LOADED_DEF_COUNT), slot = 0;
        while (slot < count && DS_U8(ds, 0x5DC0 + slot) != (uint8_t)id)
            ++slot;
        if (slot == count) {
            DS_U8(ds, 0x5DC0 + slot) = (uint8_t)id;
            ++DS_U16(ds, DS_LOADED_DEF_COUNT);
        }
        put_word(g, seg, rec + 8, slot);
    }
}

static void copy_bytes(Game *g, uint16_t from, uint16_t at, uint16_t to, uint16_t dest, uint16_t size)
{
    for (unsigned i = 0; i < size; ++i)
        *far_ptr(g, to, (uint16_t)(dest + i)) = *far_ptr(g, from, (uint16_t)(at + i));
}

/* 1317/1358: the first size includes itself. MUL DL uses byte dimensions. */
static uint16_t bitmap_size(Game *g, uint16_t seg, uint16_t at)
{
    uint16_t size = get_word(g, seg, at);
    uint16_t flag = at + size;
    size += 2;
    if (get_word(g, seg, flag)) {
        uint16_t bits = (uint8_t)get_word(g, seg, flag + 10) * (uint8_t)get_word(g, seg, flag + 12);
        size += 12 + ((uint16_t)(bits + 7) >> 3);
    }
    return size;
}

/* 1117. Slots follow first appearance in row-major order. The original then
 * processes a short list of mandatory records before copying LA.DEF and LA.BMP. */
int load_window_objects(Game *g, const ImageIO *files)
{
    uint8_t *ds = g->ds;
    uint16_t work = DS_U16(ds, DS_FILE_BUFFER_SEG), work_off = DS_U16(ds, DS_FILE_BUFFER);
    if (file_load(g, files, 0x5E53, work, work_off) == UINT32_MAX)
        return -1;
    DS_U16(ds, DS_VEHICLE_COUNT) = DS_U16(ds, 0x72B6) = DS_U16(ds, DS_SHOP_COUNT) = DS_U16(ds, DS_LOADED_DEF_COUNT) = 0;
    DS_U16(ds, 0x72BE) = 0x5CE4;
    uint16_t cells = DS_U16(ds, DS_SEG_CELLS);
    uint32_t x0 = origin(g, 0x72D2);
    for (unsigned row = 0; row < 24; ++row) {
        for (unsigned col = 0; col < 24; ++col) {
            prepare_records(g, cells, get_word(g, cells, 2 * (row * 24 + col)));
            put_long(g, g->ds_seg, 0x72D2, origin(g, 0x72D2) + 1024);
        }
        put_long(g, g->ds_seg, 0x72D6, origin(g, 0x72D6) + 1024);
        put_long(g, g->ds_seg, 0x72D2, x0);
    }
    prepare_records(g, g->ds_seg, 0x746C);
    --DS_U16(ds, DS_VEHICLE_COUNT);
    const uint16_t ids[] = {10, 100, 74, 79};
    for (unsigned i = 0; i < 4; ++i) {
        uint16_t rec = 0x746E + 12 * i;
        if (i < 3)
            DS_U16(ds, 0x72CA + 2 * i) = DS_U16(ds, rec + 8);
        else
            DS_U8(ds, 0x5EE3) = (uint8_t)DS_U16(ds, rec + 8);
        DS_U16(ds, rec + 8) = ids[i];
    }
    uint16_t count = DS_U16(ds, DS_LOADED_DEF_COUNT), obj = DS_U16(ds, DS_SEG_OBJECTS), dest = 0;
    uint16_t code = g->ds_seg - 0x5C27 + 0x11BC;
    for (unsigned i = 0; i < count; ++i) {
        uint16_t at = 2, id = DS_U8(ds, 0x5DC0 + i);
        for (unsigned j = 0; j < id; ++j)
            at += 2 + get_word(g, work, at);
        uint16_t body = get_word(g, work, at);
        DS_U16(ds, 0x91DA + 2 * i) = dest;
        copy_bytes(g, work, at, obj, dest, body + 2);
        dest += body + 2;
        if (dest > get_word(g, code, 0x094C))
            put_word(g, code, 0x094C, dest);
    }
    DS_U16(ds, 0x94DA) = dest;
    for (unsigned i = 0; i < count; ++i) {
        uint16_t body = DS_U16(ds, 0x91DA + 2 * i) + 2;
        uint16_t v = body + get_word(g, obj, body + 8), n = get_word(g, obj, body + 4);
        int16_t lowest = 30000;
        do {
            int16_t y = get_word(g, obj, v + 2);
            if (y < lowest)
                lowest = y;
            v += 6;
        } while (--n);
        DS_U16(ds, 0x75EC + 2 * i) = lowest;
    }
    if (file_load(g, files, 0x8656, work, work_off) == UINT32_MAX)
        return -1;
    uint16_t bmp = DS_U16(ds, 0x91B0);
    put_word(g, bmp, 0, count);
    dest = 2;
    for (unsigned i = 0; i < count; ++i) {
        uint16_t at = 2, id = DS_U8(ds, 0x5DC0 + i);
        for (unsigned j = 0; j < id; ++j)
            at += bitmap_size(g, work, at);
        uint16_t size = bitmap_size(g, work, at);
        copy_bytes(g, work, at, bmp, dest, size);
        DS_U16(ds, 0x8FEC + 2 * i) = dest;
        dest += size;
    }
    for (uint16_t entry = 0x72A4; entry <= 0x72A8; entry += 2) {
        uint16_t id = DS_U8(ds, entry + 6), slot = 0;
        while (slot < count && DS_U8(ds, 0x5DC0 + slot) != id)
            ++slot;
        if (count)
            DS_U16(ds, entry) = slot < count ? slot : 0xFFFF;
    }
    return 0;
}
