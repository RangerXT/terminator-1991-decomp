/* The copy-protection screen (0000:EA86, once, after the main menu): 24 symbols in two
 * columns, chosen with the arrow keys and Enter. In this build the answer is never checked:
 * the comparison after the choice (a call at ED90) is skipped by NOP / JMP, the routine that
 * would print a message and hang (EE0C) is unreachable, and only the "wrong symbol" timer
 * DS:EA2E is cleared.
 *
 * The question names a row and column of a 16 x 24 table of symbol numbers that is
 * shuffled from fixed seeds in the text segment (words 7F1 / 7F3); ten such tables (7F3 =
 * 41h, 42h, ...) give the ten answers kept at DS:E6E0, which also seed the symbols shown.
 */
#include "term.h"

enum {
    PR_SHOWN = 0xE67E,      /* u8: the screen has been shown */
    PR_TABLE = 0xE72E,      /* u16[384]: shuffled symbol numbers (also the VGA palette buffer) */
    PR_ANSWERS = 0xE6E0,    /* u16[10]: the answer under each of the ten seeds */
    PR_PRESET = 0xE6DF,     /* u8: answers still to be used as symbols */
    PR_INDEX = 0xE6F4,      /* u16: byte index into the answers */
    PR_SYMBOLS = 0xE6F6,    /* u16[24]: the symbols shown, then whatever follows */
    PR_NORMAL = 0xE72A,     /* u16: colours of a symbol (VGA: 0 bits, 1 bits; EGA: low byte set = inverted) */
    PR_SELECTED = 0xE72C,   /* u16: colours of the selected symbol */
    PR_CORRECT = 0xEA30,    /* u16: where the right symbol is */
    PR_QUESTION = 0xEA32,   /* u16: row (high byte) and column (low byte) asked, times 8 */
    PR_ANSWER = 0xEA34,
};

static int host_call(Game *g, const ProtectionServices *host, uint16_t op, uint16_t a)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, 0, r->user) ? -1 : 0;
}

/* orig 0000:EABB   a random number 1..n */
static uint16_t random_from_1(uint8_t *ds, uint16_t n)
{
    return (uint16_t)(random_word(ds) % n + 1);
}

/* orig 0000:EE37 */
static void clear_table(uint8_t *ds)
{
    for (uint16_t i = 0; i < 0x180; ++i)
        DS_U16(ds, (uint16_t)(PR_TABLE + 2 * i)) = 0;
}

/* orig 0000:EE42   the numbers 1..384 shuffled into the table from the seed in the text
 * segment's words 7F1 / 7F3; the random generator is set back afterwards */
static void shuffle_table(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t first = random_word(ds), second = random_word(ds);
    const uint8_t *text = far_ptr(g, DS_U16(ds, 0xEA36), 0);
    DS_U16(ds, 0xEA42) = (uint16_t)((text[0x7F1] | text[0x7F2] << 8) | 1);
    DS_U16(ds, 0xEA44) = (uint16_t)(text[0x7F3] | text[0x7F4] << 8);
    random_refill(ds);
    uint16_t number = 1;
    for (uint16_t n = 0x180; n; --n) { /* DIV CX by the loop counter itself */
        uint16_t at = (uint16_t)(random_word(ds) % n * 2);
        while (DS_U16(ds, (uint16_t)(PR_TABLE + at))) {
            at = (uint16_t)(at + 2);
            if (at >= 0x300)
                at = 0;
        }
        DS_U16(ds, (uint16_t)(PR_TABLE + at)) = number++;
    }
    DS_U16(ds, 0xEA42) = second;
    DS_U16(ds, 0xEA44) = first;
    random_refill(ds);
}

/* orig 0000:EC25   the table entry at row AH / 8, column AL / 8 (both from 1) */
static uint16_t table_entry(const uint8_t *ds, uint16_t question)
{
    uint16_t row = (uint8_t)(question >> 8) >> 3, column = (uint8_t)question >> 3;
    uint16_t at = (uint16_t)((uint16_t)((uint16_t)(column - 1) * 0x18 + (uint16_t)(row - 1)) * 2);
    return DS_U16(ds, (uint16_t)(PR_TABLE + at));
}

/* orig 0000:F5C0   AL in decimal at DS:dest, NUL after it */
static void byte_decimal_unsigned(uint8_t *ds, uint16_t dest, uint8_t value)
{
    uint8_t digits[3];
    unsigned n = 0;
    do {
        digits[n++] = (uint8_t)(value % 10);
        value /= 10;
    } while (value);
    while (n)
        DS_U8(ds, dest++) = (uint8_t)('0' + digits[--n]);
    DS_U8(ds, dest) = 0;
}

static int text8(Game *g, const ProtectionServices *host, uint16_t text)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN)) {
        if (!host->screen)
            return -1;
        screen_text8_vga(g, host->screen, g->ds_seg, text);
        return 0;
    }
    return screen_text8(g, g->ds_seg, text) < 0 ? -1 : 0;
}

/* orig 0000:ECDE   the three lines of the question, the row and column filled in */
static int show_question(Game *g, const ProtectionServices *host, uint16_t question)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0xADD0))
        DS_U8(ds, DS_SCREEN_STRIDE) = 0x28; /* a byte store */
    uint8_t facility = DS_U8(ds, DS_FACILITY_SCREEN);
    DS_U8(ds, DS_FACILITY_SCREEN) = DS_U8(ds, 0xADD0);
    byte_decimal_unsigned(ds, 0xE6AE, (uint8_t)((uint8_t)question >> 3));
    byte_decimal_unsigned(ds, 0xE69C, (uint8_t)((uint8_t)(question >> 8) >> 3));
    DS_U8(ds, DS_TEXT_COLUMN) = 7;
    DS_U8(ds, DS_TEXT_ROW) = 0x15;
    if (text8(g, host, 0xE67F) < 0)
        return -1;
    DS_U8(ds, DS_TEXT_ROW)++;
    if (text8(g, host, 0xE68D) < 0)
        return -1;
    DS_U8(ds, DS_TEXT_ROW)++;
    if (text8(g, host, 0xE69F) < 0)
        return -1;
    DS_U8(ds, DS_FACILITY_SCREEN) = facility;
    return 0;
}

/* orig 0000:EAF5 (with EADC, EB86)   the symbol at place 0..23 (two columns, 16 pixels
 * apart rows) in the given colours; the symbols are 16x16 bits in the file buffer, 40 a
 * row of 500h bytes */
static void draw_symbol(Game *g, const ProtectionServices *host, uint16_t place, uint16_t colours)
{
    uint8_t *ds = g->ds;
    uint16_t number = (uint16_t)(DS_U16(ds, (uint16_t)(PR_SYMBOLS + place * 2)) - 1);
    const uint8_t *buffer = far_ptr(g, DS_U16(ds, DS_FILE_BUFFER_SEG), 0);
    uint16_t source = (uint16_t)(DS_U16(ds, DS_FILE_BUFFER) + (uint16_t)(number / 40 * 0x500) + number % 40 * 2);
    uint16_t x = place & 1 ? 24 : 8, y = (uint16_t)((uint16_t)(place >> 1) * 16 + 4);
    if (DS_U8(ds, 0xADD0)) {
        uint16_t at = (uint16_t)(y * 0x140 + x);
        for (unsigned row = 0; row < 16; ++row, source = (uint16_t)(source + 0x50)) {
            uint16_t bits = (uint16_t)(buffer[source] << 8 | buffer[(uint16_t)(source + 1)]);
            for (unsigned i = 0; i < 16; ++i, bits = (uint16_t)(bits << 1))
                if (host->screen)
                    host->screen[at++] = (uint8_t)(bits & 0x8000 ? colours >> 8 : colours);
            at = (uint16_t)(at + 0x130);
        }
        return;
    }
    uint8_t *p = g->planes;
    ega_seq_mask(p, 0x0F);
    uint16_t at = (uint16_t)(y * 0x28 + (x >> 3));
    for (unsigned row = 0; row < 16; ++row, source = (uint16_t)(source + 0x50), at = (uint16_t)(at + 0x28)) {
        uint16_t word = (uint16_t)(buffer[source] | buffer[(uint16_t)(source + 1)] << 8);
        if ((uint8_t)colours)
            word = (uint16_t)~word;
        ega_store(p, at, (uint8_t)word);
        ega_store(p, (uint16_t)(at + 1), (uint8_t)(word >> 8));
    }
}

/* orig 0000:ECAF   the symbols' file (DS:E673) into far DS:91B8, unpacked into the file buffer */
static int load_symbols(Game *g, const ProtectionServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0x91BA), off = DS_U16(ds, 0x91B8);
    uint32_t read = file_load(g, host->images, 0xE673, seg, off);
    if (read == UINT32_MAX)
        return -1;
    if (!(uint16_t)read)
        return 0;
    const uint8_t *packed = far_ptr(g, seg, off);
    uint16_t length = (uint16_t)(packed[0x10] | packed[0x11] << 8);
    bytekiller_unpack(far_ptr(g, seg, (uint16_t)(off + 0x20)), length,
                      far_ptr(g, DS_U16(ds, DS_FILE_BUFFER_SEG), DS_U16(ds, DS_FILE_BUFFER)));
    return 0;
}

/* orig 0000:EDBD   the answers under the ten seeds 41h..4Ah (text segment word 7F3) */
static void ten_answers(Game *g)
{
    uint8_t *ds = g->ds, *text = far_ptr(g, DS_U16(ds, 0xEA36), 0);
    uint8_t saved_lo = text[0x7F3], saved_hi = text[0x7F4];
    text[0x7F3] = 0x41;
    text[0x7F4] = 0;
    for (unsigned i = 0; i < 10; ++i) {
        clear_table(ds);
        shuffle_table(g);
        DS_U16(ds, (uint16_t)(PR_ANSWERS + DS_U16(ds, PR_INDEX))) = table_entry(ds, DS_U16(ds, PR_QUESTION));
        DS_U16(ds, PR_INDEX) = (uint16_t)(DS_U16(ds, PR_INDEX) + 2);
        uint16_t seed = (uint16_t)((text[0x7F3] | text[0x7F4] << 8) + 1);
        text[0x7F3] = (uint8_t)seed;
        text[0x7F4] = (uint8_t)(seed >> 8);
    }
    DS_U16(ds, PR_INDEX) = 0;
    text[0x7F3] = saved_lo;
    text[0x7F4] = saved_hi;
}

/* orig 0000:EC41   24 different symbols, the right one first, then swapped to a random
 * place (returned); all drawn. The first DS:E6DF of the others are the kept answers. A
 * candidate is compared with every word from DS:E6F6 up to the first zero. */
static uint16_t choose_symbols(Game *g, const ProtectionServices *host, uint16_t right)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, PR_SYMBOLS) = right;
    uint16_t to = PR_SYMBOLS + 2;
    for (unsigned n = 0; n < 0x17; ++n) {
        uint16_t candidate;
        int taken;
        do {
            if (DS_U8(ds, PR_PRESET)) {
                candidate = DS_U16(ds, (uint16_t)(PR_ANSWERS + DS_U16(ds, PR_INDEX)));
                DS_U16(ds, PR_INDEX) = (uint16_t)(DS_U16(ds, PR_INDEX) + 2);
                DS_U8(ds, PR_PRESET)--;
            } else
                candidate = random_from_1(ds, 0x180);
            taken = 0;
            for (uint16_t at = PR_SYMBOLS;; at = (uint16_t)(at + 2)) {
                uint16_t value = DS_U16(ds, at);
                if (!value)
                    break;
                if (value == candidate) {
                    taken = 1;
                    break;
                }
            }
        } while (taken);
        DS_U16(ds, to) = candidate;
        to = (uint16_t)(to + 2);
    }
    uint16_t place = (uint16_t)(random_word(ds) % 0x18); /* EACC */
    uint16_t swap = DS_U16(ds, (uint16_t)(PR_SYMBOLS + place * 2));
    DS_U16(ds, (uint16_t)(PR_SYMBOLS + place * 2)) = DS_U16(ds, PR_SYMBOLS);
    DS_U16(ds, PR_SYMBOLS) = swap;
    for (uint16_t i = 0; i < 0x18; ++i)
        draw_symbol(g, host, i, DS_U16(ds, PR_NORMAL));
    return place;
}

/* orig 0000:EB9A   move the selection with the arrow keys (held keys repeat every ten
 * frames) until Enter; returns the place. The keys come from the key table, read in a busy
 * loop: the host's poll stands for the time between two reads. */
static int select_symbol(Game *g, const ProtectionServices *host, uint16_t *chosen)
{
    uint8_t *ds = g->ds;
    uint16_t place = 0;
    for (;;) {
        draw_symbol(g, host, place, DS_U16(ds, PR_SELECTED));
        uint16_t next;
        for (;;) {
            if (DS_U8(ds, KEY_DOWN(SC_ENTER))) {
                *chosen = place;
                return 0;
            }
            /* the original tests Right, Down, Up, then Left */
            if (DS_U8(ds, KEY_DOWN(SC_RIGHT))
                || (DS_U8(ds, KEY_DOWN(SC_LEFT)) && !DS_U8(ds, KEY_DOWN(SC_DOWN)) && !DS_U8(ds, KEY_DOWN(SC_UP)))) {
                next = place ^ 1;
                break;
            }
            if (DS_U8(ds, KEY_DOWN(SC_DOWN))) {
                next = (uint16_t)(place + 2);
                if ((int16_t)next >= 0x18)
                    next = place;
                break;
            }
            if (DS_U8(ds, KEY_DOWN(SC_UP))) {
                next = (uint16_t)(place - 2);
                if (next & 0xFF00)
                    next = place;
                break;
            }
            const KeyboardPlatform *keys = host->keys;
            if (!keys || !keys->poll || keys->poll(g, keys->user))
                return -1;
        }
        for (unsigned n = 0; n < 10; ++n)
            if (host_call(g, host, 0x0D8D, 0) < 0 || host_call(g, host, 0x0DAA, 0) < 0)
                return -1;
        draw_symbol(g, host, place, DS_U16(ds, PR_NORMAL));
        place = next;
    }
}

/* orig 0000:ED35 */
static int protection_body(Game *g, const ProtectionServices *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_TEXT_COLOUR) = 0x0E;
    if (DS_U8(ds, 0xADD0)) {
        DS_U16(ds, PR_NORMAL) = 0x0803;
        DS_U16(ds, PR_SELECTED) = 0x0804;
    } else {
        DS_U16(ds, PR_NORMAL) = 0;
        DS_U16(ds, PR_SELECTED) = 0xFFFF;
    }
    if (load_symbols(g, host) < 0)
        return -1;
    uint8_t row = (uint8_t)(random_from_1(ds, 0xBF) + 8); /* EC0E */
    uint8_t column = (uint8_t)(random_from_1(ds, 0x7F) + 8);
    uint16_t question = (uint16_t)(row << 8 | column);
    if (show_question(g, host, question) < 0)
        return -1;
    DS_U16(ds, PR_QUESTION) = question;
    uint16_t right = table_entry(ds, question);
    ten_answers(g);
    DS_U16(ds, PR_CORRECT) = choose_symbols(g, host, right);
    uint16_t chosen;
    if (select_symbol(g, host, &chosen) < 0)
        return -1;
    DS_U8(ds, 0xB6A0) = 0;
    DS_U16(ds, DS_WRONG_SYMBOL_TIMER) = 0;
    DS_U16(ds, PR_ANSWER) = DS_U16(ds, PR_CORRECT); /* the choice is not used */
    return 0;
}

/* orig 0000:EA86 */
int protection_screen(Game *g, const ProtectionServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    if (DS_U8(ds, PR_SHOWN))
        return 0;
    DS_U8(ds, PR_SHOWN) = 0xFF;
    if (DS_U8(ds, 0xADD0)) {
        if (host_call(g, host, MS_VIDEO_MODE, 0x13) < 0
            || image_vga_protection_load(g, host->images, host->screen, host->palette) < 0)
            return -1;
    } else if (host_call(g, host, MS_VIDEO_MODE, 0x0D) < 0 || image_load_screen(g, host->images, 0xE65E) < 0)
        return -1;
    clear_table(ds);
    shuffle_table(g);
    if (protection_body(g, host) < 0)
        return -1;
    map_clear_key_buffer(ds);
    return 0;
}
