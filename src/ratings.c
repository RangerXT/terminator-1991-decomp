/* Rating table obfuscation, record selection and insertion, original D5FA..D74A. */
#include "term.h"

void ratings_decode(uint8_t *data, uint16_t count)
{
    for (unsigned i = 0; i < count; ++i)
        data[i] = (uint8_t)(data[i] + (uint8_t)(count - i)) ^ 0xA5;
}

/* D5FA's encode body always writes capacity five: 2 + 5*41 = 207 bytes. */
void ratings_encode(uint8_t *data)
{
    for (unsigned i = 0; i < 207; ++i)
        data[i] = (uint8_t)((data[i] ^ 0xA5) - (uint8_t)(207 - i));
}

void ratings_stats_save(uint8_t *ds)
{
    memcpy(ds + 0xE39C, ds + 0x0376, 41);
}

void ratings_stats_restore(uint8_t *ds)
{
    memcpy(ds + 0x0376, ds + 0xE39C, 41);
    DS_U16(ds, 0x11A8) = DS_U16(ds, 0xE34C);
}

void ratings_select(uint8_t *ds, uint16_t index)
{
    uint16_t at = 0x50B4 + (uint16_t)(index * 41);
    for (unsigned i = 0; i < 41; ++i)
        DS_U8(ds, 0x0376 + i) = DS_U8(ds, (uint16_t)(at + i));
}

/* orig 0000:D67F   the score DS:0376 (signed) into the table DS:50B2 (a count, then 29h-byte
 * records whose first word is the score): before the first record it beats (ties do not),
 * DS:11A8 = what the LOOP count was there (FFFFh: none); the records from there moved one
 * down, CL (the count left - 1, low byte) of them, backwards (STD; REP MOVSB), then the
 * record copied in and the count raised up to 5. As the original for any count: 0 scans
 * 65536 records, offsets wrap in the segment. */
void ratings_insert(uint8_t *ds)
{
    uint16_t cx = DS_U16(ds, 0x50B2), si = 0x50B4;
    int16_t ax = DS_I16(ds, 0x0376);
    for (;;) {
        if (ax > DS_I16(ds, si))
            break;
        si = (uint16_t)(si + 0x29);
        if (!--cx) {
            DS_U16(ds, 0x11A8) = 0xFFFF;
            return;
        }
    }
    DS_U16(ds, 0x11A8) = cx;
    uint16_t entry = si;
    if (--cx) {
        uint16_t n = (uint16_t)(0x29 * (uint8_t)cx);  /* MUL CL */
        uint16_t from = (uint16_t)(si + n - 1), to = (uint16_t)(si + 0x29 + n - 1);
        for (; n; --n)
            DS_U8(ds, to--) = DS_U8(ds, from--);
    }
    for (uint16_t i = 0; i < 0x29; ++i)
        DS_U8(ds, (uint16_t)(entry + i)) = DS_U8(ds, (uint16_t)(0x0376 + i));
    if (DS_U16(ds, 0x50B2) < 5)
        DS_U16(ds, 0x50B2)++;
}

void ratings_update_time(uint8_t *ds)
{
    DS_U16(ds, 0x0380) = DS_U16(ds, 0x1174);
}

void ratings_clear_stats(uint8_t *ds)
{
    memset(ds + 0x0376, 0, 41);
}
