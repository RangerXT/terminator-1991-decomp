/* Opponent's far inventory and attack-item choice bookkeeping (C068..C1AF). */
#include "term.h"

/* C125: AX | DI<<16 | ES<<32 | carry<<48. The first matching zero-count
 * record fails immediately; it does not continue to another duplicate. */
uint64_t opponent_find_item(Game *g, uint8_t item)
{
    uint16_t seg = DS_U16(g->ds, 0x120A), at = DS_U16(g->ds, 0x1208);
    for (;;) {
        uint8_t id = *far_ptr(g, seg, (uint16_t)(at + 2));
        if (!id)
            break;
        if (id == item) {
            uint8_t count = *far_ptr(g, seg, (uint16_t)(at + 5));
            return item | ((uint64_t)count << 8) | ((uint64_t)at << 16) | ((uint64_t)seg << 32)
                   | ((uint64_t)!count << 48);
        }
        at += 6;
    }
    return item | ((uint64_t)at << 16) | ((uint64_t)seg << 32) | ((uint64_t)1 << 48);
}

/* C0F5: the original searches 21 bytes, extending past the eight ID entries. */
void opponent_sound_for_item(uint8_t *ds, uint8_t item)
{
    for (unsigned index = 0; index < 21; ++index)
        if (DS_U8(ds, 0x78DC + index) == item) {
            uint16_t kind = DS_U8(ds, 0x78E4 + index);
            uint8_t sound = DS_U8(ds, 0x80DA + kind);
            DS_U8(ds, 0x035F) = sound == 4 ? 5 : sound;
            break;
        }
}

/* C0A7: consume paired inventory records into the four choice/counter slots.
 * Missing pairs leave holes in 035B; the count does not compact those slots. */
uint16_t opponent_build_choices(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t ax = 0;
    DS_U8(ds, 0x035A) = 0;
    for (unsigned i = 0; i < 4; ++i) {
        ax = DS_U16(ds, 0xDE3E + i * 2);
        uint64_t first = opponent_find_item(g, (uint8_t)ax);
        if (first & ((uint64_t)1 << 48))
            continue;
        uint64_t second = opponent_find_item(g, ax >> 8);
        ax = (uint16_t)second;
        if (second & ((uint64_t)1 << 48))
            continue;
        uint16_t seg = (uint16_t)(second >> 32), at = (uint16_t)(second >> 16);
        (*far_ptr(g, seg, (uint16_t)(at + 5)))--;
        opponent_sound_for_item(ds, *far_ptr(g, seg, (uint16_t)(at + 2)));
        seg = (uint16_t)(first >> 32);
        at = (uint16_t)(first >> 16);
        *far_ptr(g, seg, (uint16_t)(at + 5)) = 0;
        DS_U8(ds, 0x0351 + i) = ax >> 8;
        DS_U8(ds, 0x035A)++;
        DS_U8(ds, 0x035B + i) = i;
    }
    return ax;
}

/* C068: AX output is also consumed by a later high-level controller branch. */
uint16_t opponent_select_choice(Game *g, uint16_t ax)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0x0359))
        return ax;
    ax = opponent_build_choices(g);
    uint8_t count = DS_U8(ds, 0x035A);
    if (!count) {
        DS_U8(ds, 0x034B) = 255;
        return ax;
    }
    DS_U8(ds, 0x0359) = 255;
    uint16_t r = random_word(ds) & 31;
    uint8_t remainder = r % count;
    uint16_t selected = DS_U8(ds, 0x035B + remainder);
    DS_U16(ds, 0xDE46) = selected;
    uint8_t capacity = DS_U8(ds, 0xDE38 + selected);
    DS_U8(ds, 0x0355) = capacity;
    return ((uint16_t)remainder << 8) | capacity;
}

/* C16D: append/increment within the source's ten-record far inventory. */
void opponent_add_item(Game *g, uint16_t definition)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0x120A), at = DS_U16(ds, 0x1208);
    uint8_t item = DS_U8(ds, definition);
    for (unsigned i = 0; i < 10; ++i, at += 6) {
        uint8_t id = *far_ptr(g, seg, (uint16_t)(at + 2));
        if (id == item) {
            (*far_ptr(g, seg, (uint16_t)(at + 5)))++;
            return;
        }
        if (!id || !*far_ptr(g, seg, (uint16_t)(at + 5))) {
            DS_U16(far_ptr(g, seg, at), 0) = 0;
            DS_U16(far_ptr(g, seg, (uint16_t)(at + 2)), 0) = DS_U16(ds, definition);
            DS_U8(far_ptr(g, seg, (uint16_t)(at + 4)), 0) = DS_U8(ds, definition + 2);
            DS_U8(far_ptr(g, seg, (uint16_t)(at + 5)), 0) = 1;
            return;
        }
    }
}

/* C14C: select a nonzero definition pointer, cycling on the table sentinel. */
void opponent_cycle_item(Game *g, uint16_t table)
{
    uint8_t *ds = g->ds;
    uint16_t definition;
    for (;;) {
        definition = DS_U16(ds, table + DS_U16(ds, 0x04C0));
        if (definition)
            break;
        DS_U16(ds, 0x04C0) = 0;
    }
    opponent_add_item(g, definition);
    DS_U16(ds, 0x04C0) += 2;
}
