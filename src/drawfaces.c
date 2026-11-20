/* Drawing the faces of a prepared mesh. */
#include "term.h"

enum {
    DF_FILL_COLOUR = 0x468C,
    DF_OUTLINE_COLOUR = 0x468D,
    DF_FACES_DRAWN = 0x50B1, /* u8: counts faces drawn for the current object */
    DF_FACE_FLAGS = 0x7744,
    DF_COLOUR_TABLE = 0x7756, /* u16: 0, or offset of a 16-entry colour translation table */
};

/* orig 0000:482B   in BX = mesh (working copy, after clipping)
 *
 * For every face whose hidden flag is clear: takes its colours (optionally through the
 * translation table at DS:[7756]), fills it if face flag bit 0 is set, and if bit 1 is set
 * draws its outline in the second colour.
 *
 * Quirk kept from the original: with a translation table active and a dithered fill colour
 * (16 or more), the outline colour is looked up with BX still pointing at the face rather
 * than at the table.
 */
uint32_t draw_visible_faces_dx(uint8_t *ds, uint8_t *planes, uint16_t mesh, uint32_t dx)
{
    uint16_t flag = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    uint16_t count = DS_U16(ds, (uint16_t)(mesh + 2));
    uint16_t face = DS_U16(ds, (uint16_t)(mesh + 6));

    do {
        if (DS_U8(ds, flag) == 0) {
            DS_U8(ds, DF_FACES_DRAWN)++;
            uint8_t colour = DS_U8(ds, face), second = DS_U8(ds, (uint16_t)(face + 1));
            DS_U8(ds, DF_FILL_COLOUR) = colour;
            DS_U8(ds, DF_OUTLINE_COLOUR) = second;
            if (DS_U16(ds, DF_COLOUR_TABLE) != 0) {
                uint16_t table = face; /* BX as the original leaves it */
                if (colour < 0x10) {
                    table = DS_U16(ds, DF_COLOUR_TABLE);
                    colour = DS_U8(ds, (uint16_t)(table + colour));
                }
                DS_U8(ds, DF_FILL_COLOUR) = colour;
                DS_U8(ds, DF_OUTLINE_COLOUR) = DS_U8(ds, (uint16_t)(table + second));
            }
            uint16_t flags = DS_U16(ds, (uint16_t)(face + 2));
            DS_U16(ds, DF_FACE_FLAGS) = flags;
            uint32_t result = polygon_face_registers(ds, planes, face + 4, flags & 1);
            dx = result >> 16;
            if ((int16_t)result >= 0 && (flags & 2)) {
                DS_U8(ds, DF_FILL_COLOUR) = DS_U8(ds, DF_OUTLINE_COLOUR);
                dx = polygon_outline_dx(ds, planes, (uint16_t)dx);
            }
        }
        flag++;
        face = (uint16_t)(face + 6 + 2 * DS_U16(ds, (uint16_t)(face + 4)));
    } while (--count);
    return dx;
}

void draw_visible_faces(uint8_t *ds, uint8_t *planes, uint16_t mesh)
{
    (void)draw_visible_faces_dx(ds, planes, mesh, 0);
}
