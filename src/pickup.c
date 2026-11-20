/* Nearby pickup interaction, original 884B/889D/88A3/8922. */
#include "term.h"

/* Source SI | AX<<16 | BP<<32 | carry<<48. Count 1..20 is used by callers.
 * The signed JL distance test and partial cell-delta scratch writes are retained. */
uint64_t pickup_query_state(uint8_t *ds, uint16_t actor, uint16_t record, uint16_t count, uint16_t ax, uint16_t bp)
{
    unsigned remaining = count ? count : 65536;
    do {
        bp = 0; /* LOOP returns through 88A3, resetting BP for each record. */
        if (DS_U8(ds, record + 10)) {
            ax = DS_U16(ds, record) - DS_U16(ds, actor + 30);
            if (ax) {
                DS_U16(ds, 0x9A5C) = 1024;
                if ((int16_t)ax < 0) {
                    ax = (uint16_t)-ax;
                    DS_U16(ds, 0x9A5C) = (uint16_t)-DS_U16(ds, 0x9A5C);
                }
                if (ax > 1)
                    goto next;
            } else
                DS_U16(ds, 0x9A5C) = 0;
            ax = DS_U16(ds, record + 2) - DS_U16(ds, actor + 32);
            if (ax) {
                DS_U16(ds, 0x9A5E) = (uint16_t)-1024;
                if ((int16_t)ax < 0) {
                    ax = (uint16_t)-ax;
                    DS_U16(ds, 0x9A5E) = (uint16_t)-DS_U16(ds, 0x9A5E);
                }
                if (ax > 1)
                    goto next;
            } else
                DS_U16(ds, 0x9A5E) = 0;
            DS_U16(ds, 0x9A5C) += DS_U16(ds, record + 4);
            DS_U16(ds, 0x9A5E) += DS_U16(ds, record + 6);
            bp = 65535;
            ax = approx_distance(DS_I16(ds, 0x9A5C), DS_I16(ds, 0x9A5E), DS_I16(ds, actor), DS_I16(ds, actor + 4));
            if ((int16_t)ax < 200)
                return record | ((uint64_t)ax << 16) | ((uint64_t)bp << 32) | ((uint64_t)1 << 48);
        }
    next:
        record += 13;
    } while (--remaining);
    return record | ((uint64_t)ax << 16) | ((uint64_t)bp << 32);
}

void pickup_check_active(Game *g, uint16_t actor)
{
    uint8_t *ds = g->ds;
    uint16_t distance =
        approx_distance(DS_I16(ds, 0x9A60), DS_I16(ds, 0x9A62), DS_I16(ds, actor), DS_I16(ds, actor + 4));
    if ((int16_t)distance >= 200) {
        DS_U8(ds, 0x99ED) = 0;
        hud_message_hide(g);
    }
}

/* The inventory-transfer panel 531C remains an explicit service. Source checks
 * the interaction key even if the preceding active-distance check cleared latch. */
int pickup_interaction(Game *g, const OpponentServices *panel)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (DS_U8(ds, 0x99ED)) {
        if (DS_U8(ds, actor + 14) != 1) {
            DS_U8(ds, 0x99ED) = 0;
            return 0;
        }
        pickup_check_active(g, actor);
        if (DS_U8(ds, KEY_DOWN(SC_L))) {
            if (!panel || !panel->call || panel->call(g, 0x531C, 0, panel->user) == UINT32_MAX)
                return -1;
            DS_U8(ds, 0x99ED) = 0;
            hud_message_hide(g);
        }
        return 0;
    }
    if (DS_U8(ds, actor + 14) != 1)
        return 0;
    uint64_t query = pickup_query_state(ds, actor, 0x0253, 20, 0, 0);
    if (!(query & ((uint64_t)1 << 48)))
        return 0;
    DS_U16(ds, 0x9A60) = DS_U16(ds, 0x9A5C);
    DS_U16(ds, 0x9A62) = DS_U16(ds, 0x9A5E);
    DS_U8(ds, 0x99ED) = 255;
    hud_message(g, 0x99EE);
    return 0;
}
