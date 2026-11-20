/* Alternate indexed VGA menu, original 9D36/9E59. */
#include "term.h"

static int menu_service(Game *g, const MenuPlatform *host, uint16_t op, uint16_t a, uint16_t b)
{
    return !host || !host->call ? -1 : host->call(g, op, a, b, host->user);
}

int menu_vga_prepare(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                     uint16_t actions, const MenuPlatform *host)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_FACILITY_SCREEN) || !screen || !host || !host->call)
        return -1;
    while (DS_U8(ds, DS_KEYBUF_COUNT))
        keyboard_read_available(g);
    DS_U16(ds, 0x7816) = actions;
    DS_U8(ds, 0x8161) = 255;
    DS_U16(ds, DS_MENU_ITEM) = DS_U16(ds, 0x784C) = 0;
    DS_U16(ds, 0x7850) = width - 2;
    text = textbox_vga_base(g, screen, text, x, y, width, height);
    DS_U16(ds, DS_BOX_X) >>= 3;
    DS_U16(ds, DS_BOX_Y) >>= 3;
    uint16_t seg = DS_U16(ds, 0xEA36);
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
            DS_U8(ds, DS_TEXT_COLOUR) = 14;
            DS_U16(ds, 0x78DA) = screen_text8_vga(g, screen, seg, text);
            DS_U8(ds, DS_TEXT_COLOUR) = colour;
            *far_ptr(g, seg, ++text) = saved;
            DS_U16(ds, DS_TEXT_COLUMN)++;
        }
        start = screen_text8_vga(g, screen, seg, text);
        if (DS_U16(ds, 0x78DA))
            start = DS_U16(ds, 0x78DA);
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
    map_clear_key_buffer(ds);
    while (DS_U8(ds, KEY_DOWN(SC_ESC)) || DS_U8(ds, KEY_DOWN(SC_ENTER)))
        if (menu_service(g, host, MM_RELEASE_BEFORE, 0, 0))
            return -1;
    DS_U16(ds, 0x784C)--;
    menu_vga_highlight(ds, screen, DS_U16(ds, 0x781A + (uint16_t)(DS_U16(ds, DS_MENU_ITEM) * 2)));
    return 0;
}

int menu_vga_run(Game *g, uint8_t *screen, const MenuPlatform *host)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_FACILITY_SCREEN) || !host || !host->call)
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
                scene_vga_overlay_restore(g, screen);
                return 0;
            } else {
                int step = DS_U8(ds, KEY_DOWN(SC_UP)) ? -1 : DS_U8(ds, KEY_DOWN(SC_DOWN)) ? 1 : 0;
                if (!step)
                    continue;
                menu_vga_highlight(ds, screen, DS_U16(ds, 0x781A + (uint16_t)(DS_U16(ds, DS_MENU_ITEM) * 2)));
                uint16_t index = DS_U16(ds, DS_MENU_ITEM), count = DS_U16(ds, 0x784C);
                if (step < 0 && !index)
                    index = count;
                index += step;
                if (index >= count)
                    index = 0;
                DS_U16(ds, DS_MENU_ITEM) = index;
                menu_vga_highlight(ds, screen, DS_U16(ds, 0x781A + (uint16_t)(index * 2)));
                continue;
            }
        }
        uint16_t index = DS_U16(ds, DS_MENU_ITEM), target = DS_U16(ds, DS_U16(ds, 0x7816) + (uint16_t)(index * 2));
        int status = menu_service(g, host, MM_ACTION, target, index);
        if (status < 0)
            return -1;
        if (status > 0)
            return status; /* the handler closed the menu (MENU_CLOSED / MENU_CLOSED_CARRY) or left it */
    }
}

int menu_vga_display(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                     uint16_t actions, const MenuPlatform *host)
{
    if (menu_vga_prepare(g, screen, text, x, y, width, height, actions, host))
        return -1;
    return menu_vga_run(g, screen, host);
}
