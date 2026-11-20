/* Explosions: blast damage, the queue of secondary blasts, and the debris that flies off.
 *
 * Four things the original does from here belong to parts of the game that are not
 * translated yet. They are not performed; each is reported as an event instead (see
 * game_events in events.c), so that a caller - or a test - can see that it was asked for:
 *
 *   EV_SOUND          0000:89A2   start sound effect A
 *   EV_PLAYER_HIT     0000:6386   the player takes A points of damage
 *   EV_FIGURE_KILLED  0000:AFD0   the figure whose record is at DS:A is killed
 *   EV_OBJECT_BLOWN   151B:02DE   bookkeeping elsewhere for the blown-up object whose record is at DS:A
 */
#include "term.h"

enum {
    BL_PLAYER = 0x03A0,
    BL_FRAME_COUNTER = 0x020C,
    BL_LIST_COUNT = 0x020E, /* u16: number of records in the unsorted frame list */
    BL_FRAME_LIST = 0x1576,
    BL_PIECE_COUNTER = 0x1178, /* u16: debris pieces made since the debris last ran out */
    BL_DEBRIS_COUNT = 0x117A,
    BL_WIDE_ARCS = 0x11CB,    /* u8: 0 = all debris flies flat */
    BL_VERTS_COPIED = 0x115E, /* u8: set while one object's faces are being turned into pieces */
    BL_DRAW_COUNT = 0x50AC,
    BL_WORK_MESH = 0x50B2,
    BL_VISIBLE = 0x5F80,
    BL_VISIBLE_COUNT = 0x7240,
    BL_VISIBLE_CELL = 0x7242,
    BL_SOURCES = 0x72DC,
    BL_CAR_MESHES = 0x72CA, /* three words: the mesh numbers of the car models */
    BL_PUMPS_MESH = 0x5EE3,
    BL_SPECIAL_ID = 0x9A64,
    BL_SPECIAL_MESH = 0x80EE,
    BL_SEG_CELLS = 0x91D4,
    BL_ARCS = 0x9564, /* 8 tables of 45 signed bytes: height change per frame */
    BL_FACES_LEFT = 0x96D0,
    BL_POS = 0x96D2, /* x, y, z of the piece or object being worked on */
    BL_SAVED_FLAGS = 0x96D8,
    BL_NUMBER = 0x96DA,
    BL_SEG_DEBRIS = 0x96DC,
    BL_FACE_BYTES = 0x96DE, /* u16: bytes of face data stored in the debris segment */
    BL_VERT_BYTES = 0x96E0,
    BL_VERT_BLOCK = 0x96E2,
    BL_FACE_VERTS = 0x96E4,
    BL_AT = 0x96EC, /* x, z of the blast */
    BL_DAMAGE = 0x96F0,
    BL_RADIUS = 0x96F2,
    BL_QUEUE_PTR = 0x96F4,
    BL_QUEUE = 0x96F6, /* 12-byte records waiting to go off */
    BL_QUEUE_COUNT = 0x97B6,
    BL_RANDOM_BUFFER = 0x97B8, /* 200 random words */
    BL_RANDOM_PTR = 0x9948,
    BL_RANDOM_END = 0x994A,
    BL_RANDOM_STATE = 0xEA42,  /* u32 */
    BL_RANDOM_FACTOR = 0xEA46, /* u32 */

    /* inside the debris segment */
    DB_RECORDS = 0x0000, /* 12-byte draw records, one per piece (flags 0100, id = piece) */
    DB_MOTION = 0x0960,  /* 20 bytes per piece: life, direction, arc pointer, three spin
                                  rates, speed, three spin angles */
    DB_HEADERS = 0x1900, /* 16 bytes per piece: a one-face mesh header */
    DB_FACES = 0x2580,
    DB_VERTICES = 0x3580,
};

static inline uint16_t far_u16(const Game *g, uint16_t seg, uint16_t off)
{
    return (uint16_t)(*far_ptr(g, seg, off) | (*far_ptr(g, seg, (uint16_t)(off + 1)) << 8));
}

static inline void far_set(Game *g, uint16_t seg, uint16_t off, uint16_t v)
{
    *far_ptr(g, seg, off) = (uint8_t)v;
    *far_ptr(g, seg, (uint16_t)(off + 1)) = (uint8_t)(v >> 8);
}

/* ---------------------------------------------------------------- random numbers */

/* orig 0000:F88A   state = state * factor (32 bits); the result is the new high word */
static uint16_t random_step(uint8_t *ds)
{
    uint32_t lo = DS_U16(ds, BL_RANDOM_STATE), hi = DS_U16(ds, BL_RANDOM_STATE + 2);
    uint32_t f_lo = DS_U16(ds, BL_RANDOM_FACTOR), f_hi = DS_U16(ds, BL_RANDOM_FACTOR + 2);
    uint32_t p = f_lo * lo;
    uint16_t high = (uint16_t)((uint16_t)(f_hi * lo) + (uint16_t)(p >> 16) + (uint16_t)(f_lo * hi));
    DS_U16(ds, BL_RANDOM_STATE) = (uint16_t)p;
    DS_U16(ds, BL_RANDOM_STATE + 2) = high;
    return high;
}

/* orig 0000:8117   200 new random words into the buffer. Also notes the time of day (DOS
 * function 2Ch: DX, CX) in DS:994C / 994E; random_refill takes it from game_set_clock,
 * random_refill_from from the caller (who asked DOS). */
void random_refill_from(uint8_t *ds, uint16_t dx, uint16_t cx)
{
    DS_U16(ds, 0x994C) = dx;
    DS_U16(ds, 0x994E) = cx;
    for (int i = 0; i < 200; i++)
        DS_U16(ds, (uint16_t)(BL_RANDOM_BUFFER + 2 * i)) = random_step(ds);
    DS_U16(ds, BL_RANDOM_PTR) = BL_RANDOM_BUFFER;
    DS_U16(ds, BL_RANDOM_END) = BL_RANDOM_PTR;
}

void random_refill(uint8_t *ds)
{
    random_refill_from(ds, game_clock_dx(), game_clock_cx());
}

/* orig 0000:80EE   out AX
 * Random words are made 200 at a time and handed out from a buffer. */
uint16_t random_word(uint8_t *ds)
{
    uint16_t at = DS_U16(ds, BL_RANDOM_PTR);
    if (at >= DS_U16(ds, BL_RANDOM_END)) {
        random_refill(ds);
        at = BL_RANDOM_BUFFER;
    }
    uint16_t value = DS_U16(ds, at);
    DS_U16(ds, BL_RANDOM_PTR) = (uint16_t)(at + 2);
    return value;
}

/* ---------------------------------------------------------------- debris */

/* orig 0000:7B28   in SI = record of the object, BX = its mesh number
 *
 * Breaks the object up: every face of its mesh becomes a piece of debris with a random
 * life (30-45 frames), direction, speed (5-20 per frame), spin and one of eight arcs.
 * In the debris segment each piece gets a draw record, a motion record and a one-face mesh
 * whose vertex references point into a copy of the object's vertices.
 * Nothing happens if there are already 150 pieces, or 150 records and pieces together.
 */
void debris_start(Game *g, uint16_t si, uint16_t number)
{
    uint8_t *ds = g->ds;
    event_push(EV_SOUND, 1, 0);
    if (DS_U16(ds, BL_DEBRIS_COUNT) >= 0x96)
        return;
    if ((uint16_t)(DS_U16(ds, BL_DRAW_COUNT) + DS_U16(ds, BL_DEBRIS_COUNT)) >= 0x96)
        return;
    if (DS_U16(ds, BL_DEBRIS_COUNT) == 0)
        DS_U16(ds, BL_PIECE_COUNTER) = 0;
    DS_U16(ds, BL_POS) = DS_U16(ds, si);
    DS_U16(ds, BL_POS + 2) = DS_U16(ds, (uint16_t)(si + 2));
    DS_U16(ds, BL_POS + 4) = DS_U16(ds, (uint16_t)(si + 4));
    DS_U16(ds, BL_SAVED_FLAGS) = DS_U16(ds, DS_OBJ_FLAGS);
    DS_U16(ds, DS_OBJ_FLAGS) = DS_U16(ds, (uint16_t)(si + 6));
    DS_U16(ds, BL_NUMBER) = number;
    mesh_fetch(g, number);
    const uint16_t mesh = BL_WORK_MESH;
    DS_U16(ds, DS_OBJ_FLAGS) = DS_U16(ds, BL_SAVED_FLAGS);

    /* the debris segment is at a fixed place in the program image (file segment 531E) */
    uint16_t seg = (uint16_t)(0x531E + (g->ds_seg - 0x5C27));
    DS_U16(ds, BL_SEG_DEBRIS) = seg;

    uint16_t di = (uint16_t)(DB_MOTION + 0x14 * DS_U16(ds, BL_PIECE_COUNTER));
    uint16_t faces = DS_U16(ds, (uint16_t)(mesh + 2));
    DS_U16(ds, BL_FACES_LEFT) = faces;
    uint16_t n = faces;
    do { /* LOOP: a count of 0 means 65536 */
        far_set(g, seg, di, (uint16_t)((random_word(ds) & 0x0F) + 0x1E));
        far_set(g, seg, (uint16_t)(di + 2), random_word(ds) & 0x199);
        uint16_t arc = random_word(ds) & 7;
        if (!DS_U8(ds, BL_WIDE_ARCS))
            arc = 0;
        far_set(g, seg, (uint16_t)(di + 4), (uint16_t)(arc * 0x2D + BL_ARCS));
        far_set(g, seg, (uint16_t)(di + 6), random_word(ds) & 0x1F);
        far_set(g, seg, (uint16_t)(di + 8), random_word(ds) & 0x1F);
        far_set(g, seg, (uint16_t)(di + 0x0A), random_word(ds) & 0x1F);
        far_set(g, seg, (uint16_t)(di + 0x0C), (uint16_t)((random_word(ds) & 0x0F) + 5));
        far_set(g, seg, (uint16_t)(di + 0x10), random_word(ds) & 0x1FF);
        DS_U16(ds, BL_DEBRIS_COUNT)++;
        di = (uint16_t)(di + 0x14);
    } while (--n);

    /* the pieces' draw records, all at the object's position for now */
    di = (uint16_t)(DB_RECORDS + (uint8_t)(DS_U16(ds, BL_DEBRIS_COUNT) - DS_U16(ds, BL_FACES_LEFT)) * 0x0C);
    n = DS_U16(ds, BL_FACES_LEFT);
    do {
        far_set(g, seg, di, DS_U16(ds, BL_POS));
        far_set(g, seg, (uint16_t)(di + 2), DS_U16(ds, BL_POS + 2));
        far_set(g, seg, (uint16_t)(di + 4), DS_U16(ds, BL_POS + 4));
        far_set(g, seg, (uint16_t)(di + 6), 0x100);
        far_set(g, seg, (uint16_t)(di + 8), (uint16_t)(DS_U16(ds, BL_PIECE_COUNTER) + DS_U16(ds, BL_FACES_LEFT) - n));
        far_set(g, seg, (uint16_t)(di + 0x0A), 0);
        di = (uint16_t)(di + 0x0C);
    } while (--n);

    if (DS_U16(ds, BL_PIECE_COUNTER) == 0) {
        DS_U16(ds, BL_FACE_BYTES) = 0;
        DS_U16(ds, BL_VERT_BYTES) = 0;
    }

    /* a one-face mesh per piece */
    di = (uint16_t)(DB_HEADERS + (uint8_t)DS_U16(ds, BL_PIECE_COUNTER) * 0x10);
    n = DS_U16(ds, BL_FACES_LEFT);
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    do {
        DS_U16(ds, BL_FACE_VERTS) = 0;
        far_set(g, seg, di, (uint16_t)(DS_U16(ds, BL_FACES_LEFT) - n));
        far_set(g, seg, (uint16_t)(di + 2), 1);
        uint16_t to = (uint16_t)(DB_FACES + DS_U16(ds, BL_FACE_BYTES));
        far_set(g, seg, (uint16_t)(di + 6), to);
        far_set(g, seg, to, DS_U16(ds, face));                                 /* colours */
        far_set(g, seg, (uint16_t)(to + 2), DS_U16(ds, (uint16_t)(face + 2))); /* flags */
        uint16_t refs = DS_U16(ds, (uint16_t)(face + 4));
        far_set(g, seg, (uint16_t)(to + 4), refs);
        DS_U16(ds, BL_FACE_VERTS) = refs;
        face = (uint16_t)(face + 6);
        to = (uint16_t)(to + 6);
        for (uint16_t k = refs; k; k--) {
            far_set(g, seg, to, DS_U16(ds, face));
            face = (uint16_t)(face + 2);
            to = (uint16_t)(to + 2);
        }
        DS_U16(ds, BL_FACE_BYTES) = (uint16_t)(DS_U16(ds, BL_FACE_BYTES) + 2 * DS_U16(ds, BL_FACE_VERTS) + 6);

        if (!DS_U8(ds, BL_VERTS_COPIED)) { /* the object's vertices, once */
            DS_U16(ds, BL_VERT_BLOCK) = (uint16_t)(DB_VERTICES + DS_U16(ds, BL_VERT_BYTES));
            uint16_t vto = DS_U16(ds, BL_VERT_BLOCK);
            uint16_t words = (uint16_t)(DS_U16(ds, (uint16_t)(mesh + 4)) * 3);
            DS_U16(ds, BL_VERT_BYTES) = (uint16_t)(DS_U16(ds, BL_VERT_BYTES) + words + words);
            uint16_t vfrom = DS_U16(ds, (uint16_t)(mesh + 8));
            for (; words; words--) {
                far_set(g, seg, vto, DS_U16(ds, vfrom));
                vfrom = (uint16_t)(vfrom + 2);
                vto = (uint16_t)(vto + 2);
            }
            DS_U8(ds, BL_VERTS_COPIED)++;
        }
        far_set(g, seg, (uint16_t)(di + 8), DS_U16(ds, BL_VERT_BLOCK));
        far_set(g, seg, (uint16_t)(di + 4), DS_U16(ds, BL_FACE_VERTS));
        far_set(g, seg, (uint16_t)(di + 0x0A), 0x96E8);
        far_set(g, seg, (uint16_t)(di + 0x0C), 0);
        far_set(g, seg, (uint16_t)(di + 0x0E), 0);
        di = (uint16_t)(di + 0x10);
    } while (--n);
    DS_U8(ds, BL_VERTS_COPIED)--;
    DS_U16(ds, BL_PIECE_COUNTER) = (uint16_t)(DS_U16(ds, BL_PIECE_COUNTER) + DS_U16(ds, BL_FACES_LEFT));
}

/* orig 0000:7D2B   once per frame: every piece lives one frame less; a piece whose life has
 * run out is removed (the records after it move down), the others move along their
 * direction by their speed, rise or fall by the next step of their arc, and spin on. */
void debris_update(Game *g)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, BL_DEBRIS_COUNT) == 0)
        return;
    uint16_t seg = DS_U16(ds, BL_SEG_DEBRIS);
    uint16_t di = (uint16_t)(DB_RECORDS - 0x0C);
    uint16_t n = DS_U16(ds, BL_DEBRIS_COUNT);
    do {
        di = (uint16_t)(di + 0x0C);
        for (int i = 0; i < 10; i += 2)
            DS_U16(ds, (uint16_t)(BL_POS + i)) = far_u16(g, seg, (uint16_t)(di + i));
        uint16_t motion = (uint16_t)(DB_MOTION + (uint8_t)DS_U16(ds, BL_NUMBER) * 0x14);
        uint16_t life = (uint16_t)(far_u16(g, seg, motion) - 1);
        far_set(g, seg, motion, life);
        if (life == 0) {
            uint16_t from = (uint16_t)(di + 0x0C), to = di;
            for (uint16_t words = (uint16_t)(6 * (uint8_t)n); words; words--) {
                far_set(g, seg, to, far_u16(g, seg, from));
                from = (uint16_t)(from + 2);
                to = (uint16_t)(to + 2);
            }
            DS_U16(ds, BL_DEBRIS_COUNT)--;
            di = (uint16_t)(di - 0x0C);
            continue;
        }
        uint16_t arc = far_u16(g, seg, (uint16_t)(motion + 4));
        DS_I16(ds, BL_POS + 2) = (int16_t)(DS_I16(ds, BL_POS + 2) + (int8_t)DS_U8(ds, arc));
        far_set(g, seg, (uint16_t)(motion + 4), (uint16_t)(arc + 1));
        uint16_t dir = (uint16_t)(far_u16(g, seg, (uint16_t)(motion + 2)) * 2);
        int16_t speed2 = (int16_t)(far_u16(g, seg, (uint16_t)(motion + 0x0C)) * 2);
        DS_I16(ds, BL_POS) = (int16_t)(DS_I16(ds, BL_POS) + mul_hi(speed2, DS_I16(ds, (uint16_t)(dir + 0x4188))));
        DS_I16(ds, BL_POS + 4) =
            (int16_t)(DS_I16(ds, BL_POS + 4) + mul_hi(speed2, DS_I16(ds, (uint16_t)(dir + 0x4288))));
        far_set(g, seg, di, DS_U16(ds, BL_POS));
        far_set(g, seg, (uint16_t)(di + 2), DS_U16(ds, BL_POS + 2));
        far_set(g, seg, (uint16_t)(di + 4), DS_U16(ds, BL_POS + 4));
        for (int k = 0; k < 3; k++) {
            uint16_t angle = (uint16_t)(motion + 0x0E + 2 * k);
            far_set(g, seg, angle,
                    (uint16_t)((far_u16(g, seg, angle) + far_u16(g, seg, (uint16_t)(motion + 6 + 2 * k))) & 0x1FF));
        }
    } while (--n);
}

/* ---------------------------------------------------------------- blast damage */

/* orig 0000:808E   in AX = mesh number, SI = record   out: carry (returned)
 * 0 for things that go off themselves when destroyed: the three car models, the petrol
 * pumps, and the special mesh when its record has flag 0x2000. 1 for everything else. */
static int ordinary_object(const uint8_t *ds, uint16_t number, uint16_t rec)
{
    if (number == DS_U16(ds, BL_CAR_MESHES) || number == DS_U16(ds, BL_CAR_MESHES + 2)
        || number == DS_U16(ds, BL_CAR_MESHES + 4) || number == DS_U16(ds, BL_PUMPS_MESH))
        return 0;
    if (number == DS_U16(ds, BL_SPECIAL_ID))
        return !(DS_U16(ds, (uint16_t)(rec + 6)) & 0x2000);
    return 1;
}

/* orig 0000:8075 (with 45E6)   put the record on the queue of blasts still to go off, and
 * hide the identical record in the visible-object list, if there is one */
static void queue_blast(uint8_t *ds, uint16_t rec)
{
    DS_U16(ds, BL_QUEUE_COUNT)++;
    uint16_t to = DS_U16(ds, BL_QUEUE_PTR);
    for (int i = 0; i < 12; i++)
        DS_U8(ds, (uint16_t)(to + i)) = DS_U8(ds, (uint16_t)(rec + i));
    DS_U16(ds, BL_QUEUE_PTR) = (uint16_t)(to + 12);

    uint16_t at = BL_VISIBLE;
    uint16_t n = DS_U16(ds, BL_VISIBLE_COUNT);
    do { /* LOOP: a count of 0 means 65536 */
        int same = 1;
        for (int i = 0; i < 12 && same; i++)
            same = DS_U8(ds, (uint16_t)(rec + i)) == DS_U8(ds, (uint16_t)(at + i));
        if (same) {
            DS_U16(ds, (uint16_t)(at + 0x0A)) = 0xFFFF;
            return;
        }
        at = (uint16_t)(at + 12);
    } while (--n);
}

/* Take the blast's damage off the record's strength. Returns 1 if that destroys it. */
static int take_damage(uint8_t *ds, uint16_t rec)
{
    uint8_t left = (uint8_t)(DS_U8(ds, (uint16_t)(rec + 0x0A)) - DS_U8(ds, BL_DAMAGE));
    DS_U8(ds, (uint16_t)(rec + 0x0A)) = left;
    return (left & 0x80) != 0;
}

/* orig 0000:4586 (reached by falling out of the little routine at 0000:4581)
 * Adds the object to the list of removed map objects at DS:0F70 (32 entries, used round
 * and round): its position inside its cell, its quarter turns and its LA.DEF number. The
 * cell walk skips cell records that match an entry. */
void map_note_removed(uint8_t *ds, uint16_t rec)
{
    uint16_t di = DS_U16(ds, 0x03A6);
    if (di == 0x10F0)
        di = 0x0F70;
    DS_U16(ds, di) = DS_U16(ds, rec) & 0x3FF;
    DS_U16(ds, (uint16_t)(di + 2)) = DS_U16(ds, (uint16_t)(rec + 2));
    DS_U16(ds, (uint16_t)(di + 4)) = DS_U16(ds, (uint16_t)(rec + 4)) & 0x3FF;
    DS_U16(ds, (uint16_t)(di + 6)) = DS_U16(ds, (uint16_t)(rec + 6)) & 3;
    uint16_t id = DS_U16(ds, (uint16_t)(rec + 8));
    uint16_t def = (uint16_t)((id & 0xFF00) | DS_U8(ds, (uint16_t)(0x5DC0 + id)));
    DS_U16(ds, (uint16_t)(di + 8)) = def;
    DS_U16(ds, (uint16_t)(di + 10)) = def;
    DS_U16(ds, 0x03A6) = (uint16_t)(di + 12);
}

/* orig 0000:7EF0   in: the record of the thing that goes off (a stack argument)
 *
 * The thing itself flies apart (debris_start). Its strength - the low byte of the last
 * word of its record - is the damage it does, and four times that is the radius. The
 * player, if inside the radius, is hit four times for a quarter of the damage. Then every
 * record of the frame's object list inside the radius:
 *
 *   figures                       are killed (the companion's damage counter goes up instead)
 *   ordinary objects              lose the damage from their strength unless that is 255;
 *                                 if the result is negative as a signed byte they fly
 *                                 apart too (their records stay)
 *   cars, pumps, special objects  lose it as well; if destroyed they are queued to go off
 *                                 themselves and removed: figure-like ones are killed, map
 *                                 objects get FFFF in the last word of their cell record
 *
 * It also forces the visible-object list to be rebuilt (DS:7242 = FFFE).
 */
static void explosion_damage_impl(Game *g, uint16_t si, int native_modes)
{
    uint8_t *ds = g->ds;
    DS_U16(ds, BL_VISIBLE_CELL) = 0xFFFE;
    uint16_t id = DS_U16(ds, (uint16_t)(si + 8));
    if (id == DS_U16(ds, BL_CAR_MESHES) || id == DS_U16(ds, BL_CAR_MESHES + 2) || id == DS_U16(ds, BL_CAR_MESHES + 4))
        DS_U16(ds, 0x0388)++;
    DS_U16(ds, BL_AT) = DS_U16(ds, si);
    DS_U16(ds, BL_AT + 2) = DS_U16(ds, (uint16_t)(si + 4));
    DS_U16(ds, BL_DAMAGE) = DS_U8(ds, (uint16_t)(si + 0x0A));
    if (!(DS_U16(ds, (uint16_t)(si + 6)) & 0x2800) && DS_U16(ds, (uint16_t)(si + 8)) != DS_U16(ds, BL_SPECIAL_MESH)) {
        event_push(EV_OBJECT_BLOWN, si, 0);
        map_note_removed(ds, si);
    }

    debris_start(g, si, record_mesh_number(ds, DS_U16(ds, (uint16_t)(si + 6)), (uint16_t)(si + 8)));

    uint16_t player = DS_U16(ds, BL_PLAYER);
    uint16_t distance = approx_distance(DS_I16(ds, si), DS_I16(ds, (uint16_t)(si + 4)), DS_I16(ds, player),
                                        DS_I16(ds, (uint16_t)(player + 4)));
    uint16_t radius = (uint16_t)(DS_U8(ds, (uint16_t)(si + 0x0A)) * 4);
    DS_U16(ds, BL_RADIUS) = radius;
    if (distance < radius) {
        uint16_t amount = DS_U8(ds, (uint16_t)(si + 0x0A)) >> 2;
        for (int i = 0; i < 4; i++) {
            if (native_modes & 2)
                player_hit_native(g, amount);
            else
                event_push(EV_PLAYER_HIT, amount, 0);
        }
    }

    uint16_t rec = BL_FRAME_LIST;
    uint16_t n = DS_U16(ds, BL_LIST_COUNT);
    if (n == 0)
        return;
    do {
        distance =
            approx_distance(DS_I16(ds, BL_AT), DS_I16(ds, BL_AT + 2), DS_I16(ds, rec), DS_I16(ds, (uint16_t)(rec + 4)));
        if (distance < DS_U16(ds, BL_RADIUS)) {
            uint16_t flags = DS_U16(ds, (uint16_t)(rec + 6));
            uint16_t number = record_mesh_number(ds, flags, (uint16_t)(rec + 8));
            if (ordinary_object(ds, number, rec)) {
                if (flags & 0x4000) {
                    if (!(flags & 0x20)) {
                        if (native_modes & 1)
                            figure_remove_complete(g, rec);
                        else
                            event_push(EV_FIGURE_KILLED, rec, 0);
                        DS_U16(ds, 0x0386)++;
                    } else {
                        DS_U16(ds, 0x053C + 0x1A) = (uint16_t)(DS_U16(ds, 0x053C + 0x1A) + DS_U16(ds, BL_DAMAGE));
                    }
                } else if (DS_U8(ds, (uint16_t)(rec + 0x0A)) != 0xFF
                           && !(DS_U16(ds, (uint16_t)(rec + 0x0A)) & 0x8000)) {
                    if (take_damage(ds, rec))
                        debris_start(g, rec,
                                     record_mesh_number(ds, DS_U16(ds, (uint16_t)(rec + 6)), (uint16_t)(rec + 8)));
                }
            } else if (!(DS_U16(ds, (uint16_t)(rec + 0x0A)) & 0x8000)) {
                if (take_damage(ds, rec)) {
                    queue_blast(ds, rec);
                    if (DS_U16(ds, (uint16_t)(rec + 6)) & 0x2000) {
                        if (native_modes & 1)
                            figure_remove_complete(g, rec);
                        else
                            event_push(EV_FIGURE_KILLED, rec, 0);
                    } else {
                        /* the cell record this list record was copied from */
                        uint16_t source = DS_U16(ds, (uint16_t)((uint16_t)(rec - BL_FRAME_LIST) / 6 + BL_SOURCES));
                        far_set(g, DS_U16(ds, BL_SEG_CELLS), (uint16_t)(source + 0x0A), 0xFFFF);
                    }
                }
            }
        }
        rec = (uint16_t)(rec + 12);
    } while (--n);
}

/* Legacy callers keep their event boundary; damage-mode callers can remove figures now. */
void explosion_damage(Game *g, uint16_t record)
{
    explosion_damage_impl(g, record, 0);
}

void explosion_damage_native_figures(Game *g, uint16_t record)
{
    explosion_damage_impl(g, record, 1);
}

void explosion_damage_native(Game *g, uint16_t record)
{
    explosion_damage_impl(g, record, 3);
}

/* orig 0000:80B6   once per frame: every fourth frame the oldest queued blast goes off */
static void blast_queue_step_impl(Game *g, int native)
{
    uint8_t *ds = g->ds;
    if (DS_U16(ds, BL_QUEUE_COUNT) == 0)
        return;
    if (DS_U8(ds, BL_FRAME_COUNTER) & 3)
        return;
    explosion_damage_impl(g, BL_QUEUE, native ? 3 : 0);
    DS_U16(ds, BL_QUEUE_PTR) = (uint16_t)(DS_U16(ds, BL_QUEUE_PTR) - 12);
    if (--DS_U16(ds, BL_QUEUE_COUNT) == 0)
        return;
    uint16_t from = BL_QUEUE + 12, to = BL_QUEUE;
    for (uint16_t words = (uint16_t)(DS_U16(ds, BL_QUEUE_COUNT) * 6); words; words--) {
        uint8_t lo = DS_U8(ds, from), hi = DS_U8(ds, (uint16_t)(from + 1));
        DS_U8(ds, to) = lo;
        DS_U8(ds, (uint16_t)(to + 1)) = hi;
        from = (uint16_t)(from + 2);
        to = (uint16_t)(to + 2);
    }
}

/* Preserve the old event contract; composed gameplay uses native player/figure work. */
void blast_queue_step(Game *g)
{
    blast_queue_step_impl(g, 0);
}
void blast_queue_step_native(Game *g)
{
    blast_queue_step_impl(g, 1);
}
