/* Per-object stages of the 3D pipeline. */
#include "term.h"

/* orig 0000:29C4   in BX = mesh header (in DS)
 *
 * Turns the object's vertices (already copied into the vertex buffer) into camera space:
 *   1. y += object y + camera y
 *   2. apply the map record's quarter turns: one turn maps (x, z) to (-z, x)
 *   3. add the object position, subtract the camera position (x and z)
 *   4. rotate about the vertical axis by the camera heading
 * It also counts the vertices that end up behind the camera (z < 0).
 *
 * In map view (DS:7AB6 set, the picture of the surroundings seen from above) step 4 is the
 * 3 x 3 matrix instead (matrix_apply), which changes y as well. Quirk kept from the
 * original: that path leaves the new y in the register that holds the behind-the-camera
 * count, so the "count" that comes out is the low byte of the last vertex's y, plus one if
 * that vertex is behind the camera.
 *
 * Always returns 0 (it used to return -1 for map view before that path was translated).
 */
int object_transform_vertices(uint8_t *ds, uint16_t mesh)
{
    if (DS_U8(ds, DS_GROUND_PASS)) {
        if (!DS_U8(ds, DS_FORCE_REDO)) {
            if (DS_U16(ds, DS_OBJ_FLAGS) & 8) { /* already transformed this frame */
                DS_U16(ds, DS_VERTS_BEHIND) = DS_U16(ds, mesh + 4);
                return 0;
            }
        } else {
            uint16_t record = DS_U16(ds, DS_DRAW_RECORD);
            DS_U16(ds, record + 6) &= 0xFFF7;
        }
    }
    unsigned turns = DS_U8(ds, DS_OBJ_QUARTER_TURNS);
    uint16_t count = DS_U16(ds, mesh + 4);
    uint16_t v = DS_U16(ds, DS_VERTEX_BUFFER_PTR);
    uint16_t heading = DS_U16(ds, DS_CAM_HEADING);
    uint8_t behind = 0;

    do { /* LOOP: a count of 0 means 65536 */
        DS_I16(ds, v + 2) = (int16_t)(DS_I16(ds, v + 2) + (int16_t)(DS_I16(ds, DS_OBJ_Y) + DS_I16(ds, DS_CAM_Y)));
        int16_t x = DS_I16(ds, v), z = DS_I16(ds, v + 4);
        if (turns >= 2) {
            z = (int16_t)-z;
            x = (int16_t)-x;
        }
        if (turns & 1) {
            int16_t t = x;
            x = (int16_t)-z;
            z = t;
        }
        x = (int16_t)(x + DS_I16(ds, DS_OBJ_X) - DS_I16(ds, DS_CAM_X));
        z = (int16_t)(z + DS_I16(ds, DS_OBJ_Z) - DS_I16(ds, DS_CAM_Z));
        if (DS_U8(ds, DS_MAP_VIEW)) {
            int16_t y = DS_I16(ds, v + 2);
            matrix_apply(ds, &x, &y, &z);
            DS_I16(ds, v + 2) = y;
            behind = (uint8_t)y; /* MOV DX,BX overwrites the count */
        } else {
            rotate_xz(ds, &x, &z, heading);
        }
        DS_I16(ds, v) = x;
        DS_I16(ds, v + 4) = z;
        if (z < 0)
            behind++;
        v = (uint16_t)(v + 6);
    } while (--count);

    DS_U8(ds, DS_ANY_VERT_BEHIND) = behind;
    DS_U16(ds, DS_VERTS_BEHIND) = behind;
    return 0;
}
