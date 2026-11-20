/* The FM music driver (segment 10BB, "FMDRV": Creative's SBFMDRV, built into TERM.EXE), its
 * functions (10BB:0000 by BX) and its two interrupt handlers, translated routine for routine.
 * It plays CMF songs: MIDI events, FM instruments from the song's table (or its own sixteen
 * at 10BB:0048), nine melodic voices or six and five drums, on the OPL2 at the port base it
 * is given (+ 8 / + 9: 388h for an AdLib, 228h for a Sound Blaster).
 *
 * Its data are at their original offsets in the driver's segment of the game's memory; the
 * ports, the PIC and the timer go through MachineServices. Its own quirks are kept: see
 * silence(), voices_init() and note_fnum().
 *
 * The driver's data (offsets in its segment):
 *   09 port base   0C version   0E old INT 8   12 old INT 9   16 instruments (far)
 *   1A song position (far)   1E song start (far)   22 ticks to the next event (32 bits)
 *   26 status byte (far)   2A user trap (far)   2E, 30 port delays (loops)   32 system clock
 *   divisor   34 driver clock divisor   36 the divisor the timer runs at   38 system clock
 *   accumulator   3A voices (9, 6 with drums)   3C event channel   3E event kind   40 event
 *   clock   42 transpose   148 voice -> channel (FFh free, bit 7 released)   153 voice -> note
 *   15E voice -> key scaling bits   169 voice -> volume   174 voice -> F-number and block
 *   18A voice -> when started   1A0 voice -> operator offset   1A9 the default instrument
 *   1AE.. drum tables   1C3 instruments   1C4 0 stopped, 1 playing, 2 paused   1C5, 1C6 note,
 *   velocity   1C7 busy   1C8 the default status byte   1C9 register BDh   1CA drums on
 *   1CC channel -> instrument   1DC voice -> pitch bend (set by channel)   252 note -> octave
 *   and semitone   2D2 F-numbers, 32 steps a semitone
 */
#include "term.h"

#define FLAG_CF 0x0001

enum { DRIVER_SEG = 0x10BB, ISR_TIMER = 0x0C83, ISR_KEYBOARD = 0x0CF3, ISR_COUNT = 0x0EF5 };

static uint16_t driver_segment(const Game *g)
{
    return (uint16_t)(g->ds_seg - 0x5C27 + DRIVER_SEG);
}

static uint8_t *drv(Game *g)
{
    return far_ptr(g, driver_segment(g), 0);
}

static uint16_t rw(const uint8_t *cs, uint16_t o)
{
    return (uint16_t)(cs[o] | cs[o + 1] << 8);
}

static void ww(uint8_t *cs, uint16_t o, uint16_t v)
{
    cs[o] = (uint8_t)v;
    cs[o + 1] = (uint8_t)(v >> 8);
}

static uint8_t port_in(Game *g, const MachineServices *mc, uint16_t port)
{
    return (uint8_t)(mc && mc->in ? mc->in(g, port, 1, mc->user) : 0xFF);
}

static void port_out(Game *g, const MachineServices *mc, uint16_t port, uint8_t value)
{
    if (mc && mc->out)
        mc->out(g, port, 1, value, mc->user);
}

/* 060B: register AH, value AL, at the port base (the original waits [2E] and [30] loops
 * after the two writes) */
static void opl(Game *g, const MachineServices *mc, uint8_t reg, uint8_t value)
{
    uint16_t port = rw(drv(g), 0x09);
    port_out(g, mc, port, reg);
    port_out(g, mc, (uint16_t)(port + 1), value);
}

/* 05FA: the timer (PIT channel 0, mode 3) at AX, noted at 36 */
static void set_timer(Game *g, const MachineServices *mc, uint16_t divisor)
{
    ww(drv(g), 0x36, divisor);
    port_out(g, mc, 0x43, 0x36);
    port_out(g, mc, 0x40, (uint8_t)divisor);
    port_out(g, mc, 0x40, (uint8_t)(divisor >> 8));
}

/* 06E3 */
static void set_status(Game *g, uint8_t value)
{
    const uint8_t *cs = drv(g);
    *far_ptr(g, rw(cs, 0x28), rw(cs, 0x26)) = value;
}

/* 0631: every voice keyed off at its F-number, the drums cleared. The release is meant for
 * register 83h + operator, but AL is reloaded before it is used: 13h goes to register 83h
 * nine times. */
static void silence(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    for (int bx = 8; bx >= 0; --bx) {
        opl(g, mc, 0x83, 0x13);
        if (cs[0x148 + bx] <= 0x7F) {
            uint16_t f = rw(cs, (uint16_t)(0x174 + 2 * bx));
            opl(g, mc, (uint8_t)(0xA0 + bx), (uint8_t)f);
            opl(g, mc, (uint8_t)(0xB0 + bx), (uint8_t)(f >> 8));
        }
    }
    if (cs[0x1CA]) {
        cs[0x1C9] &= 0xE0;
        opl(g, mc, 0xBD, cs[0x1C9]);
    }
}

/* 067A: no instruments chosen, every voice free, each voice's operators given the default
 * instrument. Its last register should be C0h + voice; the original adds the voice to the
 * operator offset instead (registers 00, 02, 04, 0B, 0D, 0F, 16, 18, 1A get 08h). */
static void voices_init(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    memset(cs + 0x1CC, 0, 16);
    memset(cs + 0x148, 0xFF, 11);
    for (uint8_t bl = 0; bl < 9; ++bl) {
        opl(g, mc, 0xBD, 0x00);
        opl(g, mc, 0x08, 0x00);
        uint8_t op = cs[0x1A0 + bl], ah = op;
        uint16_t si = 0x1A9;
        for (int i = 0; i < 4; ++i) {
            ah = (uint8_t)(ah + 0x20);
            opl(g, mc, ah, cs[si++]);
            opl(g, mc, (uint8_t)(ah + 3), cs[si++]);
        }
        ah = (uint8_t)(ah + 0x60);
        opl(g, mc, ah, cs[si++]);
        opl(g, mc, (uint8_t)(ah + 3), cs[si++]);
        opl(g, mc, (uint8_t)(op + bl), cs[si++]);
    }
}

/* 06EE: instrument AL for voice BX (a drum voice above 6 has one operator) */
static void load_instrument(Game *g, const MachineServices *mc, uint8_t number, uint16_t bx)
{
    uint8_t *cs = drv(g);
    if (number >= cs[0x1C3])
        return;
    uint16_t seg = rw(cs, 0x18), di = (uint16_t)(rw(cs, 0x16) + (uint16_t)((int8_t)number * 16));
#define IN(o) (*far_ptr(g, seg, (uint16_t)(di + (o))))
    uint8_t level = IN(3);
    cs[0x15E + bx] = level & 0xC0;
    cs[0x169 + bx] = (uint8_t)(0x3F - (level & 0x3F));
    if (cs[0x1CA] && bx > 6) {
        uint8_t ah = cs[0x1AE + bx];
        for (int i = 0; i < 4; ++i) {
            ah = (uint8_t)(ah + 0x20);
            opl(g, mc, ah, IN(2 * i));
        }
        opl(g, mc, (uint8_t)(ah + 0x60), IN(8));
        opl(g, mc, (uint8_t)(cs[0x1B8 + bx] + 0xC0), IN(10));
    } else {
        uint8_t ah = cs[0x1A0 + bx];
        for (int i = 0; i < 4; ++i) {
            ah = (uint8_t)(ah + 0x20);
            opl(g, mc, ah, IN(2 * i));
            opl(g, mc, (uint8_t)(ah + 3), IN(2 * i + 1));
        }
        ah = (uint8_t)(ah + 0x60);
        opl(g, mc, ah, IN(8));
        opl(g, mc, (uint8_t)(ah + 3), IN(9));
        opl(g, mc, (uint8_t)(0xC0 + bx), IN(10));
    }
#undef IN
}

/* 07A0: a variable-length number at the song position, which moves past it (in its
 * segment) */
static uint32_t read_number(Game *g)
{
    uint8_t *cs = drv(g);
    uint16_t seg = rw(cs, 0x1C), si = rw(cs, 0x1A);
    uint32_t v = 0;
    for (;;) {
        uint8_t b = *far_ptr(g, seg, si++);
        v += b & 0x7F;
        if (!(b & 0x80))
            break;
        v <<= 7;
    }
    ww(cs, 0x1A, si);
    return v;
}

/* 07D0: the song position moved on by DL:AX */
static void skip(Game *g, uint32_t length)
{
    uint8_t *cs = drv(g);
    uint32_t off = (uint32_t)rw(cs, 0x1A) + (uint16_t)length;
    ww(cs, 0x1A, (uint16_t)off);
    uint16_t seg = rw(cs, 0x1C);
    if (off > 0xFFFF)
        seg = (uint16_t)(seg + 0x1000);
    ww(cs, 0x1C, (uint16_t)(seg + (((length >> 16) & 0xFF) << 12)));
}

/* 07EF: a voice for channel AL: one of its own released ones, a free one, any released one,
 * else the one started longest ago (keyed off first) */
static uint16_t voice_for(Game *g, const MachineServices *mc, uint8_t channel)
{
    uint8_t *cs = drv(g);
    uint16_t n = rw(cs, 0x3A);
    for (uint16_t v = 0; v < n; ++v)
        if (cs[0x148 + v] == (uint8_t)(channel | 0x80))
            return v;
    for (uint16_t v = 0; v < n; ++v)
        if (cs[0x148 + v] == 0xFF)
            return v;
    for (uint16_t v = 0; v < n; ++v)
        if (cs[0x148 + v] > 0x7F)
            return v;
    uint16_t oldest = 0, age = 0;
    for (uint16_t v = 0; v < n; ++v) {
        uint16_t a = (uint16_t)(rw(cs, 0x40) - rw(cs, (uint16_t)(0x18A + 2 * v)));
        if (a > age) {
            age = a;
            oldest = v;
        }
    }
    uint16_t f = rw(cs, (uint16_t)(0x174 + 2 * oldest));
    opl(g, mc, (uint8_t)(0xA0 + oldest), (uint8_t)f);
    opl(g, mc, (uint8_t)(0xB0 + oldest), (uint8_t)(f >> 8));
    return oldest;
}

/* 086F: melodic, nine voices */
static void melodic(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    ww(cs, 0x3A, 9);
    ww(cs, 0x1C9, 0x00C0);
    opl(g, mc, 0xBD, 0xC0);
}

/* 0DB1: stopped: the timer at the system clock, every voice off, the status byte 0 */
static void stop(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    if (!cs[0x1C4])
        return;
    cs[0x1C4] = 0;
    set_timer(g, mc, rw(cs, 0x32));
    silence(g, mc);
    set_status(g, 0);
}

/* 0881 */
static void reset(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    stop(g, mc);
    melodic(g, mc);
    cs[0x1C3] = 0x10;
    ww(cs, 0x16, 0x0048);
    ww(cs, 0x18, driver_segment(g));
    voices_init(g, mc);
    ww(cs, 0x34, 0x48D3);
    ww(cs, 0x42, 0);
}

/* 0AF9: the F-number and block (in the high byte) of note 1C5 for voice BX, noted as the
 * voice's note. Two quirks: the pitch bend is taken from the table by voice, though it is
 * set by channel; and a note bent up past the top of an octave goes to the very top of the
 * scale unless the octave already was the highest. */
static uint16_t note_fnum(Game *g, uint16_t bx)
{
    uint8_t *cs = drv(g);
    uint8_t note = cs[0x1C5];
    cs[0x153 + bx] = note;
    int16_t di = (int16_t)(rw(cs, 0x42) + (int8_t)note);
    if (di < 0)
        di = 0;
    uint8_t code = cs[0x252 + (di & 0x7F)];
    uint8_t dl = (uint8_t)((code & 0x70) >> 2);
    uint16_t ax = (uint16_t)((code & 0x0F) << 5);
    ax = (uint16_t)(ax + rw(cs, (uint16_t)(0x1DC + 2 * bx)));
    if (ax & 0x8000) {
        ax = (uint16_t)(ax + 0x180);
        dl = (uint8_t)(dl - 4);
        if (dl & 0x80) {
            dl = 0;
            ax = 0;
        }
    } else if (ax >= 0x180) {
        ax = (uint16_t)(ax - 0x180);
        dl = (uint8_t)(dl + 4);
        if (dl < 0x1C) {
            ax = 0x17F;
            dl = 0x1C;
        }
    }
    return (uint16_t)(rw(cs, (uint16_t)(0x2D2 + 2 * ax)) | dl << 8);
}

/* 09A1: note 1C5 off on channel 3C (a drum: its bit in BDh cleared) */
static void note_off(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    uint16_t n = rw(cs, 0x3A);
    uint8_t channel = cs[0x3C];
    if (n <= 6 && channel >= 0x0B) {
        cs[0x1C9] = (uint8_t)(~cs[0x1AE + channel] & cs[0x1C9]);
        opl(g, mc, 0xBD, cs[0x1C9]);
        return;
    }
    for (uint16_t v = 0; v < n; ++v)
        if (cs[0x153 + v] == cs[0x1C5] && cs[0x148 + v] == channel) {
            cs[0x148 + v] |= 0x80;
            uint16_t f = rw(cs, (uint16_t)(0x174 + 2 * v));
            opl(g, mc, (uint8_t)(0xA0 + v), (uint8_t)f);
            opl(g, mc, (uint8_t)(0xB0 + v), (uint8_t)(f >> 8));
            return;
        }
}

/* the carrier's level from the voice's volume and the velocity, with its key scaling */
static uint8_t level_of(const uint8_t *cs, uint16_t bx)
{
    uint16_t product = (uint16_t)(cs[0x169 + bx] * (uint8_t)(cs[0x1C6] | 0x80));
    return (uint8_t)((uint8_t)(0x3F - (product >> 8)) | cs[0x15E + bx]);
}

/* 0A96: a drum (channel 11..15 with drums on) */
static void drum_on(Game *g, const MachineServices *mc, uint8_t channel)
{
    uint8_t *cs = drv(g);
    uint16_t bx = (uint16_t)(int8_t)(channel - 5);
    cs[0x1C9] |= cs[0x1B3 + bx];
    uint8_t reg = cs[0x1AE + bx];
    if (bx == 6)
        reg = (uint8_t)(reg + 3);
    opl(g, mc, (uint8_t)(reg + 0x40), level_of(cs, bx));
    uint16_t f = note_fnum(g, bx);
    ww(cs, (uint16_t)(0x174 + 2 * bx), f);
    ww(cs, (uint16_t)(0x18A + 2 * bx), rw(cs, 0x40));
    uint8_t voice = cs[0x1B8 + bx];
    opl(g, mc, (uint8_t)(0xA0 + voice), (uint8_t)f);
    opl(g, mc, (uint8_t)(0xB0 + voice), (uint8_t)(f >> 8));
    opl(g, mc, 0xBD, cs[0x1C9]);
}

/* the event's handler by its kind (table 1FC), the data at seg:*si */
static void event(Game *g, const MachineServices *mc, uint16_t seg, uint16_t *si)
{
    uint8_t *cs = drv(g);
    uint8_t d0 = *far_ptr(g, seg, *si), d1 = *far_ptr(g, seg, (uint16_t)(*si + 1));
    switch (cs[0x3E]) {
    case 0: /* 8x (0995): note off */
        cs[0x1C5] = d0;
        cs[0x1C6] = d1;
        *si = (uint16_t)(*si + 2);
        note_off(g, mc);
        return;
    case 1: { /* 9x (0A0D): note on, velocity 0 off */
        cs[0x1C5] = d0;
        cs[0x1C6] = d1;
        *si = (uint16_t)(*si + 2);
        if (!d1) {
            note_off(g, mc);
            return;
        }
        uint8_t channel = cs[0x3C];
        if (cs[0x1CA] && channel >= 0x0B) {
            drum_on(g, mc, channel);
            return;
        }
        uint16_t bx = voice_for(g, mc, channel);
        uint8_t old = cs[0x148 + bx];
        cs[0x148 + bx] = channel;
        if ((old & 0x7F) != channel)
            load_instrument(g, mc, cs[0x1CC + rw(cs, 0x3C)], bx);
        opl(g, mc, (uint8_t)(cs[0x1A0 + bx] + 0x43), level_of(cs, bx));
        uint16_t f = note_fnum(g, bx);
        ww(cs, (uint16_t)(0x174 + 2 * bx), f);
        ww(cs, (uint16_t)(0x18A + 2 * bx), rw(cs, 0x40));
        opl(g, mc, (uint8_t)(0xA0 + bx), (uint8_t)f);
        opl(g, mc, (uint8_t)(0xB0 + bx), (uint8_t)((f >> 8) | 0x20));
        return;
    }
    case 2: /* Ax, Ex: two bytes skipped */
    case 6:
        *si = (uint16_t)(*si + 2);
        return;
    case 5: /* Dx: one */
        *si = (uint16_t)(*si + 1);
        return;
    case 3: { /* Bx (0B5E): controllers 66h marker, 67h drums, 68h / 69h bend up / down */
        *si = (uint16_t)(*si + 2);
        uint8_t which = (uint8_t)(d0 - 0x66), value = d1;
        if (which >= 4)
            return;
        if (which == 0)
            set_status(g, value);
        else if (which == 1) {
            uint16_t cx = value ? 0x06E0 : 0x09C0;
            cs[0x1CA] = value;
            cs[0x1C9] = (uint8_t)cx;
            cs[0x3A] = (uint8_t)(cx >> 8);
            ww(cs, 0x14E, 0xFFFF);
            cs[0x150] = 0xFF;
            opl(g, mc, 0xBD, cs[0x1C9]);
            voices_init(g, mc);
        } else {
            if (which == 3)
                value = (uint8_t)-value;
            ww(cs, (uint16_t)(0x1DC + 2 * rw(cs, 0x3C)), (uint16_t)((int16_t)(int8_t)value >> 2));
        }
        return;
    }
    case 4: { /* Cx (0BC1): the channel's instrument, given to its voices */
        uint8_t n = d0, count = cs[0x1C3];
        *si = (uint16_t)(*si + 1);
        if (count) /* (the original loops for ever on a table of none) */
            while (n >= count)
                n = (uint8_t)(n - count);
        uint8_t channel = cs[0x3C];
        cs[0x1CC + channel] = n;
        if (cs[0x1CA] && rw(cs, 0x3C) >= 0x0B) {
            load_instrument(g, mc, cs[0x1CC + channel], (uint16_t)(uint8_t)(channel - 5));
            return;
        }
        uint16_t voices = rw(cs, 0x3A);
        for (uint16_t v = 0; v < voices; ++v) /* its released voices freed */
            if (cs[0x148 + v] == (uint8_t)(channel | 0x80))
                cs[0x148 + v] = 0xFF;
        for (uint16_t v = 0; v < voices; ++v)
            if (cs[0x148 + v] == channel)
                load_instrument(g, mc, cs[0x1CC + channel], v);
        return;
    }
    case 7: /* Fx (0C3B): by the low nibble */
        switch (cs[0x3C]) {
        case 0x0: /* F0: a SysEx (the user's trap first, which the game never sets), F7 */
        case 0x7:
            ww(cs, 0x1A, *si);
            skip(g, read_number(g));
            *si = rw(cs, 0x1A);
            return;
        case 0x2:
            *si = (uint16_t)(*si + 2);
            return;
        case 0x3:
            *si = (uint16_t)(*si + 1);
            return;
        case 0xC:
            stop(g, mc);
            return;
        case 0xF: /* meta: 2Fh ends the song */
            *si = (uint16_t)(*si + 1);
            if (d0 == 0x2F)
                stop(g, mc);
            ww(cs, 0x1A, *si);
            skip(g, read_number(g));
            *si = rw(cs, 0x1A);
            return;
        }
        return;
    }
}

/* 092B: the events due now, until one comes after a delay */
static void tick(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    ww(cs, 0x40, (uint16_t)(rw(cs, 0x40) + 1));
    ww(cs, 0x1C, (uint16_t)(rw(cs, 0x1C) + (rw(cs, 0x1A) >> 4)));
    ww(cs, 0x1A, rw(cs, 0x1A) & 0x0F);
    for (;;) {
        uint16_t seg = rw(cs, 0x1C), si = rw(cs, 0x1A);
        uint8_t status = *far_ptr(g, seg, si);
        if (status & 0x80) { /* else the last status goes on */
            si++;
            cs[0x3C] = status & 0x0F;
            cs[0x3E] = (uint8_t)((status >> 4) - 8);
        }
        event(g, mc, seg, &si);
        ww(cs, 0x1A, si);
        if (!cs[0x1C4])
            return;
        uint32_t delay = read_number(g);
        ww(cs, 0x22, (uint16_t)delay);
        ww(cs, 0x24, (uint16_t)(delay >> 16));
        if (delay) {
            delay -= 1;
            ww(cs, 0x22, (uint16_t)delay);
            ww(cs, 0x24, (uint16_t)(delay >> 16));
            return;
        }
    }
}

/* 08A5: the song at DX:AX started */
static uint16_t play(Game *g, const MachineServices *mc, uint16_t off, uint16_t seg)
{
    uint8_t *cs = drv(g);
    if (cs[0x1C4])
        return 0xFFFE;
    ww(cs, 0x1E, off);
    ww(cs, 0x20, seg);
    ww(cs, 0x1A, off);
    ww(cs, 0x1C, seg);
    memset(cs + 0x1DC, 0, 32);
    memset(cs + 0x148, 0xFF, 9);
    uint32_t delay = read_number(g);
    ww(cs, 0x22, (uint16_t)delay);
    ww(cs, 0x24, (uint16_t)(delay >> 16));
    ww(cs, 0x40, 0);
    set_timer(g, mc, rw(cs, 0x34));
    ww(cs, 0x38, 0);
    melodic(g, mc);
    cs[0x1C4] = 1;
    set_status(g, 0xFF);
    return 0;
}

/* 0E97: AL to the FM chip's register AH... as the detection writes them (AL the register, AH
 * the value), with five status reads after each write (0EAA) */
static void detect_write(Game *g, const MachineServices *mc, uint8_t reg, uint8_t value)
{
    uint16_t port = (uint16_t)((rw(drv(g), 0x09) & 0xFF00) | (uint8_t)(rw(drv(g), 0x09) + 8));
    port_out(g, mc, port, reg);
    for (int i = 0; i < 5; ++i)
        port_in(g, mc, port);
    port_out(g, mc, (uint16_t)(port + 1), value);
    for (int i = 0; i < 5; ++i)
        port_in(g, mc, port);
}

/* 0E76: the status's top three bits AL within 64 reads */
static int detect_status(Game *g, const MachineServices *mc, uint8_t want)
{
    uint16_t port = (uint16_t)((rw(drv(g), 0x09) & 0xFF00) | (uint8_t)(rw(drv(g), 0x09) + 8));
    for (int n = 0; n < 0x40; ++n)
        if ((port_in(g, mc, port) & 0xE0) == (want & 0xE0))
            return 1;
    return 0;
}

/* 0EBB: an OPL2 at base + 8: its timer 1 runs out */
static int detect(Game *g, const MachineServices *mc)
{
    detect_write(g, mc, 0x01, 0x00);
    detect_write(g, mc, 0x04, 0x60);
    detect_write(g, mc, 0x04, 0x80);
    if (!detect_status(g, mc, 0x00))
        return 0;
    detect_write(g, mc, 0x02, 0xFF);
    detect_write(g, mc, 0x04, 0x21);
    if (!detect_status(g, mc, 0xC0))
        return 0;
    detect_write(g, mc, 0x04, 0x60);
    detect_write(g, mc, 0x04, 0x80);
    return 1;
}

/* 0EFE: the port delays measured: the timer at 98BAh with only its interrupt let through
 * (handled by 0EF5, which inverts AX), the loops counted from one interrupt to the next;
 * [2E] = loops / 8192 + 1, [30] = 6 ([2E] - 1) + 1. The loops are the host's: one poll of
 * MachineServices.irq each. Then the base moved to the FM ports (+ 8). */
static int calibrate(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    uint32_t old = vector_get(g, 8);
    ww(cs, 0x0E, (uint16_t)old);
    ww(cs, 0x10, (uint16_t)(old >> 16));
    uint16_t ax = (uint16_t)old; /* AH stays the old offset's: IN AL,21h */
    ax = (uint16_t)((ax & 0xFF00) | port_in(g, mc, 0x21));
    ww(cs, 0x2E, ax);
    port_out(g, mc, 0x21, 0xFE);
    set_timer(g, mc, 0x98BA);
    vector_set(g, 8, ISR_COUNT, driver_segment(g));
    uint16_t value = 0, cx = 0;
    int (*irq)(Game *, void *) = mc ? mc->irq : NULL;
    if (!irq)
        return -1;
    /* the interrupt's handler (0EF5): NOT AX, EOI */
#define POLL()                                                                                                        \
    do {                                                                                                              \
        int vector = irq(g, mc->user);                                                                                \
        if (vector == 8) {                                                                                            \
            value = (uint16_t)~value;                                                                                 \
            port_out(g, mc, 0x20, 0x20);                                                                              \
        } else if (vector >= 0)                                                                                       \
            return -1;                                                                                                \
    } while (0)
    for (unsigned guard = 0; !value; ++guard) {
        POLL();
        if (guard > 10000000)
            return -1;
    }
    for (unsigned guard = 0; value; ++guard) {
        POLL();
        if (guard > 10000000)
            return -1;
    }
    for (unsigned guard = 0; !value; ++guard) {
        cx++;
        POLL();
        if (guard > 10000000)
            return -1;
    }
#undef POLL
    port_out(g, mc, 0x21, (uint8_t)rw(cs, 0x2E));
    set_timer(g, mc, rw(cs, 0x32));
    vector_set(g, 8, rw(cs, 0x0E), rw(cs, 0x10));
    uint16_t loops = (uint16_t)((cx >> 13) + 1);
    ww(cs, 0x2E, loops);
    ww(cs, 0x30, (uint16_t)((loops - 1) * 6 + 1));
    ww(cs, 0x09, (uint16_t)(rw(cs, 0x09) + 8));
    return 0;
}

/* 0FED: found and set up (0F70), the timer and keyboard interrupts taken (0FA1): AX 1, or 0
 * without the chip */
static int init(Game *g, const MachineServices *mc, uint16_t *ax)
{
    uint8_t *cs = drv(g);
    if (!detect(g, mc)) {
        *ax = 0;
        return 0;
    }
    ww(cs, 0x32, 0xFFFF);
    ww(cs, 0x36, 0xFFFF);
    ww(cs, 0x34, 0x48D3);
    ww(cs, 0x28, driver_segment(g));
    ww(cs, 0x26, 0x01C8);
    if (calibrate(g, mc) < 0)
        return -1;
    opl(g, mc, 0x01, 0x20);
    opl(g, mc, 0x08, 0x00);
    reset(g, mc);
    uint32_t old8 = vector_get(g, 8);
    ww(cs, 0x0E, (uint16_t)old8);
    ww(cs, 0x10, (uint16_t)(old8 >> 16));
    vector_set(g, 8, ISR_TIMER, driver_segment(g));
    uint32_t old9 = vector_get(g, 9);
    ww(cs, 0x12, (uint16_t)old9);
    ww(cs, 0x14, (uint16_t)(old9 >> 16));
    vector_set(g, 9, ISR_KEYBOARD, driver_segment(g));
    *ax = 1;
    return 0;
}

/* orig 10BB:0000 (0D28)   the driver's functions by BX: 0 version, 1 the status byte at
 * DX:AX (the old address back in DX:AX), 2 instruments (CX at DX:AX), 3 the system clock's
 * divisor, 4 the driver clock's, 5 transpose, 6 play the song at DX:AX, 7 stop, 8 reset,
 * 9 pause, 10 go on, 11 the user's trap; FFFFh set up, FFFEh shut down, FFFDh the port
 * base. AX the result (FFFFh for no such function, FFF8h while busy); the carry only from a
 * pause or a go-on in the wrong state. */
int fmdrv_call(Game *g, const MachineServices *mc, CpuRegs *r)
{
    uint8_t *cs = drv(g);
    r->flags &= (uint16_t)~FLAG_CF;
    if (cs[0x1C7]) {
        r->ax = 0xFFF8;
        return 0;
    }
    cs[0x1C7] = 1;
    uint16_t ax = 0xFFFF;
    switch (r->bx) {
    case 0:
        ax = rw(cs, 0x0C);
        break;
    case 1: {
        uint16_t old_off = rw(cs, 0x26), old_seg = rw(cs, 0x28);
        ww(cs, 0x26, r->ax);
        ww(cs, 0x28, r->dx);
        r->dx = old_seg;
        set_status(g, 0);
        ax = old_off;
        break;
    }
    case 2:
        cs[0x1C3] = (uint8_t)r->cx;
        ww(cs, 0x18, r->dx);
        ww(cs, 0x16, r->ax);
        melodic(g, mc);
        voices_init(g, mc);
        ax = 0;
        break;
    case 3:
        ww(cs, 0x32, r->ax);
        ax = r->ax;
        break;
    case 4:
        ww(cs, 0x34, r->ax);
        set_timer(g, mc, r->ax);
        ax = 0;
        break;
    case 5:
        ww(cs, 0x42, r->ax);
        ax = 0;
        break;
    case 6:
        ax = play(g, mc, r->ax, r->dx);
        break;
    case 7:
        ax = 0xFFFD;
        if (cs[0x1C4]) {
            stop(g, mc);
            ax = 0;
        }
        break;
    case 8:
        reset(g, mc);
        ax = 0;
        break;
    case 9:
        ax = 0xFFFD;
        if (cs[0x1C4] == 1) {
            cs[0x1C4] = 2;
            silence(g, mc);
            ax = 0;
        } else if (cs[0x1C4] < 1)
            r->flags |= FLAG_CF; /* CMP [1C4],1 */
        break;
    case 10:
        ax = 0xFFFC;
        if (cs[0x1C4] == 2)
            ax = (cs[0x1C4] = 1, 0);
        else
            r->flags |= FLAG_CF; /* CMP [1C4],2 */
        break;
    case 11:
        ww(cs, 0x2C, r->dx);
        ww(cs, 0x2A, r->ax);
        ax = 0;
        break;
    case 0xFFFF:
        if (init(g, mc, &ax) < 0) {
            cs[0x1C7] = 0;
            return -1;
        }
        break;
    case 0xFFFE: /* 1000: stopped, the two interrupts given back */
        stop(g, mc);
        vector_set(g, 8, rw(cs, 0x0E), rw(cs, 0x10));
        vector_set(g, 9, rw(cs, 0x12), rw(cs, 0x14));
        ax = 0;
        break;
    case 0xFFFD:
        ww(cs, 0x09, r->ax);
        ax = 0;
        break;
    }
    r->ax = ax;
    cs[0x1C7] = 0;
    return 0;
}

/* orig 10BB:0C83   the timer interrupt while the driver has it: a song tick (the events due
 * when the count to the next one runs out), then the system clock: each time the timer's
 * divisor (36) has added up to the system clock's (32), the interrupt is passed on to the
 * handler found at set-up (the far pointer at 0E), which the caller runs: the number of
 * times is returned; with none the EOI is given here. */
int fmdrv_timer(Game *g, const MachineServices *mc)
{
    uint8_t *cs = drv(g);
    if (cs[0x1C4] == 1) {
        uint32_t delay = (uint32_t)rw(cs, 0x22) | (uint32_t)rw(cs, 0x24) << 16;
        delay -= 1;
        ww(cs, 0x22, (uint16_t)delay);
        ww(cs, 0x24, (uint16_t)(delay >> 16));
        if (delay == 0xFFFFFFFFu)
            tick(g, mc);
    }
    uint16_t cx = rw(cs, 0x32);
    uint32_t sum = (uint32_t)rw(cs, 0x38) + rw(cs, 0x36);
    uint16_t acc = (uint16_t)sum;
    int chain = 0;
    if (sum > 0xFFFF || acc >= cx) {
        do {
            acc = (uint16_t)(acc - cx);
            ++chain;
        } while (acc > cx);
    } else
        port_out(g, mc, 0x20, 0x20);
    ww(cs, 0x38, acc);
    return chain;
}

/* orig 10BB:0CF3   the keyboard interrupt while the driver has it: a scancode 83h with Ctrl
 * and Alt down would silence the song, but a code below 80h is never 83h; the interrupt then
 * goes on to the handler found at set-up (the far pointer at 12), which the caller runs */
int fmdrv_keyboard(Game *g, const MachineServices *mc)
{
    uint8_t al = port_in(g, mc, 0x60);
    if (!(al & 0x80) && al == 0x83) {
        CpuRegs r = {0};
        r.ax = 0x0200;
        if (machine_interrupt(g, mc, 0x16, &r) < 0)
            return -1;
        if ((r.ax & 0x0C) == 0x0C)
            silence(g, mc);
    }
    return 0;
}
