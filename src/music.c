/* Starting and stopping the music (0000:8986, 899C, 8C52, 8C64): the game's flags around the
 * FM driver's calls, which the host's audio backend performs (by original address):
 * MU_LOAD 89F0 (load and register DX = the file name), MU_STOP F472, MU_RESET F445, MU_CLOSE
 * F4C1, MU_SAMPLES_OFF F205.
 */
#include "term.h"

enum {
    MU_WANTED = 0x0361,    /* u8: the music is switched on (the game menu's option) */
    MU_DEVICE = 0xA773,    /* u16: the sound device: 2 Sound Blaster, 4 AdLib and samples ... */
    MU_LOADED = 0xA615,    /* u8: a song is loaded */
    MU_PLAYING = 0xA616,   /* u8 */
    MU_DRIVER = 0xEA3C,    /* u8: the FM driver is playing */
    MU_SONG = 0xA617,      /* the song's file name */
};

static int audio(Game *g, const MapResources *host, uint16_t op, uint16_t a)
{
    return !host || !host->call || host->call(g, op, a, 0, host->user) ? -1 : 0;
}

/* orig 0000:8C52 */
int music_stop(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, MU_LOADED) && DS_U8(ds, MU_DRIVER))
        return audio(g, host, MU_STOP, 0);
    return 0;
}

/* orig 0000:8986   (re)start the song if the music is switched on */
int music_start(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, MU_WANTED))
        return 0;
    if (music_stop(g, host) < 0)
        return -1;
    DS_U8(ds, MU_PLAYING) = 1;
    return audio(g, host, MU_LOAD, MU_SONG);
}

/* orig 0000:899C */
void music_mark_ending(uint8_t *ds)
{
    DS_U8(ds, 0xA622) = 0xFF;
}

/* orig 0000:8C64   stop and close the driver (Sound Blaster, or AdLib with samples) */
int music_close(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, MU_LOADED)) {
        uint16_t device = DS_U16(ds, MU_DEVICE);
        if (device == 2 || device == 4) {
            if (device == 4 && audio(g, host, MU_SAMPLES_OFF, 0) < 0)
                return -1;
            if (music_stop(g, host) < 0 || audio(g, host, MU_RESET, 0) < 0 || audio(g, host, MU_CLOSE, 0) < 0)
                return -1;
        }
    }
    DS_U8(ds, MU_PLAYING) = 0;
    return 0;
}
