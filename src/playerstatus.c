/* Map-edge warning and vehicle refuelling, with native text and buffered input. */
#include "term.h"

int player_check_map_edge(Game *g, const TextPlatform *platform)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    uint16_t column = DS_U16(ds, actor + 30), row = DS_U16(ds, actor + 32);
    uint8_t flag;
    if (column <= 1) {
        flag = 1;
        if (!column)
            goto outside;
        if (!DS_U8(ds, 0x5CDC))
            goto message;
        goto north;
    }
    if (column >= 190) {
        flag = 2;
        if (column == 191)
            goto outside;
        if (!DS_U8(ds, 0x5CDC))
            goto message;
        goto north;
    }
    if (row <= 1)
        goto north;
    if (row >= 126)
        goto south;
    if (DS_U8(ds, 0x5CDC)) {
        DS_U8(ds, 0x5CDC) = 0;
        DS_U8(ds, 0x5CDA) = 0;
        hud_message_hide(g);
    }
    return 0;
north:
    flag = 4;
    if (!row)
        goto outside;
    if (!DS_U8(ds, 0x5CDC))
        goto message;
south:
    flag = 8; /* The source compares 63 here, despite the earlier >=126 gate. */
    if (row == 63)
        goto outside;
    if (!DS_U8(ds, 0x5CDC))
        goto message;
    return 0;
outside:
    DS_U8(ds, 0x5CDA) |= flag;
    if (actor == 0x04D4) {
        DS_U8(ds, DS_MISSION_OVER) = 1;
        DS_U8(ds, 0x5CDB) = 1;
    }
    return 0;
message:
    if (textbox_draw(g, 0x045B, 10, 8, 26, 6, platform) < 0)
        return -1;
    DS_U8(ds, 0x5CDC) = 255;
    return 0;
}

int vehicle_refuel_nearby(Game *g, const TextPlatform *ui, const KeyboardPlatform *keys)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_FUEL) == 100)
        return 0;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (!(DS_U8(ds, actor + 14) & 2))
        return 0;
    if (DS_U16(ds, actor + 10)) {
        DS_U8(ds, 0x5EE5) = 0;
        return 0;
    }
    uint16_t count = DS_U16(ds, DS_DRAW_COUNT), record = DS_U16(ds, DS_DRAW_LIST);
    for (uint16_t i = 0; i < count; ++i, record += 12) {
        if (DS_U16(ds, record + 8) != DS_U8(ds, 0x5EE3))
            continue;
        if (approx_distance(DS_I16(ds, actor), DS_I16(ds, actor + 4), DS_I16(ds, record), DS_I16(ds, record + 4))
            >= 800)
            continue;
        if (DS_U8(ds, 0x5EE5))
            return 0;
        DS_U8(ds, 0x5EE5) = 255;
        uint16_t cost = (uint16_t)((100 - DS_U16(ds, DS_FUEL)) * 2);
        /* 455F immediately returns because the latch was just set at 44F2.
         * The insufficient-funds message at 4569 is unreachable from this entry. */
        if (cost >= DS_U16(ds, DS_CASH))
            return 0;
        DS_U8(ds, 0x5A4E) = 255;
        if (textbox_draw_nonmodal(g, 0x083A, 12, 8, 24, 10) < 0)
            return -1;
        uint32_t ch;
        do {
            map_clear_key_buffer(ds);
            ch = keyboard_read(g, keys);
            if (ch == UINT32_MAX)
                return -1;
        } while ((uint8_t)ch == ']');
        DS_U8(ds, 0x5A4E) = 0;
        if (scene_overlay_restore(g) < 0)
            return -1;
        if (((uint8_t)ch & 0xDF) != 'F')
            return 0;
        cost = (uint16_t)((100 - DS_U16(ds, DS_FUEL)) * 2);
        DS_U16(ds, DS_CASH) -= cost;
        DS_U16(ds, DS_FUEL) = 100;
        return textbox_draw(g, 0x08A4, 12, 8, 22, 8, ui);
    }
    return 0;
}
