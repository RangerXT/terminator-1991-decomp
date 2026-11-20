/* Draw-order control for the faces of one mesh. */
#include "term.h"

enum {
    OR_OUT_BUFFER = 0x57DA, /* u16: where a reordered face list is written */
    OR_GROUPS = 0x57DC,     /* group list: { u16 first_face; u16 face_count } */
    OR_GROUP_COUNT = 0x59DC,
    OR_ALT_BUFFER = 0x4E54,
};

/* orig 0000:2E59   in SI = mesh.  out BP = number of visible faces
 *
 * Splits the mesh's visible faces into groups. A face whose facing-table entry is 0 or FF
 * starts a group; a face with an entry of 1..7F (coplanar detail) joins the group before it.
 * Hidden faces are left out. Returns the address just past the last group entry in *end.
 *
 * Quirk kept from the original: if the first visible face is a detail face there is no group
 * to join, and the word just before the list (DS:57DA, the output buffer pointer) is
 * incremented instead.
 */
static uint16_t group_faces(uint8_t *ds, uint16_t mesh, uint16_t *end)
{
    DS_U16(ds, OR_GROUP_COUNT) = 0;
    uint16_t visible = 0;
    uint16_t flag = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    uint16_t out = OR_GROUPS;
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 2));
    uint16_t table = DS_U16(ds, (uint16_t)(mesh + 0x0A));
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));
    do {
        if (DS_U8(ds, flag) == 0) {
            uint8_t how = DS_U8(ds, table);
            visible++;
            if (how != 0 && !(how & 0x80)) {
                DS_U16(ds, (uint16_t)(out - 2))++;
            } else {
                DS_U16(ds, OR_GROUP_COUNT)++;
                DS_U16(ds, out) = face;
                DS_U16(ds, (uint16_t)(out + 2)) = 1;
                out = (uint16_t)(out + 4);
            }
        }
        face = (uint16_t)(face + 6 + 2 * DS_U16(ds, (uint16_t)(face + 4)));
        flag++;
        table++;
    } while (--count);
    *end = out;
    return visible;
}

/* Copies `n` consecutive faces from `src` to `dst`; returns the new write position. */
static uint16_t copy_faces(uint8_t *ds, uint16_t src, uint16_t dst, uint16_t n)
{
    do {
        uint16_t words = (uint16_t)(3 + DS_U16(ds, (uint16_t)(src + 4)));
        for (uint16_t i = 0; i < words; i++) {
            DS_U16(ds, dst) = DS_U16(ds, src);
            src = (uint16_t)(src + 2);
            dst = (uint16_t)(dst + 2);
        }
    } while (--n);
    return dst;
}

/* orig 0000:2D2A   in SI = mesh (working copy)
 *
 * Mesh header word 6 ("order") selects one face as a pivot: when order is N with
 * 0 < N < face count and face N-1 is hidden, the visible faces are regrouped (see
 * group_faces) and the groups are written out in reverse order, so that what the model
 * lists first is drawn last. The hidden flags are then cleared for the shorter list.
 * Nothing happens in the ground pass, for order 0, or for an order >= the face count.
 *
 * Returns 0. Returns -1 without doing anything for an order with the top bit set that is
 * still below the face count: the original has a depth-sorting branch for that
 * (0000:2DA5), but it can only be reached by a mesh with more than 32768 faces, so it is
 * dead code for every mesh in the game and is not translated.
 */
int mesh_order_faces(uint8_t *ds, uint16_t mesh)
{
    if (DS_U8(ds, DS_GROUND_PASS))
        return 0;
    uint16_t order = DS_U16(ds, (uint16_t)(mesh + 0x0C));
    if (order >= DS_U16(ds, (uint16_t)(mesh + 2)))
        return 0;
    if (DS_U16(ds, (uint16_t)(mesh + 6)) == DS_U16(ds, OR_OUT_BUFFER))
        DS_U16(ds, OR_OUT_BUFFER) = OR_ALT_BUFFER;
    if (order == 0)
        return 0;
    if (order & 0x8000)
        return -1;
    if (DS_U8(ds, (uint16_t)(order - 1 + DS_U16(ds, DS_FACE_HIDDEN_PTR))) == 0)
        return 0;

    uint16_t groups_end;
    uint16_t visible = group_faces(ds, mesh, &groups_end);
    DS_U16(ds, (uint16_t)(mesh + 2)) = visible;
    uint16_t groups = DS_U16(ds, OR_GROUP_COUNT);
    if (groups == 0)
        return 0;

    uint16_t dst = DS_U16(ds, OR_OUT_BUFFER);
    uint16_t g = groups_end;
    do {
        g = (uint16_t)(g - 4);
        dst = copy_faces(ds, DS_U16(ds, g), dst, DS_U16(ds, (uint16_t)(g + 2)));
    } while (--groups);

    DS_U16(ds, (uint16_t)(mesh + 6)) = DS_U16(ds, OR_OUT_BUFFER);
    uint16_t flag = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    for (uint16_t n = DS_U16(ds, (uint16_t)(mesh + 2)); n; n--) {
        DS_U8(ds, flag) = 0;
        flag++;
    }
    return 0;
}
