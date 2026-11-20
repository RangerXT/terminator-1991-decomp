/* Planar text windows and saved backgrounds (5032 and 5776 helpers). */
#include "term.h"

int scene_overlay_save(Game *g, uint16_t dest, uint16_t width, uint16_t rows)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    DS_U8(ds, 0xC4AB)++;
    DS_U16(ds, 0xC4B2) = dest;
    DS_U16(ds, 0xC4B6) = width;
    DS_U16(ds, 0xC4B4) = rows;
    uint16_t source = 0x8000 + DS_U16(ds, 0xC546), ptr = DS_U16(ds, 0xC4C4);
    DS_U16(ds, ptr) = width;
    DS_U16(ds, ptr + 2) = rows;
    DS_U16(ds, ptr + 4) = dest;
    DS_U16(ds, ptr + 6) = source;
    DS_U16(ds, 0xC4C4) += 8;
    screen_copy_rect(g, dest, source, width, rows);
    DS_U16(ds, 0xC546) += (uint16_t)(DS_U16(ds, DS_SCREEN_STRIDE) * rows);
    return 0;
}

/* E0C0: character-cell text using the loaded 8x8 font, with a far source. */
int screen_text8(Game *g, uint16_t text_seg, uint16_t text)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t stride = DS_U16(ds, DS_SCREEN_STRIDE);
    ega_gc(p, 0, DS_U8(ds, DS_TEXT_COLOUR));
    ega_gc(p, 1, 15);
    ega_gc(p, 5, 0);
    ega_gc(p, 3, 0);
    ega_gc_select(p, 8);
    uint16_t dest = DS_U8(ds, DS_TEXT_ROW) * (stride == 80 ? 640 : 320) + DS_U16(ds, 0xE41C) * stride;
    DS_U8(ds, 0xE413) = 0;
    dest += DS_U16(ds, DS_TEXT_COLUMN) + DS_U16(ds, DS_DRAW_PAGE);
    uint16_t font_seg = DS_U16(far_ptr(g, (uint16_t)(g->ds_seg - 0x5C27), 0), 0x16A7);
    ega_load(p, 0x1F3E);
    for (;;) {
        uint8_t ch = *far_ptr(g, text_seg, text++);
        if (!ch)
            break;
        uint16_t glyph = ch * 8;
        for (unsigned row = 0; row < 8; ++row) {
            ega_gc_data(p, *far_ptr(g, font_seg, glyph++));
            uint16_t at = dest + row * stride;
            uint8_t old = ega_load(p, at);
            ega_store(p, at, old);
        }
        dest++;
    }
    ega_gc_data(p, 255);
    ega_gc(p, 1, 0);
    return 0;
}

static void box_line(Game *g, uint16_t x, uint16_t y, uint8_t colour)
{
    DS_U8(g->ds, DS_FILL_COLOUR) = colour;
    if (DS_U16(g->ds, DS_SCREEN_STRIDE) == 80)
        area_line_to(g->ds, g->planes, x, y);
    else
        line_to(g->ds, g->planes, x, y);
}

/* 5776:03ED: four edges, retaining the original endpoint/colour state. */
void textbox_border_layer(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t x = DS_U8(ds, DS_BOX_X) * 8 + DS_U16(ds, 0xC4BC), y = DS_U8(ds, DS_BOX_Y) * 8 + DS_U16(ds, 0xC4BE);
    DS_U16(ds, 0xC4C0) = x;
    DS_U16(ds, 0xC4C2) = y;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y;
    uint16_t right = x + DS_U16(ds, 0xC4BA) - 1, bottom = y + DS_U16(ds, 0xC4B8) - 1;
    box_line(g, right, y, DS_U8(ds, 0xC4B0));
    box_line(g, right, bottom, DS_U8(ds, 0xC4B1));
    box_line(g, x, bottom, DS_U8(ds, 0xC4B1));
    box_line(g, x, y, DS_U8(ds, 0xC4B0));
}

/* 5776:0346: three dark bevel layers followed by three bright ones. */
void textbox_border(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0xC4B0) = 8;
    DS_U16(ds, 0xC4B8) = DS_U16(ds, 0xC4B4);
    DS_U16(ds, 0xC4BA) = DS_U16(ds, 0xC4B6) * 8;
    DS_U16(ds, 0xC4BC) = DS_U16(ds, 0xC4BE) = 0;
    for (unsigned i = 0; i < 6; ++i) {
        if (i == 3)
            DS_U16(ds, 0xC4B0) = 0x0F0F;
        if (i) {
            DS_U16(ds, 0xC4BC)++;
            DS_U16(ds, 0xC4BE)++;
            DS_U16(ds, 0xC4BA) -= 2;
            DS_U16(ds, 0xC4B8) -= 2;
        }
        textbox_border_layer(g);
    }
}

/* 5032 planar painting. Completion below retains the source page-stack behavior. */
static int textbox_paint(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                         uint16_t *saved_page, uint16_t *last_text)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    DS_U16(ds, 0x7850) = width - 2;
    uint16_t rows = height * 8;
    DS_U8(ds, DS_BOX_X) = x;
    DS_U8(ds, DS_BOX_Y) = y;
    uint16_t page = DS_U16(ds, 0x123C + DS_U8(ds, DS_PAGE_SHOWN) * 2);
    uint16_t dest = x + (uint16_t)(DS_U16(ds, DS_SCREEN_STRIDE) * 8) * y + page;
    DS_U16(ds, 0x7818) = page;
    int timed = DS_U16(ds, DS_WARNING_COUNTDOWN) || DS_U8(ds, DS_RELOAD_COUNTDOWN);
    if (timed) {
        DS_U16(ds, 0x78AC) = width;
        DS_U16(ds, 0x78AE) = rows;
        DS_U16(ds, 0x78B0) = dest;
        DS_U16(ds, 0xC4B6) = width;
        DS_U16(ds, 0xC4B4) = rows;
    } else
        scene_overlay_save(g, dest, width, rows);
    ega_seq_mask(p, 15);
    ega_gc(p, 8, 255);
    ega_gc(p, 0, DS_U8(ds, 0x775C));
    ega_gc(p, 1, 15);
    ega_gc(p, 5, 0);
    ega_gc(p, 3, 0);
    unsigned count = rows ? rows : 65536;
    for (unsigned row = 0; row < count; ++row) {
        for (unsigned col = 0; col < width; ++col)
            ega_store(p, (uint16_t)(dest + col), 3);
        dest += DS_U16(ds, DS_SCREEN_STRIDE);
    }
    uint16_t seg = DS_U16(ds, 0xEA36), old_page = DS_U16(ds, DS_DRAW_PAGE);
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, DS_FILL_COLOUR) = *far_ptr(g, seg, text++);
    DS_U16(ds, DS_DRAW_PAGE) = page;
    textbox_border(g);
    for (;;) {
        DS_I16(ds, DS_TEXT_COLUMN) = (int8_t)(*far_ptr(g, seg, text++) + DS_U8(ds, DS_BOX_X));
        DS_I16(ds, DS_TEXT_ROW) = (int8_t)(*far_ptr(g, seg, text++) + DS_U8(ds, DS_BOX_Y));
        screen_text8(g, seg, text);
        uint16_t scan = text, left = 65535;
        while (left--)
            if (!*far_ptr(g, seg, scan++))
                break;
        if (*far_ptr(g, seg, scan) == 255)
            break;
        text = scan;
    }
    *saved_page = old_page;
    if (last_text)
        *last_text = text;
    return 0;
}

static int textbox_nonmodal(const uint8_t *ds)
{
    return DS_U16(ds, DS_WARNING_COUNTDOWN) || DS_U8(ds, DS_RELOAD_COUNTDOWN) || DS_U8(ds, 0x5A4E);
}

static int textbox_pressed(const uint8_t *ds)
{
    return DS_U8(ds, KEY_DOWN(SC_ESC)) || DS_U8(ds, KEY_DOWN(SC_ENTER));
}

static void textbox_finish_immediate(Game *g, uint16_t saved_page)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_WARNING_COUNTDOWN) || (!DS_U8(ds, 0x5A4E) && DS_U8(ds, DS_RELOAD_COUNTDOWN)))
        scene_overlay_save(g, DS_U16(ds, 0x78B0), DS_U16(ds, 0x78AC), DS_U16(ds, 0x78AE));
    else
        DS_U16(ds, DS_DRAW_PAGE) = saved_page;
}

int textbox_draw_nonmodal_state(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                                uint16_t *si)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN) || !textbox_nonmodal(g->ds))
        return -1;
    uint16_t page;
    if (textbox_paint(g, text, x, y, width, height, &page, si) < 0)
        return -1;
    textbox_finish_immediate(g, page);
    return 0;
}

int textbox_draw_nonmodal(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height)
{
    return textbox_draw_nonmodal_state(g, text, x, y, width, height, NULL);
}

/* Modal 5032 completion: release existing input, wait in five-retrace batches,
 * then release the dismissal input and restore the saved background. Host calls
 * supply timing/input only. Recheck the source's nonmodal gates during release. */
int textbox_draw(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                 const TextPlatform *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN) || (!textbox_nonmodal(ds) && (!host || !host->poll)))
        return -1;
    uint16_t page;
    if (textbox_paint(g, text, x, y, width, height, &page, NULL) < 0)
        return -1;
    for (;;) {
        if (textbox_nonmodal(ds)) {
            textbox_finish_immediate(g, page);
            return 0;
        }
        if (!textbox_pressed(ds))
            break;
        if (host->poll(g, TX_RELEASE_BEFORE, 0, host->user))
            return -1;
    }
    DS_U16(ds, DS_DRAW_PAGE) = page;
    do {
        if (host->poll(g, TX_WAIT_KEY, 5, host->user))
            return -1;
    } while (!textbox_pressed(ds));
    while (textbox_pressed(ds))
        if (host->poll(g, TX_RELEASE_AFTER, 0, host->user))
            return -1;
    return scene_overlay_restore(g);
}

/* 093A: one-shot warning and its 200-frame latch. */
int scene_warning(Game *g)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0x00B9)) {
        DS_U16(ds, DS_WARNING_COUNTDOWN) = 0;
        DS_U8(ds, 0x00BA) = 0;
        return 0;
    }
    if (DS_U8(ds, 0x00BA))
        return 0;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    DS_U8(ds, 0x00BA) = 255;
    DS_U16(ds, DS_WARNING_COUNTDOWN) = 200;
    uint16_t a = DS_U16(ds, DS_PAGE_SHOWN);
    DS_U16(ds, DS_PAGE_SHOWN) = DS_U16(ds, DS_PAGE_DRAWN);
    DS_U16(ds, DS_PAGE_DRAWN) = a;
    DS_U8(ds, 0x5A4E) = 255;
    textbox_draw_nonmodal(g, 0x0729, 6, 4, 13, 3);
    DS_U8(ds, 0x5A4E) = 0;
    a = DS_U16(ds, DS_PAGE_SHOWN);
    DS_U16(ds, DS_PAGE_SHOWN) = DS_U16(ds, DS_PAGE_DRAWN);
    DS_U16(ds, DS_PAGE_DRAWN) = a;
    return 0;
}

/* 5776:0295/02AF: close all saved windows, or reset their bookkeeping. */
int scene_overlay_restore_all(Game *g, uint8_t *screen)
{
    while (DS_U8(g->ds, 0xC4AB))
        if (scene_overlay_restore(g))
            return -1;
    if (DS_U8(g->ds, 0xAE04)) {
        if (!screen)
            return -1;
        scene_vga_overlay_restore(g, screen);
    }
    return 0;
}
void scene_overlay_reset(uint8_t *ds)
{
    DS_U8(ds, 0xC4AB) = 0;
    DS_U16(ds, 0xC4C4) = 0xC4C6;
    DS_U16(ds, 0xC546) = 0;
    DS_U8(ds, 0xAE04) = 0;
}
