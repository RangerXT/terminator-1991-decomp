/* Inventory equipment flags, component combination and dynamic menu (93CA/943E/946C). */
#include "term.h"

void inventory_combine_components(uint8_t *ds)
{
    if (DS_U8(ds, 0xAAA6) || !DS_U8(ds, 0xAA99) || !DS_U8(ds, 0xAA9A) || !DS_U8(ds, 0xAA9B))
        return;
    DS_U8(ds, 0xAAA6) = 1;
    inventory_remove(ds, DS_U8(ds, 0xAA99));
    inventory_remove(ds, DS_U8(ds, 0xAA9A));
}

uint16_t inventory_equipment_menu(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0xEA36), source = 0x0AE5, dest = 0x0AF9;
    uint8_t ch;
    DS_U16(ds, DS_SPECIAL_MENU_HEIGHT) = 5;
    do {
        ch = *far_ptr(g, seg, source++);
        *far_ptr(g, seg, dest++) = ch;
    } while (ch);
    uint16_t line = 4;
    for (unsigned i = 0; i < 5; ++i) {
        if (!DS_U8(ds, 0xAAA5 + i))
            continue;
        *far_ptr(g, seg, dest++) = 4;
        *far_ptr(g, seg, dest++) = line;
        source = DS_U16(far_ptr(g, seg, (uint16_t)(0x0BC1 + 2 * i)), 0);
        do {
            ch = *far_ptr(g, seg, source++);
            *far_ptr(g, seg, dest++) = ch;
        } while (ch);
        DS_U16(ds, 0xAAAD + (line - 4)) = DS_U16(ds, 0xAB2E + 2 * i);
        line += 2;
        DS_U16(ds, DS_SPECIAL_MENU_HEIGHT) += 2;
        DS_U8(ds, DS_SPECIAL_MENU_READY) = 1;
    }
    *far_ptr(g, seg, dest++) = 255;
    return dest;
}

void inventory_refresh_equipment(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t item = 0x05B0;
    while (DS_U8(ds, item + 2)) {
        uint8_t id = DS_U8(ds, item + 2);
        if (DS_U8(ds, item + 5) >= 1) {
            uint16_t i = 0;
            while (DS_U8(ds, 0xAAB9 + i)) {
                if (id == DS_U8(ds, 0xAAB9 + i)) {
                    DS_U8(ds, DS_U16(ds, 0xAB04 + (uint16_t)(i * 2))) = id;
                    break;
                }
                ++i;
            }
        }
        item += 6;
    }
    inventory_combine_components(ds);
    DS_U8(ds, DS_SPECIAL_MENU_READY) = 0;
    inventory_equipment_menu(g);
}

/* 9407: one contribution per required ID, scanning exactly nineteen slots. */
void inventory_count_required(uint8_t *ds)
{
    DS_U16(ds, 0xAB02) = 0;
    uint16_t list = DS_U16(ds, DS_PLAYER) == 0x04D4 ? 0xAAD2 : 0xAAE2;
    while (DS_U8(ds, list)) {
        uint8_t id = DS_U8(ds, list++);
        for (unsigned i = 0; i < 19; ++i)
            if (DS_U8(ds, 0x05B2 + 6 * i) == id) {
                DS_U16(ds, 0xAB02)++;
                break;
            }
    }
}
