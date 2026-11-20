/* Purchase leaves used by 84BF/850E: 865C/868C/86EA and regular 855A items. */
#include "term.h"

static int shop_close_window(Game *g, uint8_t *screen)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN)) {
        if (!screen)
            return -1;
        scene_vga_overlay_restore(g, screen);
        return 0;
    }
    return scene_overlay_restore(g);
}
static int shop_notice(Game *g, uint8_t *screen, const TextPlatform *input, uint16_t text, uint16_t x, uint16_t y,
                       uint16_t width, uint16_t height)
{
    if (shop_close_window(g, screen))
        return -1;
    int status = DS_U8(g->ds, DS_FACILITY_SCREEN) ? textbox_vga_draw(g, screen, text, x, y, width, height, input)
                                                  : textbox_draw(g, text, x, y, width, height, input);
    return status < 0 ? -1 : 1;
}

/* 0 accepted, 1 declined with original message, -1 unavailable UI. Equality is
 * insufficient funds in the executable, so an item needs strictly more cash. */
int shop_pay_item(Game *g, uint16_t definition, const TextPlatform *input, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    uint16_t price = DS_U8(ds, definition + 3);
    if (price == 255)
        return shop_notice(g, screen, input, 0x0EA6, 4, 2, 17, 7);
    price *= 4;
    if (price >= DS_U16(ds, DS_CASH))
        return shop_notice(g, screen, input, 0x0E7A, 12, 8, 22, 10);
    DS_U16(ds, DS_CASH) -= price;
    DS_U16(ds, DS_U16(ds, 0x9A6E) == 0x9AB8 ? 0x04C8 : 0x04CA) += price;
    return 0;
}

int shop_check_permit(Game *g, uint16_t definition, const TextPlatform *input, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, 0x9A6E) != 0x9BE2 || DS_U8(ds, definition) == 0xA8 || DS_U8(ds, 0xAAA4))
        return 0;
    return shop_notice(g, screen, input, 0x0F9A, 12, 8, 22, 7);
}

/* Outputs are source SI and category counter DI on acceptance. Failure's two
 * DOS stack pops are represented as return 1 to the structured caller. */
int shop_check_capacity(Game *g, uint16_t *definition, uint16_t *counter, const TextPlatform *input, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    uint16_t item = DS_U16(ds, DS_U16(ds, 0x9A88) + DS_U16(ds, 0x9A70));
    *definition = item;
    uint16_t weight = (uint16_t)((int16_t)(int8_t)DS_U8(ds, item + 1) + DS_U16(ds, DS_CARRIED_WEIGHT));
    if (weight >= DS_U16(ds, 0x03F2))
        return shop_notice(g, screen, input, 0x0E49, 15, 4, 22, 10);
    uint16_t category = (uint8_t)(DS_U8(ds, item + 2) - 1);
    if (category > 4)
        category = 5;
    uint16_t count = DS_U16(ds, 0x9A4E + 2 * category);
    *counter = count;
    if (DS_U8(ds, count) > 19)
        return shop_notice(g, screen, input, 0x0E49, 15, 4, 22, 10);
    DS_U16(ds, DS_CARRIED_WEIGHT) = weight;
    return 0;
}

/* 855A excluding weapon upgrades 23/26, which need the selection menu. Returns
 * original carry (1 stacked, 0 appended); -1 unsupported before mutation. */
int shop_add_regular_item(Game *g, uint16_t definition, uint16_t counter)
{
    uint8_t *ds = g->ds;
    uint8_t id = DS_U8(ds, definition);
    if (id == 0x23 || id == 0x26)
        return -1;
    DS_U8(ds, 0x9950) = 0;
    uint16_t slot = 0x05B0;
    int stacked = 0;
    if (id != 0x10 && id != 0xA5) {
        DS_U8(ds, 0x7A18) = 0;
        if (id == 15)
            DS_U8(ds, DS_U16(ds, DS_PLAYER) + 51) += 8;
        uint16_t i = 0;
        while (DS_U8(ds, 0x9A39 + i) != 255) {
            if (DS_U8(ds, 0x9A39 + i) == id) {
                DS_U8(ds, 0x1138 + DS_U8(ds, 0x9A3A + i))++;
                break;
            }
            i += 2;
        }
        for (;;) {
            if (DS_U8(ds, slot + 2) == id) {
                DS_U8(ds, slot + 5)++;
                stacked = 1;
                break;
            }
            slot += 6;
            if (!DS_U8(ds, slot))
                break;
        }
    }
    if (!stacked) {
        uint16_t ax = id;
        if (id == 0x10) {
            ax = DS_U16(ds, 0x04C8);
            DS_U16(ds, DS_CASH) += ax;
            DS_U16(ds, 0x04C8) = 0;
            DS_U8(ds, 0x9A49) = 255;
        }
        /* Source compares AL again after the first refund replaced AX. */
        if ((uint8_t)ax == 0xA5) {
            DS_U8(ds, 0x9A49) = 255;
            DS_U16(ds, DS_CASH) += DS_U16(ds, 0x04CA);
            DS_U16(ds, 0x04CA) = 0;
        }
        slot = DS_U16(ds, DS_INVENTORY_END);
        DS_U16(ds, slot + 2) = DS_U16(ds, definition);
        DS_U16(ds, slot + 4) = 0x0100 | DS_U8(ds, definition + 2);
        DS_U16(ds, slot) = DS_U16(ds, DS_U16(ds, 0x9A6E) + DS_U16(ds, 0x9A70));
        DS_U16(ds, DS_INVENTORY_END) += 6;
        DS_U8(ds, counter)++;
    }
    DS_U16(ds, 0x0384)++;
    inventory_refresh_equipment(g);
    return stacked;
}

/* Complete 855A composition. Results describe which DOS caller levels were
 * unwound, so the purchase-action controller can perform the right cleanup. */
int shop_add_item(Game *g, uint16_t definition, uint16_t counter, const MenuPlatform *menu, const TextPlatform *input,
                  uint8_t *screen)
{
    uint8_t *ds = g->ds;
    uint8_t id = DS_U8(ds, definition);
    if (id != 0x23 && id != 0x26)
        return shop_add_regular_item(g, definition, counter);
    DS_U8(ds, 0x9950) = 0;
    DS_U8(ds, 0x7A18) = id == 0x23 ? 1 : 2;
    int slot = inventory_choose_weapon(g, menu, screen);
    if (slot == -1)
        return -1;
    /* 571F bypasses 861A on cancel: retain 7A18 and skip the counter/refresh. */
    if (slot == -2)
        return SHOP_ADD_CANCELED;
    int result = SHOP_ADD_UPGRADED;
    if (slot == -3) {
        int status = DS_U8(ds, DS_FACILITY_SCREEN) ? textbox_vga_draw(g, screen, 0x0FEC, 8, 4, 23, 6, input)
                                                   : textbox_draw(g, 0x0FEC, 8, 4, 23, 6, input);
        if (status < 0)
            return -1;
        result = SHOP_ADD_NO_WEAPON;
    } else
        DS_U8(ds, 0x8097 + (uint16_t)(slot * 3 + 2)) |= DS_U8(ds, 0x7A18);
    DS_U8(ds, 0x7A18) = 0;
    DS_U16(ds, 0x0384)++;
    inventory_refresh_equipment(g);
    return result;
}
