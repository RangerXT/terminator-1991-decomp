/* Setting up a session (called from the program's start, 0000:0000, before each game). */
#include <string.h>

#include "term.h"

/* orig 0000:0B12   clear the actors and their tables, copy the start values, clear the
 * statistics. It then means to fill the removed-objects list (DS:0F70, SI) with FFFF but
 * stores through DI, which ratings_clear_stats left at 039F: 32 words from DS:039F
 * (0B4E sets 03A0..03A8 again right after). */
void session_reset(Game *g)
{
    uint8_t *ds = g->ds;
    memset(ds + 0x04D4, 0, 0x0CCE);
    memmove(ds + 0x11A2, ds + 0x11CE, 0x2C);
    uint8_t *to = far_ptr(g, DS_U16(ds, 0x120A), 0);
    for (uint16_t i = 0, at = DS_U16(ds, 0x1208); i < 0x3C; ++i)
        to[(uint16_t)(at + i)] = DS_U8(ds, (uint16_t)(0x11FA + i));
    to = far_ptr(g, DS_U16(ds, 0x1202), 0);
    for (uint16_t i = 0, at = DS_U16(ds, 0x1200); i < 0xC4; ++i)
        to[(uint16_t)(at + i)] = DS_U8(ds, (uint16_t)(0x1236 + i));
    ratings_clear_stats(ds);
    for (uint16_t i = 0; i < 0x20; ++i)
        DS_U16(ds, (uint16_t)(0x039F + i * 2)) = 0xFFFF;
}

/* orig 0000:0B4E   the record pointers: Reese, the item list, figures, removed objects, and
 * DS:03A8 from the level (DS:1176, 11 bytes each; level 6 like 0) */
void session_pointers(uint8_t *ds)
{
    DS_U16(ds, DS_PLAYER) = 0x04D4;
    DS_U16(ds, DS_INVENTORY_END) = 0x05B0;
    DS_U16(ds, 0x03A4) = 0x0DF0;
    DS_U16(ds, 0x03A6) = 0x0F70;
    uint16_t level = DS_U16(ds, 0x1176);
    DS_U16(ds, 0x03A8) = level == 6 ? 0x03AA : (uint16_t)((uint8_t)level * 0x0B + 0x03AA); /* MUL CL: AL only */
}

/* orig 0000:0B80   (no caller found) the drawing page from the 640-wide page table */
void session_draw_page_wide(uint8_t *ds, uint16_t page)
{
    DS_U16(ds, DS_PAGE_DRAWN) = page;
    DS_U16(ds, DS_DRAW_PAGE) = DS_U16(ds, (uint16_t)(0x1244 + page * 2));
}

/* orig 0000:1483   the row table: 350 rows of 40 bytes */
void session_row_table(uint8_t *ds)
{
    for (uint16_t i = 0; i < 0x15E; ++i)
        DS_U16(ds, (uint16_t)(0x1252 + i * 2)) = (uint16_t)(i * 0x28);
}

/* orig 0000:057C   after a fast travel (and at the start): as Reese, the companion goes with
 * him - Reese's record copied to the companion's (DS:053C), its time + 50 */
void session_arrival_followup(uint8_t *ds)
{
    if (DS_U16(ds, DS_PLAYER) == 0x04D4)
        DS_U8(ds, 0x1154) = 0xFF;
    memmove(ds + 0x053C, ds + 0x04D4, 0x34);
    uint32_t time = (uint32_t)DS_U16(ds, 0x055E) | (uint32_t)DS_U16(ds, 0x0560) << 16;
    time += 0x32;
    DS_U16(ds, 0x055E) = (uint16_t)time;
    DS_U16(ds, 0x0560) = (uint16_t)(time >> 16);
    position_normalize_companion(ds);
}

/* orig 0000:97BF   an empty item list */
void session_clear_items(uint8_t *ds)
{
    DS_U16(ds, DS_INVENTORY_END) = 0x05B0;
    memset(ds + 0x05B0, 0, (uint16_t)(0x13 * 6 * 3) * 2);
}

/* orig 0000:9845 */
void session_clear_flags(uint8_t *ds)
{
    memset(ds + 0xAA96, 0, 0x23);
    DS_U16(ds, 0x0384) = 0;
    DS_U16(ds, 0x11C0) = 0x320;
}

/* orig 0000:97B4   x and z of the record at `from` to `to` */
void point_copy(uint8_t *ds, uint16_t from, uint16_t to)
{
    DS_U16(ds, to) = DS_U16(ds, from);
    DS_U16(ds, (uint16_t)(to + 2)) = DS_U16(ds, (uint16_t)(from + 4));
}

/* orig 0000:168E (with 11BC:2A5E)   the 8x8 font (DS:1536) into far DS:155A; its segment goes
 * into the code words 0000:16A7 and 11BC:2A63, where the text routines read it */
int font8_load(Game *g, const ImageIO *images)
{
    uint8_t *ds = g->ds;
    uint16_t off = DS_U16(ds, 0x155A), seg = DS_U16(ds, 0x155C), code = (uint16_t)(g->ds_seg - 0x5C27);
    uint8_t *word = far_ptr(g, code, 0x16A7);
    word[0] = (uint8_t)seg;
    word[1] = (uint8_t)(seg >> 8);
    word = far_ptr(g, (uint16_t)(code + 0x11BC), 0x2A63);
    word[0] = (uint8_t)seg;
    word[1] = (uint8_t)(seg >> 8);
    return file_load(g, images, 0x1536, seg, off) == UINT32_MAX ? -1 : 0;
}

/* orig 11BC:11ED   the slot of the record's DEF number (byte +6) in the loaded list DS:5DC0
 * into its word +0, FFFF when it is not there; nothing when the list is empty */
void def_slot_of(uint8_t *ds, uint16_t record)
{
    uint16_t count = DS_U16(ds, 0x72B4);
    if (!count)
        return;
    uint8_t id = DS_U8(ds, (uint16_t)(record + 6));
    for (uint16_t i = 0; i < count; ++i)
        if (DS_U8(ds, (uint16_t)(0x5DC0 + i)) == id) {
            DS_U16(ds, record) = i;
            return;
        }
    DS_U16(ds, record) = 0xFFFF;
}

/* orig 0000:CA1A   (at start-up) the file DS:E00E into DS:E01A, and its 160 bytes from E02A
 * with the nibbles swapped into E0CA */
int session_load_swapped(Game *g, const ImageIO *images)
{
    uint8_t *ds = g->ds;
    if (file_load(g, images, 0xE00E, g->ds_seg, 0xE01A) == UINT32_MAX)
        return -1;
    for (uint16_t i = 0; i < 0xA0; ++i) {
        uint8_t v = DS_U8(ds, (uint16_t)(0xE02A + i));
        DS_U8(ds, (uint16_t)(0xE0CA + i)) = (uint8_t)(v >> 4 | v << 4);
    }
    return 0;
}

/* orig 0000:E475   (at start-up) DS:E435 = 0; the file DS:E41E into far DS:E520 and far
 * pointers to its eight records (16-byte headers, word +0Eh the size after them) at DS:E500;
 * the file DS:E42A into far DS:E524 */
int session_load_records(Game *g, const ImageIO *images)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0xE435) = 0;
    uint16_t seg = DS_U16(ds, 0xE522);
    if (file_load(g, images, 0xE41E, seg, DS_U16(ds, 0xE520)) == UINT32_MAX)
        return -1;
    const uint8_t *data = far_ptr(g, seg, 0);
    uint16_t at = 0;
    for (uint16_t i = 0; i < 8; ++i) {
        DS_U16(ds, (uint16_t)(0xE500 + i * 4)) = at;
        DS_U16(ds, (uint16_t)(0xE502 + i * 4)) = seg;
        at = (uint16_t)(at + (data[(uint16_t)(at + 0x0E)] | data[(uint16_t)(at + 0x0F)] << 8) + 0x10);
    }
    return file_load(g, images, 0xE42A, DS_U16(ds, 0xE526), DS_U16(ds, 0xE524)) == UINT32_MAX ? -1 : 0;
}

/* orig 0000:1AC9   (at start-up) five pictures (the name at DS:1550, its fourth letter counted
 * up each time and left so): each read into far DS:155A, unpacked after a copy of its
 * 16-byte header at far DS:120C, which then moves past it; their places at DS:1216. Then the
 * 8x8 font (168E). */
int session_load_pictures(Game *g, const ImageIO *images)
{
    uint8_t *ds = g->ds;
    for (uint16_t i = 0; i < 5; ++i) {
        uint16_t from_seg = DS_U16(ds, 0x155C), from = DS_U16(ds, 0x155A);
        if (file_load(g, images, 0x1550, from_seg, from) == UINT32_MAX)
            return -1;
        uint16_t to_seg = DS_U16(ds, 0x120E), to = DS_U16(ds, 0x120C), size;
        if (image_unpack_compressed(g, from_seg, from, to_seg, (uint16_t)(to + 0x10), &size) < 0)
            return -1;
        const uint8_t *header = far_ptr(g, from_seg, 0);
        uint8_t *dest = far_ptr(g, to_seg, 0);
        for (uint16_t n = 0; n < 0x10; ++n)
            dest[(uint16_t)(to + n)] = header[(uint16_t)(from + n)];
        DS_U16(ds, 0x120C) = (uint16_t)(to + size + 0x10);
        DS_U16(ds, (uint16_t)(0x1216 + i * 2)) = to;
        DS_U8(ds, 0x1553)++;
    }
    return font8_load(g, images);
}

/* orig 0000:F879 (with F654)   the random generator's state from the BIOS tick count 0:46C,
 * the low bit set */
void random_seed_from_clock(Game *g)
{
    const uint8_t *ticks = g->mem + 0x46C;
    DS_U16(g->ds, 0xEA42) = (uint16_t)((ticks[0] | ticks[1] << 8) | 1);
    DS_U16(g->ds, 0xEA44) = (uint16_t)(ticks[2] | ticks[3] << 8);
}
