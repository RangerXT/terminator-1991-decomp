/* Original 17E6 and 0C7D: present the completed page on vertical retrace; 0C6B: select the
 * pages. */
#include "term.h"

static uint16_t next_page(uint16_t value)
{
    ++value;
    return (uint8_t)value < 3 ? value : value & 0xff00;
}

/* orig 0000:0C7D   show DS:122A (the BIOS page) and draw into DS:122C */
static int show_pages(Game *g, const MapResources *host)
{
    uint8_t *ds = g->ds;
    uint16_t front = DS_U16(ds, DS_PAGE_SHOWN), back = DS_U16(ds, DS_PAGE_DRAWN);
    uint8_t single_page = DS_U8(ds, 0x1534) != 0;
    if (host->call(g, MS_VIDEO_PAGE, single_page ? 0 : (uint8_t)front, 0, host->user))
        return -1;
    if (single_page)
        DS_U16(ds, DS_DRAW_PAGE) = 0;
    else {
        DS_U16(ds, 0x1236) = DS_U16(ds, 0x123C + 2 * front);
        uint16_t table = DS_U16(ds, DS_SCREEN_STRIDE) == 80 ? 0x1244 : 0x123C;
        DS_U16(ds, DS_DRAW_PAGE) = DS_U16(ds, table + 2 * back);
    }
    return 0;
}

int scene_present(Game *g, const MapResources *host)
{
    if (!host || !host->call)
        return -1;
    if (host->call(g, 0x0D8D, 0, 0, host->user))
        return -1;
    uint8_t *ds = g->ds;
    DS_U16(ds, DS_PAGE_SHOWN) = next_page(DS_U16(ds, DS_PAGE_SHOWN));
    DS_U16(ds, DS_PAGE_DRAWN) = next_page(DS_U16(ds, DS_PAGE_DRAWN));
    if (show_pages(g, host) < 0)
        return -1;
    return host->call(g, 0x0DAA, 0, 0, host->user) ? -1 : 0;
}

/* orig 0000:0C6B   AL = the page to show (a byte store), AH = the page to draw; nothing on a
 * facility screen. What hosts can run for MS_SELECT_PAGES. */
int select_pages(Game *g, const MapResources *host, uint16_t pages)
{
    uint8_t *ds = g->ds;
    if (DS_U8(ds, DS_FACILITY_SCREEN))
        return 0;
    if (!host || !host->call)
        return -1;
    DS_U8(ds, DS_PAGE_SHOWN) = (uint8_t)pages;
    DS_U16(ds, DS_PAGE_DRAWN) = (uint16_t)(pages >> 8);
    return show_pages(g, host);
}
