/* Weapon display helpers traced from 0000:6AFC and 7008. */
#include "term.h"

void weapon_classify_source(uint8_t *ds)
{
    uint16_t slot = (uint16_t)((DS_U16(ds, DS_WEAPON) - 1) * 2);
    DS_U8(ds, 0x115D) = DS_U16(ds, 0x11AE + slot) == DS_U16(ds, 0x8100) ? 255 : 0;
}

void weapon_draw_numbers(Game *g, uint16_t player)
{
    uint8_t *ds = g->ds;
    if (!(DS_U8(ds, player + 14) & 2) && DS_U8(ds, DS_CAMERA_MODE) != 2) {
        hud_clear_bytes(g, 0x1424, 2);
        if (DS_U16(ds, DS_WEAPON)) {
            uint16_t slot = (uint8_t)(DS_U16(ds, DS_WEAPON) - 1) * 6;
            DS_U8(ds, DS_NUMBER_COLOUR) = 15;
            DS_U8(ds, DS_NUMBER_DIGITS) = 2;
            DS_U16(ds, 0xE170) ^= 0xFFFF;
            hud_draw_number(g, (uint16_t)(int16_t)(int8_t)DS_U8(ds, 0x573 + slot), 0x1424);
            DS_U16(ds, 0xE170) ^= 0xFFFF;
            hud_clear_bytes(g, 0x162C, 2);
            if (DS_U16(ds, DS_WEAPON_SLOT)) {
                slot = (uint8_t)(DS_U16(ds, DS_WEAPON_SLOT) - 1) * 6;
                DS_U16(ds, 0xE170) ^= 0xFFFF;
                hud_draw_number(g, (uint16_t)(int16_t)(int8_t)DS_U8(ds, 0x573 + slot), 0x162C);
                DS_U16(ds, 0xE170) ^= 0xFFFF;
            }
        }
    }
    DS_U8(ds, DS_NUMBER_DIGITS) = 3;
}

/* 78D6: horizontal window predicate; deliberately no depth rejection. */
uint8_t weapon_target_rejected(uint8_t *ds, uint16_t entry)
{
    uint16_t target = DS_U16(ds, entry + 2), player = DS_U16(ds, DS_PLAYER);
    if (DS_I16(ds, target + 10) < 0)
        return 1;
    int16_t x = (uint16_t)(DS_U16(ds, target) - DS_U16(ds, player));
    int16_t z = (uint16_t)(DS_U16(ds, target + 4) - DS_U16(ds, player + 4));
    int16_t y = 30;
    rotate_xz(ds, &x, &z, (DS_U16(ds, player + 6) + DS_U16(ds, player + 8)) & 511);
    project_point(ds, &x, &y, (uint16_t)z);
    x = (uint16_t)(x + DS_U16(ds, DS_VIEW_CENTRE_X));
    return x < DS_I16(ds, DS_VIEW_LEFT) || x > DS_I16(ds, DS_VIEW_RIGHT);
}

/* 7884 / 789B: cycling changes the starting index, not the accepted index. */
void weapon_select_target(uint8_t *ds, uint8_t cycle)
{
    uint16_t count = DS_U16(ds, 0x1194), index = DS_U16(ds, 0x11AA);
    if (cycle && count) {
        index++;
        if (index >= count)
            index = 0;
        DS_U16(ds, 0x11AA) = index;
    }
    uint16_t entry = (uint16_t)(0x041A + index * 4);
    for (uint32_t n = 0; n < count; ++n) {
        if (!weapon_target_rejected(ds, entry)) {
            DS_U16(ds, DS_TARGET_RECORD) = DS_U16(ds, entry + 2);
            return;
        }
        entry += 4;
        if (++index == count) {
            index = 0;
            entry = 0x041A;
        }
    }
    DS_U16(ds, DS_TARGET_RECORD) = 0;
}

/* 720C: unsigned approximate distance after 16-bit absolute values. */
void weapon_lock_colour(uint8_t *ds, uint16_t x, uint16_t y)
{
    if ((int16_t)x < 0)
        x = (uint16_t)-x;
    if ((int16_t)y < 0)
        y = (uint16_t)-y;
    if (x > y) {
        uint16_t t = x;
        x = y;
        y = t;
    }
    uint16_t distance = (uint16_t)((x >> 2) + y);
    uint8_t colour = 15;
    if (DS_U8(ds, 0x0365) || distance < 6) {
        colour = 12;
        DS_U8(ds, 0x0365) = 1;
    }
    DS_U8(ds, DS_FILL_COLOUR) = DS_U8(ds, 0x0364) = colour;
}

/* 7158: target selection, lock indication and four-edge box. */
void weapon_draw_autoaim(Game *g)
{
    uint8_t *ds = g->ds;
    uint8_t cycle = DS_U8(ds, KEY_DOWN(SC_X)) && !DS_U8(ds, 0x8160);
    if (cycle)
        DS_U8(ds, 0x8160) = 1;
    if (!DS_U8(ds, KEY_DOWN(SC_X)))
        DS_U8(ds, 0x8160) = 0;
    weapon_select_target(ds, cycle);
    uint16_t target = DS_U16(ds, DS_TARGET_RECORD), player = DS_U16(ds, DS_PLAYER);
    if (target) {
        int16_t x = (uint16_t)(DS_U16(ds, target) - DS_U16(ds, player));
        int16_t z = (uint16_t)(DS_U16(ds, target + 4) - DS_U16(ds, player + 4));
        int16_t y = target;
        rotate_xz(ds, &x, &z, (DS_U16(ds, player + 6) + DS_U16(ds, player + 8)) & 511);
        if (z > 31) {
            project_point(ds, &x, &y, (uint16_t)z);
            weapon_lock_colour(ds, (uint16_t)x, 0);
            uint16_t sx = (uint16_t)(x + DS_U16(ds, DS_VIEW_CENTRE_X));
            uint16_t sy = DS_U16(ds, DS_VIEW_CENTRE_Y);
            if (sx > 56 && sx < 264 && sy > 36 && sy < 98) {
                sx -= 10;
                sy -= 10;
                DS_U16(ds, 0x04CC) = DS_U16(ds, DS_PEN_X) = sx;
                DS_U16(ds, 0x04CE) = DS_U16(ds, DS_PEN_Y) = sy;
                line_to(ds, g->planes, sx + 20, sy);
                line_to(ds, g->planes, sx + 20, sy + 20);
                line_to(ds, g->planes, sx, sy + 20);
                line_to(ds, g->planes, sx, sy);
                return;
            }
        }
    }
    DS_U16(ds, 0x04CC) = 65535;
    DS_U8(ds, 0x0365) = 0;
}

/* 6C93: low-word multiply and signed LOW BYTE angle conversion are intentional. */
void weapon_update_sight(uint8_t *ds)
{
    if (DS_U8(ds, DS_JOYSTICK)) {
        for (unsigned axis = 0; axis < 2; ++axis) {
            uint16_t delta = DS_U16(ds, 0x5A5E + axis * 2) - DS_U16(ds, axis ? 0x5A5A : 0x5A54);
            int16_t fraction = (uint16_t)((uint32_t)delta * DS_U16(ds, 0x5A64 + axis * 4));
            uint16_t value = (uint16_t)((fraction >> 7) + (uint32_t)delta * DS_U16(ds, 0x5A62 + axis * 4)
                                        + DS_U16(ds, 0x0408 + axis * 2));
            uint16_t limit = axis ? 86 : 296;
            if (value < 24)
                value = 24;
            else if (value >= limit)
                value = limit;
            DS_U16(ds, 0x11A2 + axis * 2) = value;
        }
    }
    for (unsigned axis = 0; axis < 2; ++axis) {
        int8_t delta = (uint8_t)(DS_U16(ds, 0x11A2 + axis * 2) - DS_U16(ds, 0x0408 + axis * 2));
        DS_I16(ds, 0x118A + axis * 2) = (delta * 49) / 160;
    }
}

/* 15F4: four disconnected white strokes; line_to updates the shared pen. */
void weapon_draw_crosshair(Game *g, uint16_t x, uint16_t y)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x1150))
        return;
    DS_U16(ds, DS_FILL_COLOUR) = 15;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y - 8;
    line_to(ds, g->planes, x, y - 2);
    uint16_t px = DS_U16(ds, DS_PEN_X), py = DS_U16(ds, DS_PEN_Y);
    DS_U16(ds, DS_PEN_Y) += 5;
    line_to(ds, g->planes, px, py + 11);
    DS_U16(ds, DS_PEN_X) = x - 8;
    DS_U16(ds, DS_PEN_Y) = y;
    line_to(ds, g->planes, x - 2, y);
    px = DS_U16(ds, DS_PEN_X);
    py = DS_U16(ds, DS_PEN_Y);
    DS_U16(ds, DS_PEN_X) += 5;
    line_to(ds, g->planes, px + 11, py);
}

/* 6EE0: charge/release tail of 6D49. No sound or damage calls on this path. */
void weapon_charge_step(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_NUMBER_COLOUR) = 15;
    DS_U16(ds, 0x04D0) += 5;
    hud_clear_bytes(g, 0x17B6, 2);
    if (DS_I16(ds, 0x04D0) <= 0)
        return;
    if (DS_U8(ds, KEY_DOWN(SC_ENTER))) {
        DS_U16(ds, 0xE170) = 65535;
        hud_draw_number(g, DS_U16(ds, 0x04D0), 0x17B6);
        DS_U16(ds, 0xE170) = 0;
        if (DS_I16(ds, 0x04D0) < 100)
            return;
    }
    if (DS_I16(ds, 0x04D0) <= 0)
        return;
    DS_U8(ds, 0x0373) = 255;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, 0x0367) = DS_U16(ds, player);
    DS_I16(ds, 0x0369) = DS_I16(ds, player + 2) >> 1;
    DS_U16(ds, 0x036B) = DS_U16(ds, player + 4);
    DS_U16(ds, 0x036D) = (DS_U16(ds, player + 6) + DS_U16(ds, player + 8) + DS_U16(ds, 0x118A)) & 511;
    DS_U16(ds, 0x036F) = ((uint8_t)DS_U16(ds, 0x04D0) * 22) / 23;
    DS_U16(ds, 0x0371) = 23;
    DS_U16(ds, 0x04D0) = 0xFFF1;
}

/* 6B70..6C92: sight composition AFTER the firing call at 6B6D.
 * Caller must have handled firing and the initial player/weapon gates. */
void weapon_draw_sights(Game *g)
{
    uint8_t *ds = g->ds;
    weapon_classify_source(ds);
    if (DS_U8(ds, 0x115D)) {
        weapon_draw_autoaim(g);
        if (DS_I16(ds, 0x04CC) >= 0 && DS_U8(ds, 0x0364) == 12 && !DS_U8(ds, KEY_DOWN(SC_BACKSLASH))) {
            weapon_draw_crosshair(g, DS_U16(ds, 0x04CC) + 10, DS_U16(ds, 0x04CE) + 10);
            return;
        }
        DS_U8(ds, 0x0365) = 0;
    }
    if (DS_U8(ds, KEY_DOWN(SC_BACKSLASH))) {
        DS_U8(ds, 0x0365) = 0;
        DS_U16(ds, DS_SIGHT_X) = DS_U16(ds, DS_VIEW_CENTRE_X);
        DS_U16(ds, DS_SIGHT_Y) = DS_U16(ds, DS_VIEW_CENTRE_Y);
        weapon_draw_crosshair(g, DS_U16(ds, DS_SIGHT_X), DS_U16(ds, DS_SIGHT_Y));
        DS_U16(ds, 0x118A) = DS_U16(ds, 0x118C) = 0;
        return;
    }
    uint16_t player = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, player + 25) & 64) {
        uint16_t r = random_word(ds);
        if ((r & 15) >= 12) {
            int16_t delta = (int8_t)r >> 4;
            uint16_t axis = (delta & 1) ? 2 : 0;
            DS_I16(ds, 0x1186 + axis) = delta;
            DS_U16(ds, 0x118A + axis) += delta;
            weapon_update_sight(ds);
            goto draw;
        }
    }
    if (DS_U8(ds, KEY_DOWN(SC_SPACE))) {
        if (!DS_U8(ds, DS_JOYSTICK)) {
            uint16_t step = (int8_t)DS_U8(ds, KEY_DOWN(SC_RSHIFT)) < 0 ? 3 : 1;
            if (DS_U8(ds, KEY_DOWN(SC_RIGHT))) {
                DS_U16(ds, DS_SIGHT_X) += step;
                if (DS_I16(ds, DS_SIGHT_X) > 290)
                    DS_U16(ds, DS_SIGHT_X) = 290;
            }
            if (DS_U8(ds, KEY_DOWN(SC_LEFT))) {
                DS_U16(ds, DS_SIGHT_X) -= step;
                if (DS_I16(ds, DS_SIGHT_X) < 28)
                    DS_U16(ds, DS_SIGHT_X) = 28;
            }
            if (DS_U8(ds, KEY_DOWN(SC_UP))) {
                DS_U16(ds, DS_SIGHT_Y) -= step;
                if (DS_I16(ds, DS_SIGHT_Y) < 18)
                    DS_U16(ds, DS_SIGHT_Y) = 18;
            }
            if (DS_U8(ds, KEY_DOWN(SC_DOWN))) {
                DS_U16(ds, DS_SIGHT_Y) += step;
                if (DS_I16(ds, DS_SIGHT_Y) > DS_I16(ds, 0x11C8))
                    DS_U16(ds, DS_SIGHT_Y) = DS_U16(ds, 0x11C8);
            }
        }
        weapon_update_sight(ds);
    }
draw:
    weapon_draw_crosshair(g, DS_U16(ds, DS_SIGHT_X), DS_U16(ds, DS_SIGHT_Y));
}

/* DAD6. If all four are occupied, the executable returns the following slot. */
uint16_t weapon_projectile_slot(uint8_t *ds)
{
    uint16_t slot = 0x10F0;
    for (unsigned i = 0; i < 4; ++i, slot += 18)
        if (!DS_U16(ds, slot + 16))
            break;
    return slot;
}

/* D896. The count gate is equality, not >=4; retain that exact behavior. */
void weapon_projectile_create(uint8_t *ds, uint16_t x, uint16_t z, uint16_t target_x, uint16_t target_z,
                              uint16_t heading, uint16_t mode)
{
    if (DS_U16(ds, DS_GUIDED_COUNT) == 4)
        return;
    DS_U16(ds, 0x037A)++;
    uint16_t slot = weapon_projectile_slot(ds);
    DS_U16(ds, slot) = x;
    DS_U16(ds, slot + 4) = z;
    DS_U16(ds, slot + 12) = target_x;
    DS_U16(ds, slot + 14) = target_z;
    DS_U16(ds, slot + 6) = heading;
    DS_U16(ds, slot + 8) = mode;
    DS_U16(ds, slot + 10) = DS_U16(ds, DS_TARGET_RECORD);
    DS_U16(ds, DS_GUIDED_COUNT)++;
    DS_U16(ds, slot + 16) = 65535;
}

/* 6B23: load weapons.cif and index its eight four-plane records.
 * Unlike the wheel indexer, this starts at the supplied far-buffer offset. */
int weapon_images_load(Game *g, const ImageIO *io)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0x80F2), source = DS_U16(ds, 0x80F0);
    if (file_load(g, io, 0x808A, seg, source) == UINT32_MAX)
        return -1;
    for (unsigned i = 0; i < 8; ++i) {
        DS_U16(ds, 0x80F4 + i * 2) = source;
        uint16_t size = 32;
        for (unsigned plane = 0; plane < 4; ++plane) {
            uint8_t *at = far_ptr(g, seg, (uint16_t)(source + 16 + plane * 2));
            size += (uint16_t)(at[0] | (at[1] << 8));
        }
        source += size;
    }
    return 0;
}

/* DA2C: return heading in low word and carry (lost tracking) in bit 16. */
uint32_t weapon_projectile_turn(uint16_t heading, uint16_t target)
{
    if (heading == target)
        return heading;
    uint16_t delta = target - heading;
    uint8_t increase;
    if ((int16_t)delta >= 0) {
        if (delta < 128)
            increase = 1;
        else if (delta >= 384)
            increase = 0;
        else
            return heading | 0x10000u;
    } else {
        delta = (uint16_t)-delta;
        if (delta < 128)
            increase = 0;
        else if (delta >= 384)
            increase = 1;
        else
            return heading | 0x10000u;
    }
    if (delta < 8)
        return target;
    return (heading + (increase ? 8 : -8)) & 511;
}

/* DABC: signed world-coordinate bounds, including both endpoints. */
uint8_t weapon_projectile_outside(uint16_t x, uint16_t z)
{
    return (int16_t)x < -924 || (int16_t)x > 1948 || (int16_t)z < -924 || (int16_t)z > 1948;
}

/* A00C: insert into the 30-entry, ten-byte shot-visual ring. */
void weapon_visual_insert(uint8_t *ds, uint16_t x, uint16_t y, uint16_t z, uint16_t heading)
{
    uint16_t slot = DS_U16(ds, 0xB64C);
    DS_U16(ds, slot) = x;
    DS_U16(ds, slot + 2) = y;
    DS_U16(ds, slot + 4) = z;
    DS_U16(ds, slot + 6) = heading;
    DS_U16(ds, slot + 8) = DS_U16(ds, 0xB65E);
    slot += 10;
    if (slot >= 0xB64C)
        slot = 0xB520;
    DS_U16(ds, 0xB64C) = slot;
}

/* A036: the pitch field is subtracted directly from y before planar movement. */
uint16_t weapon_visual_step_dx(uint8_t *ds, uint16_t dx)
{
    for (uint16_t slot = 0xB520; slot < 0xB64C; slot += 10) {
        if (DS_I16(ds, slot + 6) < 0)
            continue;
        DS_U16(ds, slot + 2) -= DS_U16(ds, slot + 8);
        if (DS_I16(ds, slot + 2) < 0) {
            DS_U16(ds, slot + 6) = 65535;
            continue;
        }
        uint16_t angle = (uint16_t)(DS_U16(ds, slot + 6) * 2);
        DS_U16(ds, slot) += mul_hi(400, DS_I16(ds, 0x4188 + angle));
        dx = (uint16_t)mul_hi(400, DS_I16(ds, 0x4288 + angle));
        DS_U16(ds, slot + 4) += dx;
    }
    return dx;
}

void weapon_visual_step(uint8_t *ds)
{
    (void)weapon_visual_step_dx(ds, 0);
}
