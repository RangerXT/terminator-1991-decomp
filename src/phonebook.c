/* The phone book the P key opens during play (0000:C45C..C764).
 *
 * Mode 0Eh, a yellow page with the PHONEHDR.IMG header; one panel per shop in the loaded
 * window (the 11-byte records at DS:5CE4) and then the four regional records, two columns,
 * each with a picture from YELLOWPG.CIF and its map reference "Sector X Z  Location x z".
 * Up and Down scroll by one row (the CRTC display start moves 80 bytes per retrace, 86
 * times); any typed key closes the book and the street view is rebuilt.
 */
#include "term.h"

enum {
    PB_SCROLL_ROW = 0xDEE8,    /* u8: rows scrolled down */
    PB_SCROLL_LIMIT = 0xDEE9,  /* u8: last row index */
    PB_DISPLAY_START = 0xDF42, /* u16: CRTC display start while scrolling */
    PB_FILE_END = 0xE004,      /* u16: end of YELLOWPG.CIF in the file buffer; pictures unpack there */
    PB_SECTOR_X = 0xE006,      /* i16: map reference of the entry being drawn */
    PB_SECTOR_Z = 0xE008,
    PB_LOCAL_X = 0xE00A,
    PB_LOCAL_Z = 0xE00C,
    PB_COLOURS = 0xDF3B,    /* u8[8]: text and picture colour, by local z & 7 */
    PB_PICTURES = 0xDF68,   /* u16[24]: offsets of the CIF pictures in the file buffer */
    PB_PANEL_DEST = 0xDF44, /* u16[]: screen offset of each panel's picture */
    PB_PANEL_TEXT = 0xDF98, /* {column, row, E41C}[]: where each panel's reference goes */
    PB_TEXT = 0x7795,       /* the reference string is built here */
    PB_SLOT = 0x7A18,       /* u8: 2 * panel number */
    PB_TEXT_E41C = 0xE41C,
    PB_IMAGE_MODE = 0x805C,
    PB_HEADER_IMAGE = 0xDECE, /* "PHONEHDR.IMG" */
    PB_PICTURE_FILE = 0xDEDB, /* "YELLOWPG.CIF" */
    PB_TITLE = 0xDEEA,        /* "Use UP arrow and DOWN arrow to see other..." (when there are shops) */
    PB_SHOPS = 0x5CE4,
};

static int resource(Game *g, const PhoneBookServices *host, uint16_t op, uint16_t a)
{
    const MapResources *r = host->resources;
    return !r || !r->call || r->call(g, op, a, 0, r->user) ? -1 : 0;
}

/* orig 0000:FA4B   copy the NUL-terminated string at DS:src to dest (same segment); returns
 * dest advanced to the copied NUL */
uint16_t string_copy(uint8_t *ds, uint16_t dest, uint16_t src)
{
    for (;; dest++, src++) {
        DS_U8(ds, dest) = DS_U8(ds, src);
        if (!DS_U8(ds, src))
            return dest;
    }
}

/* orig 0000:F604   write value in base (2..36, digits 0-9 then A-Z) at dest, no NUL;
 * returns dest advanced past the digits. Bases below 2 write nothing. */
uint16_t number_format(uint8_t *ds, uint16_t dest, uint16_t value, uint8_t base)
{
    if (base < 2)
        return dest;
    uint8_t digits[16];
    unsigned n = 0;
    do {
        digits[n++] = (uint8_t)(value % base);
        value /= base;
    } while (value);
    while (n) {
        uint8_t c = (uint8_t)(digits[--n] + '0');
        DS_U8(ds, dest++) = c > '9' ? (uint8_t)(c + 7) : c;
    }
    return dest;
}

/* orig 0000:C72F   load YELLOWPG.CIF into the file buffer and index its 24 pictures */
static int load_panels(Game *g, const PhoneBookServices *host)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, DS_FILE_BUFFER_SEG), at = DS_U16(ds, DS_FILE_BUFFER);
    uint32_t loaded = file_load(g, host->images, PB_PICTURE_FILE, seg, at);
    if (loaded == UINT32_MAX)
        return -1;
    DS_U16(ds, PB_FILE_END) = (uint16_t)loaded;
    uint8_t *buffer = g->mem + ((uint32_t)seg << 4);
    for (unsigned i = 0; i < 24; ++i) {
        DS_U16(ds, (uint16_t)(PB_PICTURES + 2 * i)) = at;
        uint16_t size = 0x20;
        for (unsigned plane = 0; plane < 4; ++plane) {
            uint16_t field = (uint16_t)(at + 0x10 + 2 * plane);
            size = (uint16_t)(size + (buffer[field] | (buffer[(uint16_t)(field + 1)] << 8)));
        }
        at = (uint16_t)(at + size);
    }
    return 0;
}

/* orig 0000:C5DA   draw count records of 11 bytes from DS:record: kind 4 is skipped; each
 * other one gets the next panel (DS:7A18) with its picture and map reference */
static int draw_records(Game *g, uint16_t record, uint16_t count)
{
    uint8_t *ds = g->ds;
    uint16_t code_seg = (uint16_t)(g->ds_seg - 0x5C27);
    for (; count; --count, record = (uint16_t)(record + 11)) {
        int32_t x = (int32_t)(DS_U16(ds, record) | ((uint32_t)DS_U16(ds, (uint16_t)(record + 2)) << 16));
        int32_t z =
            (int32_t)(DS_U16(ds, (uint16_t)(record + 4)) | ((uint32_t)DS_U16(ds, (uint16_t)(record + 6)) << 16));
        if (x / 1024 > 32767 || x / 1024 < -32768 || z / 1024 > 32767 || z / 1024 < -32768)
            return -1; /* IDIV overflow: a CPU fault in the original */
        DS_U16(ds, PB_SECTOR_X) = (uint16_t)(x / 1024);
        DS_U16(ds, PB_LOCAL_X) = (uint16_t)(x % 1024);
        DS_U16(ds, PB_SECTOR_Z) = (uint16_t)(z / 1024);
        DS_U16(ds, PB_LOCAL_Z) = (uint16_t)(1024 - z % 1024);
        uint16_t kind = DS_U16(ds, (uint16_t)(record + 8));
        if (kind == 4)
            continue;
        kind--;
        if (kind > 3)
            kind--;
        uint16_t local_z = DS_U16(ds, PB_LOCAL_Z);
        uint8_t colour = DS_U8(ds, (uint16_t)(PB_COLOURS + (local_z & 7)));
        DS_U8(far_ptr(g, code_seg, 0x1B41), 0) = colour;
        uint16_t picture = DS_U16(ds, (uint16_t)(kind * 8 + (local_z & 6) + PB_PICTURES));

        uint16_t seg = DS_U16(ds, DS_FILE_BUFFER_SEG);
        uint16_t src_seg = DS_U16(ds, DS_UNPACK_SRC_SEG), dst_seg = DS_U16(ds, DS_UNPACK_DST_SEG);
        uint16_t planes = DS_U16(ds, 0x8544);
        DS_U16(ds, DS_UNPACK_SRC_SEG) = DS_U16(ds, DS_UNPACK_DST_SEG) = seg;
        DS_U16(ds, 0x8544) = 1;
        uint64_t unpacked = image_unpack_shared(g, picture, DS_U16(ds, PB_FILE_END), 0);
        DS_U16(ds, 0x8544) = planes;
        DS_U16(ds, DS_UNPACK_DST_SEG) = dst_seg;
        DS_U16(ds, DS_UNPACK_SRC_SEG) = src_seg;
        if (unpacked == UINT64_MAX)
            return -1;

        uint8_t slot = DS_U8(ds, PB_SLOT);
        uint16_t dest = DS_U16(ds, (uint16_t)(PB_PANEL_DEST + (int8_t)slot));
        DS_U16(far_ptr(g, code_seg, 0x1B42), 0) = 0x50;
        screen_blit_mask(g, seg, DS_U16(ds, PB_FILE_END), dest, 0x25, 0x48, colour, 0x50);
        DS_U16(far_ptr(g, code_seg, 0x1B42), 0) = 0x28;

        uint16_t place = (uint16_t)(PB_PANEL_TEXT + 3 * (int8_t)slot);
        DS_U16(ds, DS_TEXT_COLUMN) = DS_U16(ds, place);
        DS_U16(ds, DS_TEXT_ROW) = DS_U16(ds, (uint16_t)(place + 2));
        DS_U16(ds, PB_TEXT_E41C) = DS_U16(ds, (uint16_t)(place + 4));
        DS_U8(ds, DS_TEXT_COLOUR) = colour;
        uint16_t stride = DS_U16(ds, DS_SCREEN_STRIDE);
        DS_U16(ds, DS_SCREEN_STRIDE) = 0x50;
        uint16_t at = PB_TEXT; /* "Sector " X " " Z "  Location " x " " z */
        at = number_format(ds, string_copy(ds, at, 0xDF23), DS_U16(ds, PB_SECTOR_X), 10);
        at = number_format(ds, string_copy(ds, at, 0xDF2B), DS_U16(ds, PB_SECTOR_Z), 10);
        at = number_format(ds, string_copy(ds, at, 0xDF2D), DS_U16(ds, PB_LOCAL_X), 10);
        at = number_format(ds, string_copy(ds, at, 0xDF39), DS_U16(ds, PB_LOCAL_Z), 10);
        DS_U8(ds, at) = 0;
        int text = screen_text8(g, g->ds_seg, PB_TEXT);
        DS_U16(ds, DS_SCREEN_STRIDE) = stride;
        if (text < 0)
            return -1;
        DS_U8(ds, PB_SLOT) = (uint8_t)(slot + 2);
    }
    DS_U16(ds, PB_TEXT_E41C) = 0;
    return 0;
}

/* orig 0000:C588   the shops of the window, then the four regional records */
static int draw_entries(Game *g, const PhoneBookServices *host)
{
    uint8_t *ds = g->ds;
    if (load_panels(g, host) < 0)
        return -1;
    DS_U8(ds, PB_SLOT) = 0;
    if (draw_records(g, PB_SHOPS, DS_U16(ds, DS_SHOP_COUNT)) < 0)
        return -1;
    return draw_records(g, shop_fallback_records(ds), 4);
}

/* orig 0000:C557   scroll one row: the display start moves by step 86 times, a retrace each */
static int scroll_row(Game *g, const PhoneBookServices *host, uint16_t step)
{
    uint8_t *ds = g->ds;
    uint16_t start = DS_U16(ds, PB_DISPLAY_START);
    const MapPlatform *wait = host->platform;
    for (unsigned i = 0; i < 0x56; ++i) {
        DS_U16(ds, PB_DISPLAY_START) = (uint16_t)(DS_U16(ds, PB_DISPLAY_START) + step);
        start = (uint16_t)(start + step);
        if (resource(g, host, PB_SET_DISPLAY_START, start) < 0) /* orig 0000:C571 */
            return -1;
        if (!wait || !wait->wait || wait->wait(g, 1, wait->user) || wait->wait(g, 0, wait->user))
            return -1;
    }
    return 0;
}

/* orig 0000:C466..C556 (called with P held) */
int phone_book(Game *g, const PhoneBookServices *host)
{
    uint8_t *ds = g->ds;
    if (!host)
        return -1;
    /* 151B:021E (AL=3) does nothing outside a link game */
    if (resource(g, host, MS_VIDEO_MODE, 0x0E) < 0 || resource(g, host, MS_SELECT_PAGES, 0) < 0)
        return -1;
    uint8_t *p = g->planes;
    ega_seq_mask(p, 15); /* the whole page in colour 14 */
    ega_gc(p, 0, 0x0E);
    ega_gc(p, 1, 0x0F);
    for (uint32_t at = 0; at < 0x10000; at += 2) {
        ega_store(p, (uint16_t)at, 0x01);
        ega_store(p, (uint16_t)(at + 1), 0x0F);
    }
    ega_gc(p, 1, 0);
    DS_U16(ds, PB_IMAGE_MODE) = 0x2F8;
    if (image_load_screen(g, host->images, PB_HEADER_IMAGE) < 0)
        return -1;
    DS_U16(ds, PB_IMAGE_MODE) = 0xFA0;
    if (DS_U16(ds, DS_SHOP_COUNT)) {
        DS_U16(ds, DS_SCREEN_STRIDE) = 0x50;
        DS_U16(ds, DS_TEXT_ROW) = 2;
        DS_U16(ds, PB_TEXT_E41C) = 6;
        DS_U16(ds, DS_TEXT_COLUMN) = 0x0A;
        DS_U8(ds, DS_TEXT_COLOUR) = 0;
        if (screen_text8(g, g->ds_seg, PB_TITLE) < 0)
            return -1;
        DS_U16(ds, DS_SCREEN_STRIDE) = 0x28;
    }
    if (draw_entries(g, host) < 0)
        return -1;
    map_clear_key_buffer(ds);
    if (DS_U16(ds, DS_SHOP_COUNT)) {
        DS_U8(ds, PB_SCROLL_LIMIT) = (uint8_t)(((uint16_t)(DS_U16(ds, DS_SHOP_COUNT) + 3) >> 1) - 1);
        DS_U8(ds, PB_SCROLL_ROW) = 0;
        DS_U16(ds, PB_DISPLAY_START) = 0;
        for (;;) {
            if (DS_U8(ds, KEY_DOWN(SC_DOWN)) && DS_U8(ds, PB_SCROLL_ROW) != DS_U8(ds, PB_SCROLL_LIMIT)) {
                DS_U8(ds, PB_SCROLL_ROW)++;
                if (scroll_row(g, host, 0x50) < 0)
                    return -1;
            }
            if (DS_U8(ds, KEY_DOWN(SC_UP)) && DS_U8(ds, PB_SCROLL_ROW)) {
                DS_U8(ds, PB_SCROLL_ROW)--;
                if (scroll_row(g, host, 0xFFB0) < 0)
                    return -1;
            }
            /* the keyboard interrupt fills the buffer meanwhile: the host's input arrives here */
            if (!host->keys || !host->keys->poll || host->keys->poll(g, host->keys->user))
                return -1;
            if (DS_U8(ds, DS_KEYBUF_COUNT)) /* the original tests the low byte only */
                break;
        }
    }
    if (keyboard_read(g, host->keys) == UINT32_MAX)
        return -1;
    if (resource(g, host, MS_VIDEO_MODE, 0x0D) < 0)
        return -1;
    DS_U8(ds, DS_FACILITY_SCREEN) = 0;
    if (camera_reset(g, host->resources, host->images) < 0)
        return -1;
    DS_U16(ds, DS_VISIBLE_CELL) = 0xFFFF;
    return 0;
}
