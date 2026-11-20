/* The ratings screen (0000:D300, from the game menu and the main menu) and the name editor
 * it opens (0000:DF4A, also used elsewhere), with their helpers.
 *
 * The screen shows the current session's statistics and the five best sessions of the
 * player's character (file at DS:E27E for Reese, E28A otherwise; decoded into DS:50B2).
 * 1-5 show a ranked session's statistics, Space the current one again, N (during play)
 * the name editor, Esc leaves. A new best session asks for a name first. DS:ABC8 marks
 * the call from the main menu: no mode switches, no scoring of the current session.
 * A VGA installation (DS:ADD0) shows it in mode 13h with a 7x7 font, an EGA one in mode
 * 0Eh with the scalable font (src/fontscale.c).
 */
#include <string.h>

#include "term.h"

enum {
    RT_FROM_MENU = 0xABC8, /* u8: called from the main menu */
    RT_SHOWN = 0x11A8,     /* i16: which ranked session is shown (5 - n), negative: none */
    RT_SHOWN_SAVED = 0xE34C,
    RT_NAMED = 0x038A,       /* u8: the current session has a name */
    RT_NAME = 0xE3FA,        /* the name typed (21 bytes) */
    RT_TABLE = 0x50B2,       /* u16 count, then 41-byte records: score ..., name at +14h */
    RT_STRIDE = 0x1228,      /* u16: bytes per screen row for font_text */
    RT_SMALL_FONT = 0xE34E,  /* far pointer: the 7x7 VGA font */
    RT_SCREEN_COPY = 0x91B8, /* far pointer: where the VGA screen is kept meanwhile */
    RT_DIGITS = 0x7B90,
};

static int resource(Game *g, const RatingsServices *host, uint16_t op, uint16_t a)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, 0, r->user) ? -1 : 0;
}

/* orig 0000:F62C   value in decimal with a NUL at DS:dest */
void number_decimal(uint8_t *ds, uint16_t dest, uint16_t value)
{
    DS_U8(ds, number_format(ds, dest, value, 10)) = 0;
}

/* orig 0000:F5EB   signed value in decimal with a NUL at DS:dest */
void number_decimal_signed(uint8_t *ds, uint16_t dest, uint16_t value)
{
    if ((int16_t)value < 0) {
        DS_U8(ds, dest++) = '-';
        value = (uint16_t)-value;
    }
    number_decimal(ds, dest, value);
}

/* orig 0000:0CC2   fill the rectangle x0..x1 (pixels), rows y0..y1 of the drawing page in
 * DS:123B's colour (EGA set/reset). The right edge's byte is x0 / 8 + (x1 - x0) / 8, the
 * middle has ((x1 & ~7) - ((x0 + 7) & ~7)) / 8 + 1 bytes, as the original computes them. */
void ega_fill_rect(Game *g, uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1)
{
    uint8_t *ds = g->ds, *p = g->planes;
    DS_U16(ds, 0x124A) = x0;
    DS_U16(ds, 0x124C) = y0;
    DS_U16(ds, 0x124E) = x1;
    ega_gc(p, 0, DS_U8(ds, 0x123B));
    ega_gc(p, 1, 15);
    ega_gc(p, 3, 0);
    ega_gc_select(p, 8);
    uint16_t stride = DS_U16(ds, DS_SCREEN_STRIDE);
    uint16_t start = (uint16_t)((uint8_t)y0 * (uint8_t)stride + (x0 >> 3) + DS_U16(ds, DS_DRAW_PAGE)); /* MUL BL */
    uint16_t rows = (uint16_t)(y1 - y0);
    DS_U16(ds, 0x1250) = rows;
    ega_gc_data(p, (uint8_t)(0xFF >> (x0 & 7)));
    uint16_t at = start, n = rows;
    do { /* LOOP: 0 rows means 65536 */
        ega_store(p, at, (uint8_t)(ega_load(p, at) | 0));
        at = (uint16_t)(at + stride);
    } while (--n);
    ega_gc_data(p, (uint8_t)((int8_t)0x80 >> (x1 & 7)));
    at = (uint16_t)(start + ((uint16_t)(x1 - x0) >> 3));
    n = rows;
    do {
        ega_store(p, at, (uint8_t)(ega_load(p, at) | 0));
        at = (uint16_t)(at + stride);
    } while (--n);
    uint16_t bytes = (uint16_t)((uint16_t)((x1 & 0xFFF8) - ((x0 + 7) & 0xFFF8)) >> 3) + 1;
    ega_gc_data(p, 0xFF);
    at = (uint16_t)(start + 1);
    n = rows;
    do {
        for (uint16_t b = 0; b < bytes; ++b)
            ega_store(p, (uint16_t)(at + b), 0xFF);
        at = (uint16_t)(at + stride);
    } while (--n);
    ega_gc(p, 1, 0);
}

/* 8x8 text: the VGA text routine on a VGA installation (E0C0 checks itself) */
static void text8(Game *g, const RatingsServices *host, uint16_t text)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN))
        screen_text8_vga(g, host->screen, g->ds_seg, text);
    else
        screen_text8(g, g->ds_seg, text);
}

/* The name field: column DS:E416, row DS:E418 in characters, 22 x 1.25 characters */
static void name_field(Game *g, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t x0 = (uint16_t)(DS_U16(ds, 0xE416) * 8), y0 = (uint16_t)(DS_U16(ds, 0xE418) * 8 - 1);
    DS_U16(ds, DS_TEXT_COLUMN) = DS_U16(ds, 0xE416);
    DS_U16(ds, DS_TEXT_ROW) = DS_U16(ds, 0xE418);
    if (DS_U8(ds, DS_FACILITY_SCREEN)) {
        DS_U8(ds, DS_TEXT_COLOUR) = 4;
        if (host->screen)
            screen_vga_fill(ds, host->screen, x0, y0, 0xA8, 0x0A);
    } else {
        DS_U8(ds, DS_FILL_COLOUR) = 4;
        ega_fill_rect(g, x0, y0, (uint16_t)(x0 + 0xA8), (uint16_t)(y0 + 0x0A));
    }
}

/* orig 0000:E046   the field again: the name so far and the cursor after it */
static void name_redraw(Game *g, const RatingsServices *host, uint16_t length)
{
    uint8_t *ds = g->ds;
    name_field(g, host);
    DS_U8(ds, DS_FILL_COLOUR) = DS_U8(ds, DS_TEXT_COLOUR) = 4; /* both set first, as in E06F */
    DS_U8(ds, (uint16_t)(RT_NAME + length)) = 0;
    uint8_t colour = DS_U8(ds, DS_FACILITY_SCREEN) ? 0xFE : 0x0E;
    DS_U8(ds, DS_FILL_COLOUR) = DS_U8(ds, DS_TEXT_COLOUR) = colour;
    text8(g, host, RT_NAME);
    DS_U16(ds, DS_TEXT_COLUMN) = (uint16_t)(DS_U16(ds, 0xE416) + length);
    text8(g, host, 0xE410);
}

/* 5776:0247: the message box off again; on the mode-13h screen it goes on to 11BC:2B91 */
static int box_restore(Game *g, const RatingsServices *host)
{
    if (!DS_U8(g->ds, DS_FACILITY_SCREEN))
        return scene_overlay_restore(g);
    if (!host->screen)
        return -1;
    scene_vga_overlay_restore(g, host->screen);
    return 0;
}

/* orig 0000:DF4A   a one-line editor under the message at text (in the text segment) at x, y
 * (characters), for up to max characters, into DS:E3FA. Returns 0 after Enter, 1 after Esc
 * (the original's carry), -1 on a missing service. */
int name_editor(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t max, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    DS_U16(ds, 0xE41A) = max;
    if (resource(g, host, MS_SELECT_PAGES, 0) < 0)
        return -1;
    DS_U8(ds, 0x5A4E) = 1; /* the message box does not wait */
    int shown = DS_U8(ds, DS_FACILITY_SCREEN) ? textbox_vga_draw(g, host->screen, text, x, y, 0x1E, 5, NULL)
                                              : textbox_draw(g, text, x, y, 0x1E, 5, NULL);
    if (shown < 0)
        return -1;
    uint8_t *seg = far_ptr(g, DS_U16(ds, 0xEA36), 0);
    uint16_t at = text;
    while (seg[at++]) /* REPNE SCASB: the field's place follows the message */
        ;
    DS_U16(ds, 0xE416) = (uint16_t)(x + seg[at]);
    DS_U16(ds, 0xE418) = (uint16_t)(y + seg[(uint16_t)(at + 1)]);
    name_field(g, host);
    uint8_t colour = DS_U8(ds, DS_FACILITY_SCREEN) ? 0xFE : 0x0E;
    DS_U8(ds, DS_FILL_COLOUR) = DS_U8(ds, DS_TEXT_COLOUR) = colour;
    text8(g, host, 0xE410);
    uint16_t length = 0;
    map_clear_key_buffer(ds);
    for (;;) {
        uint32_t ch = keyboard_read(g, host->keys);
        if (ch == UINT32_MAX)
            return -1;
        if (DS_U8(ds, KEY_DOWN(SC_ESC))) {
            const KeyboardPlatform *keys = host->keys;
            while (DS_U8(ds, KEY_DOWN(SC_ESC)))
                if (!keys || !keys->poll || keys->poll(g, keys->user))
                    return -1;
            return box_restore(g, host) < 0 ? -1 : 1;
        }
        if (ch == 0x0D) {
            DS_U8(ds, (uint16_t)(RT_NAME + length)) = 0;
            if (box_restore(g, host) < 0)
                return -1;
            DS_U8(ds, 0x5A4E) = 0;
            return resource(g, host, MS_SELECT_PAGES, 2) < 0 ? -1 : 0;
        }
        if (ch == 8) {
            if (length) {
                length--;
                name_redraw(g, host, length);
            }
            continue;
        }
        if (ch < 0x20 || length >= DS_U16(ds, 0xE41A))
            continue;
        DS_U8(ds, (uint16_t)(RT_NAME + length)) = (uint8_t)ch;
        length++;
        name_redraw(g, host, length);
    }
}

/* orig 0000:D7F9   digits, letters and spaces in the 7x7 VGA font at screen offset di;
 * anything else ends the text */
static void small_text(Game *g, const RatingsServices *host, uint16_t text, uint16_t di)
{
    uint8_t *ds = g->ds;
    uint8_t *font = far_ptr(g, DS_U16(ds, RT_SMALL_FONT + 2), 0);
    for (;;) {
        uint8_t ch = DS_U8(ds, text++), index;
        if (!ch)
            return;
        if (ch != ' ') {
            if (ch < '0')
                return;
            if (ch <= '9')
                index = (uint8_t)(ch - '0');
            else {
                index = (uint8_t)((ch & 0xDF) - 'A');
                if ((uint8_t)((ch & 0xDF)) < 'A' || index > 0x19)
                    return;
                index = (uint8_t)(index + 10);
            }
            uint16_t glyph = (uint16_t)(DS_U16(ds, RT_SMALL_FONT) + index), at = di;
            uint8_t colour = DS_U8(ds, DS_TEXT_COLOUR);
            for (unsigned row = 0; row < 7; ++row) {
                uint8_t bits = font[glyph];
                glyph = (uint16_t)(glyph + 0x24);
                for (unsigned x = 0; x < 7; ++x, bits <<= 1)
                    if (bits & 0x80 && host->screen)
                        host->screen[(uint16_t)(at + x)] = colour;
                at = (uint16_t)(at + 0x140);
            }
        }
        di = (uint16_t)(di + 8);
    }
}

/* orig 0000:D74B   the VGA statistics table */
static int vga_stats(Game *g, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    if (file_load(g, host->images, 0xE319, DS_U16(ds, RT_SMALL_FONT + 2), DS_U16(ds, RT_SMALL_FONT)) == UINT32_MAX)
        return -1; /* orig 0000:D856 */
    DS_U8(ds, DS_TEXT_COLOUR) = 0xFE;
    uint16_t row = 0x2F58, item = 0xE352;
    do { /* the end marker is tested after each line */
        number_decimal(ds, RT_DIGITS, DS_U16(ds, DS_U16(ds, (uint16_t)(item + 6))));
        small_text(g, host, RT_DIGITS, row);
        item = (uint16_t)(item + 8);
        row = (uint16_t)(row + 0xC80);
    } while (DS_U16(ds, item) != 0xFFFF);
    row = (uint16_t)(row + 0x780);
    uint16_t score = DS_U16(ds, 0x0376);
    number_decimal_signed(ds, RT_DIGITS, (int16_t)score < 0 ? 0 : score);
    small_text(g, host, RT_DIGITS, 0xE40C);
    uint16_t place = (uint16_t)(row - 0x6C), record = 0x50B4, rank = '1';
    uint16_t count = DS_U16(ds, RT_TABLE);
    do { /* LOOP */
        DS_U8(ds, DS_TEXT_COLOUR) = count == DS_U16(ds, RT_SHOWN) ? 0xFF : 0xFE;
        DS_U16(ds, RT_DIGITS) = rank;
        small_text(g, host, RT_DIGITS, place);
        small_text(g, host, (uint16_t)(record + 0x14), (uint16_t)(place + 0x10));
        uint16_t value = DS_U16(ds, record);
        number_decimal_signed(ds, RT_NAME, (int16_t)value < 0 ? 0 : value);
        small_text(g, host, RT_NAME, (uint16_t)(place + 0x10 + 0x58));
        record = (uint16_t)(record + 0x29);
        place = (uint16_t)(place + 0xC80);
        rank++;
    } while (--count);
    return 0;
}

/* orig 0000:D4C3   the statistics table */
static int draw_stats(Game *g, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return vga_stats(g, host);
    DS_U8(ds, DS_TEXT_COLOUR) = 0x0E;
    uint16_t item = 0xE352;
    do { /* the end marker is tested after each line */
        font_text(g, DS_U16(ds, item), DS_U16(ds, (uint16_t)(item + 2)), DS_U16(ds, (uint16_t)(item + 4)));
        number_decimal(ds, RT_DIGITS, DS_U16(ds, DS_U16(ds, (uint16_t)(item + 6))));
        font_text(g, 0x24E, DS_U16(ds, (uint16_t)(item + 2)), RT_DIGITS);
        item = (uint16_t)(item + 8);
    } while (DS_U16(ds, item) != 0xFFFF);
    uint16_t x = 0x140, y = 0x82, label = 0xE33D, record = 0x50B4;
    uint16_t count = DS_U16(ds, RT_TABLE);
    do { /* LOOP */
        DS_U8(ds, DS_TEXT_COLOUR) = count == DS_U16(ds, RT_SHOWN) ? 0x0F : 0x0E;
        font_text(g, x, y, label);
        font_text(g, (uint16_t)(x + 0x1E), y, (uint16_t)(record + 0x14));
        uint16_t value = DS_U16(ds, record);
        number_decimal_signed(ds, RT_NAME, (int16_t)value < 0 ? 0 : value);
        font_text(g, 0x24E, y, RT_NAME);
        y = (uint16_t)(y + 0x0D);
        label = (uint16_t)(label + 3);
        record = (uint16_t)(record + 0x29);
    } while (--count);
    font_text(g, 0x28, 0xB4, 0xE30C);
    uint16_t score = DS_U16(ds, 0x0376);
    number_decimal_signed(ds, RT_DIGITS, (int16_t)score < 0 ? 0 : score);
    font_text(g, 0xF0, 0xB4, RT_DIGITS);
    return 0;
}

/* orig 0000:9A13   four frame lines of the EGA ratings screen (table at DS:ABCC) */
static void frame_lines(Game *g)
{
    uint8_t *ds = g->ds;
    for (uint16_t at = 0xABCC; at < 0xABCC + 32; at = (uint16_t)(at + 8)) {
        DS_U16(ds, DS_PEN_X) = DS_U16(ds, at);
        DS_U16(ds, DS_PEN_Y) = DS_U16(ds, (uint16_t)(at + 2));
        area_line_to(ds, g->planes, DS_U16(ds, (uint16_t)(at + 4)), DS_U16(ds, (uint16_t)(at + 6)));
    }
}

/* orig 0000:D628   the character's ratings file into DS:50B2, decoded */
static int load_table(Game *g, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t name = DS_U16(ds, DS_PLAYER) == 0x04D4 ? 0xE27E : 0xE28A;
    uint32_t read = file_load(g, host->images, name, g->ds_seg, RT_TABLE);
    if (read == UINT32_MAX)
        return -1;
    ratings_decode(ds + RT_TABLE, (uint16_t)read);
    return 0;
}

static int load_font(Game *g, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    if (font_load(g, host->images, 0x7A49) < 0)
        return -1;
    font_scale(g, 0x0C0C, 0x0C0C, 0x46, DS_U16(ds, 0xADE6), DS_U16(ds, 0xADFE));
    return 0;
}

/* orig 0000:D3D2..D42F   ask for the new best session's name and put it in the table */
static int enter_name(Game *g, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    if (name_editor(g, 0x1012, 5, 5, 0x0A, host) < 0) /* orig 0000:DF3A; the name is taken even after Esc */
        return -1;
    memcpy(ds + RT_NAMED, ds + RT_NAME, 0x15);
    memcpy(ds + 0xE3B0, ds + RT_NAME, 0x15);
    if (resource(g, host, MS_SELECT_PAGES, 0) < 0 || load_font(g, host) < 0)
        return -1;
    uint16_t at = (uint16_t)(RT_TABLE + (uint16_t)(5 - DS_U16(ds, RT_SHOWN)) * 0x29 + 2 + 0x14);
    memcpy(ds + at, ds + RT_NAMED, 0x15);
    return 0;
}

/* orig 0000:D300 */
int ratings_screen(Game *g, const RatingsServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    keyboard_flush(g);
    ratings_update_time(ds);
    DS_U8(ds, RT_NAME) = 0;
    DS_U16(ds, RT_STRIDE) = 0x50;
    uint8_t vga = DS_U8(ds, DS_FACILITY_SCREEN) = DS_U8(ds, 0xADD0);
    uint8_t from_menu = DS_U8(ds, RT_FROM_MENU);
    uint8_t *copy = far_ptr(g, DS_U16(ds, RT_SCREEN_COPY + 2), DS_U16(ds, RT_SCREEN_COPY));
    if (vga) {
        DS_U16(ds, RT_STRIDE) = 0x140;
        if (!from_menu && resource(g, host, MS_VIDEO_MODE, 0x13) < 0)
            return -1;
        if (!host->screen || image_vga_load(g, host->images, 0xE332, host->screen, host->palette) < 0)
            return -1;
        memcpy(copy, host->screen, 64000); /* orig 0000:D863 */
    } else {
        if (!from_menu && resource(g, host, MS_VIDEO_MODE, 0x0E) < 0)
            return -1;
        if (resource(g, host, MS_DEFAULT_PALETTE, 0) < 0)
            return -1;
        DS_U16(ds, DS_SCREEN_STRIDE) = 0x50;
        if (resource(g, host, MS_SELECT_PAGES, 0) < 0)
            return -1;
        DS_U16(ds, 0x805C) = 0x1F40;
        if (image_load_screen(g, host->images, 0xE326) < 0)
            return -1;
        DS_U8(ds, DS_FILL_COLOUR) = 15;
        frame_lines(g);
    }
    if (load_font(g, host) < 0)
        return -1;
    screen_copy_rect(g, 0, 0x4000, 0x50, 0xC8);
    if (resource(g, host, MS_PALETTE, 0) < 0)
        return -1;
    map_clear_key_buffer(ds);
    if (load_table(g, host) < 0)
        return -1;
    ratings_stats_save(ds);
    int name = 0;
    if (!from_menu) {
        score_update(ds);
        ratings_stats_save(ds);
        ratings_insert(ds);
        DS_U16(ds, RT_SHOWN_SAVED) = DS_U16(ds, RT_SHOWN);
        name = DS_I16(ds, RT_SHOWN) >= 0 && !DS_U8(ds, RT_NAMED);
    }
    for (;;) {
        if (name && enter_name(g, host) < 0)
            return -1;
        name = 0;
        if (DS_U8(ds, DS_FACILITY_SCREEN))
            memcpy(host->screen, copy, 64000); /* orig 0000:D877 */
        screen_copy_rect(g, 0x4000, 0, 0x50, 0xC8);
        if (draw_stats(g, host) < 0)
            return -1;
        for (;;) {
            uint32_t key = keyboard_read(g, host->keys);
            if (key == UINT32_MAX)
                return -1;
            uint8_t ch = (uint8_t)key;
            if (ch == ' ') {
                ratings_stats_restore(ds);
                break;
            }
            if (ch >= '1' && ch <= '5') {
                uint16_t index = (uint16_t)(ch - '1');
                DS_U16(ds, RT_SHOWN) = (uint16_t)(5 - index);
                ratings_select(ds, index);
                break;
            }
            if (!from_menu && (ch & 0xDF) == 'N') {
                name = 1;
                break;
            }
            if (ch == 0x1B)
                goto leave;
        }
    }
leave:
    if (!from_menu) {
        DS_U16(ds, RT_STRIDE) = 0x50;
        DS_U8(ds, DS_FACILITY_SCREEN) = 0;
        if (resource(g, host, MS_VIDEO_MODE, 0x0D) < 0)
            return -1;
        DS_U16(ds, DS_SCREEN_STRIDE) = 0x28;
        DS_U16(ds, RT_STRIDE) = 0x28;
        if (camera_reset(g, host->resources, host->images) < 0)
            return -1;
        DS_U16(ds, DS_VISIBLE_CELL) = 0xFFFF;
        if (update_visible_cells(g, host->images) < 0) /* the original tests DS:ABC8 again */
            return -1;
    }
    ratings_stats_restore(ds);
    return 0;
}
