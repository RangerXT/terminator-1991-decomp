/* Score calculation and decimal string used by the system HUD. */
#include "term.h"

/* orig D6CB. Arithmetic wraps before the signed clamp and completion bonuses. */
uint16_t score_update(uint8_t *ds)
{
    uint16_t score = (uint16_t)(3 * DS_U16(ds, 0x0386) + 2 * DS_U16(ds, 0x0384) + (DS_U16(ds, 0x0388) << 5)
                                + 2 * DS_U16(ds, 0x037E) + 2 * DS_U16(ds, 0x037C) + 2 * DS_U16(ds, 0x0380)
                                - (DS_U16(ds, 0x0378) >> 1) + (DS_U16(ds, DS_CASH) >> 3));
    unsigned shift = DS_U8(ds, DS_DIFFICULTY) & 31;
    score = shift >= 16 ? 0 : (uint16_t)((uint32_t)score << shift);
    if ((int16_t)score < 0)
        score = 0;
    if (DS_U8(ds, 0x1157))
        score += 300;
    if (DS_U8(ds, 0x1158))
        score += 600;
    DS_U16(ds, 0x0376) = score;
    return score;
}

/* orig E26D, including decimal conversion F639. Leave bytes past the NUL intact. */
void hud_format_score(uint8_t *ds)
{
    uint16_t score = score_update(ds);
    if ((int16_t)score < 0)
        score = 0;
    uint8_t digits[5];
    unsigned count = 0;
    do {
        digits[count++] = (uint8_t)('0' + score % 10);
        score /= 10;
    } while (score);
    uint16_t dest = 0x7795;
    while (count)
        DS_U8(ds, dest++) = digits[--count];
    DS_U8(ds, dest) = 0;
}
