/* Nearby shops and their HUD notices, original 74CE..7669/C5AF. */
#include "term.h"

uint16_t shop_distance(uint8_t *ds, uint16_t actor, uint16_t record)
{
    return approx_distance(DS_I16(ds, actor + 34), DS_I16(ds, actor + 42), DS_I16(ds, record), DS_I16(ds, record + 4));
}

/* SI | AX<<16 | BX<<32 | ZF<<48. Source leaves ADD SI's ZF on failure. */
uint64_t shop_try_record_state(uint8_t *ds, uint16_t actor, uint16_t record)
{
    uint16_t ax = shop_distance(ds, actor, record), bx = DS_U16(ds, record + 8) >= 4 ? 800 : 300;
    if (ax > bx) {
        record += 11;
        return record | ((uint64_t)ax << 16) | ((uint64_t)bx << 32) | ((uint64_t)(record == 0) << 48);
    }
    DS_U16(ds, 0x8546) = record;
    DS_U16(ds, 0x8514) = DS_U16(ds, record);
    DS_U16(ds, 0x8518) = DS_U16(ds, record + 4);
    DS_U8(ds, 0x8447) = DS_U8(ds, record + 10);
    if (DS_U8(ds, 0x0374)) {
        DS_U8(ds, 0x8447) = 0;
        DS_U8(ds, 0x0374) = 0;
    }
    ax = DS_U16(ds, record + 8);
    DS_U16(ds, 0x1180) = ax;
    return record | ((uint64_t)ax << 16) | ((uint64_t)1 << 48);
}

uint16_t shop_fallback_records(uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER), low = DS_U16(ds, player + 34), high = DS_U16(ds, player + 36);
    uint16_t quotient = high < 65535 ? (uint16_t)(((uint32_t)high << 16 | low) / 65535) : low;
    uint16_t offset = quotient * 44;
    if (DS_U16(ds, player + 44))
        offset += 132;
    return offset + 0x854E;
}

void shop_check_active(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t distance = shop_distance(ds, DS_U16(ds, DS_PLAYER), 0x8514), limit = DS_U16(ds, 0x1180) >= 4 ? 800 : 300;
    if (distance <= limit)
        return;
    DS_U16(ds, 0x8548) = DS_U16(ds, 0x1180) = 0;
    hud_message_hide(g);
    if (DS_U8(ds, DS_CAMERA_MODE)) {
        uint16_t page = DS_U16(ds, DS_DRAW_PAGE);
        DS_U16(ds, DS_DRAW_PAGE) = DS_U16(ds, 0x8512);
        hud_clear_bytes(g, 0x1E51, 7);
        DS_U16(ds, DS_DRAW_PAGE) = page;
    }
}

int shop_interaction(Game *g, const OpponentServices *panel)
{
    uint8_t *ds = g->ds;
    uint16_t actor = DS_U16(ds, DS_PLAYER);
    if (DS_U16(ds, 0x1180)) {
        shop_check_active(g);
        if (DS_U16(ds, 0x1180)) {
            if (DS_U8(ds, KEY_DOWN(SC_S)) && DS_U8(ds, 0x8447) && (DS_U8(ds, actor + 14) & 1)) {
                uint16_t kind = DS_U16(ds, 0x1180) - 1;
                if (!panel || !panel->call || panel->call(g, 0x813E, kind, panel->user) == UINT32_MAX)
                    return -1;
                DS_U16(ds, 0x1180) = 0;
            }
            return 0;
        }
    }
    uint16_t record = 0x5CE4, count = DS_U16(ds, DS_SHOP_COUNT), kind = 0;
    int found = 0;
    for (unsigned group = 0; group < 2 && !found; ++group) {
        if (group) {
            record = shop_fallback_records(ds);
            count = 4;
        }
        for (unsigned i = 0; i < count; ++i) {
            uint64_t result = shop_try_record_state(ds, actor, record);
            record = (uint16_t)result;
            if (result & ((uint64_t)1 << 48)) {
                kind = (uint16_t)(result >> 16);
                found = 1;
                break;
            }
        }
    }
    if (!found)
        return 0;
    uint16_t index = kind - 1;
    if (index > 4)
        DS_U8(ds, 0x8447) = 255;
    else if (!DS_U8(ds, 0x8447)) {
        hud_message(g, DS_U16(ds, 0x8536 + (uint16_t)(index * 2)));
        return 0;
    }
    if (DS_U8(ds, DS_CAMERA_MODE)) {
        event_push(EV_SOUND, 12, 0);
        DS_U8(ds, DS_NUMBER_COLOUR) = index + 9;
        hud_draw_text(g, DS_U16(ds, 0x851A + (uint16_t)(index * 2)), 0x1E51);
        DS_U16(ds, 0x8512) = DS_U16(ds, DS_DRAW_PAGE);
        return 0;
    }
    if (DS_U8(ds, actor + 14) & 1)
        hud_message(g, DS_U16(ds, 0x8528 + (uint16_t)(index * 2)));
    else {
        event_push(EV_SOUND, 12, 0);
        DS_U16(ds, 0x8548) = DS_U16(ds, 0x851A + (uint16_t)(index * 2));
    }
    return 0;
}

/* 893F/8962: visited-shop records. Count itself is not clamped to the six-slot ring. */
void shop_record_visit(uint8_t *ds)
{
    uint16_t source = DS_U16(ds, 0x8546), dest = DS_U16(ds, 0x03A8);
    for (unsigned i = 0; i < 11; ++i)
        DS_U8(ds, dest++) = DS_U8(ds, source++);
    DS_U16(ds, 0x03A8) = dest;
    if (++DS_U16(ds, 0x1176) == 6)
        DS_U16(ds, 0x03A8) = 0x03AA;
}

uint8_t shop_was_visited(const uint8_t *ds)
{
    uint16_t source = DS_U16(ds, 0x8546), count = DS_U16(ds, 0x1176), record = 0x03AA;
    for (unsigned i = 0; i < count; ++i, record += 11) {
        unsigned j = 0;
        while (j < 10 && DS_U8(ds, source + j) == DS_U8(ds, record + j))
            ++j;
        if (j == 10)
            return 1;
    }
    return 0;
}

/* 8451: the uncompressed one-bit shop-item mask; row stride is rounded to words.
 * Bounds and row arithmetic wrap at 16 bits, and only the first stored plane is read. */
uint8_t shop_item_hit(Game *g, uint16_t seg, uint16_t record, uint16_t x, uint16_t y)
{
    uint8_t *header = far_ptr(g, seg, record);
    uint16_t left = DS_U16(header, 8), top = DS_U16(header, 10), width = DS_U16(header, 4), height = DS_U16(header, 6);
    if (x < left || x >= (uint16_t)(left + width) || y < top || y >= (uint16_t)(top + height))
        return 0;
    uint16_t row = (uint16_t)(width + 15) >> 4;
    row *= 2;
    uint16_t offset = record + 16 + (uint16_t)((uint16_t)(y - top) * row) + ((uint16_t)(x - left) >> 3);
    return (*far_ptr(g, seg, offset) & (128u >> ((x - left) & 7))) != 0;
}
