/* Target tracking: which objects the weapon sights could lock on to this frame. */
#include "term.h"

enum {
    TG_ACTIVE = 0x118E, /* u8: non-zero while targets are being collected */
    TG_PLAYER_PTR = 0x03A0,
    TG_OBJECT_ID = 0x57C4, /* u16: word +8 of the draw record */
    TG_SPECIAL_ID = 0x9A64,
    TG_SPECIAL_REC = 0xAAF2,
    TG_PEOPLE = 0x0DF0, /* 12-byte records */
    TG_TABLE = 0xB18E,  /* 18-byte target entries */
    TG_COUNT = 0xB64E,
    TG_MAX_X = 0xB650,
    TG_MIN_X = 0xB652,
    TG_MAX_Y = 0xB654,
    TG_MIN_Y = 0xB656,
    TG_HEIGHT_DIFF = 0xB65C,
    TG_CAR_PTR = 0xDE4C,
    TG_CAR_PTR_2 = 0xDE4E,
};

/* orig 0000:5EEE   in AX,BX = one point (x, z), CX,DX = the other   out AX
 * Quick distance estimate: the larger of |dx|, |dz| plus a quarter of the smaller. */
uint16_t approx_distance(int16_t x1, int16_t z1, int16_t x2, int16_t z2)
{
    int16_t a = (int16_t)(x1 - x2), b = (int16_t)(z1 - z2);
    uint16_t ua = (uint16_t)(a < 0 ? -a : a), ub = (uint16_t)(b < 0 ? -b : b);
    if (ua >= ub) {
        uint16_t t = ua;
        ua = ub;
        ub = t;
    }
    return (uint16_t)((ua >> 2) + ub);
}

/* orig 0000:A2D5   called for each object after projection.
 *
 * While target collection is active, an object that is a vehicle (object flag 0x20), or
 * has flag 0x2000 or 0x4000, gets an entry in the target table:
 *   +0  address of the object's own record     +2  its id
 *   +4  twice its estimated 3D distance from the player
 *   +6  min x, +8 max x, +10 min y, +12 max y of its projected points
 *
 * `al` is the value the AL register holds on entry; the return value is what the original
 * leaves in AL, which a later stage can pick up (see mesh_face_visibility).
 */
uint8_t track_target(uint8_t *ds, uint8_t al)
{
    if (DS_U8(ds, TG_ACTIVE) == 0)
        return al;
    uint16_t flags = DS_U16(ds, DS_OBJ_FLAGS);
    uint16_t rec;
    al = (uint8_t)flags;
    if (flags & 0x20)
        rec = DS_U16(ds, (flags & 4) ? TG_CAR_PTR_2 : TG_CAR_PTR);
    else if (flags & 0x6000)
        rec = TG_PEOPLE;
    else
        return al;

    uint16_t entry = (uint16_t)(TG_TABLE + 0x12 * (uint8_t)DS_U16(ds, TG_COUNT));
    if (!(DS_U16(ds, DS_OBJ_FLAGS) & 0x20)) {
        uint16_t id = DS_U16(ds, TG_OBJECT_ID);
        if (id == DS_U16(ds, TG_SPECIAL_ID)) {
            DS_U16(ds, (uint16_t)(entry + 2)) = id;
            rec = TG_SPECIAL_REC;
        } else {
            id >>= 1;
            DS_U16(ds, (uint16_t)(entry + 2)) = id;
            rec = (uint16_t)(rec + (uint8_t)id * 12);
        }
    }
    DS_U16(ds, entry) = rec;

    int16_t ox = DS_I16(ds, rec), oz = DS_I16(ds, (uint16_t)(rec + 4));
    uint16_t player = DS_U16(ds, TG_PLAYER_PTR);
    int16_t dy = (int16_t)(DS_I16(ds, (uint16_t)(rec + 2)) - DS_I16(ds, (uint16_t)(player + 2)));
    if (dy < 0)
        dy = (int16_t)-dy;
    DS_I16(ds, TG_HEIGHT_DIFF) = dy;
    int16_t flat = (int16_t)approx_distance(DS_I16(ds, player), DS_I16(ds, (uint16_t)(player + 4)), ox, oz);
    int16_t big = flat, small = dy;
    if (big < small) {
        big = dy;
        small = flat;
    }
    DS_U16(ds, (uint16_t)(entry + 4)) = (uint16_t)(2 * (uint16_t)(big + ((uint16_t)small >> 2)));

    uint16_t p = DS_U16(ds, DS_VERTEX_BUFFER_2D_PTR);
    DS_I16(ds, TG_MAX_X) = DS_I16(ds, p);
    DS_I16(ds, TG_MIN_X) = DS_I16(ds, p);
    DS_I16(ds, TG_MAX_Y) = DS_I16(ds, (uint16_t)(p + 2));
    DS_I16(ds, TG_MIN_Y) = DS_I16(ds, (uint16_t)(p + 2));
    while (p != DS_U16(ds, DS_VERTEX_BUFFER_END)) {
        int16_t x = DS_I16(ds, p), y = DS_I16(ds, (uint16_t)(p + 2));
        if (x >= DS_I16(ds, TG_MAX_X))
            DS_I16(ds, TG_MAX_X) = x;
        if (DS_I16(ds, TG_MIN_X) >= x)
            DS_I16(ds, TG_MIN_X) = x;
        if (y >= DS_I16(ds, TG_MAX_Y))
            DS_I16(ds, TG_MAX_Y) = y;
        if (DS_I16(ds, TG_MIN_Y) >= y)
            DS_I16(ds, TG_MIN_Y) = y;
        p = (uint16_t)(p + 6);
    }
    DS_I16(ds, (uint16_t)(entry + 6)) = DS_I16(ds, TG_MIN_X);
    DS_I16(ds, (uint16_t)(entry + 8)) = DS_I16(ds, TG_MAX_X);
    DS_I16(ds, (uint16_t)(entry + 10)) = DS_I16(ds, TG_MIN_Y);
    DS_I16(ds, (uint16_t)(entry + 12)) = DS_I16(ds, TG_MAX_Y);
    DS_U16(ds, TG_COUNT)++;
    return (uint8_t)DS_U16(ds, TG_MAX_Y);
}
