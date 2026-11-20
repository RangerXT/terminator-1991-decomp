/* The Terminator (Bethesda, 1991) - C rewrite of routines from TERM.EXE v1.00B.
 *
 * Every function here is a hand translation of one routine of the original (hand-written
 * assembly) program and is checked against it by tests/: the original routine is run in the
 * emulator, the C version on the same inputs, and the results must be identical.
 *
 * Conventions
 *   - Each function names the original address it was translated from ("orig 0000:1B7D").
 *   - The original keeps almost all state in one 64 KB data segment (file segment 5C27).
 *     Functions that touch that state take `ds`, a pointer to a copy of the segment, and use
 *     the DS_* accessors with the original offsets, so memory can be compared byte for byte.
 *   - Routines that also reach outside that segment (meshes live in other segments) take
 *     a `Game`, which holds the whole 1 MB real-mode address space.
 *   - 16-bit wrap-around is part of the behaviour and is kept (casts to int16_t / uint16_t).
 *   - Little-endian host assumed.
 */
#ifndef TERM_H
#define TERM_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API
#endif

#define DS_U8(ds, off)  (*(uint8_t *)((ds) + (uint16_t)(off)))
#define DS_I16(ds, off) (*(int16_t *)((ds) + (uint16_t)(off)))
#define DS_U16(ds, off) (*(uint16_t *)((ds) + (uint16_t)(off)))

#include "dsvars.h"

/* The machine as the far-reaching routines see it. `ds` must point into `mem`. */
typedef struct Game {
    uint8_t *mem;    /* real-mode memory, 1 MB (addresses wrap at 1 MB) */
    uint8_t *ds;     /* the main data segment: mem + ds_seg * 16 */
    uint8_t *planes; /* EGA screen: four bit planes of 65536 bytes, plane 0 first */
    uint16_t ds_seg; /* run-time segment address of the data segment */
} Game;

static inline uint8_t *far_ptr(const Game *g, uint16_t seg, uint16_t off)
{
    return g->mem + ((((uint32_t)seg << 4) + off) & 0xFFFFF);
}

/* High word of a signed 16x16 multiply, as IMUL leaves it in DX. */
static inline int16_t mul_hi(int16_t a, int16_t b)
{
    return (int16_t)(((int32_t)a * (int32_t)b) >> 16);
}

/* What a 32/16 IDIV leaves in AX: the quotient, or - when it does not fit or the divisor is
 * zero, and the game's divide-error handler (0000:0407) skips the instruction - the
 * untouched low word of the dividend. */
static inline int16_t idiv_or_skip(int32_t dividend, int16_t divisor)
{
    if (divisor == 0)
        return (int16_t)(uint16_t)dividend;
    int32_t q = dividend / divisor;
    if (q > 32767 || q < -32768)
        return (int16_t)(uint16_t)dividend;
    return (int16_t)q;
}

/* The EGA screen as the C code sees it: four bit planes of 65536 bytes, plane 0 first,
 * followed by the card's registers and latches (EgaRegs, 16 bytes). So a screen buffer is
 * 4 * 65536 + 16 bytes.
 *
 * The registers have to be kept because the original leaves them set between routines and
 * some routines rely on what is there: line drawing never sets the plane mask, for one, so
 * a line drawn after the horizon picture (which ends with only plane 3 enabled) and before
 * any fill touches plane 3 alone. The drawing code below therefore does to this model
 * exactly what the original does to the card: the same register writes, the same reads
 * (which load the latches) and the same writes, in the same order. */
typedef struct EgaRegs {
    uint8_t seq_mask; /* sequencer register 2: planes that can be written */
    uint8_t gc[9];    /* graphics controller 0..8: set/reset, enable set/reset, colour
                           compare, rotate/function, read plane, mode, misc, don't care, bit mask */
    uint8_t gc_index; /* graphics controller register selected last */
    uint8_t latch[4]; /* what the last read of video memory found in each plane */
    uint8_t unused;
} EgaRegs;

#define EGA_PLANE_BYTES (4 * 65536)

static inline EgaRegs *ega_regs(uint8_t *planes)
{
    return (EgaRegs *)(planes + EGA_PLANE_BYTES);
}

/* OUT 3C4/3C5: plane mask */
static inline void ega_seq_mask(uint8_t *planes, uint8_t value)
{
    ega_regs(planes)->seq_mask = value;
}

/* OUT 3CE, AX: select a graphics controller register and write it */
static inline void ega_gc(uint8_t *planes, uint8_t index, uint8_t value)
{
    EgaRegs *r = ega_regs(planes);
    r->gc_index = index;
    if (index < 9)
        r->gc[index] = value;
}

/* OUT 3CE, AL: select only */
static inline void ega_gc_select(uint8_t *planes, uint8_t index)
{
    ega_regs(planes)->gc_index = index;
}

/* OUT 3CF, AL: write the selected register */
static inline void ega_gc_data(uint8_t *planes, uint8_t value)
{
    EgaRegs *r = ega_regs(planes);
    if (r->gc_index < 9)
        r->gc[r->gc_index] = value;
}

/* A read of video memory: loads the latches and returns what the CPU sees. */
static inline uint8_t ega_load(uint8_t *planes, uint16_t addr)
{
    EgaRegs *r = ega_regs(planes);
    for (int p = 0; p < 4; p++)
        r->latch[p] = planes[((size_t)p << 16) + addr];
    if (r->gc[5] & 0x08) { /* read mode 1: colour compare */
        uint8_t same = 0xFF;
        for (int p = 0; p < 4; p++)
            if (r->gc[7] >> p & 1)
                same &= (uint8_t)~(r->latch[p] ^ ((r->gc[2] >> p & 1) ? 0xFF : 0));
        return same;
    }
    return r->latch[r->gc[4] & 3];
}

/* A write to video memory, as the card performs it in write modes 0 to 3. */
static inline void ega_store(uint8_t *planes, uint16_t addr, uint8_t value)
{
    EgaRegs *r = ega_regs(planes);
    unsigned mode = r->gc[5] & 3;
    uint8_t bitmask = r->gc[8];
    unsigned func = (r->gc[3] >> 3) & 3, rot = r->gc[3] & 7;
    if ((mode == 0 || mode == 3) && rot)
        value = (uint8_t)((value >> rot) | (value << (8 - rot)));
    for (int p = 0; p < 4; p++) {
        if (!(r->seq_mask >> p & 1))
            continue;
        uint8_t *b = planes + ((size_t)p << 16) + addr;
        uint8_t lt = r->latch[p], src;
        if (mode == 1) {
            *b = lt;
            continue;
        }
        if (mode == 3) {
            uint8_t bm = value & bitmask;
            src = (r->gc[0] >> p & 1) ? 0xFF : 0;
            *b = (uint8_t)((src & bm) | (lt & ~bm));
            continue;
        }
        if (mode == 0)
            src = (r->gc[1] >> p & 1) ? ((r->gc[0] >> p & 1) ? 0xFF : 0) : value;
        else
            src = (value >> p & 1) ? 0xFF : 0;
        if (func == 1)
            src &= lt;
        else if (func == 2)
            src |= lt;
        else if (func == 3)
            src ^= lt;
        *b = (uint8_t)((src & bitmask) | (lt & ~bitmask));
    }
}

/* math3d.c */
API void rotate_xz(const uint8_t *ds, int16_t *x, int16_t *z, uint16_t angle);
API void rotate_xz_inverse(const uint8_t *ds, int16_t *x, int16_t *z, uint16_t angle);
API void rotate_bc(const uint8_t *ds, int16_t *b, int16_t *c, uint16_t angle);
API void rotate_ab(const uint8_t *ds, int16_t *a, int16_t *b, uint16_t angle);
API void build_dither_table(uint8_t *ds);
API void matrix_from_angles(uint8_t *ds, uint16_t ax, uint16_t bx, uint16_t cx);
API void matrix_apply(uint8_t *ds, int16_t *x, int16_t *y, int16_t *z);

/* facing.c */
API uint8_t face_is_hidden(int16_t ax, int16_t bx, int16_t cx, int16_t dx);

/* clip2d.c */
API void mesh_clip_window(uint8_t *ds, uint16_t mesh);

/* clipnear.c */
API void mesh_clip_near(uint8_t *ds, uint16_t mesh);

/* Face rasterization returns its fill status in the low word and DX in the high word.
 * The setup-only path returns the same registers without filling the face. */
uint32_t polygon_face_registers(uint8_t *ds, uint8_t *planes, uint16_t count_at, int fill);
uint16_t polygon_outline_dx(uint8_t *ds, uint8_t *planes, uint16_t dx);
API uint32_t draw_visible_faces_dx(uint8_t *ds, uint8_t *planes, uint16_t mesh, uint32_t dx);

/* drawobject.c */
API int pipeline_sanity_failed(const uint8_t *ds);
API int draw_object(uint8_t *ds, uint8_t *planes, uint16_t mesh, uint8_t ds_segment_low);

/* events.c */
typedef struct GameEvent {
    uint16_t kind, a, b;
} GameEvent;
/* EV_SOUND: a=request ID; b=source 80E9 playback flag for native driving events. */
enum {
    EV_SOUND = 1,
    EV_PLAYER_HIT = 2,
    EV_FIGURE_KILLED = 3,
    EV_OBJECT_BLOWN = 4,
    EV_BORDER = 5
};
void event_push(uint16_t kind, uint16_t a, uint16_t b);
API int game_events(GameEvent *out, int max);
API void game_set_clock(uint16_t cx, uint16_t dx);
uint16_t game_clock_cx(void);
uint16_t game_clock_dx(void);

/* blast.c */
API uint16_t random_word(uint8_t *ds);
API void random_refill(uint8_t *ds);
API void random_refill_from(uint8_t *ds, uint16_t dx, uint16_t cx);
API void debris_start(Game *g, uint16_t record, uint16_t mesh_number);
API void debris_update(Game *g);
API void explosion_damage(Game *g, uint16_t record);
API void blast_queue_step(Game *g);

/* drawlist.c */
API uint16_t record_mesh_number(uint8_t *ds, uint16_t flags, uint16_t id_at);
API void mesh_fetch(Game *g, uint16_t number);
API void mesh_prepare(Game *g, uint16_t mesh);
API void object_translate_only(uint8_t *ds, uint16_t mesh);
API int draw_flat_mesh(uint8_t *ds, uint8_t *planes, uint16_t mesh);
API int draw_object_list(Game *g, uint16_t first_record, uint16_t count);

/* hudquery.c: query-only A07B; UINT32_MAX rejects the weapon/damage mode. */
API uint16_t collision_grid_address(uint8_t *ds);
API uint8_t collision_line_blocker(Game *g);
API int hud_target_contains_sight(uint8_t *ds, uint16_t target);
API uint32_t hud_scan_target(Game *g);

/* hudscore.c */
API uint16_t score_update(uint8_t *ds);
API void hud_format_score(uint8_t *ds);

/* hudsweep.c: EV_SOUND reports the untranslated sound request. */
API void hud_sweep_clear(uint8_t *ds);
API void hud_draw_sweep(Game *g);

/* hudstatus.c */
API void hud_collect_status(uint8_t *ds);
API int hud_cycle_status(uint8_t *ds); /* original carry; current index must be 0..6 */
API void hud_draw_status(Game *g);

/* hudcompose.c: synchronous remaining services. LOAD_IMAGE takes filename in a;
 * The HUD-only target scan runs natively; the weapon/damage mode is separate.
 * Return UINT32_MAX when a service is unavailable. Sound uses EV_SOUND events. */
enum {
    HS_LOAD_IMAGE = 0x6962,
    HS_LOAD_FILE = 0xFACE
};
typedef uint32_t (*HudCall)(Game *g, uint16_t service, uint16_t a, void *user);
typedef struct HudServices {
    HudCall call;
    void *user;
} HudServices;
/* hudoptics.c: LOAD_FILE uses filename in a and the far buffer at DS:91C0. */
API int hud_load_optics(Game *g, const HudServices *host);
API int hud_init_optics(Game *g, const HudServices *host);
API int hud_draw_optics(Game *g, const HudServices *host);

API int hud_refresh_pages(Game *g, const HudServices *host);
API void hud_clear_target_info(Game *g);
API void hud_draw_target_info(Game *g);
API void hud_draw_target_frame(Game *g);
API int hud_draw_target(Game *g, const HudServices *host);
API int hud_draw_warnings(Game *g, const HudServices *host);
API int hud_draw_system(Game *g, const HudServices *host);

/* systemhud.c */
API void hud_zoom_key(uint8_t *ds);
API void hud_flash_bitmap(Game *g, uint16_t record);
API void hud_draw_system_frame(Game *g);

/* indicators.c */
API void hud_indicator_erase(Game *g, uint16_t history);
API uint16_t hud_bearing_x(uint8_t *ds);
API void hud_bearing_tick(Game *g, uint16_t x);
API void hud_draw_indicators(Game *g);

/* hud.c */
API void hud_clear_bytes(Game *g, uint16_t dest, uint16_t width);
API void hud_draw_speed(Game *g);
API void hud_draw_vehicle_counter(Game *g);
API void hud_compass_needle(Game *g, uint16_t history, uint16_t heading, uint8_t colour);
API void hud_draw_compass(Game *g);
API void hud_clear_number(Game *g, uint16_t dest, uint16_t digits);
API uint16_t heading_degrees(uint16_t heading);
API void hud_draw_counters(Game *g);
API void hud_format_number(uint8_t *ds, uint16_t value);
API void hud_draw_number(Game *g, uint16_t value, uint16_t dest);
API void hud_draw_text(Game *g, uint16_t text, uint16_t dest);
API void map_draw_grid_labels(Game *g, uint16_t column, uint16_t row);

/* travel.c: calls into untranslated code are explicit, synchronous host operations.
 * Return low 16 bits = CX after TR_SIMULATE, bit 16 = original carry for simulation,
 * interruption check and collision; UINT32_MAX = unavailable. Other results ignored.
 * Argument = requested ticks for TR_SIMULATE, player record for TR_COLLISION, zero
 * for other services. Host code may modify Game state. Hooks do not implement
 * the external routines. travel_run/map_select/setup return -1 for a missing service. */
enum {
    TR_WORLD_STEP = 0xB5F9,
    TR_SIMULATE = 0xB588,
    TR_LOAD_CELLS = 0x3B88,
    TR_CHECK_INTERRUPT = 0xC42F,
    TR_OTHER_INTERRUPT = 0xBBF1,
    TR_TERMINATOR_INTERRUPT = 0xC35F,
    TR_TERMINATOR_FOLLOWUP = 0xDC7B,
    TR_COLLISION = 0x1FCC,
    TR_ARRIVAL_FOLLOWUP = 0x057C
};
typedef uint32_t (*TravelCall)(Game *g, uint16_t service, uint16_t argument, void *user);
typedef struct TravelServices {
    TravelCall call;
    void *user;
} TravelServices;
API int travel_apply_destination(Game *g, const TravelServices *host);
API int travel_run(Game *g, const TravelServices *host);
/* Native simulation loop and opponent encounters; WORLD_STEP/LOAD_CELLS remain host. */
API int travel_run_native_opponents(Game *g, const TravelServices *host);
API uint32_t travel_simulate(Game *g, const TravelServices *host, uint16_t ticks);
API int travel_clear_arrival(Game *g, const TravelServices *host);
/* Modal map selection after setup. The wait callback supplies retrace timing and may
 * update input state. high=0 means wait for retrace end, high=1 wait for its start.
 * Return zero on a completed wait; nonzero means the platform wait is unavailable. */
typedef int (*MapWait)(Game *g, uint8_t high, void *user);
typedef struct MapPlatform {
    MapWait wait;
    void *user;
} MapPlatform;
API int map_select(Game *g, const MapPlatform *platform, uint8_t area);
/* Map setup's remaining resource/platform services, identified by original offset.
 * SELECT_PAGES uses a=AX; LOAD_IMAGE a=filename in DS; READ_FILE a=filename,b=buffer;
 * READ_FAR_FILE uses a=filename,b=offset; its segment is DS:91BE.
 * VIDEO_MODE uses a=BIOS mode; VIDEO_PAGE uses a=BIOS page. Retrace waits and
 * PALETTE/DEFAULT_PALETTE take no arguments.
 * Return zero on success, nonzero on unavailable/error. */
enum {
    MS_SELECT_PAGES = 0x0C6B,
    MS_LOAD_IMAGE = 0x6962,
    MS_READ_FILE = 0xFAAF,
    MS_PALETTE = 0x7AB6,
    MS_DEFAULT_PALETTE = 0x7AAF,
    MS_READ_FAR_FILE = 0xFACE,
    MS_VIDEO_MODE = 0xFF10,
    MS_VIDEO_PAGE = 0xFF05
};
typedef int (*MapResourceCall)(Game *g, uint16_t service, uint16_t a, uint16_t b, void *user);
typedef struct MapResources {
    MapResourceCall call;
    void *user;
} MapResources;
API int map_setup_local(Game *g, const MapResources *resources);
API int map_begin_local(Game *g, const MapResources *resources);
API int map_setup_area(Game *g, const MapResources *resources);
API int map_begin_area(Game *g, const MapResources *resources);
API void map_clear_key_buffer(uint8_t *ds);
/* imageload.c: only DOS file services remain external. op is AH (3D/3F/3E).
 * OPEN: handle=access mode, seg:off=filename, count=0. READ: handle and far buffer/count.
 * CLOSE: handle, other arguments zero. Host returns AX plus carry in bit 16;
 * UINT32_MAX means unavailable. Only successful, valid asset streams are supported.
 * The host writes READ bytes to the physical buffer, without 16-bit pointer wrapping. */
enum {
    IMG_OPEN = 0x3D,
    IMG_READ = 0x3F,
    IMG_CLOSE = 0x3E,
    IMG_ATTR = 0x43
};
typedef uint32_t (*ImageFileCall)(Game *g, uint16_t op, uint16_t handle, uint16_t seg, uint16_t off, uint16_t count,
                                  void *user);
typedef struct ImageIO {
    ImageFileCall call;
    void *user;
} ImageIO;
/* vehiclehud.c: shared decoder returns SI/DI/BX/AX, 16 bits each; UINT64_MAX unsupported. */
API uint64_t image_unpack_shared(Game *g, uint16_t source, uint16_t dest, uint8_t lzhuf);
API uint32_t screen_blit_five_planes(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest, uint16_t words,
                                     uint16_t rows, uint16_t stride);
API int vehicle_hud_load(Game *g, const ImageIO *io);
API int vehicle_hud_draw(Game *g);

API uint32_t file_load(Game *g, const ImageIO *io, uint16_t filename, uint16_t dest_seg, uint16_t dest);
API uint32_t image_hud_service(Game *g, uint16_t service, uint16_t filename, void *user);
API int image_map_service(Game *g, uint16_t service, uint16_t filename, uint16_t dest, void *user);
API int image_prepare(Game *g, const ImageIO *io, uint16_t filename, uint16_t header_segment);
API int image_next_plane(Game *g, const ImageIO *io);
API int image_draw_loaded(Game *g, const ImageIO *io);
API int image_load_screen(Game *g, const ImageIO *io, uint16_t filename);

/* planarblit.c: negative means unsupported plane count. */
API int64_t screen_blit_planar(Game *g, uint16_t source_seg, uint16_t source);
API int hud_restore_background(Game *g);

/* maskblit.c */
API uint32_t screen_blit_mask(Game *g, uint16_t source_segment, uint16_t source, uint16_t dest, uint16_t width,
                              uint16_t rows, uint8_t colour, uint16_t stride);

/* maparea.c */
API void area_line_to(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y);
API void area_line_clipped(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y);
API void map_area_viewport(Game *g);

/* position.c */
API void position_normalize(Game *g, uint16_t record);
API int position_relative_actor(uint8_t *ds);

/* mapscreen.c */
API void map_write_destination_position(uint8_t *ds);
API void map_draw_homing(Game *g);
API uint8_t map_requested_action(uint8_t *ds);
API void map_draw_grid(Game *g);
API void map_draw_markers(Game *g);
API int map_draw_local_scene(Game *g);
API void screen_copy_rect(Game *g, uint16_t src, uint16_t dst, uint16_t width, uint16_t rows);
API int screen_draw_mask16(Game *g, uint16_t x, uint16_t y, uint16_t rows, uint16_t mask);
API void map_restore_pointer(Game *g);
API int map_draw_pointer(Game *g);
API int map_pointer_step(Game *g);
API int map_local_destination(uint8_t *ds);
API void map_area_destination(uint8_t *ds);
API void map_destination_measure(uint8_t *ds);
API void map_clear_info(Game *g);
API void map_draw_info(Game *g, uint16_t text);

/* mappage.c */
API void set_view_window(uint8_t *ds, uint16_t which);
API int draw_map_view(Game *g, uint16_t height);
API int map_page_update(Game *g);

/* background.c */
API void draw_ground_fill(uint8_t *ds, uint8_t *planes);
API void draw_horizon(Game *g);
API int horizon_load(Game *g, const ImageIO *files);
API void draw_background(Game *g);

/* framelist.c */
API uint16_t angle_between(uint8_t *ds, int16_t ax, int16_t az, int16_t bx, int16_t bz);
API int build_frame_draw_list(Game *g);

/* cells.c */
API void collect_visible_objects(Game *g, uint16_t cell_id, uint16_t column, uint16_t row);
API void build_ground_list(Game *g);

/* sortlist.c */
API uint16_t sort_draw_list(Game *g);

/* order.c */
API int mesh_order_faces(uint8_t *ds, uint16_t mesh);

/* target.c */
API uint16_t approx_distance(int16_t x1, int16_t z1, int16_t x2, int16_t z2);
API uint8_t track_target(uint8_t *ds, uint8_t al);

/* drawfaces.c */
API void draw_visible_faces(uint8_t *ds, uint8_t *planes, uint16_t mesh);

/* line.c */
API void line_to(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y);
API void polygon_outline(uint8_t *ds, uint8_t *planes);

/* polyfill.c */
API uint16_t polygon_setup(uint8_t *ds, uint16_t count_at);
API int fill_polygon(uint8_t *ds, uint8_t *planes, uint16_t count_at);

/* project.c */
API void project_point(const uint8_t *ds, int16_t *x, int16_t *y, uint16_t depth);
API int project_vertices(uint8_t *ds);

/* visibility.c */
API void face_reverse_winding(uint8_t *ds, uint16_t face);
void face_edge_vectors(uint8_t *ds, uint16_t face, int16_t *x01, int16_t *y01, int16_t *x21, int16_t *y21);
API void mesh_reverse_all_faces(uint8_t *ds, uint16_t mesh);
API void mesh_face_visibility(uint8_t *ds, uint16_t mesh, uint8_t al_in);

/* object.c */
API int object_transform_vertices(uint8_t *ds, uint16_t mesh);

/* unpack.c */
API int unpack_block(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest_seg, uint16_t dest,
                     uint16_t packed_len, uint16_t type);
API int image_unpack_compressed(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest_seg, uint16_t dest,
                                uint16_t *ax_out);
API int bytekiller_unpack(const uint8_t *src, uint16_t packed_len, uint8_t *dst);
API uint16_t lzhuf_unpack(const uint8_t *src, uint8_t *dst);

/* weaponsight.c */
API void weapon_classify_source(uint8_t *ds);
API void weapon_draw_numbers(Game *g, uint16_t player);

API uint8_t weapon_target_rejected(uint8_t *ds, uint16_t entry);
API void weapon_select_target(uint8_t *ds, uint8_t cycle);
API void weapon_lock_colour(uint8_t *ds, uint16_t x, uint16_t y);
API void weapon_draw_autoaim(Game *g);

API void weapon_update_sight(uint8_t *ds);
API void weapon_draw_crosshair(Game *g, uint16_t x, uint16_t y);
API void weapon_charge_step(Game *g);

/* Post-firing suffix only, original 6B70. */
API void weapon_draw_sights(Game *g);

API uint16_t weapon_projectile_slot(uint8_t *ds);
API void weapon_projectile_create(uint8_t *ds, uint16_t x, uint16_t z, uint16_t target_x, uint16_t target_z,
                                  uint16_t heading, uint16_t mode);

API int weapon_images_load(Game *g, const ImageIO *io);

API uint32_t weapon_projectile_turn(uint16_t heading, uint16_t target);
API uint8_t weapon_projectile_outside(uint16_t x, uint16_t z);

API void weapon_visual_insert(uint8_t *ds, uint16_t x, uint16_t y, uint16_t z, uint16_t heading);
API void weapon_visual_step(uint8_t *ds);
API uint16_t weapon_visual_step_dx(uint8_t *ds, uint16_t incoming_dx);

/* AFD0 bookkeeping; return 1 requests external AD37(1) spawn. */
API int figure_remove(uint8_t *ds, uint16_t record);

API uint16_t figure_map_sample(Game *g, uint16_t x, uint16_t z);
API void figure_spawn_grid_block(Game *g);
API void figure_spawn_grid(Game *g);

API void figure_grid_to_world(uint8_t *ds, uint16_t address);
API uint8_t figure_select_position(uint8_t *ds, uint16_t random_start, uint16_t wanted);

API uint8_t figure_init_movement(uint8_t *ds, uint16_t figure, uint16_t record);
API void figure_select_frames(uint8_t *ds);
API void figure_spawn(Game *g, uint16_t requested, uint8_t civilian);
API void figure_remove_complete(Game *g, uint16_t record);

API uint16_t figure_feedback_draw(Game *g, uint16_t source_seg, uint16_t source);
API void figure_feedback(Game *g, uint16_t family);

API void explosion_damage_native_figures(Game *g, uint16_t record);
/* A07B damage path, 01DE serial mode returns -1 before mutation. Sound remains an event; player damage is native. */
API int weapon_scan_damage(Game *g);

/* Spawn DX output matters to the firing controller even in inactive guidance fields. */
API uint16_t figure_spawn_dx(Game *g, uint16_t requested, uint8_t civilian, uint16_t dx);

API void weapon_resolve_shot(Game *g, uint16_t kind, uint16_t cx, uint16_t dx);
API int weapon_fire(Game *g, uint16_t incoming_dx);
API int weapon_frame(Game *g, uint16_t incoming_dx);

/* blocking byte | CX<<16 | DX<<32 for projectile call-site state. */
API uint64_t collision_line_blocker_state(Game *g);
API int weapon_charge_projectile_step(Game *g, uint16_t incoming_cx, uint16_t incoming_dx);
/* No-host entry rejects serial mode and camera 1; the host variant supports its reset. */
API int weapon_guided_projectiles_step(Game *g);

/* Player damage and its native inventory/text dependencies. Border and sound are events. */
API void inventory_remove(uint8_t *ds, uint8_t item);
API void inventory_transfer(uint8_t *ds, uint16_t list, uint8_t item, int remove);
API void hud_message_clear(Game *g);
API void hud_message_hide(Game *g);
API void hud_message(Game *g, uint16_t text);
API uint32_t player_damage_region(uint8_t *ds, uint16_t actor, uint16_t region, uint16_t damage);
API void player_hit_native(Game *g, uint16_t damage);

API void explosion_damage_native(Game *g, uint16_t record);

API uint16_t collect_cell_extras(Game *g, uint16_t dest);
API void collision_stamp_setup(Game *g);
API uint16_t collision_stamp_object(Game *g, uint16_t source_seg, uint16_t source);
API void collision_map_build(Game *g);

/* Camera modes 1/2; host supplies BIOS/pages/palette and native image-service adapter. */
API void camera_clear_pages(Game *g);
API int camera_reset_full_view(Game *g, const MapResources *host);
API int weapon_guided_projectiles_step_host(Game *g, const MapResources *host);

API void weapon_inventory_rebuild(uint8_t *ds);
API void hud_weapon_icon(Game *g, uint16_t dest, uint16_t mask);
API void hud_weapon_selection(Game *g, uint16_t slot, uint8_t colour);
API int hud_weapon_slots(Game *g);

API uint32_t screen_blit_five_plane_bytes(Game *g, uint16_t source_seg, uint16_t source, uint16_t dest, uint16_t width,
                                          uint16_t rows, uint16_t stride);
API void hud_choose_panel(uint8_t *ds);
API void hud_field_marker(Game *g);
API int hud_armor_overlay(Game *g, const ImageIO *io);
API int hud_init_normal(Game *g, const ImageIO *io);
API int camera_reset(Game *g, const MapResources *platform, const ImageIO *images);

API uint8_t scene_contact_test(uint8_t *ds, uint16_t actor, int16_t x, int16_t z, int16_t tx, int16_t tz);
API void scene_contact_update(uint8_t *ds);
API void scene_flash(Game *g);
API void scene_timed_effect(Game *g);
API void hud_vehicle_remaining(Game *g);
API int scene_overlay_restore(Game *g);
API int scene_overlay_replay(Game *g);

API int scene_overlay_save(Game *g, uint16_t dest, uint16_t width, uint16_t rows);
API int screen_text8(Game *g, uint16_t text_seg, uint16_t text);
API void textbox_border_layer(Game *g);
API void textbox_border(Game *g);
API int textbox_draw_nonmodal(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height);
API int scene_warning(Game *g);

API int scene_draw_overlays(Game *g, const HudServices *host);
API int scene_draw_instruments(Game *g);

/* Textbox platform updates input/timing, without supplying rendering or game logic.
 * Release phases are input polls; WAIT_KEY represents five complete retraces.
 * Return zero on success. Failure after drawing leaves the partial UI state. */
enum {
    TX_RELEASE_BEFORE = 0,
    TX_WAIT_KEY = 1,
    TX_RELEASE_AFTER = 2
};
typedef int (*TextPoll)(Game *g, uint16_t phase, uint16_t ticks, void *user);
typedef struct TextPlatform {
    TextPoll poll;
    void *user;
} TextPlatform;
API int textbox_draw(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                     const TextPlatform *host);

API uint16_t inventory_remove_state(uint8_t *ds, uint8_t item, uint16_t si);
API int textbox_draw_nonmodal_state(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                                    uint16_t *si);
API int weapon_refresh_selection(Game *g, const HudServices *host);
API int weapon_deselect_slot(Game *g, uint16_t slot, const HudServices *host);
API int weapon_select_slot(Game *g, uint16_t actor, uint16_t slot, uint8_t al, const HudServices *host);
API int weapon_reload_slot(Game *g, uint16_t slot);
API int weapon_hotkeys(Game *g, uint16_t actor, const HudServices *host);
API void player_look_keys(uint8_t *ds);

API void player_companion_indicator(Game *g);
API void player_sample_warning(Game *g);
API void world_toggle_records(uint8_t *ds);

API void player_update_threat(uint8_t *ds);
API void figure_retry_deferred(Game *g);
API int debug_vector_toggle(Game *g, const TextPlatform *platform);
API int gameplay_prepare(Game *g, const TextPlatform *platform);

/* Poll supplies new buffered input while 37AC waits; no rendering/game outputs. */
typedef int (*KeyboardPoll)(Game *g, void *user);
typedef struct KeyboardPlatform {
    KeyboardPoll poll;
    void *user;
} KeyboardPlatform;
API uint32_t keyboard_read(Game *g, const KeyboardPlatform *host);
API uint8_t keyboard_read_available(Game *g);
API int keyboard_scancode(Game *g, uint8_t code);
API int player_check_map_edge(Game *g, const TextPlatform *platform);
API int vehicle_refuel_nearby(Game *g, const TextPlatform *ui, const KeyboardPlatform *keys);

API uint8_t weapon_target_candidate(const uint8_t *ds, uint16_t record);
API void weapon_collect_targets(uint8_t *ds);
API int camera_full_image(Game *g, const MapResources *host, const ImageIO *io);
API int camera_full_height(Game *g, const MapResources *host, const ImageIO *io);
API int camera_key_step(Game *g, const MapResources *host, const ImageIO *io);

API void blast_queue_step_native(Game *g);
API int gameplay_update_opening(Game *g, const TextPlatform *ui, const KeyboardPlatform *keys);
API void player_recover_pose(uint8_t *ds);
API void joystick_apply(uint8_t *ds, uint16_t horizontal, uint16_t vertical, uint8_t port);

API void world_clamp_actor(uint8_t *ds, uint16_t actor);
API void position_normalize_companion(uint8_t *ds);
API void world_follow_companion(uint8_t *ds);
API void world_wander_vehicle(Game *g, uint16_t random);
API void world_displace_vehicle(Game *g);
API void world_clock_step(Game *g);

API int position_relative_vehicle(Game *g);

API int collision_steer(Game *g);
API uint8_t vehicle_choose_destination(uint8_t *ds);
API void vehicle_follow_route(Game *g);
API void world_update_delay(uint8_t *ds);

API uint64_t opponent_find_item(Game *g, uint8_t item);
API void opponent_sound_for_item(uint8_t *ds, uint8_t item);
API uint16_t opponent_build_choices(Game *g);
API uint16_t opponent_select_choice(Game *g, uint16_t ax);
API void opponent_add_item(Game *g, uint16_t definition);
API void opponent_cycle_item(Game *g, uint16_t table);

/* BC68/BF1B/C397 on-foot target contract; vehicle targets reject atomically. */
API int opponent_fire_on_foot(Game *g, uint16_t x, uint16_t z, uint16_t sound, uint16_t threshold);
API int opponent_burst_on_foot(Game *g, uint8_t fast, uint16_t incoming_dx);

API uint64_t opponent_destination_query(Game *g);
API void opponent_pick_destination(Game *g);
API uint8_t opponent_has_openings(uint8_t *ds);
API void opponent_choose_follow_mode(uint8_t *ds);
API void opponent_follow_destination(uint8_t *ds);
API int opponent_check_travel_interrupt(Game *g);

/* opponentplace.c: native encounter positions and companion follow-up. */
API void opponent_place_ahead(Game *g);
API void opponent_place_flank(Game *g);
API void opponent_place_companion(Game *g);

/* companion.c: motion table modes 0..2; modal modes 3/4 are unavailable (-1). */
API int companion_choose_behavior(uint8_t *ds, uint16_t mode);
API void companion_move(Game *g);
API int companion_step(Game *g);
API void opponent_init_difficulty(uint8_t *ds);

/* AI call-site registers: angle AX|DX<<16; opening query AX|CF<<16. */
API uint32_t angle_between_state(uint8_t *ds, int16_t ax, int16_t az, int16_t bx, int16_t bz);
API uint32_t opponent_openings_state(uint8_t *ds);
API int opponent_controller_on_foot(Game *g);
API void opponent_fire_at_companion(Game *g);

/* B7B6 uses these external presentation/streaming boundaries only on its movie branch.
 * UINT32_MAX means unavailable; CUTSCENE gets filename DE34 (AX=40 BX=8 CX=0).
 * WAIT gets CX ticks; remaining service arguments are zero. */
enum {
    OS_CUTSCENE = 0xB210,
    OS_WAIT = 0x02C6,
    OS_LOAD_CELLS = 0x3B88,
    OS_CAMERA_RESET = 0x7A28
};
typedef uint32_t (*OpponentCall)(Game *g, uint16_t service, uint16_t arg, void *user);
typedef struct OpponentServices {
    OpponentCall call;
    void *user;
} OpponentServices;
API uint32_t opponent_fire_at_companion_state(Game *g, uint16_t ax, uint16_t dx);
API int opponent_controller_slow_on_foot(Game *g, const OpponentServices *host);

/* worldstep.c: B5F9 native controller for on-foot targets, including DB26.
 * Modal panel bodies remain services; this is not a complete serial/network loop.
 * The two panels are Sarah's item exchange: a host can serve them with
 * companion_exchange (src/gamemenus.c), take for 57E7 and give for 57D4. */
enum {
    OS_COMPANION_PANEL3 = 0x57E7,
    OS_COMPANION_PANEL4 = 0x57D4
};
API int companion_step_with_services(Game *g, const OpponentServices *host);
API int world_step_on_foot(Game *g, const OpponentServices *host);

/* Native hit feedback AX outputs, required by DB26's following direction lookup. */
API uint16_t player_hit_native_state(Game *g, uint16_t damage);
API int32_t opponent_fire_on_foot_state(Game *g, uint16_t x, uint16_t z, uint16_t sound, uint16_t threshold);
API int companion_ai_on_foot(Game *g);

/* D177 with native B588/B5F9; IO supplies cell loading only. */
API int travel_run_native_world(Game *g, const TravelServices *io, const OpponentServices *platform);

/* Player position/control helpers and complete 30A0 walking path. */
API void player_position_backup(uint8_t *ds);
API void player_position_restore(uint8_t *ds);
API void player_keep_inside(Game *g);
API void driving_reset(uint8_t *ds);
API uint32_t player_movement_gate(uint8_t *ds, uint16_t incoming_ax);
API void walking_speed_step(uint8_t *ds, uint16_t actor, uint8_t scan_keys);
API void driving_steer(uint8_t *ds, uint16_t actor);
API void driving_accelerate(uint8_t *ds, uint16_t actor);
API uint32_t driving_gear_key(uint8_t *ds);
API void walking_step(Game *g);

/* Driving/transmission/motion; only the 02B5 exit body remains a service. */
enum {
    OS_PLAYER_TRANSITION = 0x02B5
};
API void driving_brake(uint8_t *ds, uint16_t actor);
API void driving_smooth_speed(Game *g, uint16_t actor);
API void driving_displace(uint8_t *ds, uint16_t actor);
API void driving_transmission(Game *g, uint16_t actor);
API int driving_damage_exit(Game *g, uint16_t actor, const OpponentServices *host);
API int driving_step(Game *g, const OpponentServices *host);

/* Native CSF/CAF resources needed by vehicle exit. Valid installed files required. */
API int character_models_load(Game *g, const ImageIO *io, uint8_t kind);
API void character_animations_index(Game *g);
API int character_animations_append(Game *g, const ImageIO *io, uint16_t filename);
API int character_resources_variant(Game *g, const ImageIO *io);
API int character_resources_load(Game *g, const ImageIO *io);

/* 02B5 status API: native character/vehicle resources, HUD and control tails.
 * vehicle_exit_state below also returns BX for the mode=1 exit. */
enum {
    VS_AUDIO_FOOT = 0x8ABE,
    VS_AUDIO_VEHICLE = 0x8A9E
};
typedef struct VehicleServices {
    const MapResources *display;
    const ImageIO *images;
    const OpponentServices *audio;
} VehicleServices;
API int vehicle_transition(Game *g, uint16_t mode, const VehicleServices *host);

/* VGA cinematic primitives: source assets to native linear buffers, no BIOS/timing. */
API void cutscene_background(uint8_t *ds, const uint8_t *dfb, uint8_t *screen, uint8_t *palette);
API void cutscene_apply_frame(const uint8_t *frame, uint8_t *work, uint8_t *screen);

/* EGA cinematic plane primitives; original video/card state supplied in Game. */
API void cutscene_ega_background(Game *g, const uint8_t *dbi, uint8_t *work);
API void cutscene_ega_frame(Game *g, const uint8_t *frame, uint8_t *work, uint16_t stride);

/* Rating table codecs and 41-byte score/stat/name records; file writes not included. */
API void ratings_decode(uint8_t *data, uint16_t count);
API void ratings_encode(uint8_t *data);
API void ratings_stats_save(uint8_t *ds);
API void ratings_stats_restore(uint8_t *ds);
API void ratings_select(uint8_t *ds, uint16_t index);
API void ratings_insert(uint8_t *ds);
API void ratings_update_time(uint8_t *ds);
API void ratings_clear_stats(uint8_t *ds);

/* Sound cache/routing; stat writes DOS DTA at 77E5, play gets segment/request.
 * Platform calls return 0 when complete, nonzero when unavailable. WAIT must
 * advance/finish sample playback through AA83. Device playback and AX are external. */
enum {
    SS_STAT = 0xF6B3,
    SS_PLAY = 0x0818,
    SS_WAIT_IDLE = 0x0100
};
typedef struct SoundServices {
    const ImageIO *files;
    const MapResources *platform;
} SoundServices;
API int sound_group_load(Game *g, const SoundServices *host, uint16_t filenames, uint16_t count, uint16_t ids);
API int sound_group_select(Game *g, const SoundServices *host, uint8_t mode);
API int sound_request(Game *g, const SoundServices *host, uint16_t request);

API uint32_t sound_group_service(Game *g, uint16_t entry, uint16_t unused, void *sound_services);

/* Original BX outputs used by guarded walking and vehicle destruction. */
API uint16_t line_to_bx(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y);
API uint16_t hud_draw_number_bx(Game *g, uint16_t value, uint16_t dest);
API uint16_t hud_compass_needle_bx(Game *g, uint16_t history, uint16_t heading, uint8_t colour);
API uint16_t position_normalize_bx(Game *g, uint16_t record);
API uint16_t walking_step_bx(Game *g, uint16_t bx);
API uint32_t walking_step_registers(Game *g, uint16_t bx);
API int32_t hud_init_walking_state(Game *g, const ImageIO *io, uint16_t bx);
API int32_t vehicle_exit_state(Game *g, const VehicleServices *host);

/* BC68 complete target path; vehicle destruction composes native mode=1 exit. */
API int32_t opponent_fire_state(Game *g, uint16_t x, uint16_t z, uint16_t sound, uint16_t threshold,
                                const VehicleServices *host);

/* Generic controllers use VehicleServices when a target can be destroyed/exited. */
API int opponent_burst(Game *g, uint8_t fast, uint16_t incoming_dx, const VehicleServices *vehicle);
API int opponent_controller(Game *g, const VehicleServices *vehicle);
API int opponent_controller_slow(Game *g, const OpponentServices *host, const VehicleServices *vehicle);
API int companion_ai(Game *g, const VehicleServices *vehicle);
API int world_step(Game *g, const OpponentServices *host, const VehicleServices *vehicle);

API int travel_run_native_simulation(Game *g, const TravelServices *io, const OpponentServices *platform,
                                     const VehicleServices *vehicle);
API uint32_t travel_simulate_world(Game *g, const TravelServices *io, const OpponentServices *platform,
                                   const VehicleServices *vehicle, uint16_t ticks);

/* Planar generic menu: input/timing and option handler bodies are host calls.
 * MM_ACTION returns a MENU_* status, -1 unavailable; menu_run and menu_display return the
 * status of the handler that closed the menu (0 after Esc).
 * Other calls return 0 after advancing input/time, -1 unavailable. */
enum {
    MENU_CONTINUE = 0,     /* the handler returned into the menu, which goes on */
    MENU_CLOSED = 1,       /* the handler closed the menu (carry clear) */
    MENU_CLOSED_CARRY = 2, /* closed with the carry flag set */
};
enum {
    MM_WAIT = 0x02C6,
    MM_ACTION = 0x4B35,
    MM_RELEASE_BEFORE = 0x1000,
    MM_RELEASE_AFTER = 0x1001
};
typedef int (*MenuCall)(Game *g, uint16_t op, uint16_t a, uint16_t b, void *user);
typedef struct MenuPlatform {
    MenuCall call;
    void *user;
} MenuPlatform;
API int menu_highlight(Game *g, uint16_t dest);
API int menu_unhighlight(Game *g);
API int menu_prepare(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height, uint16_t actions,
                     const MenuPlatform *host);
API int menu_run(Game *g, const MenuPlatform *host);

API int menu_display(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height, uint16_t actions,
                     const MenuPlatform *host);

/* Basic menu actions return 1 after native close; music driver ops F494/F4A1. */
API int menu_basic_action(Game *g, uint16_t target, const MenuPlatform *host);

/* B31C..B365 EGA DCF sequence: native repeats/key skip and retrace count.
 * Background/setup/file/music bodies are separate. Host ops are 0D8D/0DAA. */
API int cutscene_ega_sequence(Game *g, const MapResources *platform);

/* Read-only F7AD AX=0 subset; ATTR receives filename like OPEN, returns CF/error. */
API uint32_t file_open_existing(Game *g, const ImageIO *io, uint16_t filename);
/* EGA B210 orchestration. Platform: FF10 mode,7AAF default palette,0BE8 palette
 * offset,0D8D/0DAA retrace boundaries. Caller owns valid movie/work buffers. */
API int cutscene_ega_play(Game *g, uint16_t filename, uint16_t width, uint16_t delay, uint16_t variant,
                          const ImageIO *files, const MapResources *platform);

/* VGA movie helpers 14B5:018A/01C2/0093: large source files, FE text masks,
 * normalized packet traversal. Sequence excludes final intro bitmap/7242 logic. */
API int movie_load_large(Game *g, const ImageIO *files, uint16_t filename, uint16_t seg, uint16_t offset);
API uint32_t cutscene_vga_overlay(const uint8_t *mask, uint8_t *screen, uint16_t source, uint16_t dest, uint16_t rows);
API int cutscene_vga_sequence(Game *g, uint8_t *screen, const MapResources *platform);

/* Native VGA framebuffer decoder/image/movie composition. The video-mode host
 * initializes the caller-owned DAC; returned pixels/palette are native outputs. */
API int unpack_block_linear(Game *g, uint16_t source_seg, uint16_t source, uint8_t *dest, uint16_t offset,
                            uint16_t packed_len, uint16_t type);
API int image_vga_load(Game *g, const ImageIO *files, uint16_t filename, uint8_t *screen, uint8_t *palette);
API int cutscene_vga_play(Game *g, uint16_t filename, uint16_t delay, uint16_t variant, uint8_t *screen,
                          uint8_t *palette, const ImageIO *files, const MapResources *platform);

/* B210 mode dispatcher and B7B6 composition; mode 13h host initializes DAC. */
typedef struct MovieServices {
    const ImageIO *files;
    const MapResources *platform;
    uint8_t *screen, *palette;
    const OpponentServices *other;
} MovieServices;
API int cutscene_play(Game *g, uint16_t filename, uint16_t width, uint16_t delay, uint16_t variant,
                      const MovieServices *host);
API uint32_t cutscene_opponent_service(Game *g, uint16_t op, uint16_t arg, void *movie_services);

/* Native indexed VGA modal window/menu drawing (11BC:29A9..2DBA). */
API uint16_t screen_text8_vga(Game *g, uint8_t *screen, uint16_t text_seg, uint16_t text);
API void screen_vga_line_to(uint8_t *ds, uint8_t *screen, uint16_t x, uint16_t y);
API void screen_vga_fill(uint8_t *ds, uint8_t *screen, uint16_t x, uint16_t y, uint16_t width, uint16_t rows);
API void scene_vga_overlay_restore(Game *g, uint8_t *screen);
API void scene_vga_overlay_save(Game *g, uint8_t *screen, uint16_t source, uint16_t width, uint16_t rows);
API void menu_vga_highlight(uint8_t *ds, uint8_t *screen, uint16_t dest);
API void textbox_vga_border(Game *g, uint8_t *screen);
API uint16_t textbox_vga_base(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                              uint16_t height);
API int menu_vga_prepare(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                         uint16_t height, uint16_t actions, const MenuPlatform *host);
API int menu_vga_run(Game *g, uint8_t *screen, const MenuPlatform *host);
API int menu_vga_display(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                         uint16_t height, uint16_t actions, const MenuPlatform *host);

API int menu_vga_basic_action(Game *g, uint8_t *screen, uint16_t target, const MenuPlatform *host);

/* VGA 5032/11BC:2BCC: TX_WAIT_KEY uses ticks=0 (input poll), 5A4E nonmodal. */
API int textbox_vga_draw(Game *g, uint8_t *screen, uint16_t text, uint16_t x, uint16_t y, uint16_t width,
                         uint16_t height, const TextPlatform *host);

/* Raw frontend image 9132 and native gameplay loss phase 089E. The latter
 * composes movies/models; wait/stream/camera/network remain explicit services. */
API void image_vga_blit_raw(Game *g, uint8_t *screen);
API void companion_promote_record(uint8_t *ds);
API int sound_stop_and_wait(Game *g, const SoundServices *host);
API int gameplay_check_losses(Game *g, const MovieServices *movie, const SoundServices *sound);

/* EE9F image loader only; retains the game's original security-chart challenge. */
API int image_vga_protection_load(Game *g, const ImageIO *files, uint8_t *screen, uint8_t *palette);

/* Nearby pickup/shop controllers. Inventory/purchase panels are host services. */
API uint64_t pickup_query_state(uint8_t *ds, uint16_t actor, uint16_t record, uint16_t count, uint16_t ax, uint16_t bp);
API void pickup_check_active(Game *g, uint16_t actor);
API int pickup_interaction(Game *g, const OpponentServices *panel);
API uint16_t shop_distance(uint8_t *ds, uint16_t actor, uint16_t record);
API uint64_t shop_try_record_state(uint8_t *ds, uint16_t actor, uint16_t record);
API uint16_t shop_fallback_records(uint8_t *ds);
API void shop_check_active(Game *g);
API int shop_interaction(Game *g, const OpponentServices *panel);

/* Native player collision and arrival push-out (cell streaming remains a host). */
API uint8_t player_collision_test(Game *g, uint16_t actor);
API int travel_clear_arrival_native(Game *g, const TravelServices *host);

/* Map removal and single-player vehicle interaction (400E..43C5). */
API void map_note_removed(uint8_t *ds, uint16_t record);
API int vehicle_park(Game *g, uint16_t actor);
API uint8_t vehicle_find_parked(Game *g);
API void vehicle_remove_parked(Game *g, uint16_t index);
API void vehicle_initial_fuel(uint8_t *ds);
API int vehicle_interaction(Game *g, const OpponentServices *transition);
API uint32_t vehicle_transition_service(Game *g, uint16_t op, uint16_t mode, void *host);
API int vehicle_interaction_native(Game *g, const VehicleServices *host);

/* 0255 control keys/parking/transitions; ordinary movement avoids palette reset. */
API int player_control_step(Game *g, const VehicleServices *vehicle, const TravelServices *stream);
enum {
    ORIGINAL_DX_UNKNOWN = 0x10000
};
API int player_control_step_dx(Game *g, const VehicleServices *vehicle, const TravelServices *stream, uint32_t *dx);
API int driving_step_dx(Game *g, const OpponentServices *host, uint32_t *dx);

/* Player hit AX | BX<<16; BX is consumed by 0255 before its parking call. */
API uint32_t player_hit_native_registers(Game *g, uint16_t damage, uint16_t incoming_bx);

/* Dynamic planar pickup menu and native item transfer (531C..53F4). */
API uint16_t pickup_menu_text(Game *g);
API int pickup_take_selected(Game *g, uint16_t index);
API int pickup_inventory_panel(Game *g, const MenuPlatform *input, const ImageIO *files);
API void shop_record_visit(uint8_t *ds);
API uint8_t shop_was_visited(const uint8_t *ds);
API uint8_t shop_item_hit(Game *g, uint16_t seg, uint16_t record, uint16_t x, uint16_t y);

API int pickup_interaction_native(Game *g, const MenuPlatform *input, const ImageIO *files);

/* Shop/inventory equipment refresh and its dynamic item-use menu. */
API void inventory_combine_components(uint8_t *ds);
API uint16_t inventory_equipment_menu(Game *g);
API void inventory_refresh_equipment(Game *g);

API void inventory_count_required(uint8_t *ds);

API int shop_pay_item(Game *g, uint16_t definition, const TextPlatform *input, uint8_t *screen);
API int shop_check_permit(Game *g, uint16_t definition, const TextPlatform *input, uint8_t *screen);
API int shop_check_capacity(Game *g, uint16_t *definition, uint16_t *counter, const TextPlatform *input,
                            uint8_t *screen);
API int shop_add_regular_item(Game *g, uint16_t definition, uint16_t counter);

API uint8_t inventory_weapon_menu_text(Game *g);
API uint16_t inventory_weapon_menu_choice(uint8_t *ds, uint16_t index);
API int inventory_choose_weapon(Game *g, const MenuPlatform *input, uint8_t *screen);

enum {
    SHOP_ADD_NEW = 0,
    SHOP_ADD_STACKED = 1,
    SHOP_ADD_UPGRADED = 2,
    SHOP_ADD_CANCELED = 3,
    SHOP_ADD_NO_WEAPON = 4
};
API int shop_add_item(Game *g, uint16_t definition, uint16_t counter, const MenuPlatform *menu,
                      const TextPlatform *input, uint8_t *screen);

/* VGA cursor preserves source save-under memory and AX=FF00 convention. */
API void screen_restore_mask16_vga(Game *g, uint8_t *screen);
API uint16_t screen_draw_mask16_vga(Game *g, uint8_t *screen, uint16_t x, uint16_t y, uint16_t rows, uint16_t mask);
API int map_draw_pointer_display(Game *g, uint8_t *screen);
API int map_pointer_step_display(Game *g, uint8_t *screen);

API int shop_alarm(Game *g, const ImageIO *files, const MenuPlatform *timing, const TextPlatform *input,
                   uint8_t *screen);
API int shop_check_theft(Game *g, const ImageIO *files, const MenuPlatform *timing, const TextPlatform *input,
                         uint8_t *screen);
API void shop_randomize_balances(uint8_t *ds);

/* Display-aware sampling/spawn for alarms that run inside indexed VGA shops. */
API uint16_t figure_map_sample_display(Game *g, uint16_t x, uint16_t z, uint8_t *screen);
API int figure_spawn_grid_display(Game *g, uint8_t *screen);
API int figure_spawn_display(Game *g, uint16_t requested, uint8_t civilian, uint8_t *screen);

API int scene_overlay_restore_all(Game *g, uint8_t *screen);
API void scene_overlay_reset(uint8_t *ds);
typedef struct ShopServices {
    const ImageIO *files;
    const MenuPlatform *menu;
    const TextPlatform *text;
    uint8_t *screen;
} ShopServices;
enum {
    SHOP_MOUSE_RELEASE = 0x1002,
    SHOP_ACTION_CLOSED = 1,
    SHOP_ACTION_EXIT = 2
};
API int shop_option_action(Game *g, uint16_t target, const ShopServices *host);
API int shop_confirm_item(Game *g, uint16_t x, uint16_t y, const ShopServices *host);

typedef struct ShopScreenServices {
    const ShopServices *actions;
    const MapResources *platform;
    const SoundServices *sound;
    const OpponentServices *extra;
    uint8_t *palette;
    const struct FacilityServices *facility; /* kinds 4..6: the bank, firing range, hospital */
} ShopScreenServices;
enum {
    SHOP_KEYS_RELEASE = 0x1003
};
API int shop_screen_exit(Game *g, const ShopScreenServices *host);
API int shop_screen(Game *g, uint16_t kind, uint16_t entry_sp, const ShopScreenServices *host);
API int shop_interaction_native(Game *g, const ShopScreenServices *host, uint16_t entry_sp);

typedef int (*JoystickRead)(uint16_t *horizontal, uint16_t *vertical, uint8_t *port, void *user);
typedef struct JoystickCalibration {
    JoystickRead read;          /* the counts and the button bits, as port 201h gives them */
    void *user;
    const TextPlatform *text;   /* the message boxes (they do not wait: DS:5A4E is set) */
    const MenuPlatform *timing; /* the 30-frame pauses (MM_WAIT) */
    uint8_t *screen;            /* the mode-13h screen when called from the VGA main menu */
} JoystickCalibration;
API int joystick_calibrate(Game *g, const JoystickCalibration *host);
typedef struct GameplayServices {
    const TextPlatform *text;
    const KeyboardPlatform *keys;
    const HudServices *hud;
    const MovieServices *movie;
    const SoundServices *sound;
    const VehicleServices *vehicle;
    const TravelServices *stream;
    const ShopScreenServices *shop;
    const MenuPlatform *menu;
    const OpponentServices *world;
    JoystickRead joystick;
    void *joystick_user;
} GameplayServices;
/* 0809..0897, ending before shot visuals and charge flight. */
API int gameplay_update_controls(Game *g, const GameplayServices *host, uint16_t shop_entry_sp);
API int gameplay_update_controls_dx(Game *g, const GameplayServices *host, uint16_t shop_entry_sp, uint32_t *dx);
/* 0897..089D; DX at 0897 is preserved if no shot visual advances. */
API int gameplay_update_projectiles(Game *g, uint16_t incoming_dx);

/* BX in the low word, DX in the high word. */
API uint32_t line_to_registers(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y);
API uint32_t line_to_wide_registers(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y);
API void line_to_wide(uint8_t *ds, uint8_t *planes, uint16_t x, uint16_t y);
API int intro_screen(Game *g, uint16_t entry_sp, const MapResources *resources, const ImageIO *images);
API void intro_set_buffer(uint8_t *ds);
API uint32_t hud_compass_needle_registers(Game *g, uint16_t history, uint16_t heading, uint8_t colour, uint16_t dx);
API uint16_t hud_draw_indicators_dx(Game *g, uint16_t dx);
API uint16_t scene_contact_update_dx(uint8_t *ds, uint16_t dx);
API uint16_t scene_timed_effect_dx(Game *g, uint16_t dx);
API int hud_draw_optics_dx(Game *g, const HudServices *host, uint16_t *dx);
/* DX in/out for guided firing; the unguided target scanner does not need its DX modelled. */
API int hud_draw_system_dx(Game *g, const HudServices *host, uint16_t *guided_dx);
API int scene_draw_overlays_dx(Game *g, const HudServices *host, uint16_t *guided_dx);
API int scene_post_render(Game *g, const HudServices *host, uint16_t dx);
/* 17E6: wait for retrace, advance both page indices, select the visible page,
 * then wait for retrace to end. Host implements 0D8D, VIDEO_PAGE and 0DAA. */
API int scene_present(Game *g, const MapResources *host);
API int select_pages(Game *g, const MapResources *host, uint16_t pages);
/* 06FF: full planar scene pass; the obscured view uses host retrace waits. */
API int draw_scene(Game *g, const MapResources *host);
API void sort_targets_by_depth(uint8_t *ds);
/* B3E4: apply an already decompressed EGA vertical-run packet. */
API void cutscene_ega_runs(Game *g, const uint8_t *work, uint16_t stride);
API void figure_feedback_step(Game *g);
API void draw_view_fill(Game *g);
API void draw_frame_background(Game *g);
API int player_pre_draw_collision(Game *g, const VehicleServices *host);

API uint8_t civilian_prepare_move(Game *g, uint16_t figure, uint16_t record);
API void civilians_move(Game *g);
API uint8_t armed_figure_fire(Game *g, uint16_t figure, uint16_t record);
API void armed_figures_move(Game *g);
API int scene_update_world(Game *g, const MapResources *display);
API int load_window_objects(Game *g, const ImageIO *files);
API int load_window_ground_and_cells(Game *g, const ImageIO *files);
/* 3B88: cache misses read installed sector, collision and character/vehicle assets. */
API int update_visible_cells(Game *g, const ImageIO *files);
API int scene_render_city(Game *g, const VehicleServices *host);

/* mapkey.c: the map screen the M key opens during play (0000:CA73..CB4A) */
typedef struct MapKeyServices {
    const MapResources *resources;     /* map setup, page selection (0C6B) and camera reset */
    const MapPlatform *platform;       /* retrace waits of the map's selection loop */
    const ImageIO *images;             /* map images and the city cells */
    const TextPlatform *text;          /* the two "cannot fast travel" messages */
    const TravelServices *travel;      /* the arrival follow-up (TR_ARRIVAL_FOLLOWUP, 0000:057C) */
    const OpponentServices *opponents; /* what the world simulation of a fast travel still needs */
    const VehicleServices *vehicle;
} MapKeyServices;
API void keyboard_flush(Game *g);
API int map_screen(Game *g, const MapKeyServices *host);

/* phonebook.c: the phone book the P key opens during play (0000:C466..C556) */
enum {
    PB_SET_DISPLAY_START = 0xC571
}; /* MapResources op: CRTC display start := a */
typedef struct PhoneBookServices {
    const MapResources *resources; /* video modes, page selection, display start, camera reset */
    const MapPlatform *platform;   /* retrace waits while scrolling */
    const ImageIO *images;         /* PHONEHDR.IMG, YELLOWPG.CIF and the camera reset's images */
    const KeyboardPlatform *keys;  /* input: polled once per pass of the scroll loop and while waiting */
} PhoneBookServices;
API uint16_t string_copy(uint8_t *ds, uint16_t dest, uint16_t src);
API uint16_t number_format(uint8_t *ds, uint16_t dest, uint16_t value, uint8_t base);
API int phone_book(Game *g, const PhoneBookServices *host);

/* fontscale.c: the scalable font (font.pck), 11BC:28F8 and 11BC:2714 */
API int font_load(Game *g, const ImageIO *io, uint16_t filename);
API void font_scale(Game *g, uint16_t src, uint16_t dst, uint16_t count, uint16_t si, uint16_t di);
API uint16_t font_text(Game *g, uint16_t x, uint16_t y, uint16_t text);

/* ratingsscreen.c: the ratings screen (0000:D300) and the name editor (0000:DF4A) */
typedef struct RatingsServices {
    const MapResources *resources; /* video modes, palettes (MS_DEFAULT_PALETTE, MS_PALETTE), page selection,
                                      camera reset */
    const ImageIO *images;         /* the screen images, font.pck, the 7x7 font, the ratings file */
    const KeyboardPlatform *keys;  /* typed keys (and Esc's release in the name editor) */
    uint8_t *screen;               /* the mode-13h screen on VGA installations */
    uint8_t *palette;              /* 768 bytes for the VGA image's palette */
} RatingsServices;
API int ratings_screen(Game *g, const RatingsServices *host);
typedef struct MainMenuServices {
    const MapResources *resources; /* video modes, pages, palettes, MN_DAC_REGISTER (a = register, b = green << 8 |
                                      blue, red 7 when b is 1C1Eh, else 0); by original address the joystick
                                      (GM_JOYSTICK_DETECT returns 1 when there is none, GM_JOYSTICK_CALIBRATE),
                                      loading a game (MN_LOAD_GAME), the ratings without `ratings` (MN_RATINGS),
                                      the serial link (MN_LINK) */
    const ImageIO *images;          /* menu.img / menu256.img, font.pck */
    const KeyboardPlatform *keys;   /* the hotkeys */
    const TextPlatform *text;       /* the version box (V) */
    const RatingsServices *ratings; /* NULL: the host's MN_RATINGS */
    uint8_t *screen;                /* the mode-13h screen on VGA installations */
    uint8_t *palette;               /* 768 bytes for the VGA picture's palette */
    const struct SaveGameServices *saves; /* loading a game (src/savegame.c); NULL: the host's MN_LOAD_GAME */
} MainMenuServices;
enum {
    MN_DAC_REGISTER = 0x1010,
    MN_LOAD_GAME = 0x4CE5,
    MN_RATINGS = 0xD300,
    MN_LINK = 0x06DE
};
API int main_menu(Game *g, const MainMenuServices *host);
typedef struct CreditsServices {
    const MapResources *resources; /* video modes, the retrace waits 0D8D / 0DAA, PB_SET_DISPLAY_START */
    const ImageIO *images;         /* the credits text, font.pck */
    const KeyboardPlatform *keys;  /* the wait for a key at the end while the music plays */
} CreditsServices;
API int credits_screen(Game *g, const CreditsServices *host);
enum {
    MU_LOAD = 0x89F0,        /* audio backend: load and start the song, a = its file name (DS) */
    MU_STOP = 0xF472,        /* stop the song */
    MU_RESET = 0xF445,
    MU_CLOSE = 0xF4C1,
    MU_SAMPLES_OFF = 0xF205
};
API int music_stop(Game *g, const MapResources *host);
API int music_start(Game *g, const MapResources *host);
API void music_mark_ending(uint8_t *ds);
API int music_close(Game *g, const MapResources *host);
API void session_reset(Game *g);
API void session_pointers(uint8_t *ds);
API void session_draw_page_wide(uint8_t *ds, uint16_t page);
API void session_row_table(uint8_t *ds);
API void session_arrival_followup(uint8_t *ds);
API void session_clear_items(uint8_t *ds);
API void session_clear_flags(uint8_t *ds);
API void point_copy(uint8_t *ds, uint16_t from, uint16_t to);
API int font8_load(Game *g, const ImageIO *images);
API void def_slot_of(uint8_t *ds, uint16_t record);
API int session_load_swapped(Game *g, const ImageIO *images);
API int session_load_records(Game *g, const ImageIO *images);
API int session_load_pictures(Game *g, const ImageIO *images);
API void random_seed_from_clock(Game *g);
API void misc_store_1204(Game *g, uint16_t ax);
API void misc_mark_record(uint8_t *ds, uint16_t record);
API uint32_t misc_band_test(const uint8_t *ds, uint16_t ax);
API void misc_append_figures(uint8_t *ds);
API uint16_t misc_collect_char(uint8_t *ds, uint16_t at, uint16_t *end);
API void misc_cell_position(uint8_t *ds, uint16_t record, uint16_t ax, uint16_t bx);
API void misc_frame_lines_abec(Game *g);
typedef struct EndingServices {
    const MapResources *resources; /* the retrace waits 0D8D / 0DAA, the pause OS_WAIT (a = frames); without
                                      `movie` the movie player OS_CUTSCENE (a = file, b = delay | variant << 8);
                                      without `sound` the sample group 6 as 8AFE */
    const MovieServices *movie;
    const SoundServices *sound;
} EndingServices;
API int ending_sequence(Game *g, const EndingServices *host);

/* The machine below the game, for the routines that use the hardware, the BIOS and DOS
 * directly (src/machine.c and on): port input / output (size 1 or 2: OUT DX,AX writes AL to
 * the port and AH to the next) and software interrupts (the registers in and out; CF is bit 0
 * of flags). A host implements it with real or emulated devices; the tests replay what the
 * original met (tests/machine.py). interrupt returns non-zero when the host cannot serve it. */
typedef struct CpuRegs {
    uint16_t ax, bx, cx, dx, si, di, bp, ds, es, flags;
} CpuRegs;
typedef struct MachineServices {
    uint16_t (*in)(Game *g, uint16_t port, uint8_t size, void *user);
    void (*out)(Game *g, uint16_t port, uint8_t size, uint16_t value, void *user);
    int (*interrupt)(Game *g, uint8_t vector, CpuRegs *regs, void *user);
    void *user;
    /* the hardware interrupt that arrives now, its vector (or -1: none), asked where the
     * original waits for one with interrupts enabled; NULL: none ever */
    int (*irq)(Game *g, void *user);
} MachineServices;
API int machine_interrupt(Game *g, const MachineServices *mc, uint8_t vector, CpuRegs *regs);
API void retrace_wait_start(Game *g, const MachineServices *mc);
API void retrace_wait_end(Game *g, const MachineServices *mc);
API void pause_frames(Game *g, const MachineServices *mc, uint16_t frames);
API void crtc_display_start(Game *g, const MachineServices *mc, uint16_t start);
API int bios_video_call(Game *g, const MachineServices *mc, CpuRegs *regs);
API void palette_registers(Game *g, const MachineServices *mc, uint16_t table);
API int dac_block(Game *g, const MachineServices *mc, uint16_t table, uint16_t es);
API uint32_t bios_ticks(const Game *g);
API void vector_set(Game *g, uint16_t number, uint16_t off, uint16_t seg);
API uint32_t vector_get(const Game *g, uint16_t number);
API void divide_handler_install(Game *g);
API void divide_handler_remove(Game *g);
API void divide_error_resume(Game *g, uint16_t ss, uint16_t sp);
API int keyboard_install(Game *g, const MachineServices *mc);
API int keyboard_remove(Game *g, const MachineServices *mc);
API int joystick_absent(Game *g, const MachineServices *mc);
API uint32_t joystick_read_port(Game *g, const MachineServices *mc, uint8_t al);
API int ems_setup(Game *g, const MachineServices *mc);
API int ems_release(Game *g, const MachineServices *mc);
API int adapter_detect(Game *g, const MachineServices *mc, uint16_t ax, uint16_t *result);
/* the DOS file library (src/dos.c): each takes the caller's registers and leaves them as the
 * original does, CF / ZF in flags */
API void dos_store_error(Game *g, uint16_t ax);
API uint16_t dos_last_error(Game *g);
API uint16_t dos_string_end(Game *g, uint16_t seg, uint16_t off);
API int dos_print(Game *g, const MachineServices *mc, CpuRegs *r);
API void dos_strip_backslash(Game *g, CpuRegs *r);
API int dos_drive_letter(Game *g, const MachineServices *mc, CpuRegs *r);
API void dos_add_backslash(Game *g, uint16_t seg, uint16_t off);
API int dos_current_directory(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_find_first(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_find_next(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_delete(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_close(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_create(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_open(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_open_mode(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_read(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_write(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_load_file(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_close_handle(Game *g, const MachineServices *mc, CpuRegs *r);
API int dos_read_at_si(Game *g, const MachineServices *mc, CpuRegs *r);
typedef struct ProtectionServices {
    const MapResources *resources; /* video modes, the retrace waits 0D8D / 0DAA */
    const ImageIO *images;         /* pass.img / pass256.img, shapes.img */
    const KeyboardPlatform *keys;  /* the time between two reads of the key table */
    uint8_t *screen;               /* the mode-13h screen on VGA installations */
    uint8_t *palette;              /* 768 bytes for the VGA image's palette */
} ProtectionServices;
API int protection_screen(Game *g, const ProtectionServices *host);
API int name_editor(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t max, const RatingsServices *host);
API void ega_fill_rect(Game *g, uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1);
API void number_decimal(uint8_t *ds, uint16_t dest, uint16_t value);
API void number_decimal_signed(uint8_t *ds, uint16_t dest, uint16_t value);

/* damagepanel.c: the damage panel ("Physical status", and the hospital's), 0000:5F06 */
typedef struct DamagePanelServices {
    const MapResources *resources;     /* page selection, video modes (MS_VIDEO_MODE), camera reset */
    const MapPlatform *platform;       /* retrace waits; the panel's loop waits once per frame (keys arrive) */
    const MenuPlatform *menu;          /* MM_WAIT: the pause after each point healed */
    const ImageIO *images;             /* Damage.img / Dam256.img and the camera reset's images */
    const TextPlatform *text;          /* message boxes */
    const TravelServices *travel;      /* healing runs the world: cell loading and the like */
    const OpponentServices *opponents; /* ... and what the world step asks of its host */
    const VehicleServices *vehicle;
    uint8_t *screen;  /* the mode-13h screen, used on VGA installations (DS:ADD0) */
    uint8_t *palette; /* 768 bytes: Dam256.img's palette is loaded here */
} DamagePanelServices;
API int damage_panel(Game *g, const DamagePanelServices *host);

/* gamemenus.c: the option handlers of the menus opened during play (GAME MENU, PLAYER MENU,
 * "Tell Sarah to...") and the menus they open. Host ops through GameMenuServices.menu: the
 * MM_* menu ops, the music driver (F494, F4A1), GM_*, and MM_ACTION for options not
 * translated (it returns a MENU_* status, like these). */
enum {
    GM_JOYSTICK_DETECT = 0x3A12, /* returns 1 when there is no joystick (the original's carry) */
    GM_JOYSTICK_CALIBRATE = 0x38F6,
    GM_RATINGS = 0xD300,
    GM_DAMAGE_PANEL = 0x5F06,
};
typedef struct GameMenuServices {
    const MenuPlatform *menu;          /* the host's menu platform, see above */
    const TextPlatform *text;          /* message boxes */
    const ImageIO *images;             /* the HUD reload after dropping an item */
    const DamagePanelServices *damage; /* "Physical status"; NULL: the host's GM_DAMAGE_PANEL */
    const RatingsServices *ratings;    /* "Ratings"; NULL: the host's GM_RATINGS */
    const MachineServices *machine;    /* DOS for saving and deleting games (src/savegame.c); NULL: the
                                          host's MM_ACTION 4B7E / 4CDE */
} GameMenuServices;
API int game_menu_display(Game *g, uint16_t text, uint16_t x, uint16_t y, uint16_t width, uint16_t height,
                          uint16_t actions, const GameMenuServices *host);
API int facility_confirm(Game *g, uint16_t question, const GameMenuServices *host);
API int game_menu_action(Game *g, uint16_t target, const GameMenuServices *host);
/* savegame.c: saving, loading and deleting games (0000:4B7E, 4CDE, 4CE5), through the DOS
 * library; menus, message boxes and the name editor through `menus` */
typedef struct SaveGameServices {
    const GameMenuServices *menus;
    const MachineServices *machine;
} SaveGameServices;
API void savegame_code_block(Game *g, uint16_t ax);
API int savegame_save_action(Game *g, const SaveGameServices *host);
API int savegame_delete_action(Game *g, const SaveGameServices *host);
API int savegame_load(Game *g, const SaveGameServices *host);

/* startup.c: the program's start-up (0000:0000) and its set-up routines; the argument
 * scanner of the run-time library works on the caller's registers. ProgramServices: the
 * machine, and the routines the host owns (the serial link, the sound drivers, screens with
 * services of their own), called by their original address with the registers they take. */
typedef int (*ProgramCall)(Game *g, uint16_t seg, uint16_t off, CpuRegs *regs, void *user);
typedef struct ProgramServices {
    const MachineServices *machine; /* DOS, the BIOS and the ports */
    ProgramCall call;               /* routines the host owns, and the sound drivers' entries */
    void *user;
} ProgramServices;
API void char_compare_nocase(CpuRegs *r);
API void string_compare_nocase(Game *g, CpuRegs *r);
API void args_reset(Game *g);
API void args_count(Game *g, CpuRegs *r);
API void args_next(Game *g, CpuRegs *r);
API int startup_options(Game *g, const ProgramServices *host);
API int startup_preload(Game *g, const ProgramServices *host);
API int startup_init(Game *g, const ProgramServices *host);
API int startup_intro(Game *g, const ProgramServices *host);
API int startup_game_setup(Game *g, const ProgramServices *host);
API int startup_inventory(Game *g, const ProgramServices *host, uint16_t *bx_out);
API int startup_position(Game *g, const ProgramServices *host);
API int ratings_commit(Game *g, const ProgramServices *host);
API int program_start(Game *g, uint16_t psp, const ProgramServices *host);

/* soundlayer.c: the sound layer between the game and its drivers (the drivers' entries are
 * ProgramServices.call's: 101F:0000, 10BB:0000, 0FBA:058F, 5B67 routines), the card
 * detection through the machine, and the C library's 32-bit division */
API void sb_dsp_read(Game *g, const MachineServices *mc, CpuRegs *r);
API void sb_dsp_write(Game *g, const MachineServices *mc, CpuRegs *r);
API void sb_dsp_read_wait(Game *g, const MachineServices *mc, CpuRegs *r);
API void sb_dsp_write_wait(Game *g, const MachineServices *mc, CpuRegs *r);
API void sb_irq_unmask(Game *g, const MachineServices *mc);
API void sb_irq_mask(Game *g, const MachineServices *mc);
API void sb_irq_handler(Game *g, const MachineServices *mc, uint8_t irq);
API void sb_irq_detect(Game *g, const MachineServices *mc, CpuRegs *r);
API void sb_dsp_reset(Game *g, const MachineServices *mc, CpuRegs *r);
API void adlib_delay(Game *g, const MachineServices *mc);
API void adlib_write(Game *g, const MachineServices *mc, CpuRegs *r);
API void adlib_wait_status(Game *g, const MachineServices *mc, CpuRegs *r);
API void sb_detect(Game *g, const MachineServices *mc, CpuRegs *r);
API int music_driver_init(Game *g, const ProgramServices *host, CpuRegs *r);
API int music_driver_close(Game *g, const ProgramServices *host, CpuRegs *r);
API void music_flag_take(Game *g, CpuRegs *r);
API int sound_wrapper(Game *g, const ProgramServices *host, uint16_t entry, CpuRegs *r, const uint16_t *args);
API void long_division(uint16_t mode, uint16_t a_lo, uint16_t a_hi, uint16_t b_lo, uint16_t b_hi, CpuRegs *r);
API int music_song_start(Game *g, const ProgramServices *host, CpuRegs *r);
API int music_load(Game *g, const ProgramServices *host, CpuRegs *r);
API int sound_init(Game *g, const ProgramServices *host, CpuRegs *r);
API int sample_init(Game *g, const ProgramServices *host, CpuRegs *r);
API int sound_memory_free(Game *g, const ProgramServices *host, CpuRegs *r);
API int sample_stop(Game *g, const ProgramServices *host, CpuRegs *r);

/* unreachable.c: the routines no path of the game reaches, translated register for register */
API void unused_plane_bits(Game *g, CpuRegs *r);
API void unused_faces_behind(Game *g, CpuRegs *r);
API void unused_camera_offset(Game *g, CpuRegs *r);
API void unused_extras_clear(Game *g, CpuRegs *r);
API void unused_scale_down(Game *g, CpuRegs *r);
API void unused_project(Game *g, CpuRegs *r);
API void unused_scale_half(Game *g, CpuRegs *r);
API void unused_divide_handler(Game *g, uint16_t ss, uint16_t sp, CpuRegs *r);
API void unused_drop_kind(Game *g, CpuRegs *r);
API void unused_unpack_far(Game *g, CpuRegs *r);
API void unused_marks_undo(Game *g, CpuRegs *r);
API void unused_model_turn(Game *g, CpuRegs *r);
API void unused_add_50(Game *g, CpuRegs *r);
API void unused_decoy_step(Game *g, CpuRegs *r);
API int unused_timer_restore(Game *g, const MachineServices *mc, CpuRegs *r);
API void unused_count_up(Game *g, CpuRegs *r);
API int unused_protection_fail(Game *g, const MachineServices *mc, CpuRegs *r);
API void unused_parse_decimal(Game *g, CpuRegs *r);
API void unused_args_restart(Game *g, CpuRegs *r);
API void unused_decimal_backwards(Game *g, CpuRegs *r);
API void unused_translate(Game *g, CpuRegs *r);
API void unused_text3_vga(Game *g, uint8_t *screen, CpuRegs *r);
API void unused_weapon_icon_redraw(Game *g, CpuRegs *r);
typedef struct FacilityServices {
    const MapResources *resources; /* video modes, page selection, camera reset */
    const ImageIO *images;         /* the facility images, cells, the alarm's text */
    const GameMenuServices *menus; /* menus and message boxes; the damage panel (the hospital) */
    const SoundServices *sound;    /* the sample groups (4 inside, 3 back on foot) */
    uint8_t *screen;               /* the mode-13h screen on VGA installations */
    uint8_t *palette;              /* 768 bytes for the VGA image's palette */
    const KeyboardPlatform *keys;  /* the key after the firing range's results */
} FacilityServices;
enum {
    FA_TICK = 0x9029 /* resources op: let the timer interrupt run (the firing range's pause) */
};
API int facility_screen(Game *g, uint16_t kind, const FacilityServices *host);
API int companion_exchange(Game *g, int take, const GameMenuServices *host);

/* frame.c: one frame of a single-player game (main loop 0000:0155) */
enum {
    FRAME_PALETTE = 0x7AB6 /* reload the game palette from DS:1510 */
};
typedef uint32_t (*FrameCall)(Game *g, uint16_t op, void *user); /* UINT32_MAX = not available */
typedef struct FrameServices {
    const GameplayServices *gameplay; /* game update; its vehicle member serves the city and scene */
    const HudServices *hud;           /* HUD and weapons after the scene */
    FrameCall call;                   /* the palette reload, FRAME_PALETTE */
    void *user;
    uint8_t *chunky_screen;         /* mode-13h screen for VGA overlays, or NULL */
    uint16_t shop_entry_sp;         /* stack pointer value the shop code records (DS:9A4C) */
    const MapKeyServices *map;      /* the M key's map screen; NULL = not available */
    const PhoneBookServices *phone; /* the P key's phone book; NULL = not available */
    const GameMenuServices *menus;  /* the Q, F10 and Esc menus; NULL = not available */
} FrameServices;
API int frame_input_check(Game *g, const FrameServices *host);
API int game_frame(Game *g, const FrameServices *host);

#endif
