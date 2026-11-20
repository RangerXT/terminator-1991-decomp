/* The closing credits (0000:91EA, after quitting): the credits text scrolls up on the
 * 640x350 screen (mode 10h) by moving the display start one row every two frames; every 12
 * rows a new line is written below the visible part, and at 360 rows the screen wraps back.
 * A key ends it.
 */
#include "term.h"

enum {
    CR_ROWS = 0xA9CB,    /* u8: rows scrolled since the last line */
    CR_TOTAL = 0xA9CC,   /* u16: rows scrolled since the last wrap */
    CR_NEXT = 0xA9CE,    /* u16: the next line of the text */
    CR_START = 0xA9D0,   /* u16: the display start */
    CR_WORDS = 0xA9D2,   /* u16: words in the line being written */
    CR_X = 0xA9D4,       /* u16: x of the next character */
    CR_ENDING = 0xA9C2,  /* u8: rows to go after the text's end (FF: over) */
    CR_TEXT = 0x1576,    /* the credits file, NUL after it */
    CR_LINE = 0x7795,    /* the words: x, then the word with NUL */
};

static int call(Game *g, const CreditsServices *host, uint16_t op, uint16_t a)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, 0, r->user) ? -1 : 0;
}

/* orig 0000:9380   one line of the text from `at` into words at DS:7795 (each its x, its
 * letters, NUL; x counts 8 a character, two spaces end a word, a single one stays in
 * it, LF is a space); returns where the next line starts. A line that starts with CR
 * (an empty one) is just skipped. */
static uint16_t split_line(uint8_t *ds, uint16_t at)
{
    uint16_t to = CR_LINE;
    for (;;) {
        if (DS_U8(ds, at) == 0x0D)
            return (uint16_t)(at + 2);
        DS_U16(ds, CR_X) = (uint16_t)(DS_U16(ds, CR_X) + 8);
        if (DS_U8(ds, at) == ' ') {
            at++;
            continue;
        }
        break;
    }
    for (;;) { /* 9397: a word */
        DS_U16(ds, to) = DS_U16(ds, CR_X);
        to = (uint16_t)(to + 2);
        DS_U16(ds, CR_WORDS)++;
        for (;;) {
            uint8_t ch = DS_U8(ds, at++);
            if (ch == ' ' && DS_U8(ds, at) == ' ') { /* two spaces end a word */
                DS_U8(ds, to++) = 0;
                DS_U16(ds, CR_X) = (uint16_t)(DS_U16(ds, CR_X) + 8);
                break;
            }
            if (ch == 0x0A)
                ch = ' ';
            if (ch == 0x0D) { /* the LF after it is skipped too */
                DS_U8(ds, to++) = 0;
                return (uint16_t)(at + 1);
            }
            DS_U8(ds, to++) = ch;
            DS_U16(ds, CR_X) = (uint16_t)(DS_U16(ds, CR_X) + 8);
        }
    }
}

/* orig 0000:9320   the next line at y = DS:1230, or the countdown after the last */
static void write_line(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t at = DS_U16(ds, CR_NEXT);
    if (!DS_U8(ds, at)) {
        DS_U8(ds, CR_ENDING) = 0x0C;
        return;
    }
    DS_U16(ds, CR_X) = 0;
    DS_U16(ds, CR_WORDS) = 0;
    DS_U16(ds, CR_NEXT) = split_line(ds, at);
    uint16_t word = CR_LINE;
    for (uint16_t n = DS_U16(ds, CR_WORDS); n; --n) {
        uint16_t x = DS_U16(ds, word);
        word = (uint16_t)(word + 2);
        font_text(g, x, DS_U16(ds, DS_PEN_Y), word);
        while (DS_U8(ds, word))
            word++;
        word++;
    }
}

/* orig 0000:92FE   clear the 12 rows below the visible part (set/reset 0) */
static void clear_band(Game *g)
{
    uint8_t *p = g->planes;
    ega_gc(p, 1, 0x0F);
    ega_gc(p, 0, 0);
    uint16_t at = (uint16_t)(DS_U16(g->ds, CR_START) + 0x7080);
    for (unsigned i = 0; i < 0x3C0; ++i)
        ega_store(p, at++, 0);
    ega_gc(p, 1, 0);
}

/* orig 0000:91EA */
int credits_screen(Game *g, const CreditsServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    DS_U8(ds, DS_TEXT_COLOUR) = 0x0F;
    map_clear_key_buffer(ds);
    if (call(g, host, MS_VIDEO_MODE, 0x10) < 0 || font_load(g, host->images, 0x7A49) < 0)
        return -1;
    font_scale(g, 0x0C0C, 0x0C0C, 0x46, DS_U16(ds, 0xADE6), DS_U16(ds, 0xADFE));
    DS_U8(ds, CR_ROWS) = 0;
    DS_U16(ds, CR_TOTAL) = 0;
    DS_U16(ds, CR_START) = 0;
    DS_U8(ds, CR_ENDING) = 0;
    DS_U16(ds, 0x1228) = 0x50;
    DS_U16(ds, DS_SCREEN_STRIDE) = 0x50;
    uint32_t length = file_load(g, host->images, 0xA9C3, g->ds_seg, CR_TEXT); /* 9368 */
    if (length == UINT32_MAX)
        return -1;
    DS_U8(ds, (uint16_t)(CR_TEXT + (uint16_t)length)) = 0;
    DS_U16(ds, CR_NEXT) = CR_TEXT;
    while (!DS_U8(ds, DS_KEYBUF_COUNT)) {
        if (call(g, host, 0x0D8D, 0) < 0 || call(g, host, 0x0DAA, 0) < 0 || call(g, host, 0x0D8D, 0) < 0
            || call(g, host, 0x0DAA, 0) < 0)
            return -1;
        DS_U16(ds, CR_START) = (uint16_t)(DS_U16(ds, CR_START) + 0x50); /* 9294 */
        DS_U8(ds, CR_ROWS)++;
        DS_U16(ds, CR_TOTAL)++;
        if (call(g, host, PB_SET_DISPLAY_START, DS_U16(ds, CR_START)) < 0)
            return -1;
        if (DS_U8(ds, CR_ROWS) < 0x0C)
            continue;
        DS_U8(ds, CR_ROWS) = 0;
        uint16_t to = (uint16_t)(DS_U16(ds, CR_START) - 0x3C0); /* 92BF: the band above, for the wrap */
        screen_copy_rect(g, (uint16_t)(to + 0x7080), to, 0x50, 0x0C);
        if (DS_U16(ds, CR_TOTAL) == 0x168) { /* 92A8 */
            DS_U16(ds, CR_TOTAL) = 0;
            DS_U8(ds, CR_ROWS) = 0;
            DS_U16(ds, CR_START) = 0;
            if (call(g, host, PB_SET_DISPLAY_START, 0) < 0)
                return -1;
        }
        clear_band(g); /* 92D9 */
        if (DS_U8(ds, CR_ENDING)) {
            if (!--DS_U8(ds, CR_ENDING))
                DS_U8(ds, CR_ENDING)--;
        } else {
            DS_U16(ds, DS_PEN_Y) = (uint16_t)(DS_U16(ds, CR_TOTAL) + 0x168);
            write_line(g);
        }
        if (DS_U8(ds, CR_ENDING) == 0xFF)
            break;
    }
    if (DS_U8(ds, 0xEA3C)) { /* the music still plays: wait for a key */
        const KeyboardPlatform *keys = host->keys;
        while (!DS_U8(ds, DS_KEYBUF_COUNT))
            if (!keys || !keys->poll || keys->poll(g, keys->user))
                return -1;
    }
    if (call(g, host, MS_VIDEO_MODE, 0x0D) < 0)
        return -1;
    DS_U16(ds, 0x1228) = 0x28;
    DS_U16(ds, DS_SCREEN_STRIDE) = 0x28;
    return 0;
}
