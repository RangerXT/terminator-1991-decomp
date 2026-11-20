/* Shop alarm and theft probability, original 873D..87FB. */
#include "term.h"

int shop_alarm(Game *g, const ImageIO *files, const MenuPlatform *timing, const TextPlatform *input, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0xAA94) = 255;
    DS_U8(ds, 0x80E9) = 255;
    event_push(EV_SOUND, 22, 255);
    DS_U8(ds, 0x80E9) = 0;
    if (DS_U8(ds, 0x7A18)) {
        if (!timing || !timing->call || timing->call(g, MM_WAIT, 100, 0, timing->user))
            return -1;
    }
    uint16_t text = DS_U16(ds, 0x9A6E) == 0x9BE2 ? 0x0FCC : DS_U8(ds, 0xA917) ? 0x0F31 : 0x0EC7;
    if (!DS_U8(ds, 0x7A18)) {
        int status = DS_U8(ds, DS_FACILITY_SCREEN) ? textbox_vga_draw(g, screen, text, 18, 3, 20, 11, input)
                                                   : textbox_draw(g, text, 18, 3, 20, 11, input);
        if (status < 0)
            return -1;
    }
    DS_U8(ds, 0xAA94) = 0;
    event_push(EV_SOUND, 21, 0);
    uint16_t count = DS_U8(ds, DS_U16(ds, DS_PLAYER) + 50) >> 1;
    if (count >= 12 && !DS_U8(ds, DS_IN_BATTLE)) {
        DS_U8(ds, 0x11CD) = 0;
        if (character_resources_variant(g, files))
            return -1;
        count -= 12;
        if (count >= 12)
            count = 12;
    }
    if (figure_spawn_display(g, (uint16_t)(count + 1), 0, screen))
        return -1;
    return 1;
}

int shop_check_theft(Game *g, const ImageIO *files, const MenuPlatform *timing, const TextPlatform *input,
                     uint8_t *screen)
{
    uint8_t *ds = g->ds;
    if ((random_word(ds) & 0x0FFF) <= DS_U16(ds, 0x11C4))
        return shop_alarm(g, files, timing, input, screen);
    DS_U16(ds, 0x11C4) += 80;
    return 0;
}

void shop_randomize_balances(uint8_t *ds)
{
    DS_U16(ds, 0x04C8) = random_word(ds) & 0x07FF;
    DS_U16(ds, 0x04CA) = random_word(ds) & 0x07FF;
}
