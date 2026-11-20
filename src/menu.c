/* Original planar menu 48E6/4A96 and highlight 5776:02D5/0330.
 * Timing/input changes and option handler bodies are explicit synchronous services. */
#include "term.h"

static int menu_service(Game *g, const MenuPlatform *host, uint16_t op, uint16_t a, uint16_t b)
{
    return !host || !host->call ? -1 : host->call(g, op, a, b, host->user);
}

int menu_highlight(Game *g, uint16_t dest)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t width = DS_U16(ds, 0x7850), rounded = width;
    if (rounded & 1)
        rounded = (rounded & 0xFF00) | (uint8_t)(rounded + 1);
    uint16_t seg = DS_U16(ds, 0x91C2), at = DS_U16(ds, DS_LOAD_BUFFER), stride = DS_U16(ds, DS_SCREEN_STRIDE);
    for (unsigned plane = 0; plane < 4; ++plane) {
        ega_gc(p, 4, plane);
        for (unsigned row = 0; row < 9; ++row)
            for (unsigned col = 0; col < rounded; ++col)
                *far_ptr(g, seg, at++) = ega_load(p, (uint16_t)(dest - stride + row * stride + col));
    }
    ega_seq_mask(p, 8);
    ega_gc(p, 1, 1);
    ega_gc(p, 0, 1);
    ega_gc(p, 8, 255);
    dest -= stride;
    DS_U16(ds, 0xC548) = dest;
    for (unsigned row = 0; row < 9; ++row)
        for (unsigned col = 0; col < width; ++col)
            ega_store(p, (uint16_t)(dest + row * stride + col), 255);
    ega_gc(p, 1, 0);
    ega_seq_mask(p, 15);
    return 0;
}

int menu_unhighlight(Game *g)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t width = DS_U16(ds, 0x7850), stride = DS_U16(ds, DS_SCREEN_STRIDE), dest = DS_U16(ds, 0xC548);
    uint16_t seg = DS_U16(ds, 0x91C2), at = DS_U16(ds, DS_LOAD_BUFFER);
    ega_gc(p, 3, 0);
    ega_gc(p, 5, 0);
    ega_gc(p, 8, 255);
    ega_gc(p, 1, 0);
    /* The source copies an extra fifth plane under sequencer mask 10h. */
    for (unsigned plane = 1; plane < 32; plane *= 2) {
        ega_seq_mask(p, plane);
        for (unsigned row = 0; row < 9; ++row) {
            for (unsigned col = 0; col < width; ++col)
                ega_store(p, (uint16_t)(dest + row * stride + col), *far_ptr(g, seg, at++));
            if (width & 1)
                ++at;
        }
    }
    ega_seq_mask(p, 15);
    return 0;
}

static uint16_t text_address(uint8_t *ds)
{
    uint16_t stride = DS_U16(ds, DS_SCREEN_STRIDE);
    return (uint16_t)(DS_U8(ds, DS_TEXT_ROW) * (stride == 80 ? 640 : 320) + DS_U16(ds, 0xE41C) * stride
                      + DS_U16(ds, DS_TEXT_COLUMN) + DS_U16(ds, DS_DRAW_PAGE));
}

int menu_prepare(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height, uint16_t actions,
                 const MenuPlatform *host)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_FACILITY_SCREEN) || !host || !host->call)
        return -1;
    while (DS_U8(ds, DS_KEYBUF_COUNT))
        keyboard_read_available(g);
    DS_U8(ds, 0x8161) = 255;
    DS_U16(ds, DS_MENU_ITEM) = DS_U16(ds, 0x784C) = 0;
    DS_U16(ds, 0x7850) = width - 2;
    uint16_t rows = height * 8;
    DS_U8(ds, DS_BOX_X) = x;
    DS_U8(ds, DS_BOX_Y) = y;
    DS_U16(ds, 0x7816) = actions;
    uint16_t page = DS_U16(ds, 0x123C + DS_U8(ds, DS_PAGE_SHOWN) * 2), old_page = DS_U16(ds, DS_DRAW_PAGE);
    uint16_t dest = x + (uint16_t)(DS_U16(ds, DS_SCREEN_STRIDE) * 8) * y + page;
    DS_U16(ds, 0x7818) = page;
    if (scene_overlay_save(g, dest, width, rows))
        return -1;
    ega_seq_mask(p, 15);
    ega_gc(p, 8, 255);
    ega_gc(p, 0, DS_U8(ds, 0x775C));
    ega_gc(p, 1, 15);
    ega_gc(p, 5, 0);
    ega_gc(p, 3, 0);
    for (unsigned row = 0; row < (rows ? rows : 65536u); ++row) {
        for (unsigned col = 0; col < width; ++col)
            ega_store(p, (uint16_t)(dest + col), 3);
        dest += DS_U16(ds, DS_SCREEN_STRIDE);
    }
    uint16_t seg = DS_U16(ds, 0xEA36);
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, DS_FILL_COLOUR) = *far_ptr(g, seg, text++);
    DS_U16(ds, DS_DRAW_PAGE) = page;
    textbox_border(g);
    DS_U16(far_ptr(g, seg, 0), 0x211) = 0x1F6;
    DS_U16(far_ptr(g, seg, 0), 0x20F) = 0;
    for (;;) {
        DS_U8(ds, DS_TEXT_COLUMN) = *far_ptr(g, seg, text++) + DS_U8(ds, DS_BOX_X);
        DS_U8(ds, DS_TEXT_ROW) = *far_ptr(g, seg, text++) + DS_U8(ds, DS_BOX_Y);
        DS_U16(ds, 0x78DA) = 0;
        uint16_t start = 0;
        if (DS_U16(ds, 0x784C)) {
            uint16_t hotkey = DS_U16(far_ptr(g, seg, 0), 0x211);
            *far_ptr(g, seg, hotkey++) = *far_ptr(g, seg, text);
            DS_U16(far_ptr(g, seg, 0), 0x211) = hotkey;
            DS_U16(far_ptr(g, seg, 0), 0x20F)++;
            uint8_t saved = *far_ptr(g, seg, text + 1), colour = DS_U8(ds, DS_TEXT_COLOUR);
            *far_ptr(g, seg, text + 1) = 0;
            DS_U8(ds, DS_TEXT_COLOUR) = 15;
            if (screen_text8(g, seg, text))
                return -1;
            DS_U16(ds, 0x78DA) = text_address(ds);
            DS_U8(ds, DS_TEXT_COLOUR) = colour;
            *far_ptr(g, seg, ++text) = saved;
            DS_U16(ds, DS_TEXT_COLUMN)++;
        }
        if (screen_text8(g, seg, text))
            return -1;
        start = DS_U16(ds, 0x78DA);
        if (!start)
            start = text_address(ds);
        DS_U16(ds, 0x784C)++;
        if (DS_U16(ds, 0x784C) >= 2)
            DS_U16(ds, 0x781A + (uint16_t)((DS_U16(ds, 0x784C) - 2) * 2)) = start - 3;
        uint16_t scan = text, left = 65535;
        while (left--)
            if (!*far_ptr(g, seg, scan++))
                break;
        if (*far_ptr(g, seg, scan) == 255)
            break;
        text = scan;
    }
    DS_U16(ds, 0x5B6A) = DS_U16(ds, DS_KEYBUF_COUNT) = 0;
    DS_U16(ds, DS_KEYBUF_READ) = DS_U16(ds, 0x5B6C) = 0x5B70;
    while (DS_U8(ds, KEY_DOWN(SC_ESC)) || DS_U8(ds, KEY_DOWN(SC_ENTER)))
        if (menu_service(g, host, MM_RELEASE_BEFORE, 0, 0))
            return -1;
    DS_U16(ds, 0x784C)--;
    DS_U16(ds, DS_DRAW_PAGE) = old_page;
    return menu_highlight(g, DS_U16(ds, 0x781A + (uint16_t)(DS_U16(ds, DS_MENU_ITEM) * 2)));
}

int menu_run(Game *g, const MenuPlatform *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN) || !host || !host->call)
        return -1;
    for (;;) {
        int invoke = 0;
        if (DS_U8(ds, DS_KEYBUF_COUNT)) {
            uint8_t ch = keyboard_read_available(g);
            if (ch >= 'a' && ch <= 'z')
                ch -= 'a' - 'A';
            uint16_t seg = DS_U16(ds, 0xEA36), at = 0x1F6, left = DS_U16(far_ptr(g, seg, 0), 0x20F) + 1;
            while (left) {
                --left;
                if (*far_ptr(g, seg, at++) == ch)
                    break;
            }
            if (left) {
                DS_U16(ds, DS_MENU_ITEM) = at - 0x1F7;
                invoke = 1;
            }
        }
        if (!invoke) {
            if (menu_service(g, host, MM_WAIT, 5, 0))
                return -1;
            if (DS_U8(ds, KEY_DOWN(SC_ENTER)))
                invoke = 1;
            else if (DS_U8(ds, KEY_DOWN(SC_ESC))) {
                while (DS_U8(ds, KEY_DOWN(SC_ESC)))
                    if (menu_service(g, host, MM_RELEASE_AFTER, 0, 0))
                        return -1;
                return scene_overlay_restore(g);
            } else {
                int step = DS_U8(ds, KEY_DOWN(SC_UP)) ? -1 : DS_U8(ds, KEY_DOWN(SC_DOWN)) ? 1 : 0;
                if (!step)
                    continue;
                if (menu_unhighlight(g))
                    return -1;
                uint16_t index = DS_U16(ds, DS_MENU_ITEM), count = DS_U16(ds, 0x784C);
                if (step < 0 && !index)
                    index = count;
                index += step;
                if (index >= count)
                    index = 0;
                DS_U16(ds, DS_MENU_ITEM) = index;
                if (menu_highlight(g, DS_U16(ds, 0x781A + (uint16_t)(index * 2))))
                    return -1;
                continue;
            }
        }
        uint16_t index = DS_U16(ds, DS_MENU_ITEM), target = DS_U16(ds, DS_U16(ds, 0x7816) + (uint16_t)(index * 2));
        int status = menu_service(g, host, MM_ACTION, target, index);
        if (status < 0)
            return -1;
        if (status > 0)
            return status; /* the handler closed the menu: MENU_CLOSED or MENU_CLOSED_CARRY */
    }
}

int menu_display(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height, uint16_t actions,
                 const MenuPlatform *host)
{
    if (menu_prepare(g, text, x, y, width, height, actions, host))
        return -1;
    return menu_run(g, host);
}

/* Option handlers that close through 4ED2/4EDC/4EEB; the 16-bit stack unwind
 * is represented by return 1. Music driver execution remains a host boundary. */
static int basic_action(Game *g, uint8_t *screen, uint16_t target, const MenuPlatform *host)
{
    uint8_t *ds = g->ds;
    if (target != 0x4B4A && target != 0x4ED2 && target != 0x4EDC && target != 0x4EEB)
        return -1;
    if (DS_U8(ds, DS_FACILITY_SCREEN) && !screen)
        return -1;
    if (target == 0x4B4A) {
        DS_U8(ds, 0x0361) ^= 1;
        if (!DS_U8(ds, 0x0361)) {
            DS_U8(ds, 0x11CC) = 0;
            if (menu_service(g, host, 0xF494, 0, 0))
                return -1;
        } else {
            DS_U8(ds, 0x11CC) = 1;
            if (DS_U8(ds, 0xA616) && menu_service(g, host, 0xF4A1, 0, 0))
                return -1;
        }
    }
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        scene_vga_overlay_restore(g, screen);
    else if (scene_overlay_restore(g))
        return -1;
    if (target == 0x4EDC)
        DS_U8(ds, DS_MENU_YES) = 1;
    else if (target == 0x4EEB)
        DS_U8(ds, DS_MENU_YES) = 0;
    return 1;
}

int menu_basic_action(Game *g, uint16_t target, const MenuPlatform *host)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN))
        return -1;
    return basic_action(g, NULL, target, host);
}

int menu_vga_basic_action(Game *g, uint8_t *screen, uint16_t target, const MenuPlatform *host)
{
    if (!DS_U8(g->ds, DS_FACILITY_SCREEN) || !screen)
        return -1;
    return basic_action(g, screen, target, host);
}
