/* Indexed VGA text, lines and modal windows; original 11BC:29A9..2DBA. */
#include "term.h"

uint16_t screen_text8_vga(Game *g, uint8_t *screen, uint16_t text_seg, uint16_t text)
{
    uint8_t *ds = g->ds;
    uint16_t dest;
    if (DS_U8(ds, 0xADE4))
        dest = (uint16_t)(320 * DS_U16(ds, DS_TEXT_ROW) + DS_U16(ds, DS_TEXT_COLUMN));
    else
        dest = (uint16_t)(2560 * DS_U16(ds, DS_TEXT_ROW) + 8 * DS_U16(ds, DS_TEXT_COLUMN)
                          + DS_U16(ds, 0xAF28 + 2 * DS_U8(ds, 0xE41C)));
    uint16_t start = dest, code = (uint16_t)(g->ds_seg - 0x5C27 + 0x11BC);
    uint16_t font_seg = DS_U16(far_ptr(g, code, 0x2A63), 0);
    uint8_t colour = DS_U8(ds, DS_TEXT_COLOUR), ch;
    while ((ch = *far_ptr(g, text_seg, text++)) != 0) {
        uint16_t glyph = ch * 8;
        for (unsigned row = 0; row < 8; ++row) {
            uint8_t bits = *far_ptr(g, font_seg, glyph++);
            for (unsigned col = 0; col < 8; ++col)
                if (bits & (128u >> col))
                    screen[(uint16_t)(dest + row * 320 + col)] = colour;
        }
        dest += 8;
    }
    return start;
}

void screen_vga_line_to(uint8_t *ds, uint8_t *screen, uint16_t x, uint16_t y)
{
    uint16_t oldx = DS_U16(ds, DS_PEN_X), oldy = DS_U16(ds, DS_PEN_Y);
    if (x == oldx && y == oldy)
        return;
    int16_t dx = (uint16_t)(x - oldx), dy = (uint16_t)(y - oldy);
    int xstep = dx < 0 ? 1 : -1, ystep = dy < 0 ? 320 : -320;
    uint16_t width = dx < 0 ? (uint16_t)-dx : (uint16_t)dx, height = dy < 0 ? (uint16_t)-dy : (uint16_t)dy;
    uint16_t at = (uint16_t)(y * 320 + x), major = width >= height ? width : height,
             minor = width >= height ? height : width, error = minor;
    unsigned count = major ? major : 65536;
    do {
        screen[at] = DS_U8(ds, DS_TEXT_COLOUR);
        at += width >= height ? xstep : ystep;
        error += minor;
        if (error >= major) {
            error -= major;
            at += width >= height ? ystep : xstep;
        }
    } while (--count);
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y;
}

void screen_vga_fill(uint8_t *ds, uint8_t *screen, uint16_t x, uint16_t y, uint16_t width, uint16_t rows)
{
    uint16_t at = (uint16_t)(y * 320 + x);
    unsigned height = rows ? rows : 65536;
    for (unsigned row = 0; row < height; ++row) {
        for (unsigned col = 0; col < width; ++col)
            screen[(uint16_t)(at + col)] = DS_U8(ds, DS_TEXT_COLOUR);
        at += 320;
    }
}

void scene_vga_overlay_restore(Game *g, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, 0xAE04))
        return;
    DS_U8(ds, 0xAE04)--;
    uint16_t source = DS_U16(ds, DS_FILE_BUFFER), seg = DS_U16(ds, DS_FILE_BUFFER_SEG), dest = DS_U16(ds, 0xAF22),
             width = DS_U16(ds, 0xAF24);
    unsigned rows = DS_U16(ds, 0xAF26);
    if (!rows)
        rows = 65536;
    for (unsigned row = 0; row < rows; ++row) {
        for (unsigned col = 0; col < width; ++col)
            screen[(uint16_t)(dest + col)] = *far_ptr(g, seg, source++);
        dest += 320;
    }
}

void scene_vga_overlay_save(Game *g, uint8_t *screen, uint16_t source, uint16_t width, uint16_t rows)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, 0xAE04))
        scene_vga_overlay_restore(g, screen);
    DS_U8(ds, 0xAE04)++;
    DS_U16(ds, 0xAF22) = source;
    DS_U16(ds, 0xAF24) = width;
    DS_U16(ds, 0xAF26) = rows;
    uint16_t dest = DS_U16(ds, DS_FILE_BUFFER), seg = DS_U16(ds, DS_FILE_BUFFER_SEG);
    unsigned height = rows ? rows : 65536;
    for (unsigned row = 0; row < height; ++row) {
        for (unsigned col = 0; col < width; ++col)
            *far_ptr(g, seg, dest++) = screen[(uint16_t)(source + col)];
        source += 320;
    }
}

void menu_vga_highlight(uint8_t *ds, uint8_t *screen, uint16_t dest)
{
    dest -= 0x155;
    uint16_t width = (uint16_t)(DS_U16(ds, 0x7850) * 8);
    unsigned count = width ? width : 65536;
    for (unsigned row = 0; row < 9; ++row)
        for (unsigned col = 0; col < count; ++col)
            screen[(uint16_t)(dest + row * 320 + col)] ^= 0xA5;
}

static void vga_border_layer(uint8_t *ds, uint8_t *screen)
{
    uint16_t x = DS_U16(ds, DS_BOX_X) + DS_U16(ds, 0xC4BC), y = DS_U16(ds, DS_BOX_Y) + DS_U16(ds, 0xC4BE);
    DS_U16(ds, 0xC4C0) = x;
    DS_U16(ds, 0xC4C2) = y;
    DS_U16(ds, DS_PEN_X) = x;
    DS_U16(ds, DS_PEN_Y) = y;
    uint16_t right = x + DS_U16(ds, 0xC4BA) - 1, bottom = y + DS_U16(ds, 0xC4B8) - 1;
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, 0xC4B0);
    screen_vga_line_to(ds, screen, right, y);
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, 0xC4B1);
    screen_vga_line_to(ds, screen, right, bottom);
    screen_vga_line_to(ds, screen, x, bottom);
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, 0xC4B0);
    screen_vga_line_to(ds, screen, x, y);
}

void textbox_vga_border(Game *g, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, 0xC4B0) = 8;
    DS_U16(ds, 0xC4BC) = DS_U16(ds, 0xC4BE) = 0;
    for (unsigned i = 0; i < 6; ++i) {
        if (i == 3)
            DS_U16(ds, 0xC4B0) = 0x0F0F;
        if (i) {
            DS_U16(ds, 0xC4BC)++;
            DS_U16(ds, 0xC4BE)++;
            DS_U16(ds, 0xC4BA) -= 2;
            DS_U16(ds, 0xC4B8) -= 2;
        }
        vga_border_layer(ds, screen);
    }
}

/* 11BC:2C58: scaled character-cell window, preserving returned text offset. */
uint16_t textbox_vga_base(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                          uint16_t height)
{
    uint8_t *ds = g->ds;
    x *= 8;
    y *= 8;
    width *= 8;
    height *= 8;
    DS_U16(ds, 0xC4B8) = height;
    DS_U16(ds, 0xC4BA) = width;
    scene_vga_overlay_save(g, screen, (uint16_t)(y * 320 + x), width, height);
    DS_U8(ds, DS_TEXT_COLOUR) = DS_U8(ds, 0x775C);
    screen_vga_fill(ds, screen, x, y, width, height);
    DS_U16(ds, DS_BOX_X) = x;
    DS_U16(ds, DS_BOX_Y) = y;
    DS_U8(ds, DS_TEXT_COLOUR) = *far_ptr(g, DS_U16(ds, 0xEA36), text++);
    textbox_vga_border(g, screen);
    return text;
}

/* 11BC:2BCC: unlike planar 5032, only 5A4E permits immediate return; modal
 * key waiting busy-polls input with no retrace wait. */
int textbox_vga_draw(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                     const TextPlatform *host)
{
    uint8_t *ds = g->ds;
    if (!DS_U8(ds, DS_FACILITY_SCREEN) || !screen || (!DS_U8(ds, 0x5A4E) && (!host || !host->poll)))
        return -1;
    text = textbox_vga_base(g, screen, text, x, y, width, height);
    uint16_t seg = DS_U16(ds, 0xEA36);
    for (;;) {
        DS_U16(ds, DS_TEXT_COLUMN) = *far_ptr(g, seg, text++) * 8 + DS_U16(ds, DS_BOX_X);
        DS_U16(ds, DS_TEXT_ROW) = *far_ptr(g, seg, text++) * 8 + DS_U16(ds, DS_BOX_Y);
        DS_U8(ds, 0xADE4) = 255;
        screen_text8_vga(g, screen, seg, text);
        DS_U8(ds, 0xADE4) = 0;
        uint16_t scan = text, left = 65535;
        while (left--)
            if (!*far_ptr(g, seg, scan++))
                break;
        if (*far_ptr(g, seg, scan) == 255)
            break;
        text = scan;
    }
    if (DS_U8(ds, 0x5A4E))
        return 0;
    while (DS_U8(ds, KEY_DOWN(SC_ESC)) || DS_U8(ds, KEY_DOWN(SC_ENTER)))
        if (host->poll(g, TX_RELEASE_BEFORE, 0, host->user))
            return -1;
    while (!DS_U8(ds, KEY_DOWN(SC_ESC)) && !DS_U8(ds, KEY_DOWN(SC_ENTER)))
        if (host->poll(g, TX_WAIT_KEY, 0, host->user))
            return -1;
    while (DS_U8(ds, KEY_DOWN(SC_ESC)) || DS_U8(ds, KEY_DOWN(SC_ENTER)))
        if (host->poll(g, TX_RELEASE_AFTER, 0, host->user))
            return -1;
    scene_vga_overlay_restore(g, screen);
    return 0;
}

/* Raw VGA image blitter used for MENU256, original 9132. Header is at
 * 91BC:91BE, but source pixels start at absolute offset 16, as in the source. */
void image_vga_blit_raw(Game *g, uint8_t *screen)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DS_FILE_BUFFER_SEG), header = DS_U16(ds, DS_FILE_BUFFER);
    uint16_t y = DS_U16(far_ptr(g, seg, (uint16_t)(header + 10)), 0),
             x = DS_U16(far_ptr(g, seg, (uint16_t)(header + 8)), 0);
    uint16_t rows = DS_U16(far_ptr(g, seg, (uint16_t)(header + 6)), 0),
             width = DS_U16(far_ptr(g, seg, (uint16_t)(header + 4)), 0);
    uint16_t source = 16, dest = (uint16_t)(y * 320 + x);
    unsigned height = rows ? rows : 65536;
    for (unsigned row = 0; row < height; ++row) {
        for (unsigned col = 0; col < width; ++col)
            screen[(uint16_t)(dest + col)] = *far_ptr(g, seg, source++);
        if (width & 1)
            ++source;
        dest += 320;
    }
}

/* EE9F: raw PASS256 image. DOS pixel bytes are read into Game's physical A000
 * transfer buffer, then published to the external native VGA framebuffer.
 * Caller has selected VGA mode 13h. Valid installed file required; read-only IO. */
int image_vga_protection_load(Game *g, const ImageIO *files, uint8_t *screen, uint8_t *palette)
{
    if (!files || !files->call || !screen || !palette)
        return -1;
    uint8_t *ds = g->ds;
    memset(ds + 0xE72E, 0, 768);
    memset(palette, 0, 768);
    uint32_t result = files->call(g, IMG_OPEN, 0, g->ds_seg, 0xE667, 0, files->user);
    if (result == UINT32_MAX || (result & 0x10000))
        return -1;
    uint16_t handle = (uint16_t)result;
    if (files->call(g, IMG_READ, handle, g->ds_seg, 0xE72E, 16, files->user) == UINT32_MAX)
        return -1;
    if (files->call(g, IMG_READ, handle, 0xA000, 0, 64000, files->user) == UINT32_MAX)
        return -1;
    memcpy(screen, g->mem + 0xA0000, 64000);
    if (files->call(g, IMG_READ, handle, g->ds_seg, 0xE72E, 768, files->user) == UINT32_MAX)
        return -1;
    if (files->call(g, IMG_CLOSE, handle, 0, 0, 0, files->user) == UINT32_MAX)
        return -1;
    for (unsigned i = 0; i < 768; ++i) {
        ds[0xE72E + i] >>= 2;
        palette[i] = ds[0xE72E + i];
    }
    return 0;
}
