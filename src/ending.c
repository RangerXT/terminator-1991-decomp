/* The end of a session (0000:5B6A, from the program's start after the main loop): the
 * cutscenes for how it ended, by who played (Reese, DS:03A0 = 04D4, or the Terminator),
 * the mission's outcome (DS:00B9, 1156, 1158) and practice mode (DS:0345).
 */
#include "term.h"

static int call(Game *g, const EndingServices *host, uint16_t op, uint16_t a, uint16_t b)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, b, r->user) ? -1 : 0;
}

/* the movie player B210 (SI = file, AX = width, BX = delay, CX = variant); without movie
 * services the host's, with b = delay | variant << 8 */
static int movie(Game *g, const EndingServices *host, uint16_t file, uint16_t delay, uint16_t variant)
{
    if (host->movie)
        return cutscene_play(g, file, 0x28, delay, variant, host->movie);
    return call(g, host, OS_CUTSCENE, file, (uint16_t)(delay | variant << 8));
}

/* orig 0000:5BCD   CX frames, or until a key */
static int frames_or_key(Game *g, const EndingServices *host, uint16_t frames)
{
    do {
        if (call(g, host, 0x0D8D, 0, 0) < 0 || call(g, host, 0x0DAA, 0, 0) < 0)
            return -1;
    } while (--frames && !DS_U8(g->ds, DS_KEYBUF_COUNT));
    return 0;
}

/* the scenes: file at DS:7A19.., delay, variant, then a pause (OS_WAIT) or frames-or-key */
static int scene(Game *g, const EndingServices *host, uint16_t file, uint16_t delay, uint16_t variant,
                 uint16_t frames, int pause)
{
    if (movie(g, host, file, delay, variant) < 0)
        return -1;
    return pause ? call(g, host, OS_WAIT, frames, 0) : frames_or_key(g, host, frames);
}

static int scene_5AA9(Game *g, const EndingServices *host)
{
    return scene(g, host, 0x7A19, 8, 1, 0x78, 0);
}

static int scene_5B10(Game *g, const EndingServices *host)
{
    return scene(g, host, 0x7A25, 8, 0, 0x3C, 0);
}

static int scene_5B25(Game *g, const EndingServices *host)
{
    return scene(g, host, 0x7A2B, 0x0F, 0, 0xB4, 0);
}

/* orig 0000:5B3A   the closing scene, not in practice mode */
static int closing(Game *g, const EndingServices *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_PRACTICE_MODE))
        return 0;
    if (DS_U16(ds, DS_PLAYER) != 0x04D4)
        return DS_U8(ds, DS_PLAYER_DOWN) ? scene_5B10(g, host) : scene_5B25(g, host);
    if (DS_U8(ds, 0x1158) || DS_U8(ds, DS_PLAYER_DOWN))
        return scene_5B25(g, host);
    return scene_5B10(g, host);
}

/* orig 0000:5ABF   the last scene (and the sample group 6) */
static int last_scene(Game *g, const EndingServices *host)
{
    uint8_t *ds = g->ds;
    if (host->sound ? sound_group_select(g, host->sound, 6) < 0 : call(g, host, 0x8AFE, 0, 0) < 0)
        return -1;
    if (DS_U8(ds, 0xADD0)) {
        if (movie(g, host, 0x7A33, 5, 0) < 0)
            return -1;
    } else {
        if (movie(g, host, 0x7A29, 6, 0) < 0)
            return -1; /* 5AD6: CX as the sample group left it: 0 */
        event_push(EV_SOUND, 0x1E, DS_U8(ds, 0x80E9));
    }
    return frames_or_key(g, host, 0x12C);
}

/* orig 0000:5B6A */
int ending_sequence(Game *g, const EndingServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    if (!DS_U8(ds, 0x5CDB)) {
        int status;
        if (DS_U8(ds, 0x00B9)) { /* 5AEF, then the closing scene */
            status = scene(g, host, 0x7A2E, 8, 1, 0xB4, 0);
            if (status >= 0 && DS_U16(ds, DS_PLAYER) == 0x04D4)
                status = scene_5AA9(g, host);
            if (status >= 0)
                status = closing(g, host);
        } else if (DS_U16(ds, DS_PLAYER) != 0x04D4) {
            if (!DS_U8(ds, DS_PLAYER_DOWN)) {
                status = scene_5AA9(g, host);
                if (status >= 0)
                    status = closing(g, host);
            } else {
                status = scene(g, host, 0x7A21, 8, 1, 0xB4, 0); /* 5A93 */
                if (status >= 0 && !DS_U8(ds, DS_PRACTICE_MODE))
                    status = closing(g, host);
            }
        } else if (DS_U8(ds, 0x1158)) {
            status = closing(g, host);
        } else if (!DS_U8(ds, DS_PLAYER_DOWN)) {
            status = scene(g, host, 0x7A21, 8, 1, 0xB4, 0); /* 5A93 */
            if (status >= 0 && !DS_U8(ds, DS_PRACTICE_MODE))
                status = closing(g, host);
        } else {
            status = scene(g, host, 0x7A1D, 8, 1, 0x78, 1); /* 5A7B */
            if (status >= 0 && !DS_U8(ds, DS_PRACTICE_MODE))
                status = scene_5AA9(g, host);
            if (status >= 0)
                status = closing(g, host);
        }
        if (status < 0)
            return -1;
    }
    DS_U8(ds, 0x5CDB) = 0;
    return last_scene(g, host);
}
