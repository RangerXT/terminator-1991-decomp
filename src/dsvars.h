/* Named variables of the game's main data segment (file segment 5C27).
 *
 * The C code keeps all game state where the original keeps it, so a variable is an offset
 * into the data segment and is read with DS_U8 / DS_U16 / DS_I16 (term.h):
 *
 *     if (DS_U8(ds, DS_OPPONENT_ACTIVE))  ...
 *     if (DS_U8(ds, KEY_DOWN(SC_ENTER)))  ...
 *
 * Each name is backed by evidence: the routines that read and write the variable (see
 * `python tools/dsxref.py <offset>`), the notes in RE_NOTES.md, and how the translated code
 * uses it. A variable whose role is not yet clear is left as a number in the code rather
 * than given a guessed name. Several variables are shared scratch: the comment then names
 * the main role and the other users.
 *
 * Widths: u8 / u16 / i16 are bytes, words and signed words; "far" is a 4-byte offset:segment
 * pointer; "seg" is a segment number. The names also appear, in lower case without DS_, in
 * the disassembly listing (tools/names.py, VARS).
 */
#ifndef DSVARS_H
#define DSVARS_H

enum {
    /* ---- tables */
    DS_SINE_TABLE = 0x4188,   /* i16[640]: sin(i * 2pi / 512) * 32767; cosine = entry i + 128 */
    DS_DITHER_PAIRS = 0x4A6D, /* u16[120]: low byte = second colour, high byte = first */

    /* ---- actors: the records at 0x04D4 and 0x0508 are the two playable characters, 0x053C
     * is a third actor; each holds x, y, z, heading, head turn, ... */
    DS_PLAYER = 0x03A0,           /* u16: offset of the player's actor record (0x04D4 or 0x0508) */
    DS_VEHICLE = 0x04BA,          /* u16: offset of the vehicle record in use; word +6 = its heading */
    DS_OPPONENT_ACTIVE = 0x1153,  /* u8: non-zero while the opponent is in the scene */
    DS_COMPANION_ACTIVE = 0x1154, /* u8: non-zero while the companion is in the scene */
    DS_OPPONENT_X = 0xDE52,       /* i16: opponent position (local to the player's cell) */
    DS_OPPONENT_Z = 0xDE54,       /* i16 */
    DS_COMPANION_X = 0xE3EC,      /* i16: companion position (moved by companion_move) */
    DS_COMPANION_Z = 0xE3EE,      /* i16 */
    DS_FIGURE_COUNT = 0x119A,     /* u16: figures in the records at 0x0DF0 */
    DS_GUIDED_COUNT = 0x11A0,     /* u16: guided-projectile entries (18 bytes each) at 0x10F0 */
    DS_PRACTICE_MODE = 0x0345,    /* u8: set by the main menu's practice option */
    DS_LINK_GAME = 0x01DE,        /* u8: two-player serial-link game (set at startup; every routine of
                                       segment 151B tests it) */
    DS_DIFFICULTY = 0x03F0,       /* u16: difficulty level (scales opponent and companion behaviour, score) */
    DS_FUEL = 0x5F72,             /* u16: fuel of the vehicle in use, 0..100 */
    DS_SCREEN_NOISE = 0x1172,     /* u16: frames of screen noise left after the player is hit */
    DS_DETAIL = 0xABCA,           /* u16: detail level (Alt+1/2/3): 0 everything, 1 up to 3072, 2 up to 2048 */
    DS_FRAME_COUNTER = 0x020C,    /* u16: counts frames (main loop); some work runs every 4th frame */

    /* ---- the main loop (src/frame.c) */
    DS_WARNING_COUNTDOWN = 0x0200,  /* u16: frames left of an on-screen warning (scene_warning); input
                                        waits meanwhile; when it runs out the player is down (4) */
    DS_RELOAD_COUNTDOWN = 0x8096,   /* u8: frames left of the weapon-reload overlay (20 per reload);
                                        input waits meanwhile */
    DS_PLAYER_DOWN = 0x1156,        /* u8: ends the session: 2 the player was killed, 4 a warning ran out */
    DS_MISSION_OVER = 0x1159,       /* u8: ends the session: 1 the mission was lost (companion, map edge,
                                        ...), 0x55 the wrong symbol was chosen */
    DS_WRONG_SYMBOL_TIMER = 0xEA2E, /* u16: frames until "The game is now over because you selected the
                                         wrong symbol" (text 0x0213) */
    DS_BORDER_FLASH = 0x7BD5,       /* u8: set when the player is hit (border flashes); reset at frame end */
    DS_PALETTE_RELOAD = 0x01DD,     /* u8: reload the game palette (DS:1510) at frame end */
    DS_CAR_EXIT_MESSAGE = 0x01DC,   /* u8: show "Leaving a moving car hurts" (text 0x0343) at frame end */
    DS_TRAVEL_MESSAGE = 0xE1F2,     /* u8: show "Your Fast Travel was not completed" (text 0x0625) next frame */
    DS_MAP_KEY_FLAG = 0xE1F0,       /* u8: set when fast travel (F) is chosen on the map, cleared every
                                         frame by 0000:CA46; nothing in the listing reads it */
    DS_MAP_ACTION = 0xE25A,         /* u8: what the map screen ended with: 'F' fast travel, 'H' homing,
                                         0 none (Esc) */
    DS_HOMING = 0xE1EF,             /* u8: the compass points at the place chosen with H on the map */
    DS_IN_BATTLE = 0x115A,          /* u8: set by player_update_threat; no fast travel meanwhile */
    DS_SHOP_COUNT = 0x72B2,         /* u16: shops in the loaded window; their 11-byte records are at 0x5CE4 */

    /* ---- the gameplay menus (src/gamemenus.c) */
    DS_JOYSTICK = 0x5A4F,            /* u8: the joystick is in use (GAME MENU, joystick on/off) */
    DS_COMPANION_ORDER = 0x11BE,     /* u16: what Sarah was told (Q): 0 stay, 1 run away, 2 follow */
    DS_FACILITY_CONFIRMED = 0xA87B,  /* u8: facility_confirm's answer, FF yes */
    DS_MENU_YES = 0x7810,            /* u8: the answer of the "Are you sure ?" menu, 1 yes */
    DS_SPECIAL_MENU_READY = 0xAAAA,  /* u8: the special-action menu has entries (inventory_equipment_menu) */
    DS_SPECIAL_MENU_HEIGHT = 0xAAAB, /* u16: its height in rows, 5 + 2 per entry */
    DS_CASH = 0x117E,                /* u16: the player's money */
    DS_INVENTORY_CATEGORY = 0x792A,  /* u8: the category being viewed or moved: 1-5, FF misc. */
    DS_INVENTORY_END = 0x03A2,       /* u16: the end of the player's item list (6-byte records at 0x05B0) */
    DS_ITEMS_FROM = 0x03FE,          /* u16: the list items are moved from (0x05B0 the player's, 0x085C Sarah's) */
    DS_ITEMS_TO = 0x0400,            /* u16: the list they go to */
    DS_EXCHANGE_TAKE = 0x0252,       /* u8: FF while taking from Sarah, 0 while giving */
    DS_SARAH_LOAD = 0x0402,          /* u16: the weight Sarah carries (below 35) */
    DS_CARRIED_WEIGHT = 0x116C,      /* u16: the weight the player carries */
    DS_DROPPED_NEXT = 0x03FC,        /* u16: next slot of the ring of 20 dropped items at 0x0253 */
    DS_PALETTE_TABLE = 0x1510,       /* u8[16]: the game palette, EGA attribute registers 0-15 (loaded by
                                        0000:7AB6); the border colour is one of its entries (0000:0A4F) */

    /* ---- weapons and sights */
    DS_WEAPON = 0x118E,        /* u8: 1-based index of the selected weapon record (6 bytes each at
                                       0x0570); 0 = none. Targets are collected while it is non-zero */
    DS_WEAPON_SLOT = 0x1190,   /* u16: 1-based HUD slot of the selected weapon */
    DS_TARGET_RECORD = 0x0418, /* u16: record of the selected target, 0 = none */
    DS_SIGHT_X = 0x11A2,       /* i16: screen position of the sight */
    DS_SIGHT_Y = 0x11A4,       /* i16 */
    DS_ZOOM_1 = 0x114D,        /* u8: first zoom step (halves projection depth; not in ground pass 2) */
    DS_ZOOM_2 = 0x114F,        /* u8: second zoom step */

    /* ---- the 3D view and the draw lists */
    DS_GROUND_PASS = 0x00BB, /* u8: non-zero while the flat ground meshes (.BIG) are drawn */
    DS_VIEW_LEFT = 0x03F4,   /* i16: view window, inclusive screen coordinates */
    DS_VIEW_TOP = 0x03F6,
    DS_VIEW_RIGHT = 0x03F8,
    DS_VIEW_BOTTOM = 0x03FA,
    DS_VIEW_CENTRE_X = 0x0408, /* i16: screen position of the optical centre */
    DS_VIEW_CENTRE_Y = 0x040A,
    DS_VIEW_HEIGHT = 0x11C6,       /* u16: rows of the 3D view; polygon fills stop at row (this + 8) */
    DS_CAMERA_MODE = 0x11CA,       /* u8: 0 normal, 1 never set, 2 full-height view */
    DS_FORCE_REDO = 0x50B0,        /* u8: non-zero = ignore the "already off screen" record flag */
    DS_MAP_VIEW = 0x7AB6,          /* u8: non-zero while the overhead-map page is drawn */
    DS_DRAW_LIST = 0x01FE,         /* u16: first record of the sorted object list */
    DS_DRAW_COUNT = 0x50AC,        /* u16: records in the object list */
    DS_GROUND_COUNT = 0x91D8,      /* u16: records in the ground list at 0x2836 */
    DS_VISIBLE_COUNT = 0x7240,     /* u16: records in the visible-object list at 0x5F80 */
    DS_VISIBLE_CELL = 0x7242,      /* u16: cell the visible-object list was built for (FFFE forces a rebuild) */
    DS_LOADED_DEF_COUNT = 0x72B4,  /* u16: LA.DEF meshes loaded for the cell window */
    DS_VEHICLE_COUNT = 0x72B0,     /* u16: cars listed while loading the cell window */
    DS_EXTRA_COUNT = 0x04C6,       /* u16: non-map objects (14-byte entries behind the far pointer at 0x1200) */
    DS_OUTCODE_UNION = 0x4B70,     /* u8: OR of the outcodes of projected points (1 left, 2 right, 4 top, 8 bottom) */
    DS_VERTEX_BUFFER_END = 0x4B86, /* u16: offset just past the last 3D vertex */
    DS_ANY_POINT_INSIDE = 0x76DE,  /* u8: non-zero if a projected point is inside the view window */
    DS_VERTEX_BUFFER_2D_PTR = 0x40DE, /* u16: offset of the projected points (x, y words, 6-byte stride) */
    DS_FACE_HIDDEN_PTR = 0x40E0,      /* u16: offset of the per-face hidden flags of the current mesh */
    DS_VERTEX_BUFFER_PTR = 0x3CDC,    /* u16: offset of the working vertex buffer (x, y, z words) */
    DS_ANY_VERT_BEHIND = 0x4B6E,      /* u8: number of vertices with z < 0, low byte */
    DS_OBJ_QUARTER_TURNS = 0x50AF,    /* u8: obj_flags & 3 */
    DS_VERTS_BEHIND = 0x57BA,         /* u16: number of vertices behind the camera */
    DS_CAM_HEADING = 0x57BC,          /* u16: 0..511 */
    DS_CAM_X = 0x57BE,
    DS_CAM_Y = 0x57C0,
    DS_CAM_Z = 0x57C2,
    DS_OBJ_FLAGS = 0x57C6, /* u16: word +6 of the 12-byte draw record */
    DS_OBJ_X = 0x57CC,
    DS_OBJ_Y = 0x57CE,
    DS_OBJ_Z = 0x57D0,
    DS_DRAW_RECORD = 0x59DE, /* u16: offset of the draw-list record being drawn */

    /* ---- positions being worked on (shared scratch) */
    DS_POINT_X = 0xB662, /* i16: world position being moved, placed or tested (movement, placement,
                                       collision, targeting) */
    DS_POINT_Z = 0xB666, /* i16 */
    DS_PROBE_Z = 0x1232, /* i16: z (or grid row) of the point the collision routines test; its x is
                                       DS_PEN_X */

    /* ---- drawing */
    DS_DRAW_PAGE = 0x1234,       /* u16: video offset of the page being drawn */
    DS_PAGE_SHOWN = 0x122A,      /* u16: index of the page on display */
    DS_PAGE_DRAWN = 0x122C,      /* u16: index of the page being drawn */
    DS_PEN_X = 0x122E,           /* u16: current drawing position (also x of the collision test point) */
    DS_PEN_Y = 0x1230,           /* u16 */
    DS_FILL_COLOUR = 0x468C,     /* u8: 0-15 solid, 16-135 dither pair index + 16 */
    DS_OUTLINE_COLOUR = 0x468D,  /* u8 */
    DS_SCREEN_STRIDE = 0x9A72,   /* u16: bytes per screen row (40 in 320-pixel modes, 80 in 640) */
    DS_TEXT_COLOUR = 0xE40F,     /* u8: colour of 8x8 text */
    DS_TEXT_COLUMN = 0xE412,     /* u16: text position: byte column */
    DS_TEXT_ROW = 0xE414,        /* u8: text position: character row */
    DS_NUMBER_COLOUR = 0xE16A,   /* u8: colour of HUD numbers and text */
    DS_NUMBER_DIGITS = 0xE172,   /* u8: digits a HUD number is drawn with */
    DS_BOX_X = 0x7758,           /* u8: text box position */
    DS_BOX_Y = 0x775A,           /* u8 */
    DS_MENU_ITEM = 0x784E,       /* u16: highlighted menu item */
    DS_POINTER_X = 0x7C90,       /* u16: map / menu pointer position */
    DS_POINTER_Y = 0x7C92,       /* u16 */
    DS_FACILITY_SCREEN = 0xADCF, /* u8: non-zero while a facility or front-end screen is up (shop, hospital,
                                       phone book, ratings...); selects how they draw */

    /* ---- keyboard: key_down[scancode] at 0x5BD9, see KEY_DOWN below */
    DS_KEYBUF_READ = 0x5B6E,   /* u16: next character to read from the ring buffer 0x5B70..0x5BD3 */
    DS_KEYBUF_COUNT = 0x5BD4,  /* u16: characters waiting in the ring buffer */
    DS_LAST_SCANCODE = 0x5BD8, /* u8 */
    DS_KEYBUF_WRITE = 0x5B6C,  /* u16: where the interrupt puts the next character */
    DS_KEY_BREAK_NEXT = 0x5BD6, /* u16: FFFF after an F0 byte, so the next scancode counts as a release */
    DS_KEYS_UNBUFFERED = 0x5B6A, /* u16: non-zero: presses are not buffered (only ever cleared; the store at
                                    3897 that would set it is unreachable) */
    DS_KEY_TABLE = 0x5A6A,     /* u8[128]: scancode -> character, and at 0x5AEA with Shift */
    DS_F12_PRESSED = 0x5A50,   /* u8: F12 was pressed (the main loop then toggles chaining to the BIOS) */

    /* ---- segments and far buffers */
    DS_FILE_BUFFER = 0x91BC,     /* far: buffer files are loaded into (offset; segment at 0x91BE) */
    DS_FILE_BUFFER_SEG = 0x91BE, /* seg */
    DS_LOAD_BUFFER = 0x91C0,     /* far: buffer for HUD and menu images (offset; segment at 0x91C2) */
    DS_WORK_BUFFER = 0x91C4,     /* far: work buffer (offset; segment at 0x91C6) */
    DS_WORK_BUFFER_SEG = 0x91C6, /* seg */
    DS_UNPACK_SRC_SEG = 0x850E,  /* seg: where image unpacking reads from */
    DS_UNPACK_DST_SEG = 0x8510,  /* seg: where image unpacking writes to */
    DS_SEG_COLLISION = 0x91B2,   /* seg: 192 x 192 byte collision map */
    DS_SEG_MODELS = 0x91CE,      /* seg: figure and vehicle meshes */
    DS_SEG_OBJECTS = 0x91D0,     /* seg: LA.DEF meshes of the cell window */
    DS_SEG_GROUND = 0x91D2,      /* seg: ground meshes and placements of the cell window */
    DS_SEG_CELLS = 0x91D4,       /* seg: 24 x 24 cell window */
    DS_SEG_DEBRIS = 0x96DC,      /* seg: debris pieces */
    DS_SEG_SCREEN = 0xADDC,      /* seg: video memory (A000) */

    /* ---- collision map building and testing (11BC:1FCC-258D) */
    DS_GRID_X = 0x9128,       /* u16: collision-grid column of the object or point */
    DS_GRID_Z = 0x912A,       /* u16: collision-grid row */
    DS_STAMP_X = 0x9136,      /* u16: first column the stamp covers (also scratch for figure spawning) */
    DS_STAMP_Z = 0x9138,      /* u16: first row (also scratch for figure spawning) */
    DS_STAMP_VALUE = 0x913E,  /* u16: value stamped: object number + 1 */
    DS_STAMP_HALF_W = 0x9142, /* u16: LA.BMP record: half width, in 16-unit cells */
    DS_STAMP_HALF_H = 0x9144, /* u16: half height */
    DS_STAMP_W = 0x9146,      /* u16: width, after clipping to the grid */
    DS_STAMP_H = 0x9148,      /* u16: height, after clipping */
    DS_GRID_CELL_X = 0x9152,  /* i16: x of the map cell being stamped, relative to the player's cell */
    DS_GRID_CELL_Z = 0x9154,  /* i16: z */
};

/* key_down[scancode]: FF while the key is held (set by the keyboard interrupt 0000:37E3).
 * The interrupt copies Left Shift into the Right Shift entry, so KEY_DOWN(SC_RSHIFT) means
 * either Shift; the joystick code also writes some entries. */
#define DS_KEY_DOWN        0x5BD9
#define KEY_DOWN(scancode) (DS_KEY_DOWN + (scancode))

/* PC keyboard scancodes (set 1) of the keys the game reads */
enum {
    SC_ESC = 0x01,
    SC_1 = 0x02,
    SC_2 = 0x03,
    SC_3 = 0x04,
    SC_MINUS = 0x0C,
    SC_EQUALS = 0x0D,
    SC_BACKSPACE = 0x0E,
    SC_TAB = 0x0F,
    SC_Q = 0x10,
    SC_W = 0x11,
    SC_E = 0x12,
    SC_U = 0x16,
    SC_P = 0x19,
    SC_RBRACKET = 0x1B,
    SC_ENTER = 0x1C,
    SC_CTRL = 0x1D,
    SC_S = 0x1F,
    SC_D = 0x20,
    SC_F = 0x21,
    SC_H = 0x23,
    SC_K = 0x25,
    SC_L = 0x26,
    SC_BACKSLASH = 0x2B,
    SC_Z = 0x2C,
    SC_X = 0x2D,
    SC_B = 0x30,
    SC_N = 0x31,
    SC_M = 0x32,
    SC_LSHIFT = 0x2A,
    SC_RSHIFT = 0x36,
    SC_ALT = 0x38,
    SC_SPACE = 0x39,
    SC_F9 = 0x43,
    SC_F10 = 0x44,
    SC_UP = 0x48,
    SC_LEFT = 0x4B,
    SC_RIGHT = 0x4D,
    SC_DOWN = 0x50,
    SC_PGDN = 0x51,
    SC_DEL = 0x53,
    SC_F12 = 0x58,
};

#endif
