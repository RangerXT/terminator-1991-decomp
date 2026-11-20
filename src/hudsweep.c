/* Animated ten-row system-HUD sweep. Sound is an EV_SOUND request, as in blast.c. */
#include "term.h"

static uint8_t shr8(uint8_t value, uint8_t count)
{
    count &= 31;
    return count >= 8 ? 0 : (uint8_t)(value >> count);
}

static uint8_t shl8(uint8_t value, uint8_t count)
{
    count &= 31;
    return count >= 8 ? 0 : (uint8_t)(value << count);
}

/* orig E44A. Erase the column six bits behind the current position. */
void hud_sweep_clear(uint8_t *ds)
{
    uint16_t dest = DS_U16(ds, 0xE439);
    uint8_t column = (uint8_t)(DS_U8(ds, 0xE435) - 6);
    if ((int8_t)column < 0) {
        column += 8;
        --dest;
        if (dest < 0xE43B)
            dest += 3;
    }
    uint8_t mask = (uint8_t)~shr8(128, column);
    for (unsigned row = 0; row < 10; ++row) {
        DS_U8(ds, dest) &= mask;
        dest += 4;
    }
}

/* orig E348. Columns 0..7 and three cycling bytes form a 24-bit sweep. */
void hud_draw_sweep(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, KEY_DOWN(SC_MINUS))) {
        if (!DS_U8(ds, 0xE4FE)) {
            DS_U8(ds, 0xE4FE) = 255;
            DS_U8(ds, 0x1141) = (uint8_t)~DS_U8(ds, 0x1141);
        }
    } else
        DS_U8(ds, 0xE4FE) = 0;
    if (!DS_U8(ds, 0xE438) && --DS_U8(ds, 0xE437)) {
        hud_sweep_clear(ds);
        uint8_t mask = shr8(128, DS_U8(ds, 0xE435));
        DS_U8(ds, DS_U16(ds, 0xE439) + 20) |= mask;
    } else {
        if (!DS_U8(ds, 0xE438)) {
            if (!DS_U8(ds, 0x1141))
                event_push(EV_SOUND, 16, 0);
            DS_U8(ds, 0xE438) = 5;
        }
        hud_sweep_clear(ds);
        uint8_t column = DS_U8(ds, 0xE435);
        uint8_t mask = shr8(128, column);
        uint8_t shift = (uint8_t)(column - DS_U8(ds, 0xE438));
        int left = (int8_t)shift < 0;
        if (left)
            shift = (uint8_t)-shift;
        --DS_U8(ds, 0xE438);
        uint16_t dest = DS_U16(ds, 0xE439);
        for (unsigned row = 0; row < 10; ++row) {
            uint8_t shape = DS_U8(ds, 0xE463 + row);
            shape = left ? shl8(shape, shift) : shr8(shape, shift);
            DS_U8(ds, dest) |= shape & mask;
            dest += 4;
        }
        uint16_t player = DS_U16(ds, DS_PLAYER);
        DS_U8(ds, 0xE437) = (uint8_t)(8 + 4 * (DS_U16(ds, player + 0x1A) >> 4));
    }
    if (++DS_U8(ds, 0xE435) > 7) {
        DS_U8(ds, 0xE435) = 0;
        if (DS_U8(ds, 0xE436) == 2) {
            DS_U16(ds, 0xE439) = 0xE43B;
            DS_U8(ds, 0xE436) = 0;
        } else {
            ++DS_U16(ds, 0xE439);
            ++DS_U8(ds, 0xE436);
        }
    }
    uint16_t code = (uint16_t)(g->ds_seg - 0x5C27);
    DS_U8(far_ptr(g, code, 0x1B41), 0) = 10;
    screen_blit_mask(g, g->ds_seg, 0xE43B, (uint16_t)(0x098A + DS_U16(ds, DS_DRAW_PAGE)), 4, 10, 10,
                     DS_U16(far_ptr(g, code, 0x1B42), 0));
    DS_U8(far_ptr(g, code, 0x1B41), 0) = 12;
}
