/* Text feedback in the 96x49 HUD panel (C898/C957/C976). */
#include "term.h"

void hud_message_clear(Game *g)
{
    ega_seq_mask(g->planes, 15);
    ega_gc(g->planes, 1, 15);
    ega_gc(g->planes, 0, 4);
    uint16_t to = 0x12C1;
    for (unsigned row = 0; row < 49; ++row) {
        for (unsigned word = 0; word < 6; ++word) {
            ega_store(g->planes, to++, 0);
            ega_store(g->planes, to++, 4);
        }
        to += 28;
    }
    ega_gc(g->planes, 1, 0);
}

static int message_visible(const uint8_t *ds)
{
    return !DS_U8(ds, 0x7AC6) && !DS_U8(ds, DS_CAMERA_MODE) && (DS_U8(ds, DS_U16(ds, DS_PLAYER) + 14) & 1);
}

static void message_copy(Game *g)
{
    screen_copy_rect(g, 0x12C1, 0x32C1, 12, 49);
    screen_copy_rect(g, 0x12C1, 0x52C1, 12, 49);
}

void hud_message_hide(Game *g)
{
    if (!message_visible(g->ds))
        return;
    hud_message_clear(g);
    message_copy(g);
}

/* Text consists of NUL-delimited lines followed by FF, as in the actual data.
 * Retain the source SCAS length bookkeeping, including its extra empty line case. */
void hud_message(Game *g, uint16_t text)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, DS_PLAYER) == 0x0508)
        event_push(EV_SOUND, 12, 0);
    if (!message_visible(ds))
        return;
    hud_message_clear(g);
    uint16_t scan = text, left = 65535;
    do {
        uint8_t value = DS_U8(ds, scan++);
        --left;
        if (value == 255)
            break;
    } while (left);
    uint16_t length = (uint16_t)(65535 - left - 2), pointer = 0xE174, lines = 1;
    DS_U16(ds, pointer) = text;
    pointer += 2;
    for (;;) {
        left = length;
        scan = text;
        while (left) {
            uint8_t value = DS_U8(ds, scan++);
            --left;
            if (!value)
                break;
        }
        text = scan;
        if (DS_U8(ds, text) == 255)
            break;
        lines++;
        DS_U16(ds, pointer) = text;
        pointer += 2;
        uint16_t consumed = length - left - 1;
        length -= consumed;
    }
    uint16_t page = DS_U16(ds, DS_DRAW_PAGE);
    DS_U16(ds, DS_DRAW_PAGE) = 0;
    for (uint16_t i = 0; i < lines; ++i)
        hud_draw_text(g, DS_U16(ds, 0xE174 + i * 2), DS_U16(ds, 0xE182 + i * 2));
    DS_U16(ds, DS_DRAW_PAGE) = page;
    message_copy(g);
}
