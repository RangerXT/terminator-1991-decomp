/* Player control helpers and walking controller, original 2E9E..370E. */
#include "term.h"

void player_position_backup(uint8_t *ds)
{
    uint16_t p = DS_U16(ds, DS_PLAYER);
    for (unsigned i = 0; i < 4; ++i)
        DS_U16(ds, 0x5A46 + i * 2) = DS_U16(ds, p + (i < 2 ? 34 : 38) + i * 2);
}

void player_position_restore(uint8_t *ds)
{
    uint16_t p = DS_U16(ds, DS_PLAYER);
    for (unsigned i = 0; i < 4; ++i)
        DS_U16(ds, p + (i < 2 ? 34 : 38) + i * 2) = DS_U16(ds, 0x5A46 + i * 2);
}

static uint16_t keep_inside_bx(Game *g, uint16_t bx)
{
    uint8_t *ds = g->ds;
    uint16_t p = DS_U16(ds, DS_PLAYER), x = DS_U16(ds, p + 30), z = DS_U16(ds, p + 32);
    if (!x || x >= 191 || !z || z >= 127) {
        player_position_restore(ds);
        bx = position_normalize_bx(g, p);
    }
    return bx;
}

void player_keep_inside(Game *g)
{
    (void)keep_inside_bx(g, 0);
}

void driving_reset(uint8_t *ds)
{
    DS_U8(ds, 0x114C) = DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, 0x114A) = DS_U8(ds, 0x114B) = 0;
    DS_U16(ds, 0x0416) = 300;
    DS_U16(ds, 0x5A40) = 65535;
    DS_U16(ds, 0x0414) = 4;
}

/* 2E9E: AX | carry<<16. A boundary stops a vehicle but still permits turning;
 * temporary overlay/lock/stun flags instead return AL=1. Other AX bits survive. */
uint32_t player_movement_gate(uint8_t *ds, uint16_t ax)
{
    uint8_t mask = DS_U8(ds, 0x5CDA);
    uint16_t p = DS_U16(ds, DS_PLAYER);
    if (mask) {
        ax = DS_U16(ds, p + 6);
        if (((mask & 1) && ax >= 256) || ((mask & 2) && ax <= 256) || ((mask & 4) && (ax >= 384 || ax <= 128))
            || ((mask & 8) && ax >= 128 && ax <= 384)) {
            if (DS_U8(ds, p + 14) & 2) {
                DS_U16(ds, p + 10) = DS_U16(ds, p + 12) = DS_U16(ds, 0x0416) = 0;
                DS_U8(ds, 0x114C) = 0;
            }
            return (ax & 0xFF00) | 0x10000;
        }
    }
    if (DS_U8(ds, DS_RELOAD_COUNTDOWN) || DS_U8(ds, KEY_DOWN(SC_SPACE)) || DS_U8(ds, 0x1155))
        return (ax & 0xFF00) | 0x10001;
    return ax;
}

/* 300B (scan=1) / 302E (scan=0). Preserve both quotient AND remainder of DIV CL
 * in the following word divisor; faults leave AX unchanged under INT 0. */
void walking_speed_step(uint8_t *ds, uint16_t actor, uint8_t scan)
{
    if (scan && !(DS_U8(ds, actor + 14) & 2))
        for (unsigned i = 0; i < 10; ++i) {
            if (DS_U8(ds, 0x5BDB + i) == 255) {
                DS_U16(ds, 0x5A44) = i;
                DS_U8(ds, 0x5A22) = 1;
                break;
            }
        }
    if (--DS_U8(ds, 0x5A22))
        return;
    DS_U8(ds, 0x5A22) = 3;
    uint16_t speed = DS_U16(ds, actor + 10), wanted = DS_U16(ds, actor + 12);
    if (speed != wanted)
        DS_U16(ds, actor + 10) = speed + (speed < wanted ? 1 : -1);
    actor = DS_U16(ds, DS_PLAYER);
    uint16_t table = actor == 0x0508 ? 0x59FA : DS_U8(ds, 0xAA9D) ? 0x5A0E : 0x59E6;
    uint16_t ax = DS_U16(ds, 0x03F2), divisor = ax;
    if (ax / 5 < 256)
        divisor = (ax / 5) | ((ax % 5) << 8);
    uint16_t load = DS_U16(ds, DS_CARRIED_WEIGHT);
    if (divisor)
        load /= divisor;
    ax = DS_U16(ds, table + (uint16_t)(DS_U16(ds, 0x5A44) * 2));
    DS_U8(ds, 0xE47B) = load > 2 ? 255 : 0;
    ax -= load;
    if ((int16_t)ax < 0)
        ax = 2;
    if (ax > 12)
        ax = 12;
    DS_U16(ds, actor + 12) = ax;
}

void driving_steer(uint8_t *ds, uint16_t actor)
{
    if (!DS_U8(ds, KEY_DOWN(SC_ALT)) && !DS_U8(ds, KEY_DOWN(SC_CTRL)) && DS_U16(ds, actor + 10) > 2) {
        int delta = 0, reverse = DS_U8(ds, 0x5A24) != 0, fast = DS_U8(ds, KEY_DOWN(SC_RSHIFT)) != 0;
        if (DS_U8(ds, KEY_DOWN(SC_LEFT))) {
            DS_U16(ds, 0x11A6) = fast ? 0 : 2;
            delta = fast ? 7 : 1;
            if (!reverse)
                delta = -delta;
        } else if (DS_U8(ds, KEY_DOWN(SC_RIGHT))) {
            DS_U16(ds, 0x11A6) = fast ? 8 : 6;
            delta = fast ? 7 : 1;
            if (reverse)
                delta = -delta;
        } else
            DS_U16(ds, 0x11A6) = 4;
        DS_U16(ds, actor + 6) += delta;
    }
    DS_U16(ds, actor + 6) &= 511;
}

void driving_accelerate(uint8_t *ds, uint16_t actor)
{
    if (DS_U8(ds, KEY_DOWN(SC_ALT)) || DS_U8(ds, KEY_DOWN(SC_CTRL)) || DS_U8(ds, 0x114A))
        return;
    if (DS_U8(ds, KEY_DOWN(SC_UP))) {
        if (DS_U8(ds, KEY_DOWN(SC_RSHIFT)))
            DS_U16(ds, actor + 10)++;
        DS_U16(ds, actor + 12)++;
    } else if (DS_U8(ds, KEY_DOWN(SC_DOWN))) {
        if (DS_U8(ds, KEY_DOWN(SC_RSHIFT)))
            DS_U16(ds, actor + 12)--;
        DS_U16(ds, actor + 12)--;
        if (DS_I16(ds, actor + 12) < 0)
            DS_U16(ds, actor + 12) = 0;
    } else
        return;
    if (DS_I16(ds, actor + 12) >= 33) {
        DS_U16(ds, actor + 12) = 33;
        if (DS_I16(ds, actor + 10) >= 33)
            DS_U16(ds, actor + 10) = 33;
    }
}

uint32_t driving_gear_key(uint8_t *ds)
{
    static const uint16_t keys[] = {0x5C2B, 0x5C2C, 0x5C20, 0x5C28, 0x5C22, 0x5C2A};
    for (unsigned i = 0; i < 6; ++i)
        if (DS_U8(ds, keys[i]))
            return i;
    return 0x10005;
}

static int16_t walking_magnitude(uint8_t *ds, uint16_t player)
{
    int16_t speed = DS_I16(ds, player + 10);
    if (DS_U16(ds, DS_WARNING_COUNTDOWN))
        speed >>= 1;
    if (DS_U8(ds, player + 25) & 32)
        speed = 2;
    return (int16_t)(uint16_t)(speed * 2);
}

static void walking_move(uint8_t *ds, uint16_t p, uint16_t heading, int16_t speed, int backwards)
{
    uint16_t index = heading * 2;
    int16_t dx = mul_hi(speed, DS_I16(ds, 0x4188 + index)), dz = mul_hi(speed, DS_I16(ds, 0x4288 + index));
    uint32_t x = DS_U16(ds, p + 34) | ((uint32_t)DS_U16(ds, p + 36) << 16),
             z = DS_U16(ds, p + 42) | ((uint32_t)DS_U16(ds, p + 44) << 16);
    if (backwards) {
        x -= (int32_t)dx;
        z += (int32_t)dz;
    } else {
        x += (int32_t)dx;
        z -= (int32_t)dz;
    }
    DS_U16(ds, p + 34) = x;
    DS_U16(ds, p + 36) = x >> 16;
    DS_U16(ds, p + 42) = z;
    DS_U16(ds, p + 44) = z >> 16;
}

/* 30A0: native walking, turning/strafe and position normalization/map bounds. */
static uint32_t finish_walking(Game *g, uint16_t player)
{
    uint16_t bx = keep_inside_bx(g, position_normalize_bx(g, player));
    uint16_t dx = 1024 - DS_U16(g->ds, player + 4);
    return bx | ((uint32_t)dx << 16);
}

uint32_t walking_step_registers(Game *g, uint16_t bx)
{
    uint8_t *ds = g->ds;
    uint16_t p = DS_U16(ds, DS_PLAYER);
    player_position_backup(ds);
    uint16_t dx = DS_U16(ds, p + 44);
    if (DS_U8(ds, 0x5CDA))
        dx = (dx & 0xFF00) | DS_U8(ds, 0x5CDA);
    uint32_t preserved = bx | ((uint32_t)dx << 16);
    uint32_t gate = player_movement_gate(ds, DS_U16(ds, p + 42));
    if (gate & 0x10000) {
        if ((uint8_t)gate)
            return preserved;
        goto turn;
    }
    if (DS_U8(ds, KEY_DOWN(SC_CTRL)))
        return preserved;
    if (DS_U8(ds, p + 25) & 16)
        goto turn;
    walking_speed_step(ds, p, 1);
    if (DS_U8(ds, KEY_DOWN(SC_ALT)))
        goto turn;
    if (DS_U8(ds, KEY_DOWN(SC_UP))) {
    forward:;
        int16_t speed = walking_magnitude(ds, p);
        if (DS_U8(ds, KEY_DOWN(SC_RSHIFT))) {
            if (DS_U8(ds, 0x0346)) {
                if (!--DS_U16(ds, 0x0410))
                    DS_U8(ds, 0x0346) = 0;
                speed = (int16_t)(uint16_t)(speed * 2);
            } else if (++DS_U16(ds, 0x0410) >= 400)
                DS_U8(ds, 0x0346) = 255;
        }
        walking_move(ds, p, (DS_U16(ds, p + 6) + DS_U16(ds, 0x5A42)) & 511, speed, 0);
        DS_U8(ds, 0x5A24) = 0;
        uint16_t strafe = DS_U16(ds, 0x5A42);
        DS_U8(ds, DS_FORCE_REDO) = strafe;
        DS_U16(ds, 0x5A42) = 0;
        if (strafe)
            return finish_walking(g, p);
    }
    if (DS_U8(ds, KEY_DOWN(SC_DOWN))) {
        walking_move(ds, p, DS_U16(ds, p + 6), walking_magnitude(ds, p), 1);
        DS_U8(ds, 0x5A24) = 255;
        DS_U8(ds, DS_FORCE_REDO) = 255;
    }
turn:
    if (DS_U8(ds, KEY_DOWN(SC_LEFT))) {
        DS_U8(ds, DS_FORCE_REDO) = 255;
        if (DS_U8(ds, KEY_DOWN(SC_ALT))) {
            if (!(DS_U8(ds, p + 25) & 16))
                DS_U16(ds, 0x5A42) = -128;
        } else
            DS_U16(ds, p + 6) = (DS_U16(ds, p + 6) - (DS_U8(ds, KEY_DOWN(SC_RSHIFT)) ? 4 : 1)) & 511;
    } else if (DS_U8(ds, KEY_DOWN(SC_DEL)))
        DS_U16(ds, p + 6) = (DS_U16(ds, p + 6) - 32) & 511;
    else if (DS_U8(ds, KEY_DOWN(SC_RIGHT))) {
        DS_U8(ds, DS_FORCE_REDO) = 255;
        if (DS_U8(ds, KEY_DOWN(SC_ALT))) {
            if (!(DS_U8(ds, p + 25) & 16))
                DS_U16(ds, 0x5A42) = 128;
        } else
            DS_U16(ds, p + 6) = (DS_U16(ds, p + 6) + (DS_U8(ds, KEY_DOWN(SC_RSHIFT)) ? 4 : 1)) & 511;
    } else if (DS_U8(ds, KEY_DOWN(SC_PGDN)))
        DS_U16(ds, p + 6) = (DS_U16(ds, p + 6) + 32) & 511;
    if (DS_U16(ds, 0x5A42))
        goto forward;
    return finish_walking(g, p);
}

uint16_t walking_step_bx(Game *g, uint16_t bx)
{
    return (uint16_t)walking_step_registers(g, bx);
}

void walking_step(Game *g)
{
    (void)walking_step_bx(g, 0);
}
