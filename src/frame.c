/* One frame of a single-player game: the body of the main loop (0000:0155) and the input
 * check it starts with (0000:05A2).
 *
 * Everything the frame does is translated except the palette reload, which goes through
 * the host callback in FrameServices:
 *   FRAME_PALETTE      0000:7AB6   load the game palette DS:1510 into the EGA attribute
 *                                  registers 0-15 (port 3C0)
 * The M key's map screen is map_screen (src/mapkey.c), with the services in host->map; the
 * P key's phone book is phone_book (src/phonebook.c), with those in host->phone; the Q, F10
 * and Esc menus and their options are in src/gamemenus.c, with host->menus.
 * The border colour (0000:0A4F) is reported as an EV_BORDER event, as in player_hit.
 * A two-player link game is not supported: game_frame returns -1 for it.
 */
#include "term.h"

enum {
    FR_LINK_EVENT = 0xAF39, /* u8: set only by the link code */
};

enum {
    TEXT_WRONG_SYMBOL = 0x0213,  /* "The game is now over because you selected the wrong symbol." */
    TEXT_CAR_EXIT = 0x0343,      /* "Leaving a moving car hurts. You took some damage." */
    TEXT_TRAVEL_FAILED = 0x0625, /* "Your Fast Travel was not completed. There is danger nearby..." */
    MENU_TELL_SARAH = 0x06E1,    /* "Tell Sarah to...": stay, run away, follow, give item, take item */
    MENU_PLAYER = 0x08CC,        /* "PLAYER MENU": inventory, physical status, drop item, special action */
    MENU_GAME = 0x1057,          /* "GAME MENU": joystick, audio, save, delete, quit, new game, ratings */
    ACTOR_REESE = 0x04D4,        /* the playable character whose companion is Sarah */
};

static uint32_t frame_call(Game *g, const FrameServices *host, uint16_t op)
{
    if (!host || !host->call)
        return UINT32_MAX;
    return host->call(g, op, host->user);
}

/* orig 0000:0A4F   set the border (overscan) colour to entry BL of the game palette; done by
 * the host */
static void border_colour(Game *g, uint8_t entry)
{
    event_push(EV_BORDER, entry, DS_U8(g->ds, (uint16_t)(DS_PALETTE_TABLE + entry)));
}

/* orig 0000:CA46   the M key (the screen itself from CA73 is map_screen). The message left by
 * an unfinished fast travel is shown first. */
static int map_key(Game *g, const FrameServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_TRAVEL_MESSAGE)) {
        DS_U8(ds, DS_TRAVEL_MESSAGE) = 0;
        if (textbox_draw(g, TEXT_TRAVEL_FAILED, 0x0A, 8, 0x16, 7, host->gameplay ? host->gameplay->text : NULL) < 0)
            return -1;
    }
    DS_U8(ds, DS_MAP_KEY_FLAG) = 0;
    if (!DS_U8(ds, KEY_DOWN(SC_M)))
        return 0;
    return map_screen(g, host->map);
}

/* orig 0000:C45C   the P key opens the phone book (from C466: phone_book) */
static int phone_book_key(Game *g, const FrameServices *host)
{
    if (!DS_U8(g->ds, KEY_DOWN(SC_P)))
        return 0;
    return phone_book(g, host->phone);
}

/* orig 0000:05A2   once per frame, unless a warning or the reload overlay is up:
 *   M map screen, P phone book, Alt+1/2/3 detail level (everything, up to 3072, up to 2048),
 *   Q (playing Reese) the "Tell Sarah to..." menu, F10 the player menu, Esc the game menu. */
int frame_input_check(Game *g, const FrameServices *host)
{
    uint8_t *ds = g->ds;
    const GameMenuServices *menus = host ? host->menus : NULL;
    if (DS_U16(ds, DS_WARNING_COUNTDOWN) || DS_U8(ds, DS_RELOAD_COUNTDOWN))
        return 0;
    if (DS_U8(ds, FR_LINK_EVENT) && DS_U8(ds, DS_OPPONENT_ACTIVE))
        return -1; /* 151B:04BA, link play only */
    if (map_key(g, host) < 0 || phone_book_key(g, host) < 0)
        return -1;
    if (DS_U8(ds, KEY_DOWN(SC_ALT))) {
        if (DS_U8(ds, KEY_DOWN(SC_1)))
            DS_U16(ds, DS_DETAIL) = 0;
        else if (DS_U8(ds, KEY_DOWN(SC_2)))
            DS_U16(ds, DS_DETAIL) = 1;
        else if (DS_U8(ds, KEY_DOWN(SC_3)))
            DS_U16(ds, DS_DETAIL) = 2;
    }
    /* orig 0000:DD0A */
    if (DS_U8(ds, KEY_DOWN(SC_Q)) && DS_U16(ds, DS_PLAYER) == ACTOR_REESE)
        if (game_menu_display(g, MENU_TELL_SARAH, 0x11, 3, 0x16, 0x0F, 0xE3F0, menus) < 0)
            return -1;
    /* 151B:021E, called before both menus below, does nothing outside a link game */
    if (DS_U8(ds, KEY_DOWN(SC_F10))) /* orig 0000:51AA */
        return game_menu_display(g, MENU_PLAYER, 0x0A, 3, 0x14, 0x0D, 0x7968, menus) < 0 ? -1 : 0;
    if (DS_U8(ds, KEY_DOWN(SC_ESC)))
        return game_menu_display(g, MENU_GAME, 0x0B, 1, 0x16, 0x13, 0x7852, menus) < 0 ? -1 : 0;
    return 0;
}

/* orig 0000:0155 (the single-player path, 019D..0247)
 *
 * One frame: input, the wrong-symbol timer, the game update, the city and the 3D scene, the
 * HUD and weapons, the page flip, then three things requested during the frame (border
 * reset, palette reload, the car-exit message). The frame counter DS:020C counts up.
 * Returns 0 to continue, 1 when the session has ended (DS_PLAYER_DOWN or DS_MISSION_OVER
 * set), -1 where a host service was missing or a path is not translated (a link game).
 *
 * The DX register: the original hands the value DX happens to hold from one phase to the
 * next. From the game update it reaches the projectile step (modelled, as in
 * gameplay_update_controls_dx); after drawing the scene it is 03CE in every path observed
 * (RE_NOTES.md, "DOS draw-to-weapon register trace") and the post-render phase receives
 * that. Its only effect is a stored field of an unguided missile that the flight code
 * never reads.
 */
int game_frame(Game *g, const FrameServices *host)
{
    uint8_t *ds = g->ds;
    if (!host || DS_U8(ds, DS_LINK_GAME))
        return -1;
    const GameplayServices *gameplay = host->gameplay;
    const TextPlatform *text = gameplay ? gameplay->text : NULL;

    if (frame_input_check(g, host) < 0)
        return -1;

    if (DS_U16(ds, DS_WRONG_SYMBOL_TIMER) && --DS_U16(ds, DS_WRONG_SYMBOL_TIMER) == 0) {
        if (textbox_draw(g, TEXT_WRONG_SYMBOL, 1, 3, 0x18, 5, text) < 0)
            return -1;
        DS_U8(ds, DS_MISSION_OVER) = 0x55;
    }

    uint32_t dx = 0;
    if (gameplay_update_controls_dx(g, gameplay, host->shop_entry_sp, &dx) < 0
        || gameplay_update_projectiles(g, (uint16_t)dx) < 0)
        return -1;

    if (!DS_U16(ds, DS_WARNING_COUNTDOWN) && !DS_U8(ds, DS_RELOAD_COUNTDOWN))
        if (scene_overlay_restore_all(g, host->chunky_screen) < 0)
            return -1;

    if (scene_render_city(g, gameplay ? gameplay->vehicle : NULL) < 0 || scene_post_render(g, host->hud, 0x03CE) < 0
        || scene_present(g, gameplay && gameplay->vehicle ? gameplay->vehicle->display : NULL) < 0)
        return -1;

    if (DS_U8(ds, DS_BORDER_FLASH)) {
        border_colour(g, 0);
        DS_U8(ds, DS_BORDER_FLASH) = 0;
    }
    if (DS_U8(ds, DS_PALETTE_RELOAD)) {
        DS_U8(ds, DS_PALETTE_RELOAD) = 0;
        if (frame_call(g, host, FRAME_PALETTE) == UINT32_MAX)
            return -1;
    }
    if (DS_U8(ds, DS_CAR_EXIT_MESSAGE)) {
        if (textbox_draw(g, TEXT_CAR_EXIT, 9, 2, 0x14, 6, text) < 0)
            return -1;
        DS_U8(ds, DS_CAR_EXIT_MESSAGE) = 0;
    }
    DS_U16(ds, DS_FRAME_COUNTER)++;
    return (DS_U8(ds, DS_PLAYER_DOWN) || DS_U8(ds, DS_MISSION_OVER)) ? 1 : 0;
}
