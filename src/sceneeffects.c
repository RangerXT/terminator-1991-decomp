/* Post-scene contact and temporary display effects from 0758's callees. */
#include "term.h"

/* AEC4: strict distance <60; the angle boundary is asymmetrical at 30/482. */
static uint8_t contact_test(uint8_t *ds, uint16_t actor, int16_t x, int16_t z, int16_t tx, int16_t tz, uint16_t *dx)
{
    *dx = tz;
    if (approx_distance(x, z, tx, tz) >= 60)
        return 0;
    int16_t delta = (uint16_t)(angle_between(ds, x, z, tx, tz) - DS_U16(ds, actor + 6));
    *dx = delta < 0 ? 0xffff : 0;
    uint16_t distance = delta < 0 ? -delta : delta;
    return distance < 30 || distance >= 482;
}

uint8_t scene_contact_test(uint8_t *ds, uint16_t actor, int16_t x, int16_t z, int16_t tx, int16_t tz)
{
    uint16_t dx;
    return contact_test(ds, actor, x, z, tx, tz, &dx);
}

/* AE2E: first contact can switch SI to the vehicle for the second test. */
uint16_t scene_contact_update_dx(uint8_t *ds, uint16_t dx)
{
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (!DS_U8(ds, DS_OPPONENT_ACTIVE) || (DS_U8(ds, actor + 14) & 1))
        return dx;
    if (actor == 0x04D4) {
        if (!contact_test(ds, actor, DS_I16(ds, actor), DS_I16(ds, actor + 4), DS_I16(ds, DS_OPPONENT_X),
                          DS_I16(ds, DS_OPPONENT_Z), &dx))
            return dx;
        DS_U16(ds, actor + 48) -= 30;
        actor = DS_U16(ds, DS_VEHICLE);
        DS_U16(ds, actor + 26) += 30;
        if (!DS_U8(ds, 0xB66D))
            DS_U16(ds, DS_VIEW_CENTRE_Y) += 8;
        return dx;
    }
    if (contact_test(ds, actor, DS_I16(ds, actor), DS_I16(ds, actor + 4), DS_I16(ds, DS_OPPONENT_X),
                     DS_I16(ds, DS_OPPONENT_Z), &dx)) {
        DS_U16(ds, actor + 48) -= 10;
        actor = DS_U16(ds, DS_VEHICLE);
        DS_U16(ds, actor + 26) += 4;
        if (!DS_U8(ds, 0xB66D))
            DS_U16(ds, DS_VIEW_CENTRE_Y) += 8;
    }
    if (contact_test(ds, actor, DS_I16(ds, actor), DS_I16(ds, actor + 4), DS_I16(ds, DS_COMPANION_X),
                     DS_I16(ds, DS_COMPANION_Z), &dx)) {
        DS_U16(ds, actor + 48) -= 10;
        DS_U16(ds, 0x0556) += 4;
        if (!DS_U8(ds, 0xB66D))
            DS_U16(ds, DS_VIEW_CENTRE_Y) += 8;
    }
    return dx;
}

void scene_contact_update(uint8_t *ds)
{
    (void)scene_contact_update_dx(ds, 0);
}

/* 18D3: alternating colour words with a random odd period across all rows. */
void scene_flash(Game *g)
{
    uint8_t *p = g->planes;
    uint16_t period = ((random_word(g->ds) & 7) + 2) | 1, remaining = period;
    uint16_t at = 0x0141 + DS_U16(g->ds, DS_DRAW_PAGE);
    ega_seq_mask(p, 15);
    ega_gc(p, 1, 15);
    for (unsigned row = 0; row < 102; ++row) {
        ega_gc(p, 0, 7);
        for (unsigned col = 0; col < 19; ++col) {
            if (!--remaining) {
                ega_gc(p, 0, 8);
                ega_store(p, at++, 0);
                ega_store(p, at++, 8);
                ega_gc(p, 0, 7);
                remaining = period;
            } else {
                ega_store(p, at++, 0);
                ega_store(p, at++, 7);
            }
        }
        at += 2;
    }
    ega_gc(p, 1, 0);
}

/* 9756: timed flash and proximity flag. */
uint16_t scene_timed_effect_dx(Game *g, uint16_t dx)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0x0344) = 0;
    if (!DS_U16(ds, 0x0B2E))
        return dx;
    DS_U16(ds, 0x0B2E)--;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (approx_distance(DS_I16(ds, 0x0404), DS_I16(ds, 0x0406), DS_I16(ds, actor), DS_I16(ds, actor + 4)) < 100) {
        DS_U8(ds, 0x0344) = 255;
        scene_flash(g);
        return 0x03CE;
    }
    if (DS_U8(ds, DS_OPPONENT_ACTIVE)
        && approx_distance(DS_I16(ds, DS_OPPONENT_X), DS_I16(ds, DS_OPPONENT_Z), DS_I16(ds, 0x0404), DS_I16(ds, 0x0406))
               >= 100)
        DS_U8(ds, 0x0344) = 255;
    return DS_U16(ds, DS_U8(ds, DS_OPPONENT_ACTIVE) ? 0x0406 : actor + 4);
}

void scene_timed_effect(Game *g)
{
    (void)scene_timed_effect_dx(g, 0);
}

/* 41C4: numeric vehicle resource, with a zero latch independent of camera mode. */
void hud_vehicle_remaining(Game *g)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_CAMERA_MODE)) {
        hud_clear_bytes(g, 0x1432, 1);
        DS_U8(ds, DS_NUMBER_DIGITS) = 2;
        hud_draw_number(g, DS_U16(ds, DS_FUEL), 0x1432);
        DS_U8(ds, DS_NUMBER_DIGITS) = 3;
    }
    if (!DS_U16(ds, DS_FUEL))
        DS_U8(ds, 0x114A) = 255;
}

/* 5776:0247. The alternative chunky-screen path requires a different framebuffer. */
int scene_overlay_restore(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    if (!DS_U8(ds, 0xC4AB))
        return 0;
    DS_U8(ds, 0xC4AB)--;
    uint16_t ptr = DS_U16(ds, 0xC4C4);
    uint16_t source = DS_U16(ds, ptr - 2), dest = DS_U16(ds, ptr - 4), rows = DS_U16(ds, ptr - 6),
             width = DS_U16(ds, ptr - 8);
    DS_U16(ds, 0xC4C4) -= 8;
    screen_copy_rect(g, source, dest, width, rows);
    DS_U16(ds, 0xC546) -= (uint16_t)(DS_U16(ds, DS_SCREEN_STRIDE) * rows);
    return 0;
}

/* 07D1: replay the top saved overlay on the current page, retaining its entry. */
int scene_overlay_replay(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return -1;
    uint16_t ptr = DS_U16(ds, 0xC4C4), dest = DS_U16(ds, ptr - 4);
    if (dest >= 0x2000) {
        dest -= 0x2000;
        if (dest >= 0x2000)
            dest -= 0x2000;
    }
    DS_U16(ds, ptr - 4) = dest + DS_U16(ds, DS_DRAW_PAGE);
    uint16_t old_ptr = DS_U16(ds, 0xC4C4), old_size = DS_U16(ds, 0xC546);
    scene_overlay_restore(g);
    DS_U8(ds, 0xC4AB)++;
    DS_U16(ds, 0xC546) = old_size;
    DS_U16(ds, 0xC4C4) = old_ptr;
    return 0;
}
