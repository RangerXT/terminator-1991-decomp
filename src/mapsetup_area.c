/* Full-area map setup; bitmap IO, BIOS mode and palette remain platform services. */
#include "term.h"

static int area_resource(Game *g, const MapResources *host, uint16_t op, uint16_t a, uint16_t b)
{
    return !host || !host->call || host->call(g, op, a, b, host->user) ? -1 : 0;
}

/* orig CF74..CFEB. Overlay decompression and mask rendering now run in C. */
int map_setup_area(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    if (area_resource(g, host, MS_VIDEO_MODE, 16, 0))
        return -1;
    DS_U16(ds, DS_DRAW_PAGE) = 0;
    if (area_resource(g, host, MS_DEFAULT_PALETTE, 0, 0))
        return -1;
    DS_U16(ds, 0x805C) = 14000;
    if (area_resource(g, host, MS_LOAD_IMAGE, 0xE1D9, 0))
        return -1;
    if (DS_U8(ds, 0xE1EE)) {
        uint16_t offset = DS_U16(ds, DS_FILE_BUFFER), segment = DS_U16(ds, DS_FILE_BUFFER_SEG);
        if (area_resource(g, host, MS_READ_FAR_FILE, 0xE1E2, offset))
            return -1;
        offset = DS_U16(ds, DS_FILE_BUFFER);
        segment = DS_U16(ds, DS_FILE_BUFFER_SEG);
        if (image_unpack_compressed(g, segment, offset, segment, (uint16_t)(offset + 3000), NULL))
            return -1;
        uint16_t code_seg = (uint16_t)(g->ds_seg - 0x5C27);
        DS_U8(far_ptr(g, code_seg, 0x1B41), 0) = 0;
        DS_U16(far_ptr(g, code_seg, 0x1B42), 0) = 80;
        offset = DS_U16(ds, DS_FILE_BUFFER);
        segment = DS_U16(ds, DS_FILE_BUFFER_SEG);
        screen_blit_mask(g, segment, (uint16_t)(offset + 3000), 0, 80, 350, 0, 80);
        DS_U16(far_ptr(g, code_seg, 0x1B42), 0) = 40;
    }
    DS_U16(ds, 0x805C) = 4000;
    map_area_viewport(g);
    if (area_resource(g, host, MS_PALETTE, 0, 0))
        return -1;
    return 0;
}

/* orig CFEC..D021. The modal loop begins after this initialization. */
int map_begin_area(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    DS_U8(ds, 0x7A18) = 255;
    if (map_setup_area(g, host))
        return -1;
    DS_U16(ds, 0x7D28) = 0x8000;
    screen_copy_rect(g, 0, 0x8000, 80, 350);
    DS_U16(ds, 0x724C) = 624;
    DS_U16(ds, 0x9A5A) = 334;
    DS_U8(ds, DS_FILL_COLOUR) = 15;
    if (map_draw_pointer(g))
        return -1;
    map_clear_key_buffer(ds);
    return 0;
}