/* Weapon picker used by shop upgrades, original 56B2..5753. */
#include "term.h"

uint8_t inventory_weapon_menu_text(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0xEA36), source = 0x0A1F, dest = 2;
    uint8_t ch;
    do {
        ch = *far_ptr(g, seg, source++);
        *far_ptr(g, seg, dest++) = ch;
    } while (ch);
    uint16_t item = 0x05B0, index = 0;
    uint8_t line = 2;
    for (;;) {
        ++line;
        if (!DS_U16(ds, item))
            break;
        if (DS_U8(ds, item + 4) != 1)
            --line;
        else {
            DS_U8(ds, 0x792B + index++) = DS_U8(ds, item + 2);
            *far_ptr(g, seg, dest++) = 4;
            *far_ptr(g, seg, dest++) = line;
            source = DS_U16(ds, item);
            do {
                ch = DS_U8(ds, source++);
                *far_ptr(g, seg, dest++) = ch;
            } while (ch);
        }
        item += 6;
    }
    *far_ptr(g, seg, dest) = 255;
    return line;
}

uint16_t inventory_weapon_menu_choice(uint8_t *ds, uint16_t index)
{
    uint8_t id = DS_U8(ds, 0x792B + index);
    DS_U8(ds, 0x793F) = id;
    uint16_t which = 0;
    while (id != DS_U8(ds, 0x78DC + which))
        ++which;
    return DS_U8(ds, 0x78E4 + which);
}

typedef struct WeaponPicker {
    const MenuPlatform *input;
    int selected;
} WeaponPicker;
static int picker_service(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user)
{
    WeaponPicker *host = (WeaponPicker *)user;
    if (op == MM_ACTION) {
        if (a < 0x5724 || a > 0x5737)
            return -1;
        host->selected = inventory_weapon_menu_choice(g->ds, 0x5737 - a);
        return 1;
    }
    return host->input && host->input->call ? host->input->call(g, op, a, b, host->input->user) : -1;
}

/* Structured representation of the DOS unwind: >=0 selected slot, -2 canceled,
 * -3 no weapons, -1 unavailable. A selected window remains for its caller to close;
 * cancel already restored its background through the native generic menu. */
int inventory_choose_weapon(Game *g, const MenuPlatform *input, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN)) {
        if (!screen)
            return -1;
        scene_vga_overlay_restore(g, screen);
    } else if (scene_overlay_restore(g))
        return -1;
    if (inventory_weapon_menu_text(g) == 3)
        return -3;
    WeaponPicker context = {input, -2};
    MenuPlatform host = {picker_service, &context};
    int result = DS_U8(ds, DS_FACILITY_SCREEN) ? menu_vga_display(g, screen, 2, 5, 0, 22, 25, 0x7940, &host)
                                               : menu_display(g, 2, 5, 0, 22, 25, 0x7940, &host);
    return result < 0 ? -1 : context.selected;
}
