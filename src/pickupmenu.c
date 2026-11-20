/* Dynamic pickup inventory menu and item transfer, original 531C..53F4. */
#include "term.h"

uint16_t pickup_menu_text(Game *g)
{
    uint8_t *ds = g->ds;
    uint16_t seg = DS_U16(ds, 0xEA36), dest = 2, source = 0x096D;
    uint8_t ch;
    do {
        ch = *far_ptr(g, seg, source++);
        *far_ptr(g, seg, dest++) = ch;
    } while (ch);
    uint16_t record = 0x0253, actor = DS_U16(ds, DS_PLAYER);
    uint8_t line = 2;
    for (unsigned i = 0; i < 20; ++i) {
        uint64_t result = pickup_query_state(ds, actor, record, 1, 0, 0);
        record = (uint16_t)result;
        if (!(result & ((uint64_t)1 << 48)))
            continue;
        *far_ptr(g, seg, dest++) = 4;
        *far_ptr(g, seg, dest++) = ++line;
        *far_ptr(g, seg, dest++) = ' ';
        source = DS_U16(ds, record + 8);
        do {
            ch = DS_U8(ds, source++);
            *far_ptr(g, seg, dest++) = ch;
        } while (ch);
        record += 13;
    }
    *far_ptr(g, seg, dest++) = 255;
    return dest;
}

/* Valid menu index required. The source adds 13 before the final LOOP falls
 * through, so a nonzero selection may take the physical record after the last
 * matched record without another proximity test. Preserve that ordering. */
int pickup_take_selected(Game *g, uint16_t index)
{
    uint8_t *ds = g->ds;
    uint16_t record = 0x0253, actor = DS_U16(ds, DS_PLAYER), left = index;
    unsigned attempts = 0;
    for (;;) {
        if (++attempts > 65536)
            return -1; /* Invalid menu selection would never return in DOS. */
        uint64_t result = pickup_query_state(ds, actor, record, 1, 0, 0);
        record = (uint16_t)result;
        if (!(result & ((uint64_t)1 << 48)))
            continue;
        if (!left)
            break;
        record += 13;
        if (!--left)
            break;
    }
    uint8_t item = DS_U8(ds, record + 10);
    uint16_t slot = 0x05B0;
    for (;;) {
        if (DS_U8(ds, slot + 2) == item) {
            DS_U8(ds, slot + 5)++;
            break;
        }
        if (!DS_U8(ds, slot + 2)) {
            DS_U16(ds, slot) = DS_U16(ds, record + 8);
            DS_U16(ds, slot + 2) = DS_U16(ds, record + 10);
            DS_U8(ds, slot + 4) = DS_U8(ds, record + 12);
            DS_U8(ds, slot + 5) = 1;
            break;
        }
        slot += 6;
    }
    DS_U16(ds, record + 10) = 0;
    return 0;
}

typedef struct PickupMenu {
    const MenuPlatform *input;
} PickupMenu;
static int pickup_menu_service(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user)
{
    PickupMenu *host = (PickupMenu *)user;
    if (op == MM_ACTION) {
        if (a < 0x5384 || a > 0x5397 || b >= 20)
            return -1;
        if (pickup_take_selected(g, 0x5397 - a) || scene_overlay_restore(g))
            return -1;
        return 1;
    }
    return host->input && host->input->call ? host->input->call(g, op, a, b, host->input->user) : -1;
}

/* Planar gameplay panel. Key timing/release and installed files remain services;
 * menu text, item transfer, background restore and complete HUD refresh are native. */
int pickup_inventory_panel(Game *g, const MenuPlatform *input, const ImageIO *files)
{
    if (DS_U8(g->ds, DS_FACILITY_SCREEN))
        return -1;
    pickup_menu_text(g);
    PickupMenu context = {input};
    MenuPlatform host = {pickup_menu_service, &context};
    if (menu_display(g, 2, 7, 0, 25, 25, 0x79BC, &host) < 0)
        return -1;
    hud_choose_panel(g->ds);
    return hud_init_normal(g, files);
}

/* Bind 884B directly to the native dynamic inventory panel. */
typedef struct PickupPanelServices {
    const MenuPlatform *input;
    const ImageIO *files;
} PickupPanelServices;
static uint32_t pickup_panel_service(Game *g, uint16_t op, uint16_t arg, void *user)
{
    PickupPanelServices *host = (PickupPanelServices *)user;
    if (op != 0x531C || arg)
        return UINT32_MAX;
    return pickup_inventory_panel(g, host->input, host->files) < 0 ? UINT32_MAX : 0;
}
int pickup_interaction_native(Game *g, const MenuPlatform *input, const ImageIO *files)
{
    PickupPanelServices context = {input, files};
    OpponentServices host = {pickup_panel_service, &context};
    return pickup_interaction(g, &host);
}
