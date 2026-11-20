/* Weapon-slot reconstruction and icon rendering for normal-view HUD setup. */
#include "term.h"

/* 5754/985C/98EF. Item records are six bytes; valid weapon IDs come from 78DC. */
void weapon_inventory_rebuild(uint8_t *ds)
{
    for (unsigned i = 0; i < 8; ++i)
        DS_U16(ds, 0x11AE + i * 2) = 65535;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U8(ds, player + 15) = 0;
    DS_U16(ds, 0xAAFE) = DS_U16(ds, DS_WEAPON) - 1;
    DS_U16(ds, 0xAB00) = DS_U16(ds, DS_WEAPON_SLOT) - 1;
    DS_U16(ds, DS_WEAPON) = DS_U16(ds, DS_WEAPON_SLOT) = 0;
    uint16_t item = 0x5B0;
    while (DS_U16(ds, item)) {
        if (DS_U8(ds, item + 4) == 1) {
            uint8_t id = DS_U8(ds, item + 2);
            uint16_t index = 0;
            while (DS_U8(ds, 0x78DC + index) != id)
                index++;
            DS_U8(ds, 0x793F) = id;
            uint16_t slot = DS_U8(ds, 0x78E4 + index), dest = 0x570 + slot * 6;
            uint16_t from = 0x8097 + index * 3;
            DS_U8(ds, dest) = slot;
            DS_U8(ds, dest + 1) = DS_U8(ds, from + 2);
            DS_U16(ds, dest + 4) = DS_U16(ds, from);
            /* 5754 leaves BX = the slot sign-extended (CBW), and the bit is ROL AL,CL: both
             * matter only for slots of 8 and up, which an unknown weapon id can produce */
            uint16_t icon = (uint16_t)(0x80F4 + 2 * (uint16_t)(int16_t)(int8_t)slot);
            DS_U16(ds, (uint16_t)(0x11AE + slot * 2)) = DS_U16(ds, icon);
            DS_U8(ds, player + 15) |= (uint8_t)(1u << (slot & 7));
            if (slot == DS_U16(ds, 0xAAFE))
                DS_U16(ds, DS_WEAPON) = slot + 1;
            if (slot == DS_U16(ds, 0xAB00))
                DS_U16(ds, DS_WEAPON_SLOT) = slot + 1;
        }
        item += 6;
    }
    if (DS_U16(ds, DS_WEAPON_SLOT) && !DS_U16(ds, DS_WEAPON)) {
        DS_U16(ds, DS_WEAPON) = DS_U16(ds, DS_WEAPON_SLOT);
        DS_U16(ds, DS_WEAPON_SLOT) = 0;
    }
}

/* 11BC:1BE1. Source rows contain six bytes; only five are displayed. */
void hud_weapon_icon(Game *g, uint16_t dest, uint16_t mask)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x9A4A) || DS_U8(ds, DS_CAMERA_MODE) == 2)
        return;
    ega_gc(g->planes, 1, 0);
    uint16_t seg = g->ds_seg - 0x426D, source = 0x13B0;
    for (unsigned plane = 0; plane < 4; ++plane) {
        ega_seq_mask(g->planes, 1 << plane);
        for (unsigned page = 0; page < 3; ++page) {
            uint16_t from = source, to = dest + page * 0x2000;
            for (unsigned row = 0; row < 20; ++row) {
                mask = (mask << 1) | (mask >> 15);
                for (unsigned word = 0; word < 2; ++word) {
                    uint8_t *at = far_ptr(g, seg, from);
                    uint16_t value = (uint16_t)(at[0] | (at[1] << 8)) & mask;
                    from += 2;
                    ega_store(g->planes, to++, (uint8_t)value);
                    ega_store(g->planes, to++, (uint8_t)(value >> 8));
                }
                ega_store(g->planes, to++, (uint8_t)(*far_ptr(g, seg, from++) & mask));
                from++;
                to += 35;
            }
        }
        source += 120;
    }
    ega_seq_mask(g->planes, 15);
}

/* 11BC:1EEB/1F17: the selection rectangle in the requested set/reset colour. */
void hud_weapon_selection(Game *g, uint16_t slot, uint8_t colour)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if (DS_U8(ds, DS_CAMERA_MODE) == 2)
        return;
    uint16_t dest = 0x1C48 + DS_U16(ds, 0x8104 + (uint16_t)((slot - 1) * 2));
    ega_gc(p, 0, colour);
    ega_gc(p, 1, 15);
    ega_gc(p, 8, 255);
    for (unsigned page = 0; page < 3; ++page) {
        uint16_t count = page ? 5 : ((slot - 1) & 0xFF00) | 5;
        for (uint32_t i = 0; i < count; ++i)
            ega_store(p, (uint16_t)(dest + page * 0x2000 + i), 0);
    }
    for (unsigned side = 0; side < 2; ++side) {
        ega_gc(p, 8, side ? 1 : 128);
        for (unsigned page = 0; page < 3; ++page)
            for (unsigned row = 0; row < 18; ++row) {
                uint16_t at = dest + side * 4 + page * 0x2000 + row * 40;
                uint8_t value = ega_load(p, at);
                ega_store(p, at, value);
            }
    }
    ega_gc(p, 8, 255);
    for (unsigned page = 0; page < 3; ++page)
        for (unsigned col = 0; col < 5; ++col)
            ega_store(p, (uint16_t)(dest + 680 + page * 0x2000 + col), 8);
    ega_gc(p, 0, 0);
    ega_gc(p, 1, 0);
}

/* 11BC:1C7D, including native inventory reconstruction. */
int hud_weapon_slots(Game *g)
{
    uint8_t *ds = g->ds;
    weapon_inventory_rebuild(ds);
    if (DS_U8(ds, DS_CAMERA_MODE) == 2)
        return 0;
    ega_gc(g->planes, 8, 255);
    uint16_t player = DS_U16(ds, DS_PLAYER), seg = g->ds_seg - 0x426D;
    for (unsigned slot = 0; slot < 8; ++slot) {
        uint16_t source = DS_U16(ds, 0x11AE + slot * 2);
        uint8_t present = !(source & 0x8000);
        if (present) {
            DS_U16(ds, DS_UNPACK_SRC_SEG) = DS_U16(ds, DS_UNPACK_DST_SEG) = seg;
            uint8_t *header = far_ptr(g, seg, (uint16_t)(source + 12));
            uint8_t lzhuf = (header[0] & 8) != 0;
            if (image_unpack_shared(g, source, 0x13B0, lzhuf) == UINT64_MAX)
                return -1;
            DS_U16(ds, DS_UNPACK_DST_SEG) = g->ds_seg;
        }
        uint8_t flags = DS_U8(ds, player + 15), draw = flags & 1;
        DS_U8(ds, player + 15) = (flags >> 1) | (flags << 7);
        if (present && draw)
            hud_weapon_icon(g, (uint16_t)(0x1C20 + DS_U16(ds, 0x8104 + slot * 2)), 65535);
    }
    if (DS_U16(ds, DS_WEAPON)) {
        hud_weapon_selection(g, DS_U16(ds, DS_WEAPON), 12);
        if (DS_U16(ds, DS_WEAPON_SLOT))
            hud_weapon_selection(g, DS_U16(ds, DS_WEAPON_SLOT), 14);
    }
    return 0;
}

/* 5776:012A: select the lower panel for the current actor/vehicle. */
void hud_choose_panel(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER), index = 16, name = 0xC48A;
    if (!(DS_U8(ds, player + 14) & 2)) {
        index = 12;
        name = 0xC494;
        if (player != 0x04D4) {
            index = 14;
            name = 0xC49F;
        }
    }
    DS_U16(ds, 0xC4AC) = name;
    DS_U16(ds, 0xC4AE) = index;
}

/* 745B: three-row marker for the currently selected body/system field. */
void hud_field_marker(Game *g)
{
    uint8_t *ds = g->ds, *p = g->planes;
    if ((DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 1) || DS_U8(ds, DS_CAMERA_MODE))
        return;
    uint16_t index = DS_U16(ds, 0x0414);
    if (index == 4)
        return;
    if (index > 4)
        index--;
    uint16_t dest = DS_U16(ds, 0x8120 + index * 2);
    ega_gc(p, 8, 192);
    ega_gc(p, 1, 15);
    ega_gc(p, 0, DS_U8(ds, 0x5A23));
    for (unsigned row = 0; row < 3; ++row)
        for (unsigned page = 0; page < 3; ++page) {
            uint16_t at = dest + row * 40 + page * 0x2000;
            uint8_t value = ega_load(p, at);
            ega_store(p, at, value);
        }
    ega_gc(p, 1, 0);
    ega_gc(p, 8, 255);
}

/* 735A: raw armor panel overlay from the far work buffer, all three pages. */
int hud_armor_overlay(Game *g, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    if (!(DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 8))
        return 0;
    uint16_t seg = DS_U16(ds, 0xE16E), offset = DS_U16(ds, 0xE16C);
    if (file_load(g, io, 0x8135, seg, offset) == UINT32_MAX)
        return -1;
    for (unsigned page = 0; page < 3; ++page)
        screen_blit_five_plane_bytes(g, seg, 16, (uint16_t)(0x184C + page * 0x2000), 4, 23, 40);
    return 0;
}

/* 4F4B: lower-panel load, upper bitmap refresh, inventory icons and counters. */
static int init_normal(Game *g, const ImageIO *io, uint16_t *bx)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_CAMERA_MODE) == 2)
        return 0;
    if (!io || !io->call)
        return -1;
    uint16_t page = DS_U16(ds, DS_DRAW_PAGE);
    DS_U16(ds, DS_DRAW_PAGE) = 0;
    DS_U16(ds, 0x8082) = 0x1130;
    DS_U16(ds, 0x805C) = 0x0898;
    if (image_load_screen(g, io, DS_U16(ds, 0xC4AC)))
        return -1;
    DS_U16(ds, 0xC4AE) = 0;
    DS_U16(ds, 0x805C) = 0x1F40;
    DS_U16(ds, 0x8082) = 0;
    DS_U16(ds, DS_DRAW_PAGE) = page;
    screen_copy_rect(g, 0x1130, 0x3130, 40, 90);
    screen_copy_rect(g, 0x1130, 0x5130, 40, 90);
    HudServices images = {image_hud_service, (void *)io};
    if (hud_refresh_pages(g, &images))
        return -1;
    if (!DS_U16(ds, 0x0208))
        DS_U16(ds, DS_VISIBLE_CELL) = 65534;
    if (hud_weapon_slots(g))
        return -1;
    if (hud_armor_overlay(g, io))
        return -1;
    if (bx) {
        uint16_t player = DS_U16(ds, DS_PLAYER);
        hud_clear_bytes(g, 0x12DF, 1);
        DS_U8(ds, DS_NUMBER_DIGITS) = 2;
        DS_U8(ds, DS_NUMBER_COLOUR) = 15;
        *bx = hud_draw_number_bx(g, DS_U16(ds, player + 10), 0x12DF);
        DS_U8(ds, DS_NUMBER_DIGITS) = 3;
        if (DS_U8(ds, 0xAA96))
            *bx = hud_compass_needle_bx(g, 0x7B3C, DS_U16(ds, player + 6), 14);
    } else {
        hud_draw_speed(g);
        hud_draw_vehicle_counter(g);
        hud_draw_compass(g);
    }
    DS_U8(ds, 0x5A23) = 12;
    hud_field_marker(g);
    return 0;
}

int hud_init_normal(Game *g, const ImageIO *io)
{
    return init_normal(g, io, NULL);
}

int32_t hud_init_walking_state(Game *g, const ImageIO *io, uint16_t bx)
{
    if (DS_U8(g->ds, DS_U16(g->ds, DS_PLAYER) + 14) != 1)
        return -1;
    return init_normal(g, io, &bx) < 0 ? -1 : bx;
}
