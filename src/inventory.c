/* Inventory removal 0000:5546 (5558's remove-only entry); ES=main DS. */
#include "term.h"

uint16_t inventory_remove_state(uint8_t *ds, uint8_t item, uint16_t si)
{
    DS_U16(ds, DS_ITEMS_FROM) = DS_U16(ds, DS_ITEMS_TO) = 0;
    uint16_t at = 0x05B0;
    while (DS_U8(ds, at + 2)) {
        if (DS_U8(ds, at + 2) == item) {
            if (--DS_U8(ds, at + 5))
                return si;
            uint16_t category = (uint8_t)(DS_U8(ds, at + 4) - 1);
            uint16_t counter = DS_U16(ds, 0x9A4E + category * 2);
            DS_U8(ds, counter)--;
            DS_U16(ds, DS_INVENTORY_END) -= 6;
            uint16_t words = (uint16_t)(DS_U16(ds, DS_INVENTORY_END) - at) >> 1;
            uint16_t source = at + 6;
            if (words)
                si = source + words * 2;
            for (unsigned i = 0; i < words; ++i, at += 2, source += 2)
                DS_U16(ds, at) = DS_U16(ds, source);
            /* The original leaves the cleared record's bytes 3 and 5 untouched. */
            DS_U8(ds, at + 4) = 0;
            DS_U16(ds, at) = 0;
            DS_U8(ds, at + 2) = 0;
            return si;
        }
        at += 6;
    }
    return si;
}

void inventory_remove(uint8_t *ds, uint8_t item)
{
    inventory_remove_state(ds, item, 0);
}

/* The category counter of a record (DS:9A4E holds one pointer per category, 1..) */
static uint16_t category_counter(uint8_t *ds, uint16_t record)
{
    uint16_t category = (uint8_t)(DS_U8(ds, (uint16_t)(record + 4)) - 1);
    return DS_U16(ds, (uint16_t)(0x9A4E + category * 2));
}

/* orig 0000:5558   add one of item id to the list at DS:list (remove = 0), or take one away
 * (remove != 0). Lists are 6-byte records (name, id, weight, category, count) ending with
 * an id of 0: the player's at 0x05B0 (its end in DS:03A2, its category counters at DS:9A4E),
 * Sarah's at 0x085C. The search starts at list itself (callers may pass a record).
 *   adding: an existing record's count goes up; otherwise the item's record is copied from
 *   the list at DS:03FE (count 1) onto the end. The counters and DS:03A2 then go up when the
 *   destination DS:0400 is the player's list - for a new record the original compares
 *   DS:0400 with the word stored at 05B0 rather than with 05B0, which C keeps.
 *   removing: the count goes down; at 0 the record goes: from Sarah's list (DS:03FE = 085C)
 *   by shifting records down to the end marker, from the player's with the counters and
 *   DS:03A2 as in inventory_remove. */
void inventory_transfer(uint8_t *ds, uint16_t list, uint8_t item, int remove)
{
    uint16_t at = list;
    while (DS_U8(ds, (uint16_t)(at + 2)) && DS_U8(ds, (uint16_t)(at + 2)) != item)
        at = (uint16_t)(at + 6);
    int counters = 0;
    if (!DS_U8(ds, (uint16_t)(at + 2))) { /* not in the list */
        if (remove)
            return;
        uint16_t source = DS_U16(ds, DS_ITEMS_FROM);
        while (DS_U8(ds, (uint16_t)(source + 2)) != item) {
            if (!DS_U8(ds, (uint16_t)(source + 2)))
                return;
            source = (uint16_t)(source + 6);
        }
        for (unsigned i = 0; i < 5; ++i)
            DS_U8(ds, (uint16_t)(at + i)) = DS_U8(ds, (uint16_t)(source + i));
        DS_U8(ds, (uint16_t)(at + 5)) = 1;
        counters = DS_U16(ds, DS_ITEMS_TO) == DS_U16(ds, 0x05B0);
    } else if (!remove) {
        DS_U8(ds, (uint16_t)(at + 5))++;
        counters = DS_U16(ds, DS_ITEMS_TO) == 0x05B0;
    } else {
        if (--DS_U8(ds, (uint16_t)(at + 5)))
            return;
        if (DS_U16(ds, DS_ITEMS_FROM) == 0x085C) {
            uint16_t to = at;
            do {
                for (unsigned i = 0; i < 6; i += 2)
                    DS_U16(ds, (uint16_t)(to + i)) = DS_U16(ds, (uint16_t)(to + 6 + i));
                to = (uint16_t)(to + 6);
            } while (DS_U8(ds, (uint16_t)(to + 2)));
            return;
        }
        DS_U8(ds, category_counter(ds, at))--;
        DS_U16(ds, DS_INVENTORY_END) = (uint16_t)(DS_U16(ds, DS_INVENTORY_END) - 6);
        uint16_t words = (uint16_t)(DS_U16(ds, DS_INVENTORY_END) - at) >> 1;
        for (uint16_t i = 0; i < words; ++i, at = (uint16_t)(at + 2))
            DS_U16(ds, at) = DS_U16(ds, (uint16_t)(at + 6));
        DS_U8(ds, (uint16_t)(at + 4)) = 0;
        DS_U16(ds, at) = 0;
        DS_U8(ds, (uint16_t)(at + 2)) = 0;
        return;
    }
    if (counters) {
        DS_U8(ds, category_counter(ds, at))++;
        DS_U16(ds, DS_INVENTORY_END) = (uint16_t)(DS_U16(ds, DS_INVENTORY_END) + 6);
    }
}
