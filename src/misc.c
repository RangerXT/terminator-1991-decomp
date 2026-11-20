/* Small routines the static scan finds no caller for but whose address does occur in the
 * executable as data, so that a table may reach them. Each matches the original when called
 * directly (tests/test_misc.py). */
#include "term.h"

/* orig 0000:4344   AX through far DS:1204 (the pointer is not moved) */
void misc_store_1204(Game *g, uint16_t ax)
{
    uint8_t *to = far_ptr(g, DS_U16(g->ds, 0x1206), 0);
    uint16_t at = DS_U16(g->ds, 0x1204);
    to[at] = (uint8_t)ax;
    to[(uint16_t)(at + 1)] = (uint8_t)(ax >> 8);
}

/* orig 0000:A075 */
void misc_mark_record(uint8_t *ds, uint16_t record)
{
    DS_U16(ds, (uint16_t)(record + 6)) = 0xFFFF;
}

/* orig 0000:C20B   |AX - DS:DE50| in AX; carry (bit 16) when it is under 80h or 180h and more */
uint32_t misc_band_test(const uint8_t *ds, uint16_t ax)
{
    uint16_t d = (uint16_t)(ax - DS_U16(ds, 0xDE50));
    if ((int16_t)d < 0)
        d = (uint16_t)-d;
    int carry = d < 0x80 || d >= 0x180;
    return d | (uint32_t)carry << 16;
}

/* orig 0000:ACE1   the figure records (6 words each at DS:0DF0) onto the draw list */
void misc_append_figures(uint8_t *ds)
{
    uint16_t count = DS_U16(ds, DS_FIGURE_COUNT);
    if (!count)
        return;
    DS_U16(ds, 0x50AC) = (uint16_t)(DS_U16(ds, 0x50AC) + count);
    uint16_t from = 0x0DF0, to = DS_U16(ds, 0x9156);
    for (uint16_t n = (uint16_t)(count * 6); n; --n, from = (uint16_t)(from + 2), to = (uint16_t)(to + 2))
        DS_U16(ds, to) = DS_U16(ds, from);
    DS_U16(ds, 0x9156) = to;
}

/* orig 0000:9BA6   read characters from DS:at until one is in the list DS:ADB6 (count
 * DS:ADD4, the scan one longer than the list); store it one before where it was found (at
 * the list's start when the list is empty), count it. Returns AX = (characters read - 1) <<
 * 8 | the character; *end is where the last one was read. */
uint16_t misc_collect_char(uint8_t *ds, uint16_t at, uint16_t *end)
{
    uint16_t start = at, to;
    uint8_t ch;
    for (;;) {
        ch = DS_U8(ds, at++);
        uint16_t count = DS_U16(ds, 0xADD4);
        to = 0xADB6;
        if (!count)
            break;
        uint16_t cx = (uint16_t)(count + 1);
        while (cx) { /* REPNE SCASB */
            cx--;
            if (DS_U8(ds, to++) == ch)
                break;
        }
        if (cx) { /* JCXZ: on to the next character when CX ran out */
            to = (uint16_t)(to - 2);
            break;
        }
    }
    DS_U8(ds, to) = ch;
    DS_U16(ds, 0xADD4)++;
    at--;
    *end = at;
    return (uint16_t)((uint8_t)(at - start) << 8 | ch);
}

/* orig 0000:DF00   the record's 32-bit x and z from the player's cell (words +1E, +20) times
 * 400h, plus AX and 400h - BX */
void misc_cell_position(uint8_t *ds, uint16_t record, uint16_t ax, uint16_t bx)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    uint32_t x = (uint32_t)DS_U16(ds, (uint16_t)(player + 0x1E)) * 0x400 + (uint32_t)(int32_t)(int16_t)ax;
    uint32_t z = (uint32_t)DS_U16(ds, (uint16_t)(player + 0x20)) * 0x400
                 + (uint32_t)(int32_t)(int16_t)(uint16_t)(0x400 - bx);
    DS_U16(ds, (uint16_t)(record + 0x22)) = (uint16_t)x;
    DS_U16(ds, (uint16_t)(record + 0x24)) = (uint16_t)(x >> 16);
    DS_U16(ds, (uint16_t)(record + 0x2A)) = (uint16_t)z;
    DS_U16(ds, (uint16_t)(record + 0x2C)) = (uint16_t)(z >> 16);
}

/* orig 0000:9A01   four frame lines in colour 15 from the table DS:ABEC */
void misc_frame_lines_abec(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_FILL_COLOUR) = 0x0F;
    for (uint16_t at = 0xABEC; at < 0xABEC + 32; at = (uint16_t)(at + 8)) {
        DS_U16(ds, DS_PEN_X) = DS_U16(ds, at);
        DS_U16(ds, DS_PEN_Y) = DS_U16(ds, (uint16_t)(at + 2));
        area_line_to(ds, g->planes, DS_U16(ds, (uint16_t)(at + 4)), DS_U16(ds, (uint16_t)(at + 6)));
    }
}
