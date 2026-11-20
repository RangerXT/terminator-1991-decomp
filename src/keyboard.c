/* Buffered ASCII input, 37AC/37D5. IRQ delivery remains platform-owned. */
#include "term.h"

uint32_t keyboard_read(Game *g, const KeyboardPlatform *host)
{
    uint8_t *ds = g->ds;
    while (!DS_U16(ds, DS_KEYBUF_COUNT))
        if (!host || !host->poll || host->poll(g, host->user))
            return UINT32_MAX;
    uint16_t at = DS_U16(ds, DS_KEYBUF_READ);
    uint8_t value = DS_U8(ds, at++);
    if (at == 0x5BD4)
        at = 0x5B70;
    DS_U16(ds, DS_KEYBUF_READ) = at;
    DS_U16(ds, DS_KEYBUF_COUNT)--;
    DS_U16(ds, 0x5B6A) = 0;
    return value;
}

uint8_t keyboard_read_available(Game *g)
{
    return DS_U16(g->ds, DS_KEYBUF_COUNT) ? (uint8_t)keyboard_read(g, NULL) : 0;
}

/* orig 0000:37E3   the keyboard interrupt, given the byte read from port 60h. The host keeps
 * the hardware part: reading the port, the port 61h acknowledge and the EOI (both skipped
 * while the code-segment byte 3B87 says to chain to the BIOS handler instead), and the
 * chaining itself. Returns 1 when Ctrl+Alt+Del are down, where the original jumps to
 * FFFF:0000 (a reboot), else 0. */
int keyboard_scancode(Game *g, uint8_t code)
{
    uint8_t *ds = g->ds, *bda = g->mem + 0x400;
    bda[0x1C] = bda[0x1A]; /* the BIOS buffer is kept empty */
    bda[0x1D] = bda[0x1B];
    if (DS_U16(ds, DS_KEY_BREAK_NEXT))
        code |= 0x80;
    else if (code == 0xF0) {
        DS_U16(ds, DS_KEY_BREAK_NEXT) = 0xFFFF;
        goto done;
    }
    DS_U16(ds, DS_KEY_BREAK_NEXT) = 0;
    uint8_t down;
    if (code & 0x80) {
        code &= 0x7F;
        down = 0;
    } else {
        if (!DS_U16(ds, DS_KEYS_UNBUFFERED)) {
            DS_U8(ds, DS_LAST_SCANCODE) = code;
            if (code == SC_F12)
                DS_U8(ds, DS_F12_PRESSED) = 0xFF;
            uint16_t table = DS_KEY_TABLE + 0x80; /* with Shift */
            if (DS_U8(ds, KEY_DOWN(SC_LSHIFT)))
                DS_U8(ds, KEY_DOWN(SC_RSHIFT)) = 0xFF;
            else if (!DS_U8(ds, KEY_DOWN(SC_RSHIFT)))
                table = DS_KEY_TABLE;
            uint8_t ch = DS_U8(ds, (uint16_t)(table + code));
            if (ch) {
                uint16_t at = DS_U16(ds, DS_KEYBUF_WRITE);
                if (at == 0x5BD4)
                    at = 0x5B70;
                DS_U8(ds, at++) = ch;
                if (at != DS_U16(ds, DS_KEYBUF_READ)) { /* a full buffer keeps its write place */
                    DS_U16(ds, DS_KEYBUF_WRITE) = at;
                    DS_U16(ds, DS_KEYBUF_COUNT)++;
                }
            }
        }
        /* the key marked down is DS:5BD8: while presses are not buffered that is still the
         * previous key's scancode */
        code = DS_U8(ds, DS_LAST_SCANCODE);
        down = 0xFF;
    }
    DS_U8(ds, KEY_DOWN(code)) = down;
    if (code == SC_LSHIFT)
        DS_U8(ds, KEY_DOWN(SC_RSHIFT)) = down;
done:
    return DS_U8(ds, KEY_DOWN(SC_CTRL)) && DS_U8(ds, KEY_DOWN(SC_ALT)) && DS_U8(ds, KEY_DOWN(SC_DEL));
}
