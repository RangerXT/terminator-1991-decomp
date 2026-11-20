/* Player-hit body 6386 and per-region accumulation 643E. */
#include "term.h"

/* Return AX | carry<<16. Region indexing uses BX, flag choice uses BL. */
uint32_t player_damage_region(uint8_t *ds, uint16_t actor, uint16_t region, uint16_t damage)
{
    uint16_t at = actor + 17 + region;
    DS_U8(ds, at) += (uint8_t)damage;
    uint8_t value = DS_U8(ds, at), limit = DS_U8(ds, at + 4);
    if (value >= limit) {
        uint8_t excess = value - limit;
        DS_U8(ds, at) -= excess;
        DS_U16(ds, actor + 26) -= excess;
        return 0x10000u | excess;
    }
    uint8_t half = limit >> 1;
    if (half < value)
        DS_U8(ds, actor + 25) |= (uint8_t)region == 0 ? 128 : (uint8_t)region == 2 ? 64 : 32;
    return value | ((uint16_t)half << 8);
}

uint32_t player_hit_native_registers(Game *g, uint16_t damage, uint16_t incoming_bx)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, DS_BORDER_FLASH) = 255;
    /* Border hardware is outside Game's planar EGA state. a=logical index,
     * b=the original attribute-controller value from the colour table. */
    event_push(EV_BORDER, 4, DS_U8(ds, 0x1514));
    DS_U16(ds, 0x0382)++;
    uint16_t player = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, player + 26) += damage;
    if (!(random_word(ds) & 3)) {
        DS_U16(ds, DS_SCREEN_NOISE) = 6;
        DS_U8(ds, 0x1155) = 10;
    }
    if (DS_U16(ds, player + 26) >= DS_U16(ds, player + 28)) {
        DS_U8(ds, DS_PLAYER_DOWN) = 2;
        DS_U16(ds, player + 26) = DS_U16(ds, player + 28);
        return DS_U16(ds, player + 28) | ((uint32_t)incoming_bx << 16);
    }
    uint16_t selector = random_word(ds) & 15;
    uint16_t region = DS_U8(ds, 0x7B96 + selector), actor = player;
    if (region == 1 && DS_U8(ds, 0xAA98)) {
        if (--DS_U8(ds, player + 51))
            return damage | ((uint32_t)region << 16);
        DS_U8(ds, 0xAA98) = 0;
        hud_message(g, 0xB6A2);
        inventory_remove(ds, 15);
        /* Original 6407..640A pops selector into BX and saved region into SI.
         * The resulting SI=1 write into low DS was confirmed by execution. */
        region = selector;
        actor = 1;
    }
    uint32_t result = player_damage_region(ds, actor, region, damage);
    if (!(result & 0x10000))
        return (uint16_t)result | ((uint32_t)region << 16);
    if ((uint8_t)region < 2)
        DS_U8(ds, DS_PLAYER_DOWN) = 2;
    else if ((uint8_t)region == 2) {
        DS_U8(ds, actor + 25) |= 8;
        if (DS_U8(ds, actor + 25) & 16)
            DS_U8(ds, DS_PLAYER_DOWN) = 2;
    } else {
        DS_U8(ds, actor + 25) |= 16;
        if (DS_U8(ds, actor + 25) & 8)
            DS_U8(ds, DS_PLAYER_DOWN) = 2;
    }
    return (uint16_t)result | ((uint32_t)region << 16);
}

uint16_t player_hit_native_state(Game *g, uint16_t damage)
{
    return (uint16_t)player_hit_native_registers(g, damage, 0);
}

void player_hit_native(Game *g, uint16_t damage)
{
    player_hit_native_state(g, damage);
}
