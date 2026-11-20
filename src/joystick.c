#include "term.h"

static void joystick_axis(uint8_t *ds, uint16_t calibration, uint16_t sample, uint16_t negative_key,
                          uint16_t positive_key)
{
    uint16_t centre = DS_U16(ds, calibration + 2);
    uint16_t distance, span, key;
    if (sample < centre) {
        distance = centre - sample;
        span = centre - DS_U16(ds, calibration);
        key = negative_key;
    } else {
        distance = sample - centre;
        span = DS_U16(ds, calibration + 4) - centre;
        key = positive_key;
    }
    uint16_t half = span >> 1;
    if (distance < half)
        return;
    DS_U8(ds, key) = 255;
    if (distance >= span - (half >> 2))
        DS_U8(ds, KEY_DOWN(SC_RSHIFT)) = 255;
}

void joystick_apply(uint8_t *ds, uint16_t horizontal, uint16_t vertical, uint8_t port)
{
    DS_U8(ds, KEY_DOWN(SC_RIGHT)) = DS_U8(ds, KEY_DOWN(SC_LEFT)) = 0;
    DS_U8(ds, KEY_DOWN(SC_UP)) = DS_U8(ds, KEY_DOWN(SC_DOWN)) = 0;
    DS_U8(ds, KEY_DOWN(SC_RSHIFT)) = 0;
    DS_U8(ds, KEY_DOWN(SC_ENTER)) = port & 0x10 ? 0 : 255;
    DS_U8(ds, KEY_DOWN(SC_SPACE)) = port & 0x20 ? 0 : 255;
    DS_U16(ds, 0x5A5E) = horizontal;
    DS_U16(ds, 0x5A60) = vertical;
    joystick_axis(ds, 0x5A52, horizontal, 0x5C24, 0x5C26);
    joystick_axis(ds, 0x5A58, vertical, 0x5C21, 0x5C29);
}

/* orig 0000:3A33 (the game part; the port timing is the host's): the counts, and the buttons
 * set Enter (button 1, bit 4 clear) and Space (button 2, bit 5 clear) in the key table */
static int calibration_read(Game *g, const JoystickCalibration *host, uint16_t *h, uint16_t *v)
{
    uint8_t port;
    if (!host->read || host->read(h, v, &port, host->user))
        return -1;
    if (!(port & 0x10))
        DS_U8(g->ds, KEY_DOWN(SC_ENTER)) = 0xFF;
    if (!(port & 0x20))
        DS_U8(g->ds, KEY_DOWN(SC_SPACE)) = 0xFF;
    return 0;
}

/* one corner: the box, a button press (the reading kept), its release, the box away, a pause */
static int calibration_corner(Game *g, const JoystickCalibration *host, uint16_t text, uint16_t height,
                              uint16_t h_at, uint16_t v_at)
{
    uint8_t *ds = g->ds;
    int shown = DS_U8(ds, DS_FACILITY_SCREEN) ? textbox_vga_draw(g, host->screen, text, 5, 5, 0x1E, height, host->text)
                                              : textbox_draw(g, text, 5, 5, 0x1E, height, host->text);
    if (shown < 0)
        return -1;
    uint16_t h, v, h0, v0;
    do
        if (calibration_read(g, host, &h, &v) < 0)
            return -1;
    while (!DS_U8(ds, KEY_DOWN(SC_ENTER)));
    h0 = h;
    v0 = v;
    do {
        DS_U8(ds, KEY_DOWN(SC_ENTER)) = 0;
        if (calibration_read(g, host, &h, &v) < 0)
            return -1;
    } while (DS_U8(ds, KEY_DOWN(SC_ENTER)));
    DS_U16(ds, v_at) = v0;
    DS_U16(ds, h_at) = h0;
    if (DS_U8(ds, DS_FACILITY_SCREEN)) {
        if (!host->screen)
            return -1;
        scene_vga_overlay_restore(g, host->screen);
    } else if (scene_overlay_restore(g) < 0)
        return -1;
    const MenuPlatform *timing = host->timing;
    return !timing || !timing->call || timing->call(g, MM_WAIT, 0x1E, 0, timing->user) ? -1 : 0;
}

/* the larger half of an axis, doubled, over 160: quotient and remainder */
static void calibration_scale(uint8_t *ds, uint16_t low, uint16_t mid, uint16_t high, uint16_t out)
{
    int16_t a = (int16_t)(DS_U16(ds, high) - DS_U16(ds, mid)), b = (int16_t)(DS_U16(ds, mid) - DS_U16(ds, low));
    if (b >= a)
        a = b;
    int32_t doubled = (int16_t)(uint16_t)(a * 2);
    DS_U16(ds, out) = (uint16_t)(doubled / 0xA0);
    DS_U16(ds, (uint16_t)(out + 2)) = (uint16_t)(doubled % 0xA0);
}

/* orig 0000:38F6   the joystick at the top left, the centre and the bottom right
 * (DS:5A52 / 5A54 / 5A56 across, 5A58 / 5A5A / 5A5C down), then the scales (5A62, 5A66) */
int joystick_calibrate(Game *g, const JoystickCalibration *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    DS_U8(ds, KEY_DOWN(SC_ENTER)) = 0;
    DS_U8(ds, 0x5A4E) = 1; /* the boxes do not wait */
    if (calibration_corner(g, host, 0x0742, 5, 0x5A52, 0x5A58) < 0
        || calibration_corner(g, host, 0x07C5, 4, 0x5A54, 0x5A5A) < 0
        || calibration_corner(g, host, 0x0783, 5, 0x5A56, 0x5A5C) < 0)
        return -1;
    DS_U8(ds, 0x5A4E) = 0;
    calibration_scale(ds, 0x5A52, 0x5A54, 0x5A56, 0x5A62);
    calibration_scale(ds, 0x5A58, 0x5A5A, 0x5A5C, 0x5A66);
    return 0;
}
