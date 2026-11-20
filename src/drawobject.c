/* One object, from its camera-space vertices to pixels. */
#include "term.h"

enum {
    DO_STAGE = 0x59E2, /* u16: progress marker the original prints if its sanity check fails */
    DO_FACES_DRAWN = 0x50B1,
};

/* orig 0000:2BBD   the original's sanity check, called between stages. If it fails the game
 * switches to text mode, prints the stage marker and hangs. Returns 1 where it would. */
int pipeline_sanity_failed(const uint8_t *ds)
{
    uint16_t player = DS_U16(ds, DS_PLAYER);
    return DS_U16(ds, 0x50B4) >= 0x40 || DS_U16(ds, (uint16_t)(player + 0x1E)) >= 0xC0
           || DS_U16(ds, (uint16_t)(player + 0x20)) >= 0x80 || DS_U16(ds, player) >= 0x5DC
           || DS_U16(ds, (uint16_t)(player + 4)) >= 0x5DC || DS_U8(ds, 0x50B6) >= 0x81;
}

/* orig 0000:2AF2   in BX = mesh (working copy in DS, vertices already in camera space)
 *
 * Runs the stages in order: clear the hidden flags, clip against the camera plane, project,
 * note the object as a possible target, find hidden faces (or, for a mirrored object,
 * reverse them all), apply the draw-order control, clip to the view window and draw.
 *
 * Returns 0 if the object was handled normally and 1 if it was found to be off screen, in
 * which case bit 3 of the draw record's flags is set so later passes can skip it. Returns
 * -2 where the original's sanity check would have stopped the game.
 *
 * `ds_segment_low` is the low byte of the data segment's run-time address. The original
 * leaves that in the AL register after projecting when some point is on screen, and one
 * path of the hidden-face stage (objects with flag 0x80) reads AL without setting it; pass
 * the same value to reproduce a given run exactly.
 */
int draw_object(uint8_t *ds, uint8_t *planes, uint16_t mesh, uint8_t ds_segment_low)
{
    uint16_t flag = DS_U16(ds, DS_FACE_HIDDEN_PTR);
    for (uint16_t n = DS_U16(ds, (uint16_t)(mesh + 2)); n; n--) {
        DS_U8(ds, flag) = 0;
        flag++;
    }
    DS_U16(ds, DO_STAGE) = 0xDF;
    mesh_clip_near(ds, mesh);
    if (pipeline_sanity_failed(ds))
        return -2;
    DS_U16(ds, DO_STAGE) = 0xE0;
    if (project_vertices(ds))
        goto off_screen;

    /* what the projection leaves in AL */
    uint8_t al;
    if (DS_U8(ds, DS_ANY_POINT_INSIDE)) {
        al = ds_segment_low;
    } else {
        al = (uint8_t)(DS_U8(ds, DS_OUTCODE_UNION) & 3);
        if (al < 3)
            al = DS_U8(ds, DS_OUTCODE_UNION);
    }

    DS_U16(ds, DO_STAGE) = 0xE1;
    if (pipeline_sanity_failed(ds))
        return -2;
    al = track_target(ds, al);
    DS_U16(ds, DO_STAGE) = 0xE2;

    if (!(DS_U8(ds, DS_GROUND_PASS) && DS_U16(ds, (uint16_t)(mesh + 2)) == 1)) {
        if (DS_U16(ds, DS_OBJ_FLAGS) & 0x4000) {
            mesh_reverse_all_faces(ds, mesh);
            DS_U16(ds, DO_STAGE) = 0xE3;
        } else {
            mesh_face_visibility(ds, mesh, al);
            DS_U16(ds, DO_STAGE) = 0xE4;
        }
        DS_U16(ds, DO_STAGE) = 0xE5;
    }

    mesh_order_faces(ds, mesh);
    DS_U16(ds, DO_STAGE) = 0xE6;
    if (DS_U16(ds, (uint16_t)(mesh + 2)) != 0) {
        mesh_clip_window(ds, mesh);
        DS_U16(ds, DO_STAGE) = 0xE7;
        DS_U8(ds, DO_FACES_DRAWN) = 0;
        draw_visible_faces(ds, planes, mesh);
        DS_U16(ds, DO_STAGE) = 0xE8;
        if (DS_U8(ds, DO_FACES_DRAWN) == 0 && DS_U8(ds, DS_GROUND_PASS))
            goto off_screen;
    }
    DS_U16(ds, DO_STAGE) = 0xE9;
    return 0;

off_screen: {
    uint16_t record = DS_U16(ds, DS_DRAW_RECORD);
    DS_U16(ds, (uint16_t)(record + 6)) |= 8;
    DS_U16(ds, DO_STAGE) = 0xEA;
    return 1;
}
}
