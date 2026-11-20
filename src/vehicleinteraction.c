/* Vehicle proximity, parked records and entry, original 400E..43C5. */
#include "term.h"

static uint16_t fword(Game *g, uint16_t seg, uint16_t off)
{
    return *far_ptr(g, seg, off) | ((uint16_t)*far_ptr(g, seg, (uint16_t)(off + 1)) << 8);
}
static void putword(Game *g, uint16_t seg, uint16_t off, uint16_t value)
{
    *far_ptr(g, seg, off) = value;
    *far_ptr(g, seg, (uint16_t)(off + 1)) = value >> 8;
}

/* 434E: source serial notification is not part of this single-player operation. */
int vehicle_park(Game *g, uint16_t actor)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    uint16_t at = DS_U16(ds, 0x1204), seg = DS_U16(ds, 0x1206);
    DS_U16(ds, 0x11FC) = at;
    DS_U16(ds, 0x11FE) = seg;
    uint16_t strength = DS_U16(ds, actor + 48) | ((uint16_t)DS_U8(ds, 0x5EF9) << 8);
    if (!(DS_U8(ds, actor + 14) & 8))
        strength |= 128;
    uint16_t orientation = ((DS_U16(ds, actor + 6) - 64) & 0x180) >> 6;
    uint16_t words[] = {DS_U8(ds, actor + 30) | ((uint16_t)DS_U8(ds, actor + 32) << 8),
                        DS_U16(ds, actor),
                        DS_U16(ds, actor + 4),
                        DS_U16(ds, 0x72D0),
                        strength,
                        DS_U16(ds, 0x729C + orientation),
                        DS_U8(ds, 0x5EF6) | ((uint16_t)DS_U8(ds, DS_FUEL) << 8)};
    for (unsigned i = 0; i < 7; ++i, at += 2)
        putword(g, seg, at, words[i]);
    DS_U16(ds, DS_EXTRA_COUNT)++;
    if (at == 0x00C4) {
        DS_U16(ds, DS_EXTRA_COUNT)--;
        at = 0;
    }
    DS_U16(ds, 0x1204) = at;
    return 0;
}

/* 4248: the synthetic nearby-record SI is 749E; only carry is needed by callers. */
uint8_t vehicle_find_parked(Game *g)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0x5F78) = 0;
    uint16_t actor = DS_U16(ds, DS_PLAYER), count = DS_U16(ds, DS_EXTRA_COUNT), at = DS_U16(ds, 0x1200),
             seg = DS_U16(ds, 0x1202);
    uint16_t cell = DS_U8(ds, actor + 30) | ((uint16_t)DS_U8(ds, actor + 32) << 8);
    for (unsigned i = 0; i < count; ++i, at += 14) {
        if (fword(g, seg, at) == cell
            && approx_distance(fword(g, seg, at + 2), fword(g, seg, at + 4), DS_U16(ds, actor), DS_U16(ds, actor + 4))
                   < 200) {
            DS_U16(ds, 0x5F70) = fword(g, seg, at + 12);
            DS_U8(ds, 0x5EF9) = (*far_ptr(g, seg, (uint16_t)(at + 9))) & 3;
            DS_U16(ds, 0x74A8) = 65535;
            DS_U16(ds, 0x74AA) = fword(g, seg, at + 6);
            DS_U16(ds, 0x74A6) =
                *far_ptr(g, seg, (uint16_t)(at + 10)) | ((uint16_t)*far_ptr(g, seg, (uint16_t)(at + 8)) << 8);
            return 1;
        }
        DS_U16(ds, 0x5F78)++;
    }
    return 0;
}

/* 421B: source copies COUNT bytes, not COUNT fourteen-byte records. */
void vehicle_remove_parked(Game *g, uint16_t index)
{
    uint8_t *ds = g->ds;
    uint16_t count = DS_U16(ds, DS_EXTRA_COUNT) - index - 1, seg = DS_U16(ds, 0x1202), at = index * 14;
    for (unsigned i = 0; i < count; ++i, ++at)
        *far_ptr(g, seg, at) = *far_ptr(g, seg, (uint16_t)(at + 14));
    DS_U16(ds, DS_EXTRA_COUNT)--;
    DS_U16(ds, 0x1204) -= 14;
}

void vehicle_initial_fuel(uint8_t *ds)
{
    uint16_t actor = DS_U16(ds, DS_PLAYER), x = DS_U16(ds, actor + 30) >> 3, z = DS_U16(ds, actor + 32) >> 3;
    uint16_t a = x >= 12 ? (uint16_t)(24 - x) : x, b = z >= 8 ? (uint16_t)(16 - z) : z;
    uint16_t fuel = (a < b ? a : b) >> 1;
    if (fuel < 2)
        fuel = 2;
    DS_U16(ds, DS_FUEL) = fuel * 8;
}

/* 400E. Only the 02B5 transition is a service; the native wrapper below binds it.
 * Serial mode is rejected before mutation because map removal/parking notifications
 * require the untranslated network protocol. */
int vehicle_interaction(Game *g, const OpponentServices *transition)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_LINK_GAME))
        return -1;
    uint16_t count = DS_U16(ds, DS_VEHICLE_COUNT), actor = DS_U16(ds, DS_PLAYER);
    if (!count || (DS_U8(ds, actor + 14) & 2))
        goto none;
    if (DS_U8(ds, 0x5CE3) && DS_U8(ds, KEY_DOWN(SC_E)))
        goto enter;
    if (!DS_U8(ds, 0x5CE3))
        DS_U8(ds, 0x5EF8) = 0;
    uint16_t record = DS_U16(ds, 0x72BA), seg = DS_U16(ds, 0x72BC);
    int found = 0;
    for (unsigned i = 0; i < count; ++i, record += 14) {
        uint16_t x = DS_U16(ds, actor + 34) - fword(g, seg, record),
                 z = DS_U16(ds, actor + 42) - fword(g, seg, record + 4);
        if ((int16_t)x < 0)
            x = -x;
        if ((int16_t)z < 0)
            z = -z;
        if (x >= z)
            z >>= 2;
        if ((uint16_t)(x + z) < 200) {
            found = 1;
            break;
        }
    }
    if (!found) {
        if (!vehicle_find_parked(g))
            goto none;
        seg = g->ds_seg;
        record = 0x749E;
    }
    uint16_t flags = fword(g, seg, record + 8), text = (flags & 0x8000) ? 0x5E9E : 0x5E5A;
    DS_U16(ds, 0x5F76) = flags >> 8;
    DS_U16(ds, 0x72D0) = fword(g, seg, record + 12);
    DS_U16(ds, 0x5F74) = fword(g, seg, record + 10);
    DS_U8(ds, 0x5EF7) = (flags & 0x8000) ? 0 : 255;
    DS_U16(ds, 0x72C8) = flags & 3;
    /* 40D3 has no ES override: this reads DS, despite loading ES from 91D4. */
    if (DS_U16(ds, DS_U16(ds, 0x5F74) + 10) == 65535)
        goto none;
    DS_U8(ds, 0x5CE3) = 255;
    if (!DS_U8(ds, 0xC54A)) {
        hud_message(g, text);
        DS_U8(ds, 0xC54A) = 255;
    }
    return 0;
none:
    DS_U8(ds, 0x5CE3) = 0;
    if (DS_U8(ds, 0xC54A)) {
        hud_message_hide(g);
        DS_U8(ds, 0xC54A) = 0;
    }
    return 0;
enter:
    if (DS_U16(ds, 0x5F74) == 65535) {
        DS_U8(ds, 0x5EF6) = DS_U8(ds, 0x5F70);
        DS_U16(ds, DS_FUEL) = DS_U8(ds, DS_FUEL);
    } else
        vehicle_initial_fuel(ds);
    if (!transition || !transition->call
        || transition->call(g, OS_PLAYER_TRANSITION, 2, transition->user) == UINT32_MAX)
        return -1;
    actor = DS_U16(ds, DS_PLAYER);
    DS_U16(ds, actor + 6) = DS_U16(ds, 0x72C0 + (uint16_t)(DS_U16(ds, 0x72C8) * 2));
    uint16_t source = DS_U16(ds, 0x5F74);
    if (source != 65535) {
        seg = DS_U16(ds, DS_SEG_CELLS);
        for (unsigned i = 0; i < 12; ++i)
            DS_U8(ds, 0x8114 + i) = *far_ptr(g, seg, (uint16_t)(source + i));
        map_note_removed(ds, 0x8114);
        DS_U8(ds, 0x5EF9) = *far_ptr(g, seg, (uint16_t)(source + 11));
        putword(g, seg, source + 10, 65535);
    } else
        vehicle_remove_parked(g, DS_U16(ds, 0x5F78));
    DS_U16(ds, DS_VISIBLE_CELL) = 65534;
    return 0;
}

uint32_t vehicle_transition_service(Game *g, uint16_t op, uint16_t mode, void *host)
{
    if (op != OS_PLAYER_TRANSITION)
        return UINT32_MAX;
    return vehicle_transition(g, mode, (const VehicleServices *)host) < 0 ? UINT32_MAX : 0;
}

int vehicle_interaction_native(Game *g, const VehicleServices *host)
{
    OpponentServices transition = {vehicle_transition_service, (void *)host};
    return vehicle_interaction(g, &transition);
}
