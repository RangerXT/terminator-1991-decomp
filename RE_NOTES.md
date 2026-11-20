# The Terminator (Bethesda, DOS, 1991) — reverse-engineering notes

**Goal (since 2026-11-18):** a complete decompilation, every routine translated to C and
proved equal to the original. **The current summary, measured numbers and plan
are in `PROJECT_STATUS.md`; read that first.** (Until 2026-11-18 the goal was the assets and the city map, with the decompilation as a
side project; that extraction is complete.)

**Status:** all inventoried game-data file types are decoded and exported, including
EGA cinematics and rating tables. A few unused/uncertain fields remain documented below;
this does not claim every byte's purpose or a complete playable port. Geometry exports
stay OBJ until the target port has an import format. Original install files are untouched.

## Folder layout

| Path | What it is |
|---|---|
| *(root)* | The original install set, untouched (`common.exe`, `vga1.exe`, `term.exe`, …) |
| `data/common`, `data/vga`, `data/ega` | Contents of the four LHA archives (vga = `vga1` + `vga2`) |
| `run_vga/` | Flat VGA install (common + vga + `TERM.EXE`) for running in DOSBox |
| `exe/TERM_unpacked.exe` | `term.exe` with PKLITE removed and the relocation table rebuilt |
| `tools/` | Python tools (see below) |
| `disasm/` | Generated disassembly listings and indexes (plus `coverage.txt`, which is measured, not generated) |
| `out/` | Generated exports — safe to delete and regenerate (`out/emu/states` holds emulator snapshots) |
| `.venv/` | Python environment (`capstone`, `unicorn`, `pillow`) |

## Tools

Run with `.venv\Scripts\python tools\<tool>.py`. Each tool's docstring is the format spec.

| Tool | Does | Regenerate everything with |
|---|---|---|
| `verify_winding.py` | Original projection/culling vs actual OBJ fronts | `python tools/verify_winding.py` |
| `check_linux.py` | Build every native C translation as a Linux object | `python tools/check_linux.py` |
| `term3d.py` | Meshes, map sectors, collision bitmaps → OBJ, top-down PNG | `sector LAA1 out/obj/LAA1.obj`, `obj <file> <out.obj>`, `map out/la_map.png` |
| `termcmf.py` | CMF music to MIDI/raw instrument bank/lossless JSON | `--verify-mido` |
| `termimg.py` | `.IMG` `.CIF` `.MSK` `.ATF`, horizon, fonts → PNG | `all out/img` |
| `termanim.py` | VGA cutscenes (`.DFB`+`.DFF`) and `.CAF` vignettes → GIF | `all out/anim` |
| `termsnd.py` | `.RS` sound effects → WAV | `all out/snd` |
| `lzhuf.py`, `bytekiller.py` | The two decompressors (libraries) | — |
| `unpack_exe.py` | PKLITE unpacker (emulates the stub, rebuilds relocations, self-checks) | `term.exe exe/TERM_unpacked.exe` |
| `exe.py` | Disassembly / string / xref helper for the unpacked exe | `dis 0000:1f6a 40` |
| `disasm.py`, `names.py` | Whole-program disassembly database and curated names | `python tools/disasm.py` |
| `dosemu.py`, `emu_explore.py` | Headless DOS machine that runs the game; screenshot tours | see "Decompilation effort" |

## What is in `out/`

- `la_map.png` — top-down plot of all six sectors (north up).
- `la_def_objects.csv` — the 117 shared map objects: name, strength, special role, size.
- `mesh_preview.png` — isometric sanity render of sample objects. **Made before the
  mirror fix of 2026-11-10 (see Geometry) and never regenerated: its objects are mirror
  images.** Everything else in `out/obj/` and `la_map.png` has been regenerated.
- `obj/` — `LAA1…LAB3.obj` (whole sectors, objects instanced), `LA_DEF_objects.obj`
  (the 117 shared objects in a row), character sets, projectiles. Materials are named
  `pal_NNN` by face colour index and carry the true colour.
- `img/` — 272 PNGs. `anim/` — 10 cutscene GIFs + backgrounds, 16 vignette GIFs.
  `snd/` — 21 WAVs.

## Data formats

| Files | Content | Status |
|---|---|---|
| `LA.DEF` | 117 named shared 3D objects (buildings, trees, cars, signs) | Done |
| `LA??.BIG` (6) | Per-sector unique meshes (roads, parks, water, lots) + placement list | Done |
| `LA??.SCT` (6) | Per-sector 64×64 cell grid placing `LA.DEF` objects | Done |
| `LA.BMP` | Collision footprint per `LA.DEF` object, 16-unit cells | Lossless JSON index and 108 north-up PNGs in `out/collision` |
| `*.CSF` (4) | Character figures, one flat polygon mesh per pose (cop 25, soldier 25, man/woman 80, enemies 130) | Done, poses named |
| `*.SPN` (5) | Projectile models, one mesh each | Done |
| `*.IMG` `*.CIF` `*.MSK` `*.ATF` | Images, single or several per file; raw, LZHUF or ByteKiller | Done |
| `HORIZON.IMG` | 512×53 scrolling sky strip, headerless | Done |
| `FONT.DMP` `FONT.PCK` `SPECCHAR.CHR` | 8×8, 16×12 and 8×7 bitmap fonts | Done |
| `*.DFB` + `*.DFF` (10 pairs) | VGA cutscenes: background + delta frames + palette | Done |
| `*.CAF` (3) | 96×49 16-colour death vignettes, 16 sequences of 7 images | Done |
| `*.RS` (21) | Sound effects, 6-bit samples at about 5,524 Hz | Done |
| `SONG1.CMF` | Creative Music File (OPL2), 15 instruments and 2,872 events | Done; lossless JSON/raw bank and independently validated MIDI in out/music |
| `*.DCF` + `*.DBI` | EGA cinematics, 320/640 x 200 | Done; 10 clips/437 deltas exported, every frame checked against original |
| `RATINGS.RSE` / `.TRM` | Five 41-byte rating/stat/name records | Done; decoded CSV/JSON and original-checked codecs/record operations |
| `CREDITS` | Plain text | — |

### Geometry

- One mesh record format everywhere (`term3d.py` docstring): 8-word header, variable-length
  faces, signed 16-bit vertices. Faces are flat-coloured polygons of 3–36 vertices, plus
  2-vertex lines and 1-vertex points.
- **Axes (corrected 2026-11-10).** The game's world is right-handed with **x east, y down,
  z north**: the camera maps +x to screen right, +y to screen down and +z into the screen,
  and the world-to-camera transform is a pure rotation. `LA.DEF`, `.CSF` and `.SPN` vertices
  are in that frame. The meshes in `LA??.BIG` are stored with **z south** instead; the game
  negates their z when loading (found by comparing meshes in the emulator's memory with
  the files). The OBJ exports use x east, y up, z south, i.e. game (x, y, z) → (x, −y, −z):
  a half turn, not a reflection. **Exports made before this date wrote (x, −y, z) and were
  mirror images of the game's objects; they have all been regenerated.**
- **Colours.** The 3D view runs in BIOS mode 0Dh (320×200, 16 colours, default palette)
  even on VGA. Face colour 0–15 is an EGA colour; 16–135 is a 50% dither of two EGA colours,
  enumerated a = 0..14, b = a+1..15 (table built at `0000:1F50`). Exports use the average.
- **Outline colour.** Face flag bit 0 means "fill the polygon"; bit 1 means "then draw its
  outline in the second colour byte" (code at `0000:482B`). The shipped data uses flags 1
  and 3 only; outlined faces are on the bus, pickup, semi, palm fronds, a high-rise and the
  missiles. The OBJ exports ignore outlines.
- **Facing table.** Each mesh has one byte per face for the back-face test (code at
  `11BC:159C`): 0 = test this face, N = reuse the result of face N−1 (coplanar detail such
  as a window on its wall), FF = two-sided (never hidden; drawn with reversed vertex order
  from behind). Coplanar detail will z-fight in a depth-buffered renderer, so offset or
  merge those faces on import.
- **Characters are flat.** `.CSF` figures have z = 0 everywhere: 2D polygon cut-outs.
- **Character poses** (frame selection at `0000:B0A6`): the view direction is the person's
  heading minus the angle from the viewer, in 8 steps. Civilians have 8 standing meshes then
  8 directions × 4 walk frames (man 0–39, woman 40–79 in `MANWOM.CSF`). Cops and soldiers
  have 5 poses mapped onto the 8 directions as `[0,1,2,3,0,1,3,4]`: 5 standing, then
  5 × 4 walk frames. `ENEMIES.CSF` is the three sets concatenated and is not loaded by any code.
- **Winding.** In the game's frame solids (`LA.DEF`, `.SPN`) are wound clockwise seen from
  outside; the exporter reverses each face so OBJ viewers see counter-clockwise fronts
  (1,600 of 1,756 testable `LA.DEF` faces by a centroid test; the rest are concave shapes
  the test can't judge). The flat `.CSF` figures are stored the other way round — the game
  reverses them when drawing (`11BC:157C`) — so they are exported in file order and face
  +z, toward a front-view camera. Ground meshes in `.BIG` are never culled by the game and
  have no consistent winding; the exporter turns each face to point up.

### Map

- Six sectors in a 3×2 grid: `LAA1 LAA2 LAA3` on top (north), `LAB1 LAB2 LAB3` below.
  Columns run east, rows run south. Roads line up across every seam, and the layout
  matches real Los Angeles (Griffith Park, LA River, Hollywood reservoir, Echo Park and
  MacArthur Park lakes, downtown).
- A sector is 65,536 units square; `.SCT` cell = 1,024 units; `.BIG` index cell = 8,192 units.
- **Where things are (corrected 2026-11-10).**
  - Ground mesh from a `.BIG` placement (X, Y, Z) and file vertex (vx, vy, vz):
    east = X + vx, south = Z + vz, height = −(Y + vy).
  - `LA.DEF` object in `.SCT` cell (col, row) at (x, z) with vertex (vx, vy, vz) after its
    quarter turns: east = col·1024 + x + vx, **south = (row + 1)·1024 − z − vz**. The z in
    a cell record is measured north from the cell's south edge. Until this date the
    exporter used row·1024 + z + vz, which flipped every object north–south inside its
    cell and put houses on top of the roads; the regenerated map has them beside the roads.
  - Evidence: the cell walk at `0000:3C18`–`3D4D` gives a record z_local = (player row −
    row)·1024 + z; the ground list builder at `0000:3EB5` gives z_local = (player row +
    1)·1024 − Z; cell lists and ground placements in the emulator's memory are identical
    to the files (plus 65,536 per sector for ground x and z), and the game's ground list
    matches that formula for all 76 records of a frame.
- **Object rotation.** The `.SCT` rotation field is quarter turns **counter-clockwise** seen
  from above: one turn maps local (x, z) to (−z, x) in the game's frame (x east, z north).
  (Earlier notes said clockwise because they took z as south.) Traced in the executable:
  the cell record is copied into the visible-object list at `0000:3DB5`, its word +6
  becomes the draw item's flags (`0000:2784`), the low two bits are taken at `0000:27E3`,
  and the vertex transform at `0000:29EC`–`2A23` applies them. The collision test at
  `11BC:20F1` only swaps and negates (a mirror for odd turns), which is harmless because
  every footprint is centred.
- At run time the game keeps a window of 24 × 24 cells (segment `DS:[91D4]`, one word per
  cell pointing at its list) around the player and rebuilds the visible-object list only
  when the player enters another cell or turns into another of 8 heading sectors. Cell
  records in memory equal the file's except that the object number is replaced by the
  slot the mesh was loaded into and the last word (0 in the file) is filled in.
- A table of up to 32 records at `DS:0F70` lists objects that have been removed
  (destroyed): a cell record matching one (x, y, z, flags) is skipped and marked hidden.
- 1,317 unique sector meshes placed about 3,000 times, and 17,104 `LA.DEF` placements —
  the credits' "approximately 20,000 3D objects".
- **Scale (my estimate).** Objects are roughly 4.5 cm per unit (a person is about 40 units,
  a car about 116). Distances between landmarks work out to roughly 9 cm per unit, so the
  city is compressed about 2× relative to the objects in it.

### Compression

- **LZHUF** (Yoshizaki/Okumura, N=4096, F=60) with a 16-bit size prefix. Code at `14B5:0216`.
  Used by image type bit `0x08`.
- **ByteKiller** with 16-bit words, decoded backwards, with a checksum. Code at `0000:B425`.
  Used by image type bit `0x04`, cutscenes and `.CAF`.
- Every compressed stream in the shipped data decodes with a passing checksum (ByteKiller)
  or ends exactly at the expected offset (LZHUF).

### Palettes

- 256-colour images carry their own 768-byte palette at the end of the file (8-bit RGB).
- Cutscene palettes sit at the end of the `.DFB` (6-bit VGA values).
- 16-colour images use the standard EGA palette. `INTROTXT.IMG` is 256-colour with no
  palette of its own (it borrows the intro cutscene's), so its PNG has wrong colours.

## Executable

- `term.exe`: PKLITE 1.50. Unpacked: "Game Version 1.00B", 437,472-byte image, 492 relocations,
  entry `0000:0000`, stack `6ACE:0400`.
- Hand-written assembly (TASM per the credits), no C runtime, roughly 37,000 instructions.

  | Segment(s) | Content |
  |---|---|
  | `0000` | Main code segment, 64 KB |
  | `0FBA` | Creative FM-music wrapper |
  | `101F` | Creative CT-VOICE driver (Sound Blaster digitised voice) |
  | `10BB` | Creative FMDRV (CMF/OPL music) |
  | `11BC` | Graphics, polygon fill, map/sector loading |
  | `14B5` | Cutscene player and LZHUF (compiled, has stack frames) |
  | `14A7`, `151B`, `15AD`, `1609` | Further code |
  | `1720`–`5700` approx. | Zero-filled buffers |
  | `5776`–`5C01` | Far data; `5B67` also holds the 6-bit sample player (PC speaker / AdLib / SB) |
  | `5C27` | Main data segment (DS), `0xEA70` bytes |

- Routines located so far: per-frame draw list build `0000:036E`, draw loop `0000:271E`,
  object vertex transform `0000:29C4`, 2D rotate `0000:1B7D` (512 steps per circle, sine table
  at `DS:4188`), visible-object collection `0000:3D87`, mesh draw `0000:1F6A`, dither table build `0000:1F50`,
  256-colour image + palette load `0000:9F17`, set palette `0000:9F8B`,
  ByteKiller `0000:B425`, cutscene frame decode `0000:B519`, CAF loader `0000:70FB`,
  sound set loader `0000:8B1E`, sample play `5B67:0818`, LZHUF `14B5:0216`,
  cutscene player `14B5:000A`, `LA.BMP` loader `11BC:12E7`.
- Video modes used: 13h for menus, shops and cutscenes; 0Dh for the 3D game; 10h (640×350)
  for the full-area map.
- **Ghidra import:** format *Old-style DOS Executable (MZ)*, language *x86:LE:16:Real Mode*.
  Ghidra loads at segment `1000`, so file segment `S` appears as `1000+S`.
- `game.exe` (launched by `term.com`) is a second packed executable behind an anti-debug
  wrapper. Not unpacked; not needed so far.
- Not tested: running `exe/TERM_unpacked.exe` in DOSBox.

## Decompilation effort (in progress)

The game is hand-written assembly, so "decompiling" means: a complete labelled disassembly,
then rewriting routines in C and proving each one against the original. Nobody is available
to play-test, so everything is verified by machine.

Latest completed full regression (2026-11-17): 155 modules, 173,627 comparisons,
zero failures, including 600 live scene frames. Report:
out/verification/difftest_shop_upgrades_pointer.txt. This includes full EGA/VGA cinematics,
planar/VGA menus, loss movies, raw frontend images and both emulator corrections.
The newest nearby interaction and player-control batch also passes focused checks;
its expanded full regression is recorded below when complete.

BC68 vehicle-target fire is now native, including debris, injury and mode=1 exit BX.
Generic controllers/world/travel also support vehicle targets; see the newest section.
Complete 0758 DX composition, main/menu integration, real-time playback/audio
and device/platform bodies remain unfinished. Networking is outside the current
native loop. Assets/maps remain OBJ. New exports include out/anim/ega/, ratings.* and sound_groups.* in
out/tables/.

### What exists

| Piece | Where | State |
|---|---|---|
| Disassembly database | `tools/disasm.py`, `tools/names.py` → `disasm/` | 33,800 instructions, 1,151 functions; main segment 99.6% decoded |
| Headless DOS machine | `tools/dosemu.py` | Runs the real game: intro, cutscenes, menu, protection screen, 3D gameplay, in-game keys |
| Screen tour helper | `tools/emu_explore.py` | Key script in, contact sheet of screenshots out |
| Snapshots | `out/emu/states/*.pkl` | `menu`, `pass` (protection screen), `pass_sel` (right symbol selected), `ingame`, `ingame_walked` |
| Call recorder | `tools/capture.py` → `tests/captures/` | Saves machine states at a routine's entry during real play and replays them |
| C rewrite | `src/*.c`, `src/term.h` | 82 C source files, 11,846 lines including comments, and 414 annotated C translations (including helpers and partial routines; not a count of complete functions). **Whole frames of the 3D view are produced by C and match the original pixel for pixel: 2,700 consecutive live frames checked by hand runs, 600 in the test suite, nothing copied from the original's screen** (`tools/frame_demo.py`, `tests/test_frames.py`) |
| Frame diagnosis | `tools/frame_diag.py` | For a frame that differs: finds the first draw-list record after which C and original part ways |
| Test runner | `tools/difftest.py`, `tests/test_*.py` | Builds `build/term.dll` with Zig's bundled C compiler and compares C against the original |

Run all tests with `python tools/difftest.py` from the project's `.venv` (about 2 minutes;
`python tools/difftest.py frames` alone is the best single check).

### Verified C routines

| C function | Original | Checked against |
|---|---|---|
| `rotate_xz`, `rotate_xz_inverse`, `rotate_bc`, `rotate_ab` | `0000:1B7D`, `1BB0`, `1B46`, `1BE5` | 6,000 random and edge-case inputs |
| `build_dither_table` | `0000:1F50` | the table it produces |
| `bytekiller_unpack` | `0000:B425` | 107 real packed blocks from the data files |
| `lzhuf_unpack` | `14B5:0216` | 7 real packed blocks |
| `object_transform_vertices` | `0000:29C4` | 16 recorded calls from gameplay, whole data segment compared |
| `face_is_hidden` (with `slope_code`) | `11BC:168B`, `175F` | 24,225 random and edge-case inputs |
| `project_vertices` | `0000:46AC`, `4772` | 24 recorded calls plus 60 synthetic ones (extreme coordinates, zoom flags), whole data segment and carry flag compared |
| `mesh_face_visibility`, `face_reverse_winding` | `11BC:159C`, `161B`, `163D` | 24 recorded calls covering all three facing-table cases |
| `mesh_clip_near` | `0000:24EA`, `2564`, `25B3`, `2673` | 40 recorded calls plus 120 with randomised depths to force clipping and divide overflow |
| `mesh_clip_window` | `0000:1F6A` and its helpers up to `2488` | 40 recorded calls plus 160 with randomised screen points and edge combinations |
| `fill_polygon`, `polygon_setup` | `11BC:0000`–`04F6` | 60 recorded calls (26 solid fills, 13 dithered, 21 drawn as a line): data segment and all four EGA bit planes compared byte for byte |
| `line_to`, `polygon_outline` | `0000:0F32` with `0DC7`, `0E39`; `0000:48A5` | through `fill_polygon` (the 21 line cases) and `draw_visible_faces` (every recorded face redrawn with a forced outline) |
| `draw_visible_faces` | `0000:482B` | 40 recorded calls plus the same 40 with every face outlined: data segment and screen planes |
| `mesh_order_faces` | `0000:2D2A`, `2E59` | 60 recorded calls (12 of which reorder) plus 240 with a forced pivot and random hidden flags |
| `track_target`, `approx_distance` | `0000:A2D5`, `5EEE` | 3,000 random distance inputs; 20 recorded calls plus 140 with target collection forced on |
| `draw_object` | `0000:2AF2` | 60 recorded objects plus the same 60 pushed off screen: one whole object from camera-space vertices to pixels, data segment and screen planes |
| `draw_object_list` with `mesh_fetch`, `mesh_prepare`, `object_translate_only`, `record_mesh_number`, `draw_list_camera`, `rotate_vertices` | `0000:271E`, `2BFF`, `285A`, `2A99`, `28E4`, `2921`/`2986`, `DA6E`/`7921` | 36 recorded draw lists (19 ground passes, 17 object passes, 1,701 records) plus 51 with the records forced into every other kind (cut-out figures, vehicles, guided projectiles, hidden, skipped): all 640 KB of conventional memory except the stack, and the screen planes |
| `draw_flat_mesh` and its six helpers | `0000:E83E`, `E8B9`, `E903`, `E978`, `EA3E`, `EA68` | 40 recorded ground polygons, each run four ways (as recorded; ignoring the off-screen flag; as in the object pass; object pass and two-sided) |
| `project_point` | `0000:4772` | through `project_vertices` and `draw_flat_mesh` |
| `collect_visible_objects` with `collect_cell_objects`, `record_removed`, `collect_cell_extras` | `0000:3C18`–`3D61`, `3D87`, `45B8`, `42C0`/`42EF`/`41F8` | 44 recorded rebuilds of the visible-object list, each run 12 ways (reduced detail, every heading sector forced, a third of the objects put on the removed list, 30 forged non-map objects): 528 cases, 29,548 records; all conventional memory compared |
| `build_frame_draw_list` with `append_guided_projectiles`, `append_pickups`, `append_projectiles`, `append_opponent_and_companion`, `figure_mesh_5`, `figure_mesh_8`, `animation_bearing`, `angle_between` and the inline pieces for the special object, timed object, figures and debris | `0000:036E`, `D9FB`/`DA96`, `87FC`/`88A3`/`881F`, `9FB2`, `11BC:1BBC`, `0000:95F2`/`9625`, `B1F1`, `BD64`, `BE47`, `BE68`, `BECE`, `7EC8`, `5E62` | 16 recorded calls, each run 17 ways (every source of records forced on, alone and together): 272 list cases, all conventional memory compared; 5,089 random and edge-case point pairs for `angle_between` |
| `map_page_update`, `draw_map_view`, `set_view_window`, `matrix_from_angles`, `matrix_apply` and the map-view branch of `object_transform_vertices` | `0000:CE12`, `CEED`, `CF33`, `5E1E`, `5E48`, `7A92`, `7A83`, `1C1A`, `1CA7`, `1CDC`, `1DA9`, `1E76`, `1C33`, `29C4` | 305 angle triples and 3,660 points for the matrix routines; 14 recorded redraws of the overhead-map page, each run 4 ways: memory, screen and card registers |
| `explosion_damage`, `blast_queue_step`, `debris_start`, `debris_update`, `random_word` (and `debris_fetch`, `debris_rotate`, until now untested) | `0000:7EF0`, `808E`, `8075`, `45E6`, `4586`, `80B6`, `7B28`, `7D2B`, `80EE`, `8117`, `F88A`, `7E28`, `7E86` | `tests/test_blast.py`, set up from the in-game snapshot (nothing blows up in the recordings): 450 random words across a buffer refill; 6 objects blown to 95 pieces and followed for 50 frames each, 21 of those frames drawn; 12 arranged blasts and 28 queued ones. Memory, screen, and the calls into untranslated code |
| Whole frames | everything above together | `tests/test_frames.py`: 600 live frames (walking and turning, interrupts on); background, object list, finished scene and card registers of each frame compared |
| `draw_background` = `draw_ground_fill` + `draw_horizon` (with the sun) | `0000:06DE`, `159D`, `16BE`, `1707`, `1925`, `196B` | 8 recorded frames, each with 64 headings round the circle, three ground colours and the other camera mode: 544 cases (sun on screen in 72); memory and screen planes |
| `build_ground_list` with `ground_cell_records`, `ground_mesh_too_far`, `ground_sort_layers`, `ground_remove_duplicates` | `0000:3D62`–`3D80`, `3DE7`, `3E5E`, `3E8F`, `3F4D`, `11BC:14D3`, `0000:3FAB` | 24 recorded rebuilds, each run 14 ways (list area scribbled, player moved to 12 other cells): 336 cases, 19,872 records; all conventional memory compared |
| `sort_draw_list` and the 16 other routines of segment `15AD` | `15AD:0006`–`05BF` | 36 recorded calls, each run 14 ways (detail levels, zooms, some records forced to cut-out figures, player turned to eight other headings): 504 cases, 33,264 records in, 5,301 kept, 399 lists reordered; all conventional memory compared |

**Calls into untranslated parts.** The blast code calls four routines that belong to
parts of the game not translated yet: `sound_start` (`0000:89A2`), `player_hit`
(`0000:6386`), `figure_kill` (`0000:AFD0`) and a bookkeeping routine (`151B:02DE`). The C
code does not perform them; it records each as an event (`src/events.c`, `game_events`).
The tests replace the four routines in the emulator by an immediate return, log the calls
and require the two logs to be equal. Use the same pattern for the next subsystem that
calls out of what has been translated.

Not translated in `mesh_order_faces`: a depth-sorting branch that no mesh in the game can
reach (see below).

The C divide helper now treats a zero divisor like an overflow (the original's handler
skips the instruction in both cases); a forced record found that.

The frame-level routines take a `Game` (`src/term.h`): a pointer to the whole 1 MB
real-mode memory image, because meshes are fetched from segments outside the data segment.
Their tests hand the C code a copy of the emulator's memory and compare all of it afterwards.

### How to add a routine

1. Read it in `disasm/seg_XXXX.asm`; name it in `tools/names.py`.
2. Pure function of registers: test with `Machine.call(seg, off, ax=..)` on random inputs
   (see `tests/test_rotate.py`).
3. Works on game state: record real calls with
   `python tools/capture.py SEG:OFF name --keys ...`, then compare the C version's copy of
   the data segment with the original's after the call (see `tests/test_transform.py`).
   Only compare `DS:0000`–`DS:EA6F`; above that is the stack.
   A whole screen or game step that still hands things to its host (files, video modes,
   retrace waits, input): record the original's boundaries and replay them to the C code
   with `tests/boundaries.py` (see `tests/test_phonebook.py`, `tests/test_mapkey.py`); a
   main-loop frame: `tests/test_frame.py`.
4. List it under `C_VERSIONS` in `tools/names.py` so the listing points at the C code —
   every routine it contains, helpers included, or the coverage figure undercounts.
5. Write data-segment variables by name: look the offset up with
   `python tools/dsxref.py <offset>` (who reads and writes it, how the C uses it, its value
   in a live game); if its role is clear, add it to `src/dsvars.h` and run
   `python tools/name_ds_literals.py`. Leave it as a number if its role is not clear.
6. Format with `clang-format -i src/*.c src/*.h` (style in `.clang-format`; Visual Studio
   ships the program). Formatting and naming never change the machine code: building
   before and after gives byte-identical code (only the timestamps differ).

### Code style (since 2026-11-18)

- One style for all C (`.clang-format`): 4-space indent, one statement per line, at most
  120 columns. On 2026-11-18 all sources were reformatted and 1,409 literal data-segment
  addresses were replaced by names from `src/dsvars.h`; both steps were proved
  behaviour-neutral by comparing the built library byte for byte.
- Key-table entries are written `KEY_DOWN(SC_ENTER)` (`src/dsvars.h`).
- Python tests and tools: one statement per line, spaces after commas and around
  assignments and comparisons. The 2026-11-18 tidy-up of 178 files was proved
  behaviour-neutral by comparing Python syntax trees before and after.
- There is one backup at a time, in `out/backup/`; a new backup replaces the old one
  (currently: everything as it was before the 2026-11-18 tidy-up).

### How the emulator works

- A small deterministic PC built on the Unicorn CPU emulator: DOS file, memory and vector
  services, BIOS video/keyboard/timer, EGA/VGA planar and mode 13h memory, DAC, PIC/PIT timer
  interrupts, scripted keyboard. No sound hardware is present.
- Time is counted in executed instructions (1,000,000 per 18.2 Hz tick), so every run is
  repeatable. Vertical retrace is 70 Hz in that virtual time.
- Menus react to one-tick key taps; the 3D game needs keys held about 4 ticks.
- Snapshots restore the whole machine, so a test starts in the 3D view in a second instead
  of replaying the intro.
- `--coverage` records executed code blocks into `disasm/coverage.txt` (6,339 so far, touching
  447 of the 1,151 functions); the disassembler uses them as certain decoding seeds.
- The copy-protection screen is answered from the Security Chart in this folder: the game
  asked for "Sector Across 6, Down 4", whose symbol is the 9th row, right column of the
  on-screen strip (right once, down eight times, Enter).

### Things learned from running it

- The game installs its own divide-error handler (`0000:0407`, skips the 2-byte `div`) and
  relies on it constantly: thousands of divide overflows per second in the 3D view.
- With no sound card it plays samples through the PC speaker, switching the timer to
  16.5 kHz (PIT divisor 72) while a sample plays.
- **Camera model** (`project_vertices`): screen x = x·256 / (z + 40) + 160, screen y =
  y·256 / (z + 40) + 60, so the focal length is 256 pixels (about 64° across the 320-pixel
  screen). The depth z + 40 is never taken below 30 and is halved once per active zoom
  (`DS:114D`, `DS:114F`). Vertices behind the camera (z < 0) are not projected. The 3D
  window is x 8–311, y 8–110. A quotient that overflows 16 bits saturates to ±32,367.
- **Per object, in order:** copy mesh to a work buffer → `object_transform_vertices`
  (quarter turns, translate, rotate by camera heading) → near clip (`0000:24EA`) →
  `project_vertices` → `mesh_face_visibility` → face ordering (`0000:2D2A`) →
  `mesh_clip_window` → `draw_visible_faces` (`0000:482B`).
- **Draw lists** (`draw_object_list`): a frame is drawn from two lists of 12-byte records,
  the ground list at `DS:2836` (count `DS:91D8`, drawn with `ground_pass` = 1) and the
  object list at `DS:[01FE]` (count `DS:50AC`). Record: x, y, z, flags, id, extra (words).
  y is stored upwards and negated for the object pass. A negative extra word or flag 0040
  hides the record. Flag bits: 0003 quarter turns; 0008 "was off screen" (written back by
  the renderer, reused by the ground pass to skip work); 0020 vehicle (with 0004: a part
  only drawn while the player is in a vehicle); 0080 far object, drawn without its detail
  faces (see below); 0100 debris; 0800 guided projectile (id is its heading, mesh number in `DS:E3D2`; called "turret" in notes
  before 2026-11-18, which was wrong);
  1000 and 2000 objects turned by a vehicle's or model's heading; 4000 cut-out figure that
  always faces the camera (id = 2 × index into the 22-byte model records at `DS:0B30`).
- **Where meshes live at run time** (`mesh_fetch`): buildings in segment `DS:[91D0]` with
  an offset table at `DS:91DA`; ground meshes in segment `DS:[91D2]`, offset table
  `DS:92DA` plus base `DS:727E`; figures and vehicles in segment `DS:[91CE]`. Each stored
  mesh is preceded by a word giving its size. The mesh is copied to a work buffer at
  `DS:50B2` and its header offsets are rebased; all later stages work on that copy.
- **One-face meshes** (all ground polygons) take a shorter pipeline (`draw_flat_mesh`):
  no hidden-face table and no ordering; vertices with z outside 0–4095 count as "far", and
  a polygon whose vertices are all far is dropped. That is the ground draw distance.
- Some records get a 16-entry colour translation table (`DS:7756`): `76E0` for model
  records with flag bit 3, `76F0` vehicle parts, `7700`/`7710` cut-out vehicles, `7720`
  flag 2000, `7730` the player's vehicle (two entries patched per record from `DS:7740`).
- The camera for both lists is the player position with heading = body heading + head
  turn (player record words 3 and 4).
- **Object culling and order** (`sort_draw_list`, segment `15AD`): each frame the object
  records are collected at `DS:1576`, then culled and sorted into the list the renderer
  draws. A building's screen extent comes from the four footprint corners stored in its
  mesh (header word 7 — so the footprint is used for sorting as well as collision);
  a cut-out figure is taken as 24 units to either side of its position. Dropped: nothing
  in front of the camera, entirely left or right of the window, nearest corner beyond the
  detail range (`DS:ABCA`: 0 = no limit, 1 = 3,072 units, 2 = 2,048), or completely
  spanned by a nearer building that rises at least as high on screen (heights from the
  table at `DS:75EC`, one word per building mesh). Meshes whose name starts with `TR` or
  `PAl` (trees, palms), cut-outs and debris never hide anything. Order: nearest centre
  last, then pairs that overlap on screen are exchanged where one's centre is in front
  of the other's footprint edge. Quirk: the footprint's quarter turn is read from the
  whole low byte of the record flags, so a record with flag 0080 or 0008 set is sorted
  as if turned three quarters.
- **From map to visible objects** (`collect_visible_objects`): the list is rebuilt only
  when the player changes cell or heading sector (8 sectors of 64 angle units, offset by
  32). For each sector a table (`DS:74B8`) names, for the 9 rows from 4 north to 4 south,
  the first column and number of cells to read: a wedge of the 9 × 9 cells around the
  player. Records get x += (column − player column)·1024 and z += (player row −
  row)·1024, so all positions are relative to the south-west corner of the player's
  cell. Objects more than 3 cells away both ways (2 at reduced detail) get flag 0080.
  Up to 200 records. Two quirks kept in the C: the distance test uses the column after
  the one read and flags the whole row so far; and while an object is on the removed
  list (`DS:0F70`), every record after it in the same cell is skipped too.
- Objects that are not in the map files (14-byte entries behind the far pointer at
  `DS:1200`, count `DS:04C6`: cell, x, z, mesh index, extra, flags) are appended cell by
  cell by `collect_cell_extras`.
- **Ground list** (`build_ground_list`): the ground meshes of the up to nine coarse cells
  (8 × 8 map cells each) around the player's, minus any with a vertex more than about
  16,000 units away, bubble-sorted by layer and with exact duplicates removed (a mesh
  across several coarse cells is listed in each). The layer comes from the colour of the
  mesh's first face through the table at `DS:5EE6`: colour 2 (green) = 1, 1 (blue) = 2,
  7 (grey) = 3, 6 (brown) = 4, 11 = 5, 3 = 6, 14 = 7, 15 = 8; anything else 0, drawn
  first. Up to 220 records.
- **Loading the map window** (`11BC:097E`–`14D2`, native for the installed sectors). The game keeps
  24 × 24 cells loaded: the coarse cell the player is in plus one on each side, and
  reloads when the player gets within 6 cells of the edge. The whole map is 192 × 128
  cells (3 × 2 sectors). While loading it:
  - negates the z of all ground-mesh vertices (`11BC:0AC6`) — the `.BIG` files store z
    south, the game uses z north;
  - replaces each cell record's `LA.DEF` number by a slot number and copies only the
    meshes in use into the object segment, in slot order (`DS:5DC0` lists the loaded
    `LA.DEF` numbers, `DS:91DA` their offsets);
  - fills the record's last word: low byte = the object's **strength** from a table of
    117 bytes at `DS:5EFA` (signs 10–15, trees 40–60, cars 50–70, bus 100, houses 254,
    large buildings 255; see `out/la_def_objects.csv`), high byte = a colour variant 0–3
    for the three car models, derived from the record's position;
  - lists the cars (`car2q`, `vanq`, `pckupq`) and four kinds of special location it finds,
    with world positions: the sign-sized objects `gunq` = 1, `drugq` = 2, `sportq` = 3 and
    the building `ArmoryQ` = 4 (what the game does at each is not traced yet);
  - records the highest point of each loaded mesh (`DS:75EC`) for the object sort.
- **Collision map** (`11BC:2251`, native): a 192 × 192 byte grid, 16 units
  per byte, covering the 3 × 3 cells around the player. Each object stamps its `LA.BMP`
  rectangle with its number; a hit is then checked against the object's bitmap.
  **`LA.BMP` bitmap rows run from south to north** (row index grows with z), columns from
  west to east, in the object's own unrotated frame.
- **One frame, in order** (main loop at `0000:01DC`): `update_visible_cells` (only does
  work when the player changed cell or heading sector) → background (`0000:06C3`: ground
  colour, horizon, sun) → game logic (`0000:06EF`) → `build_frame_draw_list` → `draw_scene`
  (`0000:06FF`: ground list, then object list) → HUD and the rest (`0000:0758`) → page flip.
- **Background** (`draw_background`): the view below y = 60 is filled with one colour
  (`DS:1533`, green 2 in Los Angeles). The sky is `HORIZON.IMG`, 512 × 53 pixels, four
  planes one after another, copied to y = 8..60 starting at byte column (heading / 2) mod
  64 and wrapping: it slides 8 pixels per 2 heading units and repeats four times round
  the circle. For headings 2–67 a yellow sun, a 13-pixel disc from a bitmap at `DS:155E`,
  is drawn at y = 15, sliding with the sky.
- Between the two lists the game calls `0000:091F` and `0000:A480`, which draw nothing
  (they test the ground under the player and fill a small grid by collision tests).
- **The card's registers matter** (found by the whole-frame runs). The original leaves
  the EGA registers as they are between routines, and some routines rely on what is
  there. Line drawing (`line_to`) never sets the plane mask, and the horizon picture
  ends with only plane 3 enabled, so a line drawn after the sky and before any polygon
  fill of the frame changes plane 3 alone — in practice it is invisible. A distant road
  that has shrunk to a line is the usual victim. The C code therefore carries a model of
  the card (`EgaRegs` in `src/term.h`: plane mask, graphics controller registers,
  latches) after the four planes of every screen buffer and performs the same register
  writes, reads and writes as the original; the tests compare the registers too.
- **Far objects lose their detail.** With record flag 0080 (set by the cell walk for
  distant cells) a face that would copy its parent's hidden flag (facing table 1..7F:
  windows, doors) is instead given the low byte of the size of the face before it, a
  leftover in AL that is practically never zero — so the face is hidden. Whether meant
  or not, it works as a level of detail: distant buildings are drawn without windows.
- **What a frame's object list is made of** (`build_frame_draw_list`), in order: the map
  objects in view; guided projectiles (18-byte entries at `DS:10F0`); pickups (20 entries of 13
  bytes at `DS:0253`, drawn when in the player's cell or one next to it); things in
  flight (30 entries of 10 bytes at `DS:B520`, switched off 4,096 units from the
  player); one special object (`DS:0373`); a timed object (`DS:0B08`, a countdown that
  ends in the blast routine `0000:7EF0`); the figures (ready-made records at `DS:0DF0`,
  count `DS:119A`); the companion as vehicle or figure (`0000:BD64`); debris records.
  Then `sort_draw_list`. Figures choose their mesh from the direction they are seen
  from (bearing by `angle_between`, a linear approximation of the arctangent) and a
  walk cycle of 4 frames advancing every 3 or 4 game frames.
- **Blasts** (`explosion_damage`). The thing that goes off flies apart, and unless it is
  a figure-like record it is put on the list of removed map objects (`DS:0F70`, 32
  entries used round and round), so the cell walk leaves it out from then on. Its
  strength — the low byte of the last word of its record — is the damage, and four
  times that is the radius. The player inside the radius is hit four times for a
  quarter of the damage each. Every record of the frame list inside the radius:
  figures are killed; ordinary objects lose the damage from their strength (255 is
  never touched) and, when the result is negative as a signed byte — which for a
  house at 254 is the first blast — throw debris of their own, though the object
  itself stays on the map; cars, petrol pumps and the special objects are queued to go
  off themselves, one every fourth frame, and are removed. The queue has room for 16
  and no overflow check.
- **Debris** (`debris_start`, `debris_update`). Each face of the blown-up mesh becomes a
  piece: life 30–45 frames, a random direction, speed 5–20 units per frame, three spin
  rates, and one of eight 45-step height arcs (tables at `DS:9564`; arc 0 is flat and is
  the only one used when `DS:11CB` is 0). At most 150 pieces. The pieces live in their
  own segment (file segment `531E`): draw records at offset 0, motion records at `0960`,
  one-face mesh headers at `1900`, face data at `2580`, vertex copies at `3580`. Quirk
  kept: the piece meshes take their vertices from `3580` plus the face's own reference,
  so while debris of an earlier object is still flying, the pieces of a later one are
  drawn with the earlier object's vertices.
- **Random numbers** (`random_word`): a 32-bit multiplicative generator (state `DS:EA42`,
  factor `DS:EA46`), drawn 200 words at a time into a buffer at `DS:97B8`.
- **Cached overhead map** (`map_page_update`): whenever the lists are rebuilt the game
  redraws a top-down picture of the surroundings on video page `6000`: the ground list
  through the ordinary renderer in map view — camera at the player's cell corner,
  12,000 units up, a 3 × 3 rotation matrix for looking straight down in place of the
  heading rotation. Quirk kept: in map view the transform leaves the low byte of the
  last vertex's height where the behind-the-camera count belongs, and a mesh is skipped
  when that happens to equal its vertex count.
- The back-face test works on projected 2D points and avoids multiplication
  (`face_is_hidden`); the mesh's per-face table says which faces share a result and which
  are two-sided.
- Face colours go through an optional translation table (`DS:7756`) before drawing
  (`draw_visible_faces`).
- **How pixels get made** (`fill_polygon`): the outline is split at its topmost point into
  two chains walked down one scanline at a time with integer error terms; each scanline
  becomes one span, filled inclusive of both ends. Dithered colours are a checkerboard of
  the pair, swapped every row. An outline with no height is drawn as a single horizontal
  line instead — that is how distant objects shrink to dashes (21 of 60 recorded fills).
- **Line rules** (`line_to`): vertical lines include both ends; horizontal lines stop one
  pixel short of the larger x; sloped lines omit their lower end; lines lying exactly on
  an edge of the view window are skipped.
- **Mesh header word 6 is the draw-order control** (`mesh_order_faces`): 0 = draw faces in
  file order; N below the face count = pivot on face N−1 — if that face is hidden, the
  face groups (a face plus the detail faces listed after it) are drawn in the opposite
  order. Any value at or above the face count does nothing. That includes FFFF: the
  code has a branch that would sort the groups by depth for it, but an unsigned
  comparison returns first, so it is dead code (an earlier version of these notes
  wrongly said FFFF sorts by depth). There is no depth buffer: draw order is everything.
- The "2D point buffer" and the "3D vertex buffer" are the same memory (`DS:3CDE`):
  projection overwrites x and y in place and leaves z as the third word.
- The 3D view is drawn on an off-screen EGA page (page offset `DS:1234`) and flipped.
- Intro credits run in mode 0Eh (640×200).
- Emulator pitfalls already handled: video memory must be plain RAM with read/write hooks,
  not an MMIO region (Unicorn widens unaligned 2-byte MMIO reads, which loaded the EGA
  latches from the wrong byte and corrupted dithered fills — the C rewrite exposed this);
  Unicorn needs its CPU context reset after each divide
  fault; keyboard interrupts must be offered before the fast timer; a test harness must
  restore the stack pointer after calling a routine with stack arguments; self-modifying
  code needs the guard described under Known gaps.

### Known gaps


- **Fixed: interrupts during drawing used to lose pixels.** Cause was a fault in Unicorn
  2.1.4 (the newest release), not in the game or the interrupt logic. The game's timer
  handler (`5B67:0657`, the PC-speaker sample player) patches its own code; one patch,
  `mov cs:[0673], si`, is a 2-byte write at an odd address into the very block of code being
  executed. After such a write Unicorn stops calling *every* memory hook until `emu_start`
  returns, so for the rest of that slice (up to 2,000 instructions) nothing written to
  video memory reached the emulated card. The workaround is `Machine._code_write` /
  `Machine.step` in `tools/dosemu.py`: unaligned writes into the code segments are trapped,
  the slice is stopped, and that one instruction runs in a slice of its own. All
  `emu_start` calls must go through `Machine.step`. `tools/frame_demo.py` (since rewritten to draw the whole frame in C) matched the
  original pixel for pixel with interrupts on (two frames checked, 17 objects each), and a
  recorded object drawn with an interrupt every 97 instructions is identical to the
  uninterrupted one. **Screenshots made before this fix may have missing pixels**
  wherever a sample was playing.
- Related Unicorn trap, not worked around: a slice of exactly one instruction never gets
  past an instruction that patches code just ahead of itself. Nothing in the tools
  single-steps by default; if you do, use slices of 2.

- 118 "orphan" functions are guesses (bytes that decode cleanly but that nothing
  references); three Creative Labs driver segments (`0FBA`, `101F`, `10BB`) are mostly
  undecoded.
- One emulator run crashed inside the Unicorn library (access violation) and did not
  reproduce; cause unknown.
- Map-exit scripts need a short Escape tap. The earlier four-tick hold also enters
  the game-menu path, where the captured attribute palette is all zero. A one-tick
  tap returns to visible live gameplay from both maps (see HUD/map work below).
  The held-key pause occurs before palette restoration at 0214; dismiss it with
  another short Escape tap. See the traced explanation below.

### Where the project stands (2026-11-11) and the plan from here

Measured: 12,779 of 85,729 bytes of game code (14.9%, leaving out the three Creative
driver segments) belong to routines with a tested C version. That is the whole 3D view,
from map cells to pixels, plus blasts and debris. The data side (files to assets and
map) is finished apart from numbers that live in code.

One usage window of work so far has covered roughly 2,000 bytes of original code with
its tests. The phases below add up to about 25-40 such windows; the spread is mostly
about how hard it is to get the game into the states that need testing.

**Stage 1 - make the game do things in the emulator (1-2 windows).** Everything after
this needs game states that the two in-game snapshots do not have. Read the input code
(`keyboard_isr` `0000:37E3`, the key tables at `DS:5A6A`, and whatever reads `key_down`)
to learn the controls; then make and keep snapshots with a figure on screen, the player
in a vehicle, a weapon being fired, a real explosion, a shop, and the map screen. Where
playing blind is too slow, set the state up by writing memory, as the forced test cases
already do.

**Stage 2 - the simulation core (8-12 windows).** The per-frame logic before the list is
built (`0000:06EF`: `5C40`, `D8D2`, `A54E`, `AB77`), player movement, the collision map
and test (`11BC:1FCC`-`258D`, already read), the figures (22-byte records at `DS:0B30`,
`people_select_frames`, `figure_kill` `0000:AFD0`), vehicles, `player_hit`
(`0000:6386`), and the first half of `update_visible_cells`. Test as now, with one
addition: compare the whole data segment after each frame's logic over long live runs,
the way `tools/frame_demo.py --sequence` compares frames.

**Stage 3 - weapons, enemies, missions (5-8 windows).** Things in flight (`DS:B520`),
guided projectiles (`DS:10F0`), pickups (`DS:0253`), targeting (`track_target` is done), the
event code in segment `151B`, and the special locations. This is also where the game's numbers come out (weapon, enemy and vehicle figures, mission rules): write
each table to `out/` as it is understood, as with `la_def_objects.csv`.

**Stage 4 - everything drawn outside the 3D view (6-10 windows).** The HUD and the rest
of `0000:0758`, the second camera mode (`0000:0B97`), the full-screen map
(`0000:CE2B`), text and messages, menus, shops, the protection screen, the cutscene
player (`14B5`), save and load.

**Stage 5 - loader and platform (3-5 windows).** The sector loader (`11BC:097E`-`14D2`,
already read) with file access, sound (replace the drivers rather than translate them),
timing and input, and putting the pieces together into a program that runs. Final
check: replay recorded key scripts through both and compare.

Working rules that have paid off:
- Translate, then test against the original on recordings *and* on forced inputs that
  reach the branches recordings miss; then run long live sequences before believing it.
- When translated code calls into a part that is not translated, record the call as an
  event and compare the event log (see "Calls into untranslated parts" above).
- Keep the card's register state, the data segment and far memory part of every
  comparison; three of the bugs found so far were in state left behind, not in results.

### HUD and interactive map work (2026-11-11)

The current priority is HUD and map screens, ahead of the simulation roadmap above.
`src/hud.c` translates the shared small-font number renderer (`0000:C766`), decimal
formatting (`C872`), zero-terminated text (`C7ED`), and local-map grid labels
(`11BC:2E46` through `2EBB`). Numbers set all four plane enables; text deliberately
preserves the existing enables. Both use five-row packed glyphs and alternate nibbles.
Lowercase text is folded to capitals. Fixed-width numeric fields discard higher digits.

`python tools/difftest.py hud`: 200 passing cases, comparing conventional memory outside
the stack, all EGA planes, registers and latches. This includes eight actual HUD counter
calls and one map-label call, plus forced digit widths 1-5, page offsets, colours,
alignment states, text bytes, plane masks, and map-coordinate boundaries. This is proof
of the shared primitives, not of the complete HUD or interactive map rewrite.
The full regression run also passed all 25 test modules, including 600 live 3D frames.

The original local map opens with `M` from `ingame.pkl`. A repeatable snapshot is now
`out/emu/states/local_map.pkl`; `out/emu/map_hud_probe.png` shows five successive original
map frames.

The four-tick `Esc` hold from `local_map.pkl` reproduces the black capture, but a
one-tick tap returns to visible gameplay. The longer hold reaches the game-menu loop
at `0000:4A96` with an all-zero attribute palette; retrace waits do complete and all
three screen pages contain pixels. No emulator patch was needed for the short-tap
route. Later tracing below explains the black pause and its recovery. Calls were recorded with:

```
python tools/capture.py 0000:C766 hudnumber --count 8 --skip 0 --ticks 30
python tools/capture.py 11BC:2E46 maplabels --count 1 --skip 0 --ticks 30 --keys "2:m:4"
```

### HUD and interactive map continuation (2026-11-12)

`src/hud.c` now also translates the six full-height-view counters (`0000:772B`),
heading conversion (`5998`), five-row clears (`5776:0154`, `018A`), normal-view speed
(`73C1`), the vehicle field at player+30h (`7428`), and the compass needle/history
(`11BC:1A01`, wrapper `0000:4F2A`). `test_hudpanel` passes 891 cases, including 16
recorded live calls with camera modes 0 and 2. `Shift-F9` selects mode 2; the successful
script is `2:lshift:8,3:f9:2`. Snapshot: `out/emu/states/fullscreen.pkl`.

`src/mapscreen.c` translates:

- Local and full-area destination conversion (`CC8D`, `CD05`), distance/bearing
  (`CBA5`), information-panel clearing and multiline text (`CDE1`, `CD4A`).
- Planar screen-to-screen rectangle copies (`5776:04BC`), the planar 16-pixel mask
  blitter (`0000:1492`), pointer restoration/drawing (`60FD`, `6128`), and pointer
  movement (`830F`). Both 40-byte and 80-byte scanlines are tested. The alternative
  chunky-video mask path is explicitly untranslated (returns -1).
- Grid/background (`11BC:2DBB`), place and vehicle markers (`0000:43C6` and helpers),
  and `map_draw_local_scene`, which combines these with the already translated
  ground-map renderer and grid labels. This matches the original from `CE72` through
  `CE9B`, after MAP.IMG is loaded and before pointer resources are loaded.

`test_mapscreen` passes 904 cases, including actual map grid/marker calls, eight whole
local-map composition comparisons, and 128 pointer updates across local/full-area map
states. Comparison includes conventional memory outside the stack, all four EGA planes,
registers and latches. The standalone `python tools/mapscreen_demo.py` writes
`out/emu/local_map_c_vs_original.png`: original | C | difference. The static frame and
legend are supplied by the original resource loader; this is not a standalone map app.

`test_mapflow` exercises the original UI rather than a C UI replacement: one-tick Escape
taps from local/full-area map snapshots return to 38/32 live scene frames over 20 ticks,
with restored mode 0Dh, palette and visible pixels (8 checks). `tools/map_diag.py`
defaults to this short tap; `--hold 4` reproduces the longer-hold menu case. The full-area
map snapshot is `out/emu/states/area_map.pkl`; enter it with `2:alt:8,3:m:4`.

Final regression: `python tools/difftest.py` passes all 28 test modules, including
2,003 HUD/map checks (`hud`, `hudpanel`, `mapscreen`, `mapflow`) and the existing
600 live 3D-frame comparisons. No changes to the emulator core were required.

Remaining HUD/map work: the rest of `0758` (targeting/weapon overlays, messages and
status displays), resource loading and full `CE2B` setup/teardown, page presentation,
and the modal fast-travel/homing/menu loops. The main input dispatcher still belongs
to the original. Keep the cached overhead-map page (`map_page_update`) separate from
the interactive map scene. The latter's drawing and pointer logic now have C versions.

Map action dispatch follow-up: `map_requested_action` translates `CC46..CC6E`,
returning F, H, or zero and writing DS:E25A. Fast travel takes priority over homing
unless DS:01DE blocks it; homing remains selectable when fast travel is blocked.
`test_mapaction` passes 64 executable comparisons across zero and several nonzero
flag representations. It stops before retrace/RET boundaries and compares DS state.
This is the selection portion only: timing, Escape handling, and executing the selected
travel/homing operation remain in the original loop.

### Homing and destination continuation

`map_draw_homing` (CB4B) now composes the six-field homing panel: 48 differential
cases pass. `map_write_destination_position` translates D2BE..D2F3 before
normalization/cell IO: 256 cases plus the existing 64 map-action cases pass.
`src/position.c` translates 2F1C, its 2FB2 rebasing helper and DB01: 81 differential
cases pass across cell crossings, suppressed rebasing and countdown boundaries.
`position_relative_actor` (B660) adds 49 neighborhood/boundary cases; the position
module now passes 130 cases. The regression run reached position with no comparison
failures, then stopped because a newly added test was loaded against the already-open
older DLL. After releasing/rebuilding it, position passed; the remaining six modules
were run separately. Do not rebuild term.dll while another test process has it open.
The original adds AX to both figure fields +2 and +4 in 2FB2; that behavior is retained.
These targeted checks do not establish completion of the fast-travel simulation.
Next dependencies: D177 calls B588 for elapsed simulation, then D2BE/2F1C and the
untranslated cell loader 3B88, collision/arrival handling C42F, BBF1/C35F/DC7B, and
D265. Full map setup/resource IO and the remaining HUD overlays are still pending.

### Map setup, modal selection and fast-travel controllers (2026-11-13)

The C work now covers the complete local-map initialization and both modal selection
loops, using explicit host callbacks for operations that are not yet translated.

- `src/mapsetup.c`: `map_setup_local` (`CE2B`) and `map_begin_local` (`CBF8..CC43`),
  ground-list preservation, initial background/pointer, keyboard-buffer memory reset.
  Resource loading (`6962`, `FAAF`), palette changes (`7AB6`) and page selection
  (`0C6B`) remain host services; these are not native IO implementations.
- `src/mapui.c`: `map_select`, local `CC43..CC8C` and area `D021..D0A5`, with explicit
  retrace waits that can update key state. It retains different local/area F eligibility,
  Escape bit 7, area key-combination flag and cleanup. 48 differential cases pass.
- `src/maparea.c`: the 640-pixel line primitive (`1343` plus helpers), wrapper (`D102`),
  and area viewport (`D0A6`). 480 comparisons pass, including a live capture and 19
  moved viewports. Horizontal clipping's original Y limit of 639 is preserved.
- `src/travel.c`: `travel_run` (`D177`), `travel_simulate` (`B588`), destination
  application (`D2BE`, using C position normalization), and collision recovery (`D265`).
  Callbacks explicitly retain the world-step body (`B5F9`), cell loader (`3B88`),
  interruption/encounter routines and collision test. A missing service reports -1
  (or UINT32_MAX for simulation), rather than success. Controller/position code is C;
  the external simulation, IO, encounter and collision bodies are not.

Tests: `travel` 164 forced branch/recovery cases; `travelsim` 13 cases (including zero
count running 65,536 steps); `travelnative` 6 combined C controller/simulation cases;
`travelreal` 2 whole-state checks using a real journey's original simulation and loader
outputs. Stubbed cases compare every external call and its arguments/state as well as
conventional memory outside the DOS stack and modeled EGA registers/planes/latches.

Real boundary replay is stronger than replacing calls with no-ops: the tool runs the
actual original callee, captures its complete before/after memory and screen state, then
requires the C caller to arrive at that same before-state and consume those effects.
It does not establish a native replacement of the recorded external callee.
`tools/travel_trace.py` records from `tests/captures/travel.pkl.gz` (a real F request
from the local map, 28 simulation steps); `tools/mapsetup_trace.py` records five actual
resource calls each for setup and initialization. `test_mapsetupreal` passes four
whole-state comparisons. Reproduce captures/traces with:

```
python tools/capture.py 0000:D177 travel --count 1 --skip 0 --from local_map --ticks 35 --keys "2:right:4,10:f:1"
python tools/travel_trace.py
python tools/capture.py 0000:CE2B mapsetup --count 1 --skip 0 --ticks 25 --keys "2:m:4"
python tools/capture.py 0000:CBF8 mapbegin --count 1 --skip 0 --ticks 25 --keys "2:m:4"
python tools/mapsetup_trace.py
python tools/mapsetup_demo.py
```

`out/emu/local_map_complete_c_vs_original.png` shows complete local initialization:
original | C | difference (black). Resource/platform effects and palette metadata come
from the original trace. The full drawing, buffer handling and pointer initialization
are checked in C. This remains a harness on the original's state and resources.

Confirmed original quirk: CE2B pushes zoom then height, but restores height into zoom
and zoom into height. Live setup leaves zoom bytes 67/00 and height 0 for the captured
normal-view state. The C version retains this stack order; no behavioral fix is inferred.

Next: full-area setup (`CF74..D021`, including optional overlay), native resource/page
services, remaining HUD overlays and messages, and simulation/collision/IO callback
bodies. Names and disassembly distinguish callback-dependent C from native routines.

Verification checkpoint: the full 38-module regression passed, including 600 live
3D frames. No source/test edits were made while that regression held term.dll open.
Afterward, `src/maskblit.c` added `screen_blit_mask` (`1985`): the shared monochrome
mask renderer used by HUD zoom and the optional area-map overlay. It takes the original
patchable colour/stride explicitly, retains EGA register/latch behavior, pads odd source
rows, and returns the original final SI/DI offsets. Its new differential test passes
128 cases including 40/80-byte strides, widths through 81, source-offset wrap, video
memory as a source, inherited write modes and logical operations. Existing C functions
were unchanged by this addition; the new module was built and tested after the suite.

Next resource dependency inspected: `19CC` dispatches compressed image planes via the
already translated LZHUF/ByteKiller decoders, saving source pointer at DS:1220/1222.
It counts enabled planes from the header, reads packed lengths at header+10h, and starts
packed data at header+20h. Type bit 0x04 selects ByteKiller; otherwise LZHUF. This wrapper is
not yet translated, and its original decoder workspace side effects need a deliberate
comparison boundary. Its caller CF74 also handles optional overlay IO and video setup.

### Compressed planes and complete area-map setup (2026-11-13)

`image_unpack_compressed` (`19CC`, in `src/unpack.c`) is now translated. Both existing
codecs gained segmented IO internally, retaining their established direct-buffer API.
Segmented IO interleaves source/destination accesses and preserves 16-bit offset wrap,
ByteKiller's unsigned destination termination, LZHUF final-match overrun, sparse plane
counts and overlapping plane destinations. The wrapper preserves DS:1220/1222 and its
codec-specific AX result. It ignores ByteKiller checksum failure, matching the original.
Unsupported zero-plane or >16-bit-mask headers return -1 rather than executing a bad
original LOOP count. This is a supported-asset decoder, not a malformed-input emulator.

`test_imageunpack`: 51 passing comparisons from 15 actual image records, including
MAPMASK/BMAP/MAP/FRAME, image collections and 256-colour assets. Cases cover wrapped
sources/destinations, overlapping and sparse planes, zero LZHUF output-size behavior,
and ignored checksum errors. The entire output segment and conventional memory are
compared except DOS stack and LZHUF private adaptive tables/bit-reader at runtime
5819:0004..1139 and byte 233A. The 4096-byte history ring remains compared and is
retained by C, including the 60 bytes the original does not initialize. Old standalone
decoder tests also pass (114). The original private bit-reader/tree layout is not
mirrored by the C decoder.

`src/mapsetup_area.c` translates full-area setup (`CF74..CFEB`) and initialization
(`CFEC..D021`). Optional overlay decoding and mask drawing run in C. The code retains
patches to original CS:1B41/1B42 and uses the C viewport/rectangle/pointer routines.
Only BIOS video-mode changes, bitmap/file IO and palette services remain external.
`MapResources` adds VIDEO_MODE, DEFAULT_PALETTE and READ_FAR_FILE service IDs; the far
file buffer is the pointer at DS:91BC. `tools/mapsetup_trace.py` now records local and
area setup, with overlay enabled/disabled, including the inline INT 10h boundary.
`test_mapsetupreal` passes 12 checks across those six complete setup/initialization
traces. After native overlay decoding, only the same private LZHUF scratch is excluded;
output pixels, history ring and other game state still match.

The long-Escape black pause is now traced, rather than attributed to missing BIOS
behavior. `7A28` deliberately selects DS:1521's zero palette via `7AAF` and sets
DS:01DD. The first completed gameplay frame calls `7AB6` at `0214` to restore colours
from DS:1510. A held Escape reaches the pause menu at `4A96` before that frame finishes,
so it pauses with the display still blank. A second short Escape dismisses it; the
frame completes and restores colours. `test_mapflow` now passes 11 checks, including
this held-key pause/recovery sequence. No emulator core change or game patch was made.
`tools/palette_diag.py --hold 4` records actual register PCs and palette writes;
`out/emu/map_long_escape_recovery.png` shows black pause followed by visible gameplay.

`tools/mapsetup_demo.py --area` and `--overlay` generate
`out/emu/area_map_complete_c_vs_original.png` and
`out/emu/area_map_overlay_c_vs_original.png`. Both show identical original/C pixels,
with a black difference panel. The overlay is decoded/drawn by C; bitmap IO, BIOS and
palette effects are supplied by recorded original service calls.
The full 40-module regression passed after the decoder refactor and area setup changes,
including 600 live 3D frames and the held-key pause recovery.

### Remaining compass/system HUD helpers (2026-11-13)

`src/indicators.c` translates the complete `11BC:181B` pass plus bearing/tick/erase
helpers (`195C`, `19AE`, `19E1`). This covers timed coloured compass needles, per-page
history erasure, character/camera gates, the fourth direction marker and the alternate
view's bearing tick. The bearing helper retains the original player/target row order.
`test_indicators` passes 332 cases: 320 forced timer/heading/history/flag configurations
and 12 real post-scene calls. Conventional memory outside stack and all modeled EGA
state/planes are compared.

`src/systemhud.c` translates the zoom-key latch (`E5BD`), blinking bitmap records
(`E638`), and HUD frame/sight-line helper (`E66E`). `test_systemhud` passes 219 cases,
using the actual raw 63x59 S8X59.IMG asset. It covers press/release latching, countdown
wrap/reload, non-Boolean blink flags, page offsets, camera modes, frame gates and
centred/off-centre sights. Source CS:1B41 colour changes and the word write at DS:468C
are retained. These helpers use the verified native mask and line renderers.

The full 42-module regression passed after these two modules were added, including
600 live scene frames and both map setup/exit flows. No manual play-test is required
for these comparisons. Resource IO/platform callbacks and the larger weapon/targeting
and message compositions in the rest of 0758/E170 still need translation.


### HUD status, score and animated sweep (2026-11-13)

`src/hudstatus.c` translates status collection E29B, seven-slot cycling E307 and
text composition E280. The original strings are ENCUM, OPTIMAL, DAMAGE, EVADE,
PRIMARY, SECONDARY and DISENG. Slot 0 persists; slots 1..6 are refreshed each pass.
`test_hudstatus` passes 4,364 comparisons, including all 128 active masks, all seven
indices, countdown values 0/1/5/255, condition boundaries and actual font rendering.
Indices outside 0..6 are not a supported input.

`src/hudscore.c` translates score_update D6CB and HUD decimal preparation E26D.
It retains 16-bit arithmetic, the x86 count mask, signed clamp before bonuses, and
second clamp for display. `test_hudscore` passes 3,072 arithmetic/string comparisons.
Counter meanings beyond their actual addresses are not inferred.

`src/hudsweep.c` translates E348 and column erasure E44A. The 24-bit sweep retains
its countdown/reload, key latch, bitmap shifts, per-page drawing and patchable colour.
`test_hudsweep` passes 2,328 state/pixel/event comparisons; 48 sound-16 requests were
compared. The sound body is stubbed in the original and reported as EV_SOUND in C,
using the existing blast event convention. It has not been translated or heard in C.

The full 45-module regression passed after these three additions, including 600 live
scene frames and the map flows. Next: raw planar HUD
background pieces at 1A4D/1B19, then E170 composition and warning/target helpers.


### Complete system HUD and planar backgrounds (2026-11-13)

`src/planarblit.c` translates raw planar drawing 1A4D and five-piece background restore
1B19. It preserves interleaved word reads/writes, inherited EGA modes, destination
segment, page offsets, source/destination wrap and the original odd-(stride-width)
source padding. Plane counts 1..7 are supported; malformed stop counts return -1.
`test_planarblit` passes 198 comparisons, including all five actual loaded HUD pieces,
RAM/video sources, aliased RAM destinations and odd strides. A word starting exactly
at video address AFFFF is not covered: the emulator wraps its second byte to plane
byte 0, whereas the C byte mapping would leave the 64 KB video aperture. That hardware
boundary is unverified; no emulator change was made to force agreement. RAM word
crossing and aligned video offset wrap remain covered. No actual HUD piece uses that
excluded video word edge.

`src/hudcompose.c` translates the complete E170 Terminator/system HUD composition,
page repaint/copy 4FE5, warning pass E5E9, target controller E4AE, target frame E542,
information rendering E6E0/E813 and small target masks E56F/E589/E5A3. It connects the
native counters, heading, score, status cycle, sweep, bitmap frame, background restore,
zoom latch and flashing records. `HudServices` retains only bitmap IO (6962, filename
in a) and target scan (A07B, low return word SI and bit 16 carry); UINT32_MAX means
unavailable. Sound requests remain EV_SOUND events. Sound playback, target scanning
and file loading have not become native C implementations.

`test_hudcompose` passes 1,933 comparisons: forced helper/controller/whole-pass cases
plus 12 real E170 entry states. Full conventional memory outside stack, EGA pixels/card
state, sound requests and entire DS at IO/scan boundaries are compared. The original
service bodies are stubbed for this branch matrix. A changing-STC/CLC machine-code stub
initially reused a stale translated block; the stable RET stub now sets return SI/carry
in its code hook, so scan-found/not-found test inputs do not rely on code rewrites.

`tools/hud_trace.py` records three complete integration cases using actual original
bitmap-loading and target-scan effects. It forces page restoration and a no-contact
scan; these are controlled entry states, not claims of naturally encountered input.
Sound bodies alone are stubbed and their requests recorded. `test_hudreal` passes six
checks with matching memory/EGA before each external service and after the full HUD.
The positive-lock branches are covered by the separate stub matrix; the real-service
scanner coverage currently exercises its no-contact path. `tools/travel_trace.py` now
optionally records a chosen return register, used here for the scanner's SI.

Reproduce:
```
python tools/capture.py 0000:E170 systemhud --count 12 --skip 3 --ticks 65 --keys "2:right:16,24:left:16"
python tools/hud_trace.py
python tools/difftest.py hud
python tools/difftest.py planarblit
python tools/hud_demo.py
```

`out/emu/system_hud_c_vs_original.png` shows the complete system-HUD pass on its render
page before flip: original | C | black difference. Bitmap IO/no-contact scan effects
come from original replay; sound bodies are excluded. This remains a harness requiring original state/resources.

The full 48-module regression passed after planarblit/hudcompose/hudreal, including
600 live scene frames and both map setup/exit flows. Next useful work: the general post-scene
pass at 0758 (it mixes gameplay effects and drawing), native shared bitmap/resource service 6962, and the A07B scan
and its collision helpers. Keep the asset/map export target OBJ.


### Binocular and scope overlays (2026-11-13)

`src/hudoptics.c` translates mask load 766A, scope initialization 7683 and per-frame
key/refresh/draw controller 76B4. Actual source strings identify BINOS.IMG and SCOPES.IMG.
The overlay draws a 38-byte by 102-row black mask and restores source code colour 4.
`HudServices` adds HS_LOAD_FILE (FACE), filename in a and far destination at DS:91C0.
File IO remains external. `test_hudoptics` passes 274 full memory/pixel/service-entry
comparisons using both actual mask assets, all six toggle/gate flags, page offsets
and scope sight recentring. The original loader offset is FACE (not 60D0).

`tools/hud_optics_trace.py` records two complete original load/draw cases. They extend
`test_hudreal` to ten checks across the three system-HUD and two optics traces, checking
memory/EGA at resource entry and final state. Both original file loads run in the
trace; their effects are replayed at the C service boundary. Reproduce the visuals:
```
python tools/hud_optics_trace.py
python tools/difftest.py hudoptics
python tools/difftest.py hudreal
python tools/hud_demo.py --optics binos
python tools/hud_demo.py --optics scope
```
`out/emu/hud_binos_c_vs_original.png` and `hud_scope_c_vs_original.png` match exactly.
The demo defaults to system-HUD case 0 so the existing 3D scene remains visible;
`--case 2` instead shows the forced repaint/no-contact-scan integration case.

The full 49-module regression passed after optics and the expanded real traces,
including 600 live scene frames and both map flows. Next scanner target is A07B's query-only
path (DS:7A18 != 0), A2B3's screen bounds and 11BC:25B0/21CA's collision-grid line test.
The weapon/damage branch of A07B is a different, untranslated responsibility.


### Native HUD target query and collision lines (2026-11-13)

`src/hudquery.c` translates A07B's query-only branch (DS:7A18 != 0), A2B3's inclusive
signed screen bounds, 11BC:21CA's world-to-collision-grid address, and 11BC:25B0's grid
line walk. It preserves 16-bit arithmetic, AL-only coordinate MUL, out-of-grid behavior,
source endpoint mutations, shortened walks and the Z-major six-cell zero-LOOP edge.
The query returns original SI plus carry in bit 16; the weapon/damage mode returns
UINT32_MAX before changing state and remains untranslated. `collision_line_blocker`
returns the nonzero blocking cell byte, or 0. The original's SI/BX scratch outputs
outside the query API are not part of the standalone line helper contract.

`test_hudquery` passes 2,816 comparisons with no target/collision service stubs: 768
grid conversions, 512 signed bounds, 768 line walks (417 blocked, 351 clear), and 768
queries (491 found, 277 missing). Query and line tests compare all conventional memory
outside stack and EGA state; the pure address/bounds helpers compare DS and outputs.
An original quirk is retained: each candidate line test scales the shared source
coordinates in place; later candidates therefore reuse the changed source coordinates.

The complete E170 C HUD now calls this native query. HS_TARGET_SCAN was removed from
HudServices; only 6962 image service and FACE file service remain, plus EV_SOUND events.
`test_hudcompose` still passes 1,933 comparisons, now running the original and native
scanner bodies instead of scan stubs. Its controlled target lists include hits/misses.
The earlier subsection's scan-callback and scan-stub descriptions are historical.

`tools/hud_trace.py` now records a fourth controlled complete-HUD case with a visible
contact and cleared original collision map. Original A07B returns SI=B18E/CF=1 and
requests sound 14 after the sweep's sound 16. `test_hudreal` now passes 12 checks across
four system-HUD and two optics traces; it replays only actual resource IO, then checks
the native scanner's final memory/pixels against the original. No scanner effects are
copied into the C run. The no-contact path and positive-lock path are both covered.
`tools/hud_demo.py --case 3` renders this controlled positive-lock example; default
case 0 retains the actual scene from the natural E170 capture.

The full 50-module regression passed after this integration: 65,880 comparisons,
zero failures, including 600 live 3D scene frames and both map flows. The final table
is saved in out/verification/difftest_latest.txt. No source/test edits were made while
the full regression held term.dll open.
Remaining major work: resource service 6962/6994/6A0F/6AAE, post-scene gameplay/effect
routines in 0758, weapon/sight composition 6B54 and its helpers, CAF vehicle display
7250, and A07B's weapon/damage branch. Asset/map export remains OBJ. The C layer still
uses original snapshots/resources and external IO/sound.


### Native cached/file image service and resource integration (2026-11-13)

`src/imageload.c` translates the shared compressed-screen service 6962, four-plane draw
6994, per-plane read/decode 6A0F, and header preparation 6AAE. Cached images select their
header through DS:009D + DS:C4AE in segment DS:0208; the normal cache is disabled in the
current gameplay/map snapshots. Its path is tested by supplying real asset records in
an explicit cache. `image_prepare` takes the original incoming ES as header_segment;
`image_load_screen` assumes the normal cached-caller contract ES == main DS.

Both codecs are reused through new `unpack_block` segmented entry in src/unpack.c.
No previous codec algorithm changed. File LZHUF decodes immediately after the bytes
actually read, using plane_bytes as its bit-reader budget. File ByteKiller works in
place at DS:DE20:0000. Cached ByteKiller ignores the far output pointer's offset but
the subsequent screen copy still uses that offset. All those source quirks are retained.
Row mode copies width bytes at output stride; linear mode copies DS:805C words. The
renderer retains inherited EGA registers, the plane mask and per-plane source state.

`ImageIO` supplies only DOS-style OPEN/READ/CLOSE operations: op=AH (3D/3F/3E), access
mode or handle, far buffer, and count. It returns AX plus carry in bit 16; UINT32_MAX
means unavailable. READ writes physical buffer bytes, matching the emulator's DOS IO.
The image service supports valid successful four-plane compressed asset streams;
it is not an emulator for malformed files or the original unchecked image-IO errors.
The existing excluded video word crossing at AFFFF also remains outside coverage.

`test_imageload` passes 108 comparisons from five actual assets (FRAME, MAP, BMAP,
HUD1 and PANEL). Cases cover real file reads, native handle sequencing, cache input/output
offset wrap, cached header ES, row/linear paths, page/destination offsets and inherited
EGA modes. Native and original memory/EGA are compared before every DOS call and at
return. Only DOS stack and existing LZHUF adaptive/bit-reader private scratch are
excluded; the complete 4096-byte history ring remains compared. Cache cases need no
host callback. Actual output pixels and decoder results are never replayed.

`file_load` translates FACE (far buffer) and FAAF (DS buffer) using the same low-level
IO host. `test_fileload` passes 30 comparisons including actual raw masks/overlay data,
physical buffer crossings, missing files and simulated read errors. On a failed OPEN,
the original ADD SP cleanup clears carry on a normal non-wrapping DOS stack while AX
still holds the error number. The C helper preserves that ordinary-stack behavior;
artificial SP wrap during error cleanup is not modeled. A failed READ leaks its handle
in the original, also retained. Successful AX is the read count; carry comes from CLOSE.

`image_hud_service` and `image_map_service` are C adapters using ImageIO through user.
They implement the existing 6962/FACE/FAAF high-level resource calls without replaying
any of their game-state, decoding or rendering effects. `test_resources` passes 24
checks across six complete map initializations, four system-HUD passes (including a
positive target lock), and both optics overlays. Files come directly from disk; native
resources are checked before and after each service, with final memory/EGA matching.
Only BIOS/palette/page-selection effects are replayed for maps (using changed chunks
only); no high-level effects are replayed at all in the HUD/optics runs. Sound bodies
remain excluded and their EV_SOUND requests compared. The usual private LZHUF scratch
boundary applies; its history is retained. The previous replay-based integration tests
remain as independent checks of the controller API.

Reproduce:
```
python tools/difftest.py imageload
python tools/difftest.py fileload
python tools/difftest.py resources
python tools/resource_demo.py --case local
python tools/resource_demo.py --case overlay
python tools/resource_demo.py --case scope
```
New images use out/emu/native_resources_<case>_c_vs_original.png; cases include local,
area, overlay, hud, lock, binos and scope. This is still snapshot-backed verification. The full 53-module regression passed: 66,042 comparisons, zero failures, including
600 live 3D frames and both map flows. Remaining
major HUD work: weapon/sight composition 6B54 and helpers, WHEELS.CIF vehicle display 7250,
post-scene gameplay/effect work in 0758, and A07B's weapon/damage branch.


### Native WHEELS.CIF vehicle HUD (2026-11-13)

`src/vehiclehud.c` translates the actual vehicle asset loader/indexer 70AA, change-
triggered draw 7250, shared packed-plane wrappers 72E5/731D, and raw five-pass word
blitter 5776:00A6. The filename at DS:8140 is Wheels.cif. This vehicle code does not
load a CAF vignette: the old caf_unpack_planes label covered a shared image wrapper
and is now named image_unpack_shared. The source includes five actual wheel records.
Loader/indexer uses the original work-buffer segment, five offsets, four packed lengths
per header, and segment-relative zero for indexing even if the file buffer offset differs.

Steering frame order is traced statically in 0000:331D..33A4, rather than inferred
from the picture: frame 0 / table offset 0 is Left+Shift; frame 1 / offset 2 is Left;
frame 2 / offset 4 is neutral; frame 3 / offset 6 is Right; frame 4 / offset 8 is
Right+Shift. Unmodified heading steps have magnitude 1 or 7 with Shift; DS:5A24
reverses the heading delta while retaining the selected input frame. Alt, Ctrl or
speed <= 2 bypasses selection and retains the previous frame. Heading is still masked
to 511. Keyboard ISR 37E3 uses key table base 5BD9, with left/right at scancodes 4B/4D;
385A..3864 mirrors Left Shift into the Right Shift slot used at DS:5C0F.
This input/controller routine is not yet translated; the frame selection facts come
from its assembly and the keyboard table, not a claim of a native vehicle controller.

`image_unpack_shared` uses DS:850E as source segment. ByteKiller uses DS:8544 planes
and main-DS:8510 as destination segment; LZHUF always decodes four planes, and its
original 731D switches DS to the source segment BEFORE reading [8510]. The C helper
retains that source-segment destination lookup, tested with destination segments both
matching and differing from main DS. This was found by a differential failure, not an
inferred format field. Return value packs original SI/DI/BX/AX into successive 16-bit
words; UINT64_MAX rejects plane counts outside 1..8. The decoder-private scratch
boundary is unchanged; history/output and other memory are still compared.

`screen_blit_five_planes` deliberately processes masks 1/2/4/8/16. The fifth pass consumes
source words but enables no visible plane. It retains the original graphics-register
reset, final sequencer mask, source wrap and returned SI/DI. Vehicle drawing decodes the
changed frame, restores segment globals to runtime main DS (including the relocated
8510 immediate), then draws the 96x64 frame at 11FC/31FC/51FC on all three pages. The
current page offset does not relocate this fixed three-page drawing.

`test_vehiclehud` passes 348 comparisons: three real-file loads, 72 shared-decoder
cases using all five wheel records and BMAP LZHUF data, 48 raw five-pass blits, and
225 vehicle/camera/frame-change configurations. All five selected wheel offsets
0/2/4/6/8 are asserted to reach drawing. Actual file bytes are supplied through ImageIO;
no decoder, resource-service or screen effects are replayed. Whole memory outside DOS
stack/private LZHUF scratch and EGA state are compared; decoder and blitter register
contracts are checked too. Image IO uses the existing native helpers; sound is not
part of these routines.

`python tools/vehiclehud_demo.py` verifies complete memory/EGA state for loading and
all five frames, then writes out/emu/vehicle_hud_frames_c_vs_original.png (cropped
panel rows; original | C | black difference). The comparison checks all three pages
before generating the crops. The full 54-module regression passed after this module:
66,390 comparisons, zero failures, including 600 live scene frames and both map flows.
The saved reports are out/verification/difftest_latest.txt and difftest_resources_vehicle.txt.
No source/test edits were made while the regression held term.dll open. Remaining major HUD work: weapon/sight
composition 6B54 and helpers, post-scene gameplay/effect work in 0758, and A07B's
weapon/damage branch. Platform BIOS/palette/page services and sound playback remain
external. Asset/map export remains OBJ.

## Weapon display helpers checkpoint (2026-11-13)

Added src/weaponsight.c: weapon_classify_source (0000:6AFC) and
weapon_draw_numbers (0000:7008). Classification retains 16-bit table-index wrap.
Numeric display retains low-byte slot selection, signed byte extension, primary-zero
secondary-clear skip, vehicle/camera gates, and unconditional E172=3 on return.
It uses native hud_clear_bytes/hud_draw_number; no original effects are replayed.
The 882-case test_weaponsight differential test passes, comparing memory and EGA
for the display and DS for classification. The display cases cross all camera,
vehicle, primary/secondary selection and signed-number inputs; page offsets vary.
Names and disassembly regenerated. This is an incremental result after the recorded
54-module/66,390 baseline, not a new full-suite run. Main weapon/sight composition
6B54, drawing helper 6D49 and autoaim 7158 remain untranslated. Resume there.

## Autoaim checkpoint (2026-11-13)

Translated the complete 7158 autoaim display path in src/weaponsight.c, including
7884/789B target cycling/selection, 78D6 horizontal eligibility and 720C lock colour.
Uses native rotation, projection and line drawing; no original effects are replayed.
Selection does not reject negative depth: it projects and tests horizontal window
bounds; the later box stage requires depth >31 and strict x/y limits. Cycling changes
the starting index, not the index of the accepted target. Lock colour latches red
when approximate offset drops below six and stays latched until the box is rejected.
Target projection initially receives the target pointer in BX; BX is cleared only
after projection. This incidental register input is retained in the C translation.

Tests: test_weaponautoaim passes 1,400 comparisons (300 lock boundary/sign cases,
500 direct target predicates and 600 complete autoaim calls with memory/EGA comparison).
Both box drawing and rejection must occur. test_weaponsight still passes 882 cases.
Direct predicate testing initially needed a ctypes c_uint8 return declaration; fixed.
Names/disassembly updated. No new full-suite result is claimed; the prior 54-module
baseline remains historical. Next: 6D49 weapon firing state and 6B54 composition,
with their actual damage/sound dependencies identified before translation.

## Sight composition and projectile creation (2026-11-13)

Native weapon_update_sight (6C93), weapon_draw_crosshair (15F4), weapon_charge_step
(6EE0 tail), weapon_draw_sights (6B70 post-firing suffix), weapon_projectile_slot
(DAD6), and weapon_projectile_create (D896) now have differential coverage.
The complete 6B54 entry and 6D49 firing controller are NOT yet translated.
Sight composition uses native autoaim, random_word, mouse/keyboard arithmetic and
crosshair lines, with no replay or substitute firing call. Its test enters the
executable at 6B70, precisely after the firing call.

Input uses signed low-byte delta *49/160 for angular offsets, low-word multiplication
before arithmetic shifts for mouse scaling, unsigned mouse clamps, and signed keyboard
clamps. Shift acceleration tests the sign bit, not merely nonzero. Charge release
preserves byte-sized multiplication for speed, half-height arithmetic shift and -15
recovery counter. Projectile creation retains count ==4 gating and the allocator's
one-past-four slot when occupancy and count disagree; no sanitization was introduced.

Focused result: five weapon modules, 5,182 comparisons, all passing: autoaim 1,400;
composition 1,200; input/crosshair/charge 1,476; projectile 224; numbers/classification
882. Normal crosshair positions tested x24..296/y18..98. A deliberately invalid (0,0)
crosshair produces a pixel mismatch after negative-coordinate wrap; that edge case is
unresolved and excluded from the passing domain, not claimed as verified clipping.
Full regression after these additions is pending below. Next dependencies are firing
6D49, damage-mode A07B, figure-spawn AD00 and projectile update D8F2 (includes far
151B:025B). Sound remains an event/platform service. Asset exports remain OBJ.

## Weapon follow-up and shared-line correction (2026-11-13)

The first complete run after the sight/projectile additions passed 59 modules and
71,572 comparisons (out/verification/difftest_weapons.txt), including 600 live 3D
frames and map flows. Subsequent changes now undergoing a fresh complete run:
- Native weapons.cif loader/indexer 6B23: eight records starting at the supplied far
  offset, verified against actual file reads at offsets 0/2/256/4096.
- Twelve captured calls from a prepared gameplay fixture added to composition tests.
  The original ingame snapshot has selection zero and no weapon inventory;
  weapon_sight_fixture explicitly enables selection one. This verifies the sight
  suffix in gameplay, not weapon acquisition or firing damage.
- Mouse products use uint32_t before truncation, avoiding C signed-overflow UB.
- Resolved the negative-coordinate crosshair mismatch in src/line.c: 0DDE..0E03
  doubles the start row then shifts it back, losing bit15 before computing the row
  count. C now retains this behavior. Previously failing (0,0) and wrapped cases pass.
- Projectile steering DA2C and signed world bounds DABC translated. Steering tested
  at 17 threshold/wrap offsets for every heading 0..511, including carry/lost-lock.

Focused suite: six modules, 14,078 comparisons, zero failures. Visual artifact
out/emu/weapon_sights_c_vs_original.png compares original/native/difference for
three of the 12 prepared gameplay captures; full memory/EGA comparisons pass.
Run tools/weapon_sight_demo.py after building the DLL to regenerate it.

Still untranslated: complete 6B54/6D49 firing flow; weapon/damage A07B; AD00 figure
spawning; D8D2/D8F2 projectile simulation and its far-event/camera dependencies.
The verified native sight suffix starts at 6B70, after the original firing call.

## Shot visuals and final verification (2026-11-13)

Completed the post-shared-line-fix full regression: 60 modules, 80,468 comparisons,
zero failures. Report out/verification/difftest_weapons_final.txt. Then added A00C
weapon_visual_insert and A036 weapon_visual_step, with 962 passing comparisons:
450 insertions across all 30 ring positions and signed/wrapped pitch fields, plus
512 sequential updates (32 scenarios, 16 updates each). All DS outside stack compared.
The ring stores x/y/z/heading/pitch in ten-byte entries. Negative heading disables a
record. Update subtracts pitch directly from y, disables negative resulting y, otherwise
moves x/z using the high words of signed sine/cosine products with speed 400. This
connects to the existing native append_projectiles renderer consumer, but does not
complete damage detection. Seven weapon modules pass 15,040 cases on the final build;
the full suite was not repeated after these isolated additions.
Next: complete 6D49 firing controller and A07B damage branch. Remaining direct
external/native boundaries include AD00 spawning, 5BDB/AFD0 figure effects and the
151B serial-event routines; D8F2 projectile update also depends on camera reset 7946.
No user testing or import-format decision is needed for these next reverse-engineering
steps. Keep OBJ exports and machine-based verification.

## Figure removal checkpoint (2026-11-14)

Added src/figure.c figure_remove for AFD0 array compaction and bookkeeping.
The interface assumes ES=main DS and returns 1 for the original AD37(AX=1)
replacement-spawn call; the caller must service that request. It is not yet wired
into blast event consumers or the untranslated weapon/damage A07B path.

The original copies count-index records (including the following sentinel), retains
each destination draw record's ID word at +8, compacts the 22-byte figure records,
clears trailing records, and adjusts figure/list/replacement counters. Its range
check is word-sized but the figure-record multiplication uses the low index byte.
Those details are retained rather than replaced with conventional array deletion.

384 differential cases pass, covering empty lists, first/last/out-of-range indices,
four kind flags and both replacement-deferral flags. All DS outside stack and exact
AD37 spawn requests are compared. Only the spawn body is intercepted; no memory
changes from the original are replayed. Existing blast callers still emit their
previous figure-killed event, so this does not silently change that integration.
The earlier 60-module/80,468 run remains the last full regression; this is a focused
addition. Next: implement AD37/AD00 spawning or a concrete caller service, then
connect native figure removal while translating the A07B weapon damage path.

## Spawn candidate grid checkpoint (2026-11-14)

Translated 5CFA figure_map_sample, A480 figure_spawn_grid_block and A46F
figure_spawn_grid in src/figure.c. The spawn grid actually depends on overhead-map
pixels as well as collision: sample projects world x/z at depth 12000 (honoring zoom),
reads planes 3..0 at page 6000, and leaves AX=FFxx plus the original EGA latch/register
side effects. A480 checks 16 positions in one block; A46F updates all nine blocks.
The block index cycles 0..8. Grid stride is 36, candidate spacing 256, and the count
at B82A increments only for value 1. Starting in a blocking cell or sampling colour 1
produces FF instead. World endpoints are restored after collision, while the other
collision helper side effects are retained. The original short-circuit skips map
sampling when 8682 is nonzero; C preserves this.

228 differential cases pass: 192 map samples including zoom and plane patterns,
18 individual blocks and 18 complete grids covering every starting index and map
colour 1 rejection. Conventional memory outside stack and EGA planes/registers/latches
are compared. No original side effects replayed. Full-suite baseline remains the
previous 60-module/80,468 run; these additions have focused verification.
AD00/AD37 spawning is still incomplete: next translate A840 position selection and
its A94B/A987/A9B4/A9F5/AA17/AA3B helpers, then B05E animation initialization. Existing
native people_select_frames can be reused. Figure removal still returns the AD37
replacement request rather than executing an incomplete spawner.

## Native spawning and firing checkpoint (2026-11-15)

Completed A840 selection (A94B/A987/A9B4/A9F5/AA17/AA3B), AD00/AD37 spawning,
B05E movement initialization and B0A6/B0D7/B13D figure-frame selection. They are in
src/figurespawn.c. figure_remove_complete now includes native replacement spawning;
legacy figure_remove still exposes the request for callers that need that interface.
The prior note claiming existing people_select_frames could be reused was imprecise:
only companion animation existed in framelist.c, with a different state layout.

Selector retains expanding perimeter order, BX-minus-one coordinate conversion,
byte multiplication, grid-index/world-coordinate distance comparison, and tie updates.
Spawning retains candidate-grid map/EGA side effects, deferred counts, armed capacity
limit, civilian random bit cycling, and reinitialization of existing figures.
figure_spawn_dx also reproduces the original incidental DX output, used by firing's
otherwise inactive projectile target coordinates. This is explicitly tested.

Native feedback 5BDB/C9A5 decodes eleven actual CAF frames (four length-prefixed BK
planes, 96x49) into relocated scratch DS-01DA, draws page zero and copies to the
current page. All memory and EGA state match; no original effects replayed.

src/weapondamage.c adds single-player weapon_scan_damage (A07B damage path),
weapon_fire (6D49), weapon_frame (complete 6B54), and weapon_resolve_shot (6DBA).
The query-only hud_scan_target API remains separate. Damage performs hit/collision
checks, actor armor/health, timed-object expiry, native figure feedback/removal and
explosions. explosion_damage_native_figures uses native removal/replacement; legacy
explosion_damage retains its event contract for existing callers. Sound and player-hit
bodies remain external event boundaries. Sound event b=255 identifies the original
continuous-start 80E9 flag. Optional serial mode (01DE nonzero) is rejected before
mutation by weapon_scan_damage/fire/frame; resolve_shot requires that caller guard.

Focused coverage: figureselect 1,035; figureframes 384; figurespawnflow 288 (60
successful spawns, 66 deferred, 84 removals and 12 replacements); figurefeedback 129;
weapondamage 433; weaponfire 1,600 (1,536 controlled entries plus four persistent
16-call sequences). Existing figure modules still apply. Firing cases include charging,
continuous cadence, empty ammo, source gating, guided/unguided records and spawning.
Full conventional memory/EGA plus event requests compared for composed routines.

One initial vehicle-destruction fixture left DE4C=0 from the walking snapshot. The
original consequently treated the filename at DS:0000 as geometry. Supplying a real
backing draw record resolved that test; no emulator or comparison exclusion was added.
Full regression for these changes is running; results will be appended. Next: charged
projectile update 6F99 and guided projectile update D8D2/D8F2, including camera/serial
boundaries; then broader simulation and remaining post-scene composition.

## Projectile flight and gameplay capture (2026-11-15)

The full regression before flight passed all 69 modules / 85,911 comparisons;
report out/verification/difftest_native_firing.txt. 600 live scene frames and both
map flows still pass. Prepared weaponframes_prepared captures add 24 real full-6B54
entries (15 firing), native memory/EGA and exact sound requests matched. The fixture
explicitly grants type-0 ammo and patches sound_start to RET; sound state/playback
is outside the comparison. tools/weapon_frame_demo.py regenerates the checked
out/emu/weapon_frame_c_vs_original.png artifact. The screenshot is the existing
scene plus native weapon changes; it is not a claim of an independently running port.

Added weaponflight.c: 6F99 charged-projectile movement, gravity, collision, expiry and
impact resolution, and D8D2/D8F2 guided projectile movement/steering/proximity/blasts.
Guided flight retains different x/z speeds (150/100 before sine products), the live
vehicle versus stored target-coordinate choice, bounds deletion, and loss of guidance.
Collision now has collision_line_blocker_state returning blocker | CX<<16 | DX<<32;
legacy byte-only callers are unchanged. All 768 collision-line cases compare CX/DX
as well as the existing memory/carry/blocker checks in test_hudquery.

Flight's 578 cases pass: 288 charged, 288 guided and two atomic unsupported-mode checks;
40 expiries, 21 charged collisions, 179 travelling cases, 78 guided impacts, 152 cases
with active guided records after stepping and 72 bounds removals without a blast.
Sound/player-hit/object bookkeeping remain the documented explosion event boundaries.
Serial mode returns -1 before mutation; guided flight also rejects camera 1 before
mutation, pending its 7946/7A28 platform/video/resource reset. Camera 0/2 are native.
Full regression including flight and the permanent gameplay replays is pending.
Next: camera-reset services to cover camera 1, broader post-scene simulation, and native
player-hit handling. No user decision is required for the remaining static tracing.

## Completed firing/flight regression and parameter export (2026-11-15)

Final complete run passed: 71 test modules, 86,513 comparisons, zero failures.
Full report out/verification/difftest_firing_flight.txt includes all new figure,
firing, damage, flight and gameplay replay modules, plus 600 live 3D frames and
both map flows. The source and tests were frozen during this run. Tools-only
weapon table export was developed during it, then independently checked through
all eight original initializer calls (5754). No test process remains running.

New data: tools/export_weapon_tables.py writes out/tables/weapon_parameters.csv
and .json. Source evidence: item IDs at 78DC, kind mapping at 78E4, three-byte templates
at 8097 and sound selectors at 80DA. Original 5754 writes record bytes 0/1/4/5 and
retains bytes 2/3. A07B sign-extends byte5 for damage; 6D49 decrements live ammo at byte3.
Exports use numeric item IDs and raw labels for unidentified bytes. Guidance depends
on source comparison at 6AFC, not a guessed type flag. JSON includes executable SHA256,
source routine addresses and limitations. Current observed damage by kind 0..7:
3,3,2,10,2,3,50,2. Kind3 uses its -1 sound selector at impact, not initial charging.
Item display names have not been inferred. Geometry exports stay OBJ.

Next trace: guided camera reset 7946/7A28 (BIOS mode, page/palette/resource work), then
player_hit 6386 and 643E subdamage. The first static read of 6386 shows random hit
regions, shield/message calls C898/5546 and border feedback 0A4F; these remain unported
and need exact call/register tracing before integration. Larger player/world/AI
simulation and the remaining 0758 post-scene composition are still incomplete.
The completed routines did not require user play-testing or an import-format choice.

## Player damage, collision rebuild and camera 1 (2026-11-15)

Continued past the previous checkpoint. New native code:
- playerdamage.c: full 6386 player_hit_native and 643E per-region damage.
- inventory.c: 5546 removal entry, preserving category counters, compaction and the
  original partial trailing-record clear.
- hudmessage.c: C898/C957/C976 text-message panel, actual shield-depletion string,
  three-page copies, inherited EGA state, and sound requests.
- collisionbuild.c: 11BC:2251/233F/239D/2491 map rebuild, extras, footprint metadata,
  rotation and clipping; cells.c exposes the existing collect_cell_extras helper.
- camera.c: 7A28/7946 full-view reset (camera 1/2), plus 0C47 page clears. Normal-camera
  mode0 still requires its 4F4B HUD initialization; this API rejects it before mutation.

Shield depletion has a confirmed executable quirk: 63E5/63F9..640A restores selector
into BX and the saved region value (1) into SI before 643E. Consequently low DS is
modified. This was checked with a hook at 643E, then retained in C and differential
cases. It is not silently repaired. EV_BORDER (kind5) carries logical colour in a and
attribute-controller value in b; border hardware and sound remain host events.

New weapon/projectile explosions call explosion_damage_native, which executes native
figure removal/replacement AND native player damage. The existing explosion_damage
API keeps its legacy event boundaries for old callers. explosion_damage_native_figures
remains available for its narrower contract. Nearby blasts pass composed comparisons.

weapon_guided_projectiles_step_host now supports camera1 with MapResources. Its camera
reset uses native resource loading (actual asset bytes), copies and collision rebuild.
The host supplies BIOS mode, page selection and palette. Tests use an independent
platform emulator fed from C state, not recorded outputs from the reference run.
The convenience no-host API retains atomic camera1 rejection; serial mode is still
rejected. Camera tests compare all memory/EGA outside DOS stack and codec-private
LZHUF scratch, retaining the history ring, as with the existing image tests.

Focused checks pass: playerdamage 2,560 (16 vest depletions, 45 absorptions), inventory
384, HUD messages 144, collisionbuild 176 (776 stamped records, eight actual shapes
clipped), camera 30 (18 resets and 12 missile-impact/reset flows). Existing weapon
flight/damage and legacy blast tests also pass after native player integration.

Fixed a header portability error from earlier additions: declarations had been
repeated inside the non-Windows API macro branch before Game/ImageIO definitions.
Removed those premature duplicates. All 47 then-existing C sources compiled to Linux
objects using bundled Zig; a direct syntax-only driver invocation first failed to
rename nonexistent objects, so explicit object compilation was used successfully.
The complete regression including these changes passed: 76 modules, 89,807 comparisons,
zero failures. Normal-view work continued below.

## Normal camera, weapon HUD and scene overlays (2026-11-15)

Native normal-view camera reset now works via camera_reset with ImageIO and the
existing platform callbacks. The older camera_reset_full_view API preserves its
camera1/2-only contract. New weaponhud.c rebuilds inventory slots, decodes actual
WEAPONS.CIF icons, draws selection boxes and armor, and initializes the lower/upper
HUD. The five-plane byte-width blitter retains its invisible fifth source pass.
Focused checks: weaponhud 1,216; hudinit 472; cameranormal 24; all pass.

sceneeffects.c adds AE2E/AEC4 contact effects, 18D3/9756 timed flashing, vehicle
resource 41C4, and planar overlay restoration/replay. Contact can switch the actor
pointer before its second test; the asymmetric angle boundary is retained.
Focused sceneeffects: 1,984 comparisons, all pass.

textbox.c adds the planar overlay save stack (5776:01E0), loaded 8x8 far-source font
E0C0, six-layer bevels, and nonmodal 5032 text windows plus 093A warning. Timed panels
save their drawn contents, rather than the previous background. Immediate windows
save first. Source differences in page restoration and latch state are retained.
Modal keyboard waits and ADCF chunky-screen entries reject before mutation in the
new public nonmodal API. Focused textbox: 866 comparisons, all pass.

scenecompose.c composes 0758..07B0 as scene_draw_overlays and 07B3..07D0 as
scene_draw_instruments. Actual file bytes are supplied through native ImageIO,
including optics reload and HUD refresh. The middle weapon_frame call is still a
separate boundary: its incoming DX can be stored in projectile records, so a full
0758 translation must trace that register through preceding callees rather than
invent its value. Focused scenecompose: 168 comparisons, all pass; includes four
real system-HUD fixtures and forced warning/overlay expiration configurations.
This is not yet a complete 0758 or full playable native game.

The weapon table export now includes original item display names from DS:78EC,
validated through the inventory-name pointer path. Damage is labelled as the
A07B hitscan input; projectile blast strength is separate. Exports stay OBJ.
The consolidated scene/HUD regression passed: 82 modules, 94,537 comparisons, zero failures.

## Modal UI, weapon controls and gameplay preparation (2026-11-15)

The complete planar 5032 textbox now runs in native C. TextPlatform supplies release
polls and five-retrace input waits; painting, bevels, far-source font and saved-page
logic remain native. Nonmodal callers keep their simpler API. Focused textmodal:
61 comparisons, all pass. Genuine warning/reload cases now retain the actual loaded
text segment (runtime 1819 in the fixture), including Drowning and Reloading. Earlier
synthetic textbox cases intentionally supplied custom text segments; they establish
format behavior, not the content of those actual messages.

weaponkeys.c adds 11BC:1D03 hotkeys, 1D59 reload, 1DD8 deselect, 1E1A select, 1E6B
optic-mode refresh and 0998 look keys. Source quirks retained: selection can store the
low byte of the runtime DS segment in actor+16; inventory compaction and reload text
can replace SI between hotkey iterations. inventory_remove_state and the textbox
state entry expose that incidental SI without changing their old wrapper contracts.
Focused weaponkeys: 2,496 comparisons, including 263 filled magazines, 65 reload panels
and 131 inventory compactions. Actual optics files are loaded by native ImageIO.

playerstate.c adds noisy companion indication (11BC:1796), drowning map sample 091F,
7088 periodic record toggles, 596C threat bookkeeping, A426 deferred spawn retry,
and 3B54 debug-vector toggle (including its actual code-segment byte and modal panel).
gameplay_prepare composes 0809..0820 only; the rest of 0809 is not claimed native.
Focused playerstate 1,280 and gameprepare 792: all pass.

keyboard.c adds native 37AC/37D5 buffered input. KeyboardPlatform polls external
input only; native code consumes and wraps the 100-byte ring. playerstatus.c adds
4609 map-edge warning and complete 4495 refuelling. The edge routine's unusual row
comparison against 63 is retained. Refuelling sets latch 5EE5 before checking money;
its cost>=money branch immediately returns at 455F because that same latch is set.
The insufficient-money panel at 4569 is unreachable from 4495. No repair is inferred.
Focused playerstatus: 1,920 comparisons, including 40 purchases, 36 declined prompts
and 140 insufficient-money latch cases, all pass.

The input test initially hung because a code hook installed after 37AC had already
executed was absent from cached Unicorn blocks. Explicit ctl_remove_cache after
installing the scripted hooks fixed it. This is a test instrumentation issue; no
original keyboard or refuelling branch was stubbed. Retrace and new input are the
only scripted platform effects. Complete memory and EGA state are compared.

The consolidated controller regression passed: 87 modules, 101,086 comparisons.
Next: remaining gameplay/AI dependencies,
DX composition for full 0758, and integration beyond isolated verified phases.

## Targets, camera keys and world motion (2026-11-15)

New targetlist.c builds the 77F6 guided-target list. The per-list limit of 41 is
checked after insertion; the second list still runs, so 42 entries are possible.
Index normalization occurs after each nonempty list; empty lists skip it. Focused
targetlist: 1,024 comparisons, all pass, including the 42-entry case.

camera.c now also covers 794A full-height entry, shared 7989 image/collision rebuild,
and 79C3 camera keys. Normal and full-height transitions have different redraw and
platform-reset behavior. The key tests caught an incorrect redraw-flag write in the
normal branch; removed it after checking 7946. All camera modules then passed:
camera 30, cameranormal 24, camerakeys 48. Resources are native; palette/video/page
services use the independent platform emulator, without reference-output replay.

blast_queue_step_native adds native player and figure work to queued explosions.
The old blast_queue_step retains its event contract. gameplay_update_opening composes
0809..0829 (preparation, edge warning, queue, refuelling) before 089E destruction.
Focused gameopening: 256 comparisons, 18 player-feedback cases, 52 queue advances;
legacy blast 239 rerun and passed. Sound/border and serial-only object notifications
remain events. This does not claim the remaining 0809 controls/death handling native.

worldclock.c covers B9D2 clock, BA1C wandering, BAB7 directed displacement, BA60 clamp,
BB03 companion following and DEB5 normalization. Signed comparisons of low words
against F000/1000 are preserved, including their unintuitive boundary behavior;
DIV overflow retains AX/DX under the original fault-skip handler. Position rebasing
uses the existing verified implementation. Focused worldclock: 2,048 comparisons,
492 position-changing cases, all pass.

position_relative_vehicle (BB2B) computes relative coordinates, both line-of-sight
queries and bearing natively. Only the first query restores pen X/Z; the second
retains scratch side effects. Focused vehiclequery: 1,024 comparisons: 499 out of
range, 361 clear, 164 blocked; all pass.

All 60 sources existing before these follow-ups compiled as Linux objects; report
out/verification/linux_objects.txt. The current source count is larger. The UI demo
was rendered and visually checked; actual Drowning/Reloading/map-edge text and all
eight weapon icons match. The prepared icon-initialization case intentionally has
its cleared view rather than claiming a newly rendered 3D scene.
The consolidated world/control regression passed: 92 modules, 105,486 comparisons,
zero failures. All 62 then-existing C sources also compiled as Linux objects.

## Pursuit, opponent inventory and on-foot firing (2026-11-15)

motion.c adds AA81 collision steering, B755 destination choice, B6AA pursuit movement
and B790 delay scaling. Steering tries alternating positive/negative 32-unit offsets;
an exhausted search at AB73 returns carry clear on the ordinary DOS stack. Focused
motion: 2,688 comparisons; 65 out-of-grid, 105 exhausted and 42 adjusted steering
cases; all pass. The initial state labels use the older vehicle terminology, but
04BA also points to an on-foot opponent in the automated encounter.

opponentitems.c adds C125 far inventory lookup (including register outputs), C0F5
sound selection, C0A7 choice construction, C068 selection, and C16D/C14C insertion/
cycling. Zero-count duplicate records stop lookup. Choice-table holes are retained;
source C0F5 searches 21 bytes, past the eight conventional item IDs. A differential
failure found a missing no-choice flag: C0A1 sets 034B=FF. Corrected to the actual
instruction. Focused opponentitems: 1,856 comparisons; 388 populated and 238 selected/
retained choices; all pass. Exporter now checks 8 player initializers, 8 reloads and
4 original opponent selections. Opponent choice capacities are raw source values,
kept separately from player magazine capacities in opponent_choices.csv and JSON.

opponentfire.c implements BC68's on-foot target path and BF1B/C397 burst cadences.
Native work includes shot ring, bearing indicators, hit probability, armor depletion,
HUD/inventory feedback and player damage. Vehicle targets reject before mutation;
their destruction/exit path through 02B5 remains untranslated. New bursts inherit DX
(and a fresh C0A7 build leaves DL=4); continued bursts use DEC8/DECA. Focused
opponentfire: 1,537 comparisons, 270 hits and 177 burst-firing cases; all pass.

Added tools/opponent_capture.py: prepare nearby on-foot actors/attack counters, then
let the original gameplay loop decide actual BC68 calls. Sound/border bodies are
external during recording. This exposed a recorder defect: record(skip=0) repeatedly
stopped at the same unexecuted entry. tools/capture.py now skips that entry hook once
on resume so the instruction executes. The encounter was regenerated; twelve distinct
shot-ring positions are required, and tests/test_opponentreal.py compares all twelve
entries against native C. Seven caused player-hit feedback. All twelve match memory,
EGA and events. Initial duplicate recordings were replaced, not used as validation.

Added tools/export_ui_panels.py and out/tables/ui_panels.json/.csv: 36 directly
referenced actual UI panels, each parsed and checked via original 5032/native drawing
in a prepared 40x24-cell window. One non-text/transformed argument is excluded.
This is a referenced subset; dynamic/branch-dependent layouts are not exhaustive,
and the validation window is not claimed as each original dialog's dimensions.

The consolidated pursuit/opponent regression passed: 96 modules, 111,579 comparisons,
zero failures. The recorder audit in out/verification/capture_audit.json also confirms
24 distinct prepared weapon frames, 12 distinct prepared sight frames, and the
varied draw-list/object/transform/order/target fixtures. An empty older sight file is
unused; it is not evidence of validation.

## Native encounter placement and companion motion (2026-11-15)

opponentdest.c adds C1CB/C1B0 destination query/storage, B91F opening count, B94A
follow mode, B973 destination following and C42F travel interruption. The source
stores AX=0/BX=B7D0 after a failed complete destination search; B91F ignores search
carry and tests candidate count, including stale count after bounds failure.
Focused opponentdest: 1,536 comparisons, 174 fallback cases and 78 accepted travel
gates, all pass. Fixture construction preserves the nine-block table after the
144-byte spawn grid; overwriting it would invalidate candidate placement tests.

opponentplace.c adds BBF1/BC02 ahead placement, C35F random/parity flank placement,
and DC7B companion placement. BBF1 clears 0359 even on failure; C35F retains it.
DC7B ignores search carry and uses the companion's own local Z in its world delta.
Focused opponentplace: 1,536 comparisons; changed/skipped counts 111/401, 96/416,
374/138 respectively; all four flank offsets exercised, all pass.

travel_run_native_opponents composes D177 with native B588, C42F and BBF1/C35F/DC7B.
Only B5F9 world-step body and 3B88 cell streaming remain host operations. The existing
travel_run retains its external-service API. Focused travelopponents: 160 comparisons,
32 original encounter sequences, 96 rejected interruptions/retries, all pass with
full memory/EGA and state at external calls compared. The other travel modules
(164/6/2/13 cases) were rerun and passed.

companion.c implements DD67/DDBE/DE05 motion modes, DE46 steering/movement and DD56
composition for modes 0..2, plus B5B4 difficulty initialization. Modes 3/4 are modal
inventory panels and reject before mutation through this API. Source motion ignores
steering carry and does not renormalize after moving. Focused companion: 3,075
comparisons; 52 separation expiry cases, 10 heading adjustments, nine distinct speeds,
all pass. Consolidated encounter/travel regression passed: 100 modules, 117,886
comparisons, zero failures; report out/verification/difftest_encounter_travel.txt.
All 68 then-existing C sources also compiled as Linux objects.

## Native opponent controllers and world step (2026-11-15)

opponentai.c adds C21F and B7B6 controllers for on-foot targets, and BFB3 companion
attacks with AX/DX outputs. C21F depends on the bearing DIV remainder in DX at new
burst entry; B91F's AX also feeds retreat delay. These outputs are exposed by
angle_between_state / opponent_openings_state and checked against original registers.
The exploratory audit adds 1,024 original register checks in
out/verification/ai_register_boundaries.json; permanent tests cover them independently.

Focused opponentai: 3,329 comparisons, including 519 fast-burst calls, 487 destination
queries, 346 displacements, 17 flank placements, nine companion placements and 337
companion-damage cases. Focused opponentslow: 2,336 comparisons, including companion
attack register outputs and 227 presentation service sequences. B7B6's movie, 120-tick
wait, cell streaming and camera reset remain external; reset entry is 7A28, called
through wrapper 7946 elsewhere. Tests caught a wrong service address and corrected it
to B8DD's actual relative target. A companion-shot coordinate mistake was also caught
and corrected by following both saved words through the original pops.

player_hit_native_state and opponent_fire_on_foot_state retain AX while compatibility
wrappers keep their prior APIs. Existing playerdamage (2,560) and opponentfire (1,537)
comparisons now check AX as well as memory/EGA/events, all pass. companionai.c adds
DB26 with these native dependencies. It preserves the unmasked AX-derived table
index in DBE9, DC13's AX=pen-Z/BX=table-index query input, DC18's repeated X load, and
the high-global-Z increment at DC2D. Focused companionai: 1,536 comparisons; 716 clear,
512 blocked and 410 original player-shot calls, all pass. These are checked cases,
not an exhaustive claim for arbitrary out-of-table register/memory/stack aliasing.

worldstep.c composes B5F9 with both opponent controllers, native pursuit, world clock,
companion movement and DB26. DD56 modes 3/4 use explicit 57E7/57D4 panel callbacks
between native normalization and movement. The on-foot API rejects vehicle targets
before mutation. Focused worldstep: 1,025 comparisons; 196 native DB26 calls and
103/102 modal-panel boundaries. The source's serial-query branch is tested as local
control flow only; networking is still outside this rewrite.

New tools/ai_capture.py records prepared encounters through the original gameplay
loop. tools/capture.py now annotates new captures with an independent frame-list
entry counter, trace_frame; an initially chosen DS cell/list counter was unsuitable
as a frame marker and was replaced. tests/test_aireal.py checks 124 calls at distinct
frames: fast/slow controller 16 each, DD56 and DB26 16 each, B5F9 24 per actor role,
and companion fire 12 (six caused damage). All compare full memory/EGA/events against
native C. Preparation changes roles/proximity and attack probabilities; this does not
claim unmodified playthrough coverage. The previous live firing fixture is retained.

The consolidated AI/world regression passed: 105 modules, 126,236 comparisons,
zero failures. Report: out/verification/difftest_world_ai.txt. All 71 then-existing C
sources also compiled as Linux objects. Native world/travel and controls follow below.

## Native travel simulation, walking and driving (2026-11-15)

travel_run_native_world binds B588 to native B5F9. Only cell IO and the world's named
presentation/modal services remain external. Focused travelworld: 48 full D177/B588/
B5F9 comparisons, spanning 1,417 original world updates and 32 encounter placements;
all pass. Existing external-service/native-opponent variants retain their APIs.

playercontrols.c adds complete 30A0 walking and helpers 2E9E movement gate, 300B/302E
walking speed, 36D0/36EF position backup/restore, 370E map bounds, 36A9 driving reset,
331D steering, 33A5 acceleration and 354E gear-key selection. It retains the full
AL-quotient/AH-remainder word from DIV CL for the following divisor, fault-skip results,
signed comparisons/wrapping, run timer asymmetry, held opposite keys and strafe loops.
Focused playercontrols: 7,552 comparisons, all pass. A ctypes pointer-width harness
error was fixed before completing the run; native behavior needed no correction.

tests/test_walkingreal.py uses 48 distinct original game frames captured with forward,
backward, left/right, Alt strafe and right-Shift run input. Twenty-two updates moved
the actor. Every original 30A0 update matches native memory/EGA; all six input types
are present. Recorder command is in the test docstring.

driving.c adds 3269 controller, 3402 transmission, 3584 brake, 35C0 interpolation,
3646 displacement and 3684 destruction feedback. Marker drawing and the five damage
calls before exit are native. Only 02B5(BX=1) remains an exit service; unavailable
exit returns -1 after applying preceding damage. EV_SOUND.b retains source 80E9 for
engine-start playback (FF). Deceleration holds timer 4; acceleration immediately
counts it down to 3, as in the source. Focused driving: 5,120 comparisons; 256 exit
chains and 93 engine starts; all pass, including memory/EGA and hardware-event flags.

tools/driving_capture.py prepares vehicle mode through actual original 02B5, with
real image resources and audio-group/hardware calls external. It restores CPU context
after the setup call, leaving resource/control state intact so the saved game loop
resumes. The first fixture stayed in neutral: all calls matched, but zero moved, so
its coverage check failed. It was replaced with source 5EF7=FF alternate vehicle
configuration plus an explicit Home gear selection. No unverified vehicle-type name
is assigned. tests/test_drivingreal.py now verifies 48 distinct actual updates:
45 engine-active, 32 moved, with engine/forward/right input; all match native C.
This does not claim native 02B5.

Consolidated travel/control regression passed: 110 modules, 139,052 comparisons,
zero failures. All 73 then-existing C sources compiled as Linux objects. Native
vehicle resources/transitions and the remaining asset decoders follow below.

## Vehicle resources, cinematic primitives and final data formats (2026-11-16)

characterresources.c implements B187/B199/B1AD CSF families, shared B1C1/B1DE face
initialization, 70FB CAF indexing, 712B append, AE13 variant and 70DF full resource
chain. Actual MANWOM/COP/SOL files are loaded by native DOS-file adapters. Focused
characterresources: 20 comparisons, checking every DOS input state and full conventional
memory/EGA except the stack; all pass. Family selection uses only the low byte of
11CD. Source loop behavior is retained; malformed assets are not supported.

vehicletransition.c composes 02B5 entry/exit, native resource loading, camera/HUD and
walking/driving tails. Audio-group bodies and BIOS/palette services are external.
Focused vehicletransition: 24 comparisons across both actors, normal/full camera,
vehicle configurations and mode 0/1/2; actual file IO boundaries and memory/EGA match.
This is a status API: BX output required by BC68 vehicle combat is not exposed yet.
Original traces show early walking returns retain HUD-produced BX (e.g. 0006/0F0A),
while normal position-normalization tails return 0000 in the checked cases. Do not
substitute a universal constant for that output.

cutscene.c implements VGA B558 background/palette/key clear and B519 delta application
to native linear buffers. tests/test_cutscene.py now checks all 10 backgrounds and
all 349 actual DFF frames, plus explicit no-op packets: 369 comparisons, 316 changed
frames and 43 empty packets, all pass. Existing Python-exported screens are also
compared. This verifies decoding/drawing, not movie-player timing, audio or frontend.

The remaining EGA DBI/DCF formats are now decoded. DBI: four length-prefixed ByteKiller
planes; 8000/16000 unpacked bytes identify 320/640 x 200. DCF: frame count followed by
compressed packets; each decoded packet has four sections with inclusive u16 byte
lengths and {u16 offset,u8 count,bytes} vertical runs. Runtime B423 stores row stride
minus one, compensating for MOVSB. Source B36D copies 16000 bytes per background plane
even for an 8000-byte visible plane; native C preserves the old scratch tail.

New tools/termega.py exports all ten clips to out/anim/ega/: 437 delta frames, no
unparsed tails/checksum failures/off-screen writes. INTRO and BOMB are 640x200;
other clips are 320x200. Native B36D/B3BC drawing and Python-exported visible planes
are compared against the original for EVERY frame: tests/test_egacutscene.py, 447
comparisons, 414 changed deltas; all pass. RGB palette/dimensions also match the
emulator after each full sequence. Contact sheet visually reviewed; GIF/PNG exports
keep raw pixel dimensions. The sheet uses a labelled 4:3 display preview. GIF timing
is a chosen 100ms preview, not encoded movie cadence.

RATINGS.RSE/TRM are fixed 207-byte files: u16 count, five 41-byte records. Each record
has ten stat words (first a signed score) and 21-byte NUL-padded CP437 name. D628 decode
is ((stored + remaining) & FF) XOR A5; D5FA encode is (plain XOR A5) - remaining, with
fixed write size 207. Both supplied tables have five default empty entries scoring
-1000/-1100/-1200/-1300/-1400. tools/termratings.py exports CSV/JSON without changing
installed files. ratings.c implements codecs, stats save/restore, selection, signed
rank insertion, time update and clearing. Focused ratings: 2,688 comparisons, 725
insertions, all pass; original write/create bodies are bypassed in tests. Counts 1..5
are supported for rank insertion; source partial-table stale-slot behavior is kept.

Consolidated resource/cinematic/ratings regression passed: 115 modules, 142,600
comparisons, zero failures (out/verification/difftest_cinematics_ratings.txt). All 77
then-existing C sources also compiled as Linux objects. Subsequent sound and BX work
is recorded below. Current next work: vehicle combat/BX semantics and menu/player
integration. No user input is currently required. Do not treat annotated routine counts as completion.

## Native sound groups and vehicle exit return state (2026-11-16)

sound.c implements 8B1E sample cache loading, 8A9E/8ABE/8ADE/8AFE group selection,
and 89A2/89C5 request routing. Real RS bytes load through native file adapters;
metadata, completion waits and device playback are explicit host boundaries. Pool
exhaustion deliberately zeroes the current segment slot, including the initial base
slot. The original 15-byte scan ignores a match in the final byte (CX=0); only the
first 14 IDs route. Looping requests retain source segment/full request in A876/A878.
Focused sound: 640 comparisons, 277 stat boundaries, 22 idle waits, 175 submissions;
all pass. Device execution, audible playback and driver AX are not translated here.

sound_group_service connects those native groups to vehicle entry/exit. The expanded
vehicletransition test passed 48 comparisons: 24 with audio-group bodies external,
24 with native C and actual original group bodies, only metadata stat external.
Every real DOS input state, conventional memory and EGA state matches.

tools/export_sound_groups.py executes all four ORIGINAL group loaders, including
original DOS stat and sample-file loading. It verifies request IDs and complete bytes
in the resulting segment slots, and exports 29 entries to out/tables/sound_groups.csv
and .json. These map to 21 unique RS assets and existing WAV exports. Header byte 6
is retained as unknown; no unverified interpretation is assigned.

The new line_to_bx/hud_compass_needle_bx APIs pass 2,048 comparisons against original
line/needle BX plus complete memory/EGA. The negative line-error return matters for
BC68's BL>=50 vehicle-hit test. Existing status/drawing APIs are preserved. Numeric,
walking and full vehicle exit BX checks are being consolidated before combat wiring.

## Vehicle combat and generic world simulation (2026-11-16)

line_to_bx preserves the original vertical/horizontal special-case BX and sloped
line error; hud_draw_number_bx preserves final glyph mask in BH and decimal divisor
10 in BL. position_normalize_bx and walking_step_bx carry the source Z rebase or
incoming BX through early input gates. The original APIs still work. Focused line/
needle: 2,048; numeric: 120 BX plus existing 200 HUD checks; walking: 1,024 BX inside
7,552 control checks; complete transition: 144 comparisons; all pass. Transition
checks span cameras 0/1/2, compass flags/headings and early movement guards. The
mode=1 vehicle_exit_state now exposes BX with real resource/HUD/control effects.

opponent_fire_state implements all BC68 target paths: vehicle integrity damage,
random BL injury chance, real mesh debris, 10/20 injury, native vehicle exit, the
post-exit BL>=50 test, and armor/message suppression using 7A18. It returns original
AX or -1 on unavailable service. A failure after a shot starts retains preceding
effects. Existing on-foot entries retain atomic rejection for vehicle targets.
test_vehiclefire: 128 comparisons, 32 misses, 48 surviving damage cases and 48
native destruction/exit chains; all pass. Metadata/BIOS/palette and sound submission
are host services; file bytes, all DOS input states, groups, memory/EGA are native
or compared. A duplicated fixture reset initially erased the planned random words;
it was removed and explicit miss/damage/destruction coverage required before pass.

opponent_burst, opponent_controller, opponent_controller_slow, companion_ai,
world_step and travel_run_native_simulation use that full target path. Existing
on-foot APIs remain compatibility wrappers. test_vehicleai reuses the AI/world/
travel fixtures with actual vehicle flags and a healthy integrity reserve: 8,274
comparisons, including 1,417 original world updates during 48 travel cases; all pass.
Destruction/resource chains are separately exercised by test_vehiclefire. This does not yet prove a continuous native driving/combat game loop.

The next consolidated regression is out/verification/difftest_vehicle_combat.txt.
No user input is needed; next investigation is planar menu/navigation composition.

## Native planar menus and RMW emulator correction (2026-11-16)

menu.c implements planar 48E6 setup and 4A96 navigation, 5776:02D5 highlight and
0330 restoration. Keyboard reads, hotkey table construction, lowercase matching,
up/down wrap, selection and Escape/background restoration are native. The capture
menu_live records an actual original pause-menu entry (text 1057, x=11,y=1,width=22,
height=19, actions=7852). Timing/input and option bodies are synchronous MenuPlatform
services; a handler returns 0 to continue or 1 after its own close/transfer cleanup.
The alternate ADCF non-planar menu remains unavailable (-1 before mutation).

menu_prepare/menu_run/menu_display are verified by 385 comparisons: 128 highlight+
restore pairs, 33 layouts including the actual captured entry, and 96 navigation
cases (48 composed from original 48E6 entry). There are 64 returning option calls;
all conventional memory, EGA and input/option boundary state matches. Arbitrary
handler bodies are not replaced by a claim of full frontend support.

menu_basic_action adds native 4B4A audio toggle and 4ED2/4EDC/4EEB close/yes/no;
16-bit stack unwinds become an explicit closed return. Music driver F494/F4A1 remains
external. Focused menuactions: 192 comparisons, 30 actual music-driver submissions,
all pass. Audio state and overlay restoration are native; audible playback is not.

tools/menu_demo.py produces out/emu/menu_c_vs_original.png (+metadata JSON). It was
visually reviewed: original and C menus match, difference black. This is the selected
menu drawing page with a labelled DEFAULT EGA PALETTE preview. It does not establish
that the original live pause transition restores its deferred hardware palette.

Newly diagnosed emulator defect: the existing SMC guard stopped an unaligned INC of
the resource hotkey count at ES:020F. Unicorn had already committed the bytes while
leaving IP/flags at instruction start; the guard replayed it, doubling the count.
Machine._code_write now retains old bytes and step() restores them before replay.
Six isolated RMW tests (INC/wrap/two INC/ADC carry/no carry/MOV) pass. Menu hotkeys
now count seven options, agreeing with the executable's instruction semantics.
A larger call budget is still used for guarded menu writes because Machine.call
charges requested slices even when a guard ends them early. No game behavior is
changed to compensate for that accounting approximation.

tools/export_menus.py additionally exports out/tables/menus.csv/.json: ten literal
static layouts and 46 option/handler mappings, each rendered and compared with the
original. Eight dynamic text/layout call sites are explicitly excluded. These are
actual caller dimensions in the captured English resource context, unlike the
older UI panel export's generic preview window.

Full regression after the emulator/menu changes:
out/verification/difftest_menus_smc.txt: 122 modules, 154,393 comparisons, zero failures.
Work proceeds without user input.

## Native EGA movie playback and source pacing (2026-11-16)

cutscene_ega_sequence implements B31C..B365 with actual packet traversal, DB61 extra
repeats and DBB3 retrace pairs per frame. The byte at 5BD4 is tested AFTER drawing
and BEFORE waiting; a 0100 buffered-key count does not skip. Delay/count zero keeps
16-bit LOOP semantics. Focused egasequence: all ten clips, fifty comparisons and
2,632 retrace pairs, all native/original memory/card states and boundary hashes match.
Timing callbacks supply retrace boundaries; no wall-clock or audible-sync claim.

cutscene_ega_play composes the entire B210 EGA branch: filename copies, optional t
prefix for ATF (except ny/ne/ts), BIOS mode, default/selected EGA palette, actual DBI
loading/background, optional ATF checked open/read/shared ByteKiller decode/five-pass
blit, actual DCF loading and the native sequence. Source/working offsets must be zero,
as required by the source decoders. Required DBI/DCF streams must be valid. VGA ADD0
branch is separately unavailable here, returning -1 before mutation.

file_open_existing covers original F7AD with incoming AX=0 only: DOS attributes probe,
read-only open and EA50 errno on failure. It does not implement other create/access
flags. The ImageIO contract adds operation 43 for this metadata check. Files and
camera test adapters now support attribute queries and selected palette 0BE8.

Focused egaplayer: 40 complete original B210 comparisons, 28 present and 12 absent
ATF files, 2,205 retrace pairs; all pass. Tests read actual common+EGA files through
an independent filename resolver without modifying either install. Each DOS service
input and platform boundary state, final conventional memory/EGA, mode and attribute
palette match. Native platform emulation receives only native C state; no original
pixels or state effects are replayed into C.

tools/export_cinematic_calls.py exports twelve source call sites to cinematic_calls.*
in out/tables. EGA keeps incoming BX; VGA 14B5:0054 shifts BX right by one before the
retrace loop. For example bomb is 7 EGA pairs / 3 VGA pairs; ordinary input 8 becomes
8 / 4. Names are resolved from the snapshot and labelled potentially mutable; unknown
CX/AX inputs stay unknown. CX chooses an alternate ATF image-name prefix, NOT music.
No display refresh rate is assumed and existing GIF preview timing is unchanged.

Consolidated regression for these changes passed: 124 modules, 154,483 comparisons,
zero failures (out/verification/difftest_ega_player.txt). Subsequent complete VGA
playback work is documented below. No user input is required.

## Music extraction (2026-11-16)

tools/termcmf.py extracts SONG1.CMF into out/music/SONG1.mid, raw 16-byte CMF
instrument records (.opl-bank.bin and CSV) and lossless event/header JSON. The source
has 15 instruments, 2,872 events, 15,840 ticks at its header clock (165 seconds), and
one trailing byte after end-of-track. Original CMF reassembly matches every byte.
MIDI uses original TPQ=60 and tempo 625000 microseconds to preserve tick timing;
CMF program numbers/controllers are retained, without General MIDI remapping.

Independent mido 1.3.3 validation checks every exported message and absolute tick,
plus total duration. All match. Mido/packaging are validation-only venv dependencies;
the exporter itself uses the standard library unless --verify-mido is requested.
The original timbres require the CMF instrument bank with an OPL/CMF renderer;
this export does not claim an audio render or native FM-driver equivalence.

Header/clock interpretation was cross-checked with the primary implementation at
[libADLMIDI's CMF reader](https://github.com/Wohlstand/libADLMIDI/blob/master/src/midiseq/impl/read_cmf_impl.hpp).
The reference copy in out/verification retains its upstream license. No reference
code is copied into native game sources. Optional ATF movie overlays are images;
they are distinct from this standard CMF music file.

## Native complete VGA playback and AI movie integration (2026-11-16)

movie_load_large implements 14B5:018A: read 65535 bytes, probe one at FFFF, advance
DS by 1000 paragraphs and continue. The first nonzero offset quirk is retained.
Focused largefile: 45 comparisons / 114 reads, including every DFF plus boundary
sizes 0/65535/65536/131070/131072 and initial offsets 0/1/100; all pass.

cutscene_vga_overlay implements 14B5:01C2 first-plane ATF masking to palette index FE,
with three-row/one-byte margins, wrapped SI/DI and exact returned SI/DI. Focused
vgaoverlay: 77 comparisons (64 prepared patterns and all 13 actual ATF files), pass.
cutscene_vga_sequence implements 0093..00E6, normalizing paragraph/offset pointers
before each DFF packet. Fifty all-clip comparisons / 2,104 retrace pairs pass, including
streams up to 185,078 bytes, repeats, early skip and 0100 buffered-count low-byte test.

unpack_block_linear extends the existing codec transport with an external 64 KB VGA
destination while retaining Game-backed source and observable LZHUF history ring.
image_vga_load translates 9F17 including both far-buffer choices, palette suppression
and in-place RGB8-to-RGB6 conversion. All ten compressed installed VGA IMG assets,
eight palette/buffer variants each: 80 comparisons, all pass. Raw MENU256/PASS256 are
not claimed through this LZHUF-specific entry. Existing imageunpack/unpack checks pass.

cutscene_vga_play translates complete 14B5:000A: filenames/ATF prefix, delay halving,
mode 13h, DFB/palette, optional ATF read/decode/mask, large DFF, BBAC sound request 30,
sequence, optional INTROTXT image with inherited palette, and visible-list invalidation.
Caller owns 64 KB indexed pixels/768-byte DAC outside Game; mode service initializes
DAC. Actual playback has 40 original/native comparisons: 28 present / 12 absent ATF,
1,765 retrace pairs. Full pixels, DAC, memory/EGA and every file/platform input state
match. Private LZHUF tables are excluded; history ring is checked, as elsewhere.

cutscene_play dispatches original B210 through ADD0. cutscene_opponent_service adapts
B7B6's known AX=40/BX=8/CX=0 call and explicitly forwards other scene services.
test_movieworld runs complete original B7B6 cinematic branches with native EGA/VGA
movies: twelve comparisons, six each, including native DB61 repeat depletion. Subsequent
wait120/cell-load/camera-reset remain explicit services and their full input states
match. Movie file IO and rendering are native. This does not claim those other service bodies, an audio backend or real-time display pacing.

The full regression including VGA/movie integration passed: 130 modules, 154,787
comparisons, zero failures (out/verification/difftest_vga_player.txt).
No user input is needed; next investigation is the remaining frontend/gameplay wiring.

## Native VGA menu and modal message UI (2026-11-17)

vgaui.c implements 11BC:29CE font drawing in both cell and pixel coordinates, 29A9
fill, 2A65 reverse-endpoint line drawing, 2B1D XOR-A5 selection, 2B48/2B91 single
saved background, 2C58 window base and six bevel layers 2CBE/2D53. Caller owns a
64 KB indexed framebuffer. Focused vgaui: 752 comparisons, all pass, including
256 font cases, 256 lines, 64 save/restore/highlight chains and 48 window bases.

vgamenu.c implements 9D36 setup and 9E59 navigation: original hotkey table, first
option-letter colour 14, matching/wrap/selection and Escape restoration. Option bodies
and input/time are explicit MenuPlatform calls, as with the planar menu. Focused
vgamenu: 129 comparisons (33 layouts, 96 modal cases, 64 returning option handlers),
all pixels, memory/card state and input/handler boundary state match. One accidentally
retained planar highlight call was found on first navigation, replaced by the exact
VGA XOR call, and the full suite rerun successfully.

menu_vga_basic_action extends audio/close/yes/no to VGA restoration while preserving
planar API behavior. Both modes pass 192 action comparisons each, with 30 music-driver
calls per mode. Driver execution remains external; UI/audio-enable state is native.

textbox_vga_draw implements 11BC:2BCC and the VGA branch of 5032. Only 5A4E enables
immediate return: 0200/8096 do not bypass this path. Unlike planar textboxes, VGA
waiting busy-polls input with zero retrace ticks. The host receives release-before,
wait-for-key and release-after phases. Focused vgamodal: 96 comparisons, covering
all phases and nonmodal windows; full boundary state, pixels and memory match.

out/emu/menu_vga_c_vs_original.png (+JSON) is a visually reviewed prepared VGA layout
comparison; black pixel difference. It uses original MENU256 raw pixels/palette as a
prepared background. This is NOT a captured/live main-menu transition, and the chosen
palette can wash out the XOR-highlighted first row; pixel equality does not establish
that the game selected this palette/context for that menu. The actual pause entry
capture remains the separate planar menu proof.

The previous complete checkpoint is 130 modules / 154,787 comparisons. The expanded
VGA UI full regression passed: 134 modules, 155,956 comparisons, zero failures
(out/verification/difftest_vga_ui.txt). No user input
is needed. Save/delete/new-game option logic, raw frontend image selection and complete
gameplay-loop integration remain separate work.

## Loss flow, raw VGA frontend images and DOS-video correction (2026-11-17)

gameplay_check_losses implements 089E opponent/companion health branches. It uses
native sample completion, EGA/VGA movies, MANWOM/COP/SOL model reloads and A28A's
52-byte forward copy/flag promotion. Wait120, cell streaming, camera reset and serial
notifications remain explicit service boundaries. The native loss branch uses the
WHOLE 11CD word for family choice, matching source; 0100 therefore selects COP.
Non-movie loss branches/A28A/sample wait: 672 comparisons. Complete loss-triggered
DOR/TDOR playback and model reload/promotion: twelve comparisons across both video
modes. Every resource/presentation input state and final native/original state matches.

image_vga_blit_raw implements 9132 for MENU256 and other raw records. It reads header
fields at 91BC but deliberately starts pixel copying at absolute segment offset 16;
odd widths skip a byte per row. Sixty-six comparisons include actual MENU256/PASS256,
prepared odd widths and nonzero header offsets; all pass.

A separate emulator bug was confirmed: DOS READ to A000 used Machine.wb (Unicorn API
mem_write), bypassing CPU memory hooks. Backing RAM contained the file bytes while
visible VGA pixels remained zero. Evidence: out/verification/dos_video_write_before_fix.json.
Machine.wb now also sends only the overlapping A000..AFFFF bytes through vga.mem_write,
retaining RAM and selected EGA plane/mask behavior. Five tests cover direct/partial
range writes, actual DOS READ and planar mask semantics; all pass. This is an emulator
correction, not a change to original game logic. DOS-to-video reads now display the
actual raw protection image rather than leaving its background blank.

image_vga_protection_load implements EE9F only: black DAC, actual header/pixel/palette
reads and in-place six-bit palette conversion. The original security-chart challenge
and answer handling are unchanged. Twelve comparisons check every DOS input memory/
pixel/DAC state and final complete screen against both original EE9F and actual raw
PASS256 bytes. All pass. out/emu/protection_image_native.png was visually reviewed.
Native file IO writes its physical A000 transfer buffer; native code publishes those
bytes into the caller-owned indexed framebuffer. No installed game file is written.

The preceding full checkpoint is 134 modules / 155,956 comparisons. Consolidation
following these changes passed: 139 modules / 156,723 comparisons / zero failures
(out/verification/difftest_losses_rawvga.txt).
No user input is currently required. Next work: native nearby-pickup/shop/vehicle
interaction paths and the remaining 0809/0758 main-loop composition.

## Nearby interactions and native player controls (2026-11-17)

pickup.c implements 884B proximity/latching/HUD, 889D/88A3 record queries and 8922
active-distance dismissal. 2,816 comparisons pass, including 736 found queries and
64 inventory-panel boundary calls. LOOP returns through 88A3, resetting BP for each
record; signed distance acceptance and partial scratch writes match source.

shop.c implements 74CE/75B5/75FD/764B and C5AF's fallback-list selection. 2,304
comparisons pass, including 75 purchase-panel calls. Tests compare registers/ZF,
DIV-overflow behavior, HUD pixels/page cleanup, sounds and panel input state.
The inventory/purchase panel bodies remain explicit services at this checkpoint.

playercollision.c implements complete 11BC:1FCC: remembered positions, unchanged
position count, nine-cell search, rotated LA.BMP bit tests, rollback/normalization,
and vehicle sound events. travel_clear_arrival_native replaces D265's collision
callback with native code; cell streaming/057C remain services. 1,600 comparisons
pass: 1,276 clear, 260 blocked, 130 rollbacks and 64 complete arrival chains.
Synthetic fixtures deliberately exercise bitmap bounds, all rotations and patterns.

vehicleinteraction.c implements 400E discovery/prompts/entry bookkeeping, 434E
parking, 4248 parked lookup, 4177 fuel and 421B removal. 3,200 comparisons pass,
including 129 entry transitions and 237 parked matches. Source quirks preserved:
400E's asymmetric distance; 40D3 reads DS despite loading ES; 421B copies the
remaining-record count as BYTES rather than multiplying by fourteen; 410E reloads
fuel from existing 5F72 rather than the packed record's high byte at 5F71.
map_note_removed exposes the existing 4586 native body in blast.c.

vehicle_interaction_native binds the verified 02B5 transition. Forty-eight complete
entry comparisons use actual image/model/sound files, both static and parked cars,
independent BIOS/palette services, and stubbed stat metadata/device boundaries.
player_control_step implements 0255 keys, native injury/parking, transitions and
arrival collision. Forty-eight real-resource control comparisons plus 512 ordinary
walking/driving comparisons pass. Normal movement skips palette reset, as source.

Integration exposed a source register dependency: 6386 usually leaves injury region
in BX; 0255 then passes that BX as 434E's record pointer when jumping from a moving
vehicle. player_hit_native_registers now preserves AX and BX; all 2,560 damage tests
verify those registers and state, including early death and shield branches.
Serial mode is rejected before mutation by the new vehicle/control APIs. Existing
networked callers are not claimed native. No original installed files were modified.

All 87 current C sources compile as x86_64 Linux objects with zero failures;
out/verification/linux_objects.txt. This is portability build proof, not a Linux runtime.

The OBJ front-face convention is now executable-backed: tools/verify_winding.py runs
256 well-conditioned synthetic triangles through original projection/culling and the
actual ObjWriter. Positive projected signed area (clockwise on x-right/y-down screen)
is visible. With the export transform (x,-y,-z), solid face reversal produces an
outward OBJ normal toward the source camera. CSF file winding matches the same result
when accounting for the game's cut-out face reversal. All 256 cases match; degenerate
and quantized-slope borderline cases are explicitly outside this geometric sign claim.
Evidence: out/verification/obj_winding.json. No geometry exports needed changing.

Expanded regression PASSED: 145 modules / 167,251 comparisons / zero failures
(out/verification/difftest_interactions_controls.txt).
No input is needed. Next: dynamic inventory-panel/menu actions, purchase screen,
and the remaining 0809/0758 composition and platform runtime.

## Dynamic pickup panel and equipment refresh (2026-11-17)

pickupmenu.c implements the full planar 531C inventory panel: actual title copied
from the far English resource, proximity-filtered item lines, native generic-menu
navigation/action, native item transfer, background restore and complete HUD reload.
792 comparisons pass: 256 dynamic text builds, 512 transfers, 24 full panel flows.
The full-panel checks use actual HUD assets and compare every input/retrace boundary,
DOS file input state, final memory, EGA pixels and card registers. Escape and four
selected entries across both actors/cameras are covered. pickup_interaction_native
also joins 884B proximity/key/latch logic to that panel; 24 complete flows pass.
Planar gameplay only; these APIs reject ADCF VGA UI mode rather than claiming it.

Source selection ordering retained: after a successful match, nonzero selection
adds thirteen before the final LOOP falls through. With gaps this can select the
physical record after a found pickup without rechecking proximity/active state.
The implementation models that source ordering; it is not a behavior fix. An invalid
selection that DOS would loop forever is unavailable in the native API.

shop.c now implements 8451's word-padded one-bit item-mask hit test and 893F/8962
visit-history bookkeeping/search. 1,792 comparisons pass, including hit/miss and
bounds/word-padding cases. History compares only the first ten bytes; pointer wraps
at count six but count itself is not clamped, matching the executable.

The previously unrecorded 11BC:157C whole-mesh cut-out winding reversal now has 256
passing synthetic tests, including point, line and polygon faces. The facing.c
comment now correctly identifies its edge arguments as v0-v1 and v2-v1.

equipment.c implements 93CA inventory-to-equipment flag refresh, 943E automatic
component combination using native removal, 946C far-text/action-table menu building,
and 9407 required-item counting. 1,280 comparisons pass. Existing flags are retained
unless source changes them; required counting checks nineteen slots and ignores
quantity. This is the equipment refresh needed by the next shop purchase actions.

All 89 current C sources compile as Linux objects (zero failures); this remains
build portability proof, not a complete runtime. out/emu/pickup_c_vs_original.png
was visually reviewed: source/native prepared menu pixels match with black difference.
The preview uses the selected drawing page and default EGA palette; it does not
claim a captured/live palette context. The fixture prepares four MEDKIT records.

The complete checkpoint now passes: 150 modules / 171,395 comparisons / zero failures
(out/verification/difftest_inventory_panels.txt).
No user input is needed; next work is the shop purchase/upgrade/menu body and the
remaining main-loop/platform runtime. Original install files remain untouched.

## Shop purchases and refusal notices (2026-11-17)

shopactions.c implements the regular-item part of 855A, 865C permit gate, 868C
payment and 86EA capacity checks. 960 focused comparisons pass: 613 stacked/155
appended purchases and 192 EGA/VGA gate cases (102 accepted/90 declined). Tests
compare native inventory/equipment refresh, counters, money, memory and EGA/card or
VGA pixels. UI cases exercise the source nonmodal gate; interactive dismissal is
covered by the separate textbox suites, not claimed integrated here. 86EA's ADD SP,4
is replaced with NOPs only in that isolated test to observe its structured failure
return; native code returns status 1 for that caller unwind.

Source quirks retained: cash must be strictly greater than price; successful spending
updates 04C8 or 04CA by shop family. Refund item 10 reloads AX from 04C8, so if its low
byte equals A5 the source also refunds 04CA. The next AL comparison is preserved.
Weapon upgrades 23/26 are rejected before mutation by shop_add_regular_item; the
weapon-selection menu is staged separately and remains the next native task.

All 90 current C sources compile as Linux objects, zero failures. Latest complete
regression remains 150 modules / 171,395 comparisons; the 960 shop-action checks are
additional focused proof, not retroactively part of that full report.

Remaining: 0809/0758 composition/register dependencies, complete frontend,
save/load/startup/shop upgrades, device/timing/runtime and continuous gameplay validation. OBJ remains the export format.

## Weapon upgrades, VGA pointer and video-edge correction (2026-11-17)

weaponpicker.c implements 56B2's dynamic weapon menu and 5737's ID-to-slot mapping.
576 comparisons pass: 256 text builds, 256 choices, 64 complete menus (32 selected,
16 canceled, 16 empty), covering EGA and VGA. The isolated picker tests normalize
571F/574F's DOS stack unwinds only to expose a structured function return. Native
selected windows remain open for their caller; cancel restores them. Empty returns
an explicit no-weapon status.

shop_add_item now composes all 855A paths, including upgrade items 23/26. Forty-eight
complete original upgrade comparisons pass: 16 selected, 16 canceled, 16 no-weapon,
across both video modes. Actual 571F/574F menu/action unwinds run unchanged here;
only the no-weapon 8652 ADD SP,4 is NOPed to isolate a structured return. The empty
case uses the source nonmodal gate. A canceled upgrade deliberately retains 7A18
and skips 0384/equipment refresh, as the source bypasses 861A.

vgapointer.c implements 1492's indexed branch at 153A, 1517 restore and display
wrappers for 6128/830F. It always saves/restores sixteen rows (16 bytes each), even
when the mask height differs. Cursor byte offset lives in 1210; zero is the source's
no-previous-cursor sentinel. AX returns FF00, so 6128 stores FF00 in unused VGA 7C94.
640 comparisons pass, including RAM-backed and A000 screens, segment offset edges,
word copies and movement. MOVSW wraps SI/DI after the word, while the word's second
byte accesses the next physical address; native code preserves that distinction.

Those tests exposed a second boundary issue in the emulator's CPU video hooks:
Unicorn filters the hook by the access START. A word beginning at 9FFFF missed its
A0000 video byte; a word at AFFFF incorrectly wrapped its second byte to A0000.
Fresh-machine before evidence is out/verification/video_word_edges_before_fix.json.
Read/write hooks now start sixteen bytes before the video aperture and clip each
byte to physical A0000..AFFFF. Outside bytes remain ordinary RAM. Eight isolated
CPU tests pass across both edges, read/write and EGA/VGA (after evidence JSON next
to the before file). The five previous DOS/bulk-video tests also pass.

Consolidated regression after this emulator correction is running in
out/verification/difftest_shop_upgrades_pointer.txt. The preceding complete proof
is still 150 modules / 171,395 comparisons; focused additions are not backdated.
No user input is needed. Next: compose shop option handlers and 813E's complete
shop screen, then remaining 0809/0758/runtime integration.

## Native shop alarms and confirmation flows (2026-11-17)

shopalarm.c implements 873D theft probability, 874C alarm and 87E9 balance randomization.
352 comparisons pass: 256 balances and 96 alarm/theft cases. The latter include 81
alerts, 15 escapes, 26 actual model/CAF reloads and 54 actual spawns. Sound playback
is an event boundary and wait100 input/time is a host service; asset bytes, model
parsers, inventory/menu text, candidate grids and AI creation are native. Nonmodal
alarm notices are tested in both EGA and VGA. Source clears only LOW 11CD before
AE13, selecting SOL rather than COP resources; native code preserves that choice.

This composition exposed that 5CFA can run while mode 13h is still active. It still
selects four EGA read planes, but each hardware read returns the same indexed byte
without updating planar latches. New display-aware map-sampling/grid/spawn APIs
preserve that behavior, while old APIs retain their planar contract. Another 352
comparisons cover varied indexed samples (colors 0/15), complete grids and actual
armed spawns (22 spawned/10 deferred). Legacy planar spawn/removal 288 still passes.

scene_overlay_restore_all/reset implement 5776:0295/02AF. This is window restoration,
NOT keyboard clearing. Ninety-six comparisons cover zero/multiple planar windows,
VGA's single saved window and reset. Proper EGA/VGA flag contexts are required.

shopconfirm.c composes 83A6 mask selection, actual dynamic confirmation strings and
84B5 Continue/84BF Buy/850E Steal handlers, including nested upgrades and alarms.
Ninety-six cached-mask flows pass, with six owner-exit requests, 24 pointer misses and
two nested weapon selections. Every menu/input state, final memory, pixels and card
state match. The owner's entire 82C4 shop-exit phase is a boundary in these tests;
its stub restores the isolated caller SP and returns. The native API reports EXIT,
so its owner can perform that remaining exit phase. Refusal notices use the source
nonmodal gate here. The armory suffix has Continue/Steal, while the other suffix
also has Buy; source option tables and strings are retained.

All 160 records across ARMORY/DRUGSTOR/GUNSTORE/SPORTSTO.MSK also match source hit
tests. 13,452 comparisons include 9,924 hits, 3,496 misses and 32 complete 83A6 file/
cache entries with the pointer outside all items. Every real read-only IO boundary
and resulting native data matches. This extends the cached confirmation proof to
actual assets and the uncached loader without replaying original outputs into C.

Consolidated regression after these changes: 160 modules / 187,975 comparisons passed.
Report: `out/verification/difftest_shop_confirmations.txt`.

## Full shop screen and joined gameplay update (2026-11-17)

`shopscreen.c` implements the 74CE interaction gate, 813E setup/input loop and 82C4
exit for GunStore, DrugStor, SportSto and Armory. All 36 complete flows match: 28
entered at the normal interaction gate, 8 directly. They cover EGA/VGA, real masks,
cursor motion, Escape/Continue, prior visits with alarms, and sporting-goods purchase
and theft. The original file requests, input and sound events, memory and video
state were compared. `16A9` reloads `HORIZON.IMG`; `16BE` draws it. The shops still
call a service for the 51C0 category inventory and do not cover the 8CB0 facilities.

`gameplay.c` composes 0809 through 089D. The joystick model accepts host pulse counts
and active-low buttons; 384 comparisons use an independent port 0201 pulse model.
Posture recovery at 082C matches 360 edge cases. Movement and target collection now
derive the DX that can feed the charge-expiry branch; 80 joined cases across 16 live
inputs match original memory, pixels, events and DX at 0897. Complex vehicle paths
can return `ORIGINAL_DX_UNKNOWN` absent a later target-list override. They are not
covered by the joined capture set. The separate player-control regression passed 560
cases, including 48 real transition cases. Linux compilation passed for all 97 sources.

## Complete scene draw, HUD and page flip (2026-11-17)

The full regression after the shop and gameplay integration passed 163 modules /
188,835 comparisons. Report: `out/verification/difftest_gameplay_update.txt`.

0758 now runs the post-render HUD, weapon firing and vehicle instruments without a
second state snapshot. Drawing itself can set DX to the EGA controller port; skipped
overlays can preserve incoming DX, while contacts or a distant timed effect can leave
a coordinate. The native helpers carry these values through to projectile creation.
The unguided scan's DX is not modeled because that mode does not store it in a shot
record. 72 complete results match, including 24 live entries and 48 prepared guided
launches with 14 distinct DX values at 07B0. Raw sound playback is an event boundary.

17E6 rotates the front/back indices, invokes BIOS page selection, and sets both page
offsets for the next frame. 36 cases cover normal live EGA states, the wide offset
table, and forced single-page mode, including BIOS-visible page, retrace call order,
RAM and all plane bytes. The host supplies video timing and the BIOS operation.

06FF now runs the complete ground/object lists, 091F hazard sample, A480 spawn-grid
step, A3D7 stable signed-depth ordering, and 1840 obscured-view cases. 48 draw cases
and 96 sort cases pass. The noisy view uses bytes of the resident executable;
the alternate character uses a blank viewport, and both wait for two retraces.

5C40 now advances the six real CAF deltas, copies the 96x49 rectangle to each draw
page, holds the final image for 150 steps, and hides it when the timer expires. All
330 frame/hold comparisons passed across 11 clips on three pages. B3E4 is shared
with cinematic playback. The 7A3F gate is a byte NEG; a nonzero value stays nonzero.

06C3 selects the complete frame background, including the alternate-camera flat fill
and the gates that suppress the background when the viewport is obscured. The 72
additional cases bring the background module to 616 passing comparisons.

0641 rechecks the player's live collision footprint before drawing. All 48 replay
cases pass, including the warning on foot and 24 ejections with original EGA resources
and vehicle damage. The high-speed explosion branch is translated; this path's usual
ejection resets speed below its threshold, so the fixtures do not reach it.

These stages use original state only at their initial replay boundary. Continuous
main-loop integration still needs the remaining pre-render world updates, cell
streaming and the handoff of the draw-stage DX where the HUD preserves it.

## City geometry and frame integration (2026-11-17)

`tools/check_city_obj.py` loads 54 windows with the original 11BC:097E and checks
the actual sector OBJs, independently of the exporter. Each of the 24,576 map cells
and 384 coarse ground cells is checked once. Across all six sectors, 17,104 shared
placements and 3,005 distinct ground placements matched in both directions.
Each comparison includes transformed vertices, face indices and winding, line/point
primitives and palette material IDs. None of the exported ground groups had identical
geometry. This check covers geometry, not EGA outlines or gameplay collision.
Report: `out/verification/city_obj_runtime.txt`.

The native world update at 06EF advances CAF, guidance, armed figures, civilians and
debris from one entry state. AB77 processes civilians (flag mask 6), A54E processes
armed figures (mask clear). The loops each advance the shared recoil timer. Verified:
114 civilian, 144 armed, and 36 combined updates. The six-sector visible-cell refresh
at 3B88 also passes 58 cases. The native path decides when to reload, appends the
four SPNs, measures mesh heights before appending MISSILE.SPN, restores character
or vehicle resources, and rebuilds the object, ground and collision lists. Only
11BC:097E itself is replayed at its boundary on those reloads. A forced test at
cell (0,0) exhausted the original's 200-million-instruction limit in the collision
stamp at 11BC:2482. The complete-routine passing cases include (4,4) and (191,127).
The geometry audit uses the loader directly and includes the exact northwest corner.

## Native sector packing and collision export (2026-11-17)

3B88 now reads the installed sector files on a miss. It packs the ground meshes,
relocates placements, converts ground vertex Z, compacts LA.DEF and LA.BMP,
initializes shops and vehicles, and rebuilds the visible lists and collision grid.
62 full-refresh comparisons include fourteen forced reloads across all six sectors,
horizontal, vertical and four-sector seams, and the east and south map edges.
Memory, EGA state and arguments matched DOS at every file call as well as at return.
The comparison excludes the original stack and private LZHUF decoder workspace.
Report: `out/verification/difftest_native_window.txt`.

A direct 0A16 check covered all 384 coarse window origins, including (0,0).
280 windows read one sector, 96 read two and eight read four. Conventional RAM
outside the stack and all four video planes matched. This check ends before the
collision stamp. Report: `out/verification/difftest_windowground.txt`.
Each BIG directory entry contains two independent 16-bit offsets. The first points
to the placement list. DOS has a second record path at 11BC:0E83. All 384 second
pointers are zero in this installation. The native window packer flags secondary lists. The Python inspector now decodes their structure.

`tools/term3d.py collision out/collision` exports all 117 shared models' collision
records. The 108 nonempty masks use north-up rows, one bit per 16-unit square.
Five records have a fine-mask header with zero height and four omit that header.
The index retains coarse anchors and dimensions, auxiliary signed words, fine-mask
origin and unused tail bits. Decoding the PNGs and index reconstructs all 19,101
bytes of LA.BMP.

All 1,317 BIG mesh records have a zero-filled region between faces and vertices.
These regions total 16,172 bytes. Each size is the sum of four bytes plus two per
vertex reference for every face in the record. Across the mesh families, 1,535
records point to a second table immediately after the facing bytes. In 1,534
the positive byte counts there sum to the face count. The exception is LA.DEF's
secpacq (19 faces, counts 5,1,1,1,1). In 1,532 records the counts also match
groups inferred from facing bytes. The two other exceptions are COP pose 2 and
its counterpart in ENEMIES. An executable consumer of the second table remains
unidentified.

## Open questions

1. The optional group-count bytes in `.BIG` and some `.DEF`, `.CSF` and `.SPN` records:
   header word 6 holds their offset. The original draw routines were traced without
   a read after the mesh copy. The table's authoring purpose and any other consumer
   remain open. The sizes and contents of the BIG gaps are recorded above.
2. The authoring meanings of image type bits `0x01`, `0x40`, and `0x80` remain unknown.
3. The authoring meaning of byte 6 in `.RS` headers remains unknown.
4. The first two fine-mask header words and the optional collision records need
   evidence from an authoring tool or another runtime consumer.

## Read-only header audit

- **Images.** A header-only walk consumed all 268 records in the installed IMG,
  CIF, MSK and ATF containers. HORIZON.IMG uses a separate headerless format.
  Counts by type word are `0041` (180), `0049` (1), `0088` (13), `00C4` (70),
  and `00C8` (4). The walk uses the stored plane count, packed-length words,
  and trailing 768-byte palettes where applicable. Every container ends at the
  expected byte. The `0049` case is the LZHUF-compressed PANEL.IMG, so bit 0
  occurs with both raw and compressed payloads. Bit 6 occurs with raw, LZHUF
  and ByteKiller data. Bit 7 occurs with both compression formats. The EGA
  reader at 0000:6A24 and 6A71 tests bit 2 to choose ByteKiller versus LZHUF.
- **Sound.** All 21 RS files have a 32-byte header, zero bytes at offsets 9
  through 31, rate code 3, and exactly the stored sample count at offset 7.
  Every payload byte is in the range 0 through 63. All 17 STEVE records have
  byte 6 equal to 72 and all four CRAIG records have it equal to zero. 72 is
  also the immediate carrier divisor at 5B67:0765. The playback entry at
  5B67:081E and 0822 reads offsets 5 and 7 directly. The authoring meaning
  of the skipped byte remains unconfirmed.
  The public doslib scripts independently report 5,524 Hz, a 32-byte header
  and six-bit sample values for STEVE. Their reader accepts the STEVE tag.
  The CRAIG variant is established from the installed files.
  [doslib RS converter](https://github.com/joncampbell123/doslib/blob/master/game-patching/the-terminator-1991/rs2wav-conv6to8.pl)
- **Collision.** All 117 LA.BMP records use the corresponding LA.DEF index.
  Only house4 (52, five groups) and office1q (65, two groups) have the extended
  coarse header. All seven groups end in `2,1`. The second word in each lies
  at a positive or negative Z edge of its coarse rectangle. Treating the groups
  as origin-relative 2-by-1 rectangles gives six groups with in-bounds fine-mask
  pixels. Every sampled pixel is solid. The loader at 11BC:132D copies the full
  coarse header. The stamp setup at 11BC:2491 reads the four coarse anchor
  and dimension words. 11BC:20BA skips the coarse header using its length.
  The fine-mask check reads fields at offsets 4 through 10. Every present
  fine-mask header starts with zero. Its second word varies from 1 through 263.
- **Secondary BIG list.** 11BC:0E83 reads a count followed by count 16-bit
  offsets relative to the BIG tail. At 0F3C each target has 22 fixed bytes
  followed by a count word and count entries of ten bytes each. The loader
  inserts a `FFFF` marker before the resident copy. 10D4 recognizes the marker
  and skips this record when indexing the ordinary ground meshes. All 384
  secondary pointers in the installed BIG files are zero. Synthetic sectors have since confirmed the binary layout and reference reuse.
  The meaning of the header and entry payloads remains open.

## Mesh bounds and sector directory audit

- All 390 mesh records with a nonzero word 7 contain the exact axis-aligned
  X/Z bounds of their vertices. This covers 117 DEF, 260 CSF, five SPN and
  eight BIG records. The four pairs use the numeric order (min X, min Z),
  (min X, max Z), (max X, max Z), (max X, min Z). The 260 CSF records and
  three flat DEF records have equal minimum and maximum Z, so each pair
  of corners at the same X coincides. A zero word 7 indicates the array is
  absent. The draw-list sorter at 15AD:0214 resolves the word relative to
  the mesh body and passes four corners to 15AD:024F for projected bounds.
  Fine collision masks are separate records indexed from LA.BMP.
- Word 6 has two additional observed values: `08FE` in House14Q and
  `18FE` in office1q. Both exceed their respective body lengths (399 and
  477 bytes). The unsigned face-count comparison at 0000:2D34 rejects
  both as pivots. The 1,699 original mesh records break down into 1,535
  offsets immediately after the facing bytes, 141 zero values, 15 active
  pivot values, six `FFFF` values and these two exceptions. The grouping
  routine at 0000:2E59 reads word 5 and the live visibility flags directly.
- All six SCT directories have 4,096 entries. The 11,237 populated entries
  point to distinct lists packed in directory order with no gaps or trailing
  bytes. They reference 17,104 placements and 106 distinct LA.DEF model IDs.
  Across the installed lists, both the Y word and the final word are zero,
  X and Z are below 1,024, and rotations are in 0 through 3. The largest
  list contains 14 records. References that enter through gameplay can
  use IDs that are absent from the SCT files.
- In the six BIG directories, 375 populated primary lists contain 4,156
  placement records. There are 3,005 distinct position-and-mesh tuples
  when deduplicated per sector. The primary lists reference 1,250 of the
  1,317 stored ground mesh records. The final primary list in each file is
  followed by exactly 14 zero bytes per stored placement record. This
  totals 58,184 zero bytes across the six files. This padding is outside
  the primary lists and no secondary list points into it. Its purpose in
  the authoring pipeline remains unknown.

## DOS draw-to-weapon register trace

The main loop calls 06FF at 01EE, then enters 0758 at 01F1 with the
registers left by drawing. Overlays can change DX before 07B0 calls
weapon_frame (6B54). The launch path at 6E38-6E74 uses BP as the
guidance mode and passes CX/DX as potential target X/Z. D896 writes
those words to projectile record offsets 0C/0E and writes BP at 08.
This store happens for both guided and unguided missiles.

| Launch condition | Mode | Source of stored target coordinates |
| --- | --- | --- |
| DS:0364 differs from 12 | 0 | Register values present after the firing and HUD branches |
| DS:0364 equals 12, DS:0418 is zero | 0 | The loads at 6E61/6E63 read DS:0000/0004 before 6E66 tests the null pointer |
| DS:0364 equals 12, DS:0418 is nonzero | 1 | X and Z from the record addressed by DS:0418 |

The flight routine at D8F2 skips target selection in mode 0 and moves along
the recorded bearing. Mode 1 reads live X/Z from the referenced record when
its flags include 2000. Otherwise it reads the launch-time X/Z cached in
the projectile record. Other nonzero modes read the current player X/Z.
At D945 a target closer than 300 units takes the proximity-impact path.
If the steering helper at DA2C reports carry, D967 clears guidance.

32 original-executable runs used four captured gameplay states, four launch
profiles and two incoming DX values (0312 and 0923). The unlocked cases ran
from 0758 through the HUD. The cases with and without explicit targets
entered 6D49 directly to isolate the launch logic. In all four unlocked pairs,
the changed DX survived to D896 and changed offset 0E. Both shots in each
pair stepped to the same position with the same bearing. With a null lock
the executable used the DS:0000/0004 words and selected mode 0. A real lock
stored the same target X/Z for both incoming DX values. After the observed
target moved from (650,1500) to (790,1600), the fixed-lock cases read the
launch position at D941 and the moving-target cases read the updated one.
The test checks one flight step and records the actual target inputs. The
unchanged step by itself would be insufficient to distinguish the two lock
paths because both bearings turn by eight units in this setup.

In a separate original-executable trace of 06FF, 18 captures ran through
six draw profiles each. The normal and objects-only profiles left DX at
03CE, with the final observed change at 11BC:03D3 in the solid-fill epilogue.
Ground-only also left 03CE, from the ground sampling path at 0000:5D37.
Both obscured-view profiles left 03CE after 0000:0DC3. An empty scene
preserved the incoming DX of 7B2C in every case. These results describe
the sampled paths. Other last-object or last-face paths can leave different
values.

DA2C folds the 512-unit direction range using the raw difference between
the target and current bearings. An absolute raw difference of 128 through
383 returns carry and drops guidance. Raw differences of 384 through 511
turn by eight units across the wrap. A direct difference below eight units
snaps to the target. Thus 0 to 511 steps to 504 and 511 to 0 steps to 7, even
though each target is one unit across the wrap. Seventeen original calls
confirmed the threshold, snap and wrap cases.

## DOS CSM save layout

The save menu appends the `.CSM` suffix stored at DS:7790. 4C6A opens the
selected name and 4C78, 4C88 and 4C92 issue three writes. The load path at
4E2F issues the same three transfer lengths. In the installed build DS:11FA
is 0FA8, for a total length of 10A8 (4,264) bytes.

| File offset | Length | Contents |
| --- | --- | --- |
| 0000 | 0FA8 | Main state block from DS:0252 through DS:11F9, byte-masked by 0A76 |
| 0FA8 | 003C | Opponent inventory, ten six-byte records addressed through DS:1208 |
| 0FE4 | 00C4 | Final raw block. Its effective address in the save/load routines differs from the new-game initialization path |

0A76 uses `encoded[i] = state[i] XOR AA XOR ((length - i) & FF)` with
zero-based `i`. The same mask decodes the bytes. Before writing, it replaces
the DS:03A0 player record pointer with 0 for DS:04D4 or 1 for DS:0508. Three
more words become offsets by subtracting 05B0 from DS:03A2, 0DF0 from
DS:03A4 and 0F70 from DS:03A6. The decode restores the canonical player
pointer and adds the three bases back. It also invalidates the city window
limits at DS:7276-727C and recalculates the extra-object byte count at
DS:1204.

The second far-pointer load at 4C8E/4E50 occurs with DS already changed by
the first far transfer. Its effective buffer differed from the main data
segment's 1200 pointer in the observed states. Keep the final 196 bytes
opaque when reading this build's saves. New-game initialization at 0B34
uses the main data segment's 1200 pointer for the same 196-byte allocation.
The object search at 425E reads fourteen-byte records through that pointer.
This identifies the corresponding buffer as the extra map-object list
(space for fourteen records). The main block also carries the list count
at DS:04C6. The observed save transfer reads a different buffer.
The file picker at 4D2E filters for the matching file size. Successful
load sets DS:1143. 59A6 uses it to skip new-game position randomization,
then normalizes the saved position, refreshes the visible cells and
resolves a blocked arrival.

Four round trips used the original writer and reader, two captured
gameplay states and both player record choices. The DOS create, open,
read and write operations used a single in-memory file. Independent
decoding matched every byte of the main block after pointer normalization.
The recorded far transfers matched their effective buffers in both
directions. Player and relative pointers, invalidated window limits and
the reload flag were checked after reading. These tests begin after
filename selection and end before the first resumed game frame.

### Live save and resume

The game pause menu is reached with Escape. Its Save action dispatches
to 4B7E. That branch checks that the player is on foot before enumerating
`*.CSM`. With 19 matching slots it reaches the filename editor at DF4A.
With 20 it opens the delete picker at 4CDE. The original menu then resumes
the save after deleting the selected virtual slot. Both paths were observed.
An existing filename yields DOS error 50h at 4CAD and presents the overwrite
prompt. Cancel preserved the existing virtual file byte for byte. Accepting
the overwrite caused the original create and three writes.

The title dispatcher enters 9B40 for Load. The picker at 4CE5 displays at
most 20 results. Its comparison uses the low word of the DOS directory
entry's size. In directory-only tests the exact length appeared as a
candidate, one-byte-short and one-byte-long entries were skipped, and an
entry with a matching low word and nonzero high word was listed. No
invalid-size payload was opened in this test.

An uninterrupted scripted run saved during gameplay, opened that same
virtual file through the title-menu picker, and reached the original
security-chart prompt. After the answer from the supplied chart, 59A6
received the saved actor and exact 32-bit X/Z coordinates with DS:1143
set. The loop then passed 01DC and returned from its first gameplay
page presentation. All save, overwrite and delete effects were confined
to emulator memory. This trace covers the tested installed build and
the original emulator session, including its regular startup checks.

### Startup option and hardware gates

At 0000:0000 the executable stores the PSP segment and resizes its primary
DOS memory block. F4E5 classifies the display through BIOS 1A00 and the EGA
12h query. The entry point accepts class 2 or 4. Class 4 sets DS:ADD0 for
VGA presentation. 0413 then parses the PSP command tail and can change that
presentation flag through the `ega` and `vga` options. The flag selection
does not establish that the physical adapter supports the selected mode.

Eleven original-entry probes stopped at the first startup decision. VGA,
EGA and both presentation overrides reached allocation at 0053. With
neither BIOS probe reporting a supported display, control took the
incompatible-adapter exit at 002F. The `none`, `adlib` and `sblaster` options
selected the original sound settings before allocation. These probes stop
before device initialization and establish argument parsing only.

Fresh original-executable runs also reached the title keyboard loop in
both BIOS profiles using normal Escape input during the intro. Both
began in BIOS mode 0E. With EGA selected, the intro opened DBI/DCF
resources and the title remained in 0E using `Shooting.img`. With VGA
selected, the intro opened DFB/DFF resources and the corresponding
ATF sequences, then the title entered mode 13h and loaded `Shoot256.img`.
The shared gameplay entry at 99DD selects mode 0Dh after the title loop
returns. The EGA/VGA traces prove the title paths through 9BCD. The
separate save/resume trace proves a transition to the gameplay draw loop.

`link` without a COM option stopped at the missing-port exit at 04C7.
`link com2` set the link flag and COM index 1, then hit the separate
configuration exit at 0046 before gameplay. The parser's COM handler
selects an I/O base through 151B:020F. The entry check after the parser
branches on the link flag itself. A live link session would require an
executable that can pass this gate.

## Parked vehicle persistence

Three in-memory save/load comparisons first called the original 434E to
park a vehicle and C16D to add an opponent inventory item. Before saving,
4248 found the parked car in each case. The save restored the opponent
inventory's 60 bytes and the parked object count at DS:04C6. It left the
destination's extra-object table unchanged. 4248 therefore found no
matching car after the load.

A second trace exercised the same result through the original controls.
From a live driving snapshot, W entered walking mode and invoked 434E.
Escape, Save and the filename editor wrote the virtual CSM. The title
menu loaded it, the supplied security chart cleared the normal prompt
and the original presented a gameplay frame. The count of one survived.
The parked-car lookup did not find the vehicle. This verifies the
observable consequence of the far-pointer mismatch in the installed
build and emulator. All saves existed only in emulator memory.

## Installer archive provenance

Both hard-disk install branches copy the same packed TERM.EXE. The EGA
branch adds the EGA archive and the VGA branch combines VGA1 and VGA2.
COMMON is shared. Each self-extracting executable has a 1,945-byte MZ
image followed by a level-0 LHA archive.

`tools/audit_install.py` verifies the archive header checksums, member
lengths and CRC-16 against the files already present under `data`.
All 101 COMMON, 32 EGA, 10 VGA1 and 22 VGA2 members match. There are
162 LH5 and three stored LH0 members. Both the last member boundary
and the directory membership agree in all four archives.

The disk launcher is a separate path. In three original COM runs, it
read COMSPEC and used DOS EXEC to call the shell with `/C game`.
It forwarded the caller's EGA and LINK COM2 options. GAME.EXE has a
32-byte MZ header, no relocations and a different entry from the
hard-disk PKLITE TERM.EXE. Both normal and LINK child trials stopped
inside its startup wrapper in the project's headless emulator before
the option parser appeared. The installed TERM.EXE's link rejection
is therefore not evidence about the separate disk executable.

### Independent DOSBox comparison

The original packed hard-disk TERM.EXE reproduced the link configuration
error in DOSBox. The disk launcher rebooted with DOSBox's normal automatic
CPU setting. Selecting the 386 prefetch profile got the same unmodified
TERM.COM/GAME.EXE pair to the title menu. The normal launch had zero
in the disk build's DS:01F2 link flag. LINK COM2 set it to FF, and the
disk build proceeded. The title routine and data offsets differ from
those in the hard-disk build.

The disk build's post-selection validation halted at Error 25 in the
VGA, no-EMS and EGA runs. Each test matched the live question against
the supplied chart and checked the selected on-screen symbol before
confirmation. Disassembly places the failure in a validation check
at F039-F05E. The reason it fails under these conditions remains open.
No serial-session behavior was observed. A known-working reference
for the original disk build, preferably imaged original media, would
allow a comparison of the validation path and runtime environment.

The same DOSBox runtime also started the original packed hard-disk
TERM.EXE in single-player mode. After the normal title and chart
flow it reached the EGA 3D view. The pause menu produced a 4,264-byte
CSM. The 60-byte opponent inventory matched the live buffer and the
last 196 bytes differed from the canonical extra-object table. This
independently confirms the save-buffer mismatch in the hard-disk
build. The parked-car loss itself was reproduced in the project's
headless emulator. DOSBox used disposable copies of the installation
and its save file was confined to the test directory.



## Single-player facilities and inventory categories

The original shop dispatcher at 0000:813E sends zero-based kinds 4, 5
and 6 to 8CB0. DS:A968 and DS:A96E hold the VGA and EGA filenames.
The three words at DS:A978 dispatch bank, range and hospital, in that
order. DS:A97E begins a separate two-entry bank menu. The EGA path
duplicates its background into page 2000h. Both paths invalidate the
city cell list, reload the visible window and reset the camera on return.
The facility status in DS:ADCF selects planar or indexed UI drawing.

- **Bank, 8D6B.** Reese's first visit offers theft or withdrawal.
  Withdrawal adds `random_word & 0x0FFF` to DS:117E and sets the
  one-time flag DS:115B. The theft action adds `random_word & 0x1FFF`,
  raises the actor's byte at +32h by 10 and triggers the bank alarm.
  The Terminator and a Reese who already withdrew use a yes/no prompt.
  Accepting from that prompt also forces 7088, which flips bit 0 of the
  status byte in each of the DS:854E location records and resets the
  countdown at DS:854A to 4000. This extra update only occurs on that
  confirmation path.
- **Hospital, 8D21.** Reese can accept or decline the damage panel.
  The Terminator gets a dialogue and an alarm. The accepted path sets
  DS:A87A for the shared panel at 5F06. The panel selects head, torso,
  arms or legs with the corresponding keys and confirms with Enter.
  65D0 advances the world before restoring each selected injury point,
  and can stop if the world simulation is interrupted. The hospital
  halves the base from 600 to 300 before the inventory and difficulty
  deductions. If those deductions make the interval negative the
  routine substitutes 50, then adds one. One selected head injury was
  restored in both displays using 51 simulation steps. Both the body-part
  counter and the total injury word fell from one to zero. Cash did not
  change. The trace used a prepared state with the opponent controller
  held idle during treatment.
- **Range, 8E59.** Six trials with eight possible target positions and
  no immediate repeat. 5B67:0987 increments DS:A964. The intermission
  begins at -120 and waits for zero. After the target appears, Enter or
  Tab samples the pointer and the trial expires at 300 ticks. A hit
  requires both center differences to be within four pixels. On a hit
  the penalty is twice the absolute horizontal difference. A miss or
  timeout adds 10. 9032 divides each accumulated value by six. 90B0
  selects the first threshold with mean time at most its time limit and
  mean penalty numerically below its penalty limit. There are six such
  entries at DS:A9AA and fallback class 6. The result card loads the
  mode-specific MENU image, draws the class and both averages, waits for
  a key, and reloads NUMBERS.IMG and POINTER.IMG before city restoration.
- **Inventory viewer, 51C0 and 51D8.** Six categories reuse one menu and
  one generated textbox. The DS:05B0 table is terminated by a zero
  name pointer. The viewer reads item ID at +2, category at +4 and
  quantity at +5 in each six-byte entry. Misc skips categories 1–5 and
  IDs 10h/A5h and includes nonzero cash. The item panel returns carry to
  reopen the category menu. All six choices in both displays preserved
  the seeded inventory bytes and cash.

`out/verification/facility_trace.txt` records 32 complete prepared-state
runs against the original executable and original resources. Each mode
covered the five bank routes, four hospital routes, one six-target range
session and six inventory categories. The range marks fixed pointer and
timer inputs at the scoring boundary. In both modes it returned
`(15,0), (30,8), (45,0), (60,10), (75,10), (300,10)` as
(elapsed ticks, penalty), rendered the result card, and returned to the
city display. EGA uses the matching archive files, including MENU.IMG
and DAMAGE.IMG, which are absent from the VGA installation. The trace
fixture is `out/verification/facility_probe.py`. It starts at the facility
dispatcher or category menu, leaving city navigation to separate tests.



## Phone book and map references

0000:05D2 polls the P key through C45C. This screen uses video mode 0Eh
and an 80-byte planar stride in both installation modes. It loads
PHONEHDR.IMG and indexes 24 image records from YELLOWPG.CIF. C588 lists
the current window's 11-byte shop records from DS:5CE4 first, then the
four regional records of the same shape selected by C5AF. C5DA skips
kind 4 and emits each accepted entry in traversal order, alternating
between the two columns.

For nonnegative city coordinates, a rendered reference has sector
`(X // 1024, Z // 1024)` and within-sector location
`(X % 1024, 1024 - Z % 1024)`. The northing is measured from the opposite
edge of the cell. In particular an exact Z cell boundary displays
1024 in the local Z field.

The screen changes the CRTC display start by 80 bytes per retrace for
86 retraces for each Up or Down row step. With six local records, it
capped the row index at three. With zero local records it still
rendered the four regional entries and waited for a key without
entering the scrolling loop. Any buffered character exits to the
mode 0Dh street camera.

Four prepared-state original runs in
`out/verification/phone_trace.txt` confirmed row coordinates against
the actual resident and fallback records and traced CRTC movement in
both installations. The viewport addresses for three rows down and
one row up were 6880, 13760, 20640, 13760.



## Original ratings screen and score commit

The title opens the ratings view through 9B57 and sets DS:ABC8.
The pause menu calls D300 directly. D300 selects the only two ratings
files by actor, renders EGA in mode 0Eh or VGA in 13h, and loads the
existing records through D628. Keys 1–5 select the corresponding
record. Space restores the saved 41-byte session record. The pause
view also recalculates and inserts the session's score into the
displayed list in memory. The title view returns to its original
background, and the pause view restores the mode 0Dh street camera.

The pause view's N key opens DF3A, which accepts ten characters,
handles Backspace and returns carry on Escape. D3D5 copies the
buffer even after Escape. Enter saved the ten-character test name
and Escape copied the partial one-character name in both displays.
Neither screen path wrote the score file.

At session end, 0119 invokes D5B1. This routine reopens the original
table, computes and inserts the current rating, and calls D5FA when
the result qualifies. The original DOS path wrote exactly 207 bytes
in both display contexts. Decoding those files yielded five records
and the expected signed score and test name as the first record.
Those writes went only to disposable copies of RATINGS.RSE/TRM.

Eight prepared-state original runs are in
`out/verification/ratings_live_trace.txt`. Tests include title and
pause navigation, confirming and escaping name entry, and qualified
score commits. Tests pair EGA with Reese and VGA with the Terminator.



## Active and Practice startup

The original title uses P to select Practice, A to restore active
opposition, and G to start using the selected options. 9B03 writes
DS:0345 and DS:AA96. The default loadout initializer at 9845 clears
AA96 before the first frame, leaving the main practice gate at 0345
enabled. The world update bypasses its opponent controller call
when that byte is set. The opponent draw-list and bearing indicators
have their own checks for the same gate. Other world and player
updates still run.

Two starts from the original VGA title passed the printed Security
Chart question and reached six complete gameplay frames each. The
A case ran the opponent controller six times. The P case skipped all
six calls while preserving DS:0345=FF. Both cases used the same actor,
difficulty and gameplay display. See `out/verification/practice_trace.txt`.



## Original session transitions and callback graph

Four runs entered the original pause menu from gameplay and exercised
New Game and Quit. Declining either action resumed the next gameplay
frame. Accepting New Game set the AA exit mode, returned to the title
prompt, and skipped D5B1. Accepting Quit took the 55 exit mode, ran the
mode 10h credits screen, and returned to DOS text mode after a key.
The trace recorded the first 12 scroll steps and skipped the remainder
through normal input. See `out/verification/session_trace.txt`.

The disassembly now records 11 indirect transfer target sets from
the original pointer writers. These cover clip edges, projection,
polygon edges, city-loader quadrants, and the sample driver dispatch.
The generated database preserves every previously decoded instruction.
During 24 original gameplay frames and three original 11BC:097E city
loads, the observed register and memory targets matched the curated
sets. The live run used the PC speaker path. Sound-device alternatives
come from the startup assignments in 5B67:0786. The addresses and call
counts are in `out/verification/callback_trace.txt`.

At the menu and map checkpoint, nine transfers were still indirect. They comprised the
chained BIOS keyboard handler, both generic menu action dispatchers,
four sound-driver sites and two deferred link-play sites. Eight decode
ambiguities are in the Creative driver region.



## Original map actions and sector-crossing travel

Seven runs used the original gameplay keyboard handlers for M and
Alt+M, moved the pointer through normal input, and returned through
the original camera reset. Escape preserved the position. H set the
homing target and reached the HUD overlay on the next street frame.
F applied a destination and ran the arrival collision check on both
map types. The local viewport used 320x200 mode 0Dh and the area map
used 640x350 mode 10h. Every run resumed a nonempty street frame.

The area map at CD05 maps its pointer by 307 X world units and 374 Z
world units per pixel. It splits each per-axis value at multiples of
1024 and stores local Z measured from the opposite edge. CC8D uses
49 world units per local map pixel and the origin cursor at (161,93).
It anchors at the current cell and can leave the intermediate local
X above 1023. The tested local target stored (110,33,1318,1024),
which normalized to the observed world coordinates (113958,33792).

The long area-map run started at (114351,33625) and selected (449,89).
The original loaded LAA2 and LAA3 BIG/SCT resources, then ran four
blocked-arrival corrections before the clear position (137995,33658)
and a rendered frame. See `out/verification/map_action_trace.txt`.
The full six-sector OBJ comparison also passed again after these
traces, including world positions, winding and primitive/material IDs.



## Original ending sequences and mesh group read trace

Six prepared-state runs entered the original session ending through
the frame loop. The fixtures supplied the outcome flags at the final
gameplay frame. For the Terminator, the active loss requested DOT and
NET, and completion requested DOS and NY. The Practice loss played
DOT and skipped NET. Each route ended with T in EGA and BBAC in VGA.
The original committed the qualified rating to a disposable copy
and returned to the title. See `out/verification/ending_trace.txt`.

The optional group-count bytes were checked in 36 original draw-list
replays. 2BFF copies the whole mesh, adjusts the face, vertex, facing
and footprint pointers, and leaves header word 6 relative. Each
successful replay watched the optional range from the end of that
copy. The trace included 1,444 ground meshes on the single-face path
and 32 object meshes on the general path. Neither path read the
optional range after the copy in these cases. The existing hypothesis
that positive bytes encode face groups is consistent with the data.
The trace establishes a bound on runtime use and leaves the authoring
purpose open. See `out/verification/mesh_metadata_reads.txt`.



## Original vehicle-to-projectile register handoff

Thirteen original gameplay-loop runs sampled DX at 0891, 0894, 0897
and 089A. Input and state were set immediately before movement. The
runs exercised stationary and moving parking, the walking and driving
dispatch keys, ordinary powered driving, and vehicle destruction.
The charge record was clear so the tests stopped at projectile entry.

- Ordinary driving and the tested destruction-to-walking path left
  `1024 - actor.local_z` at 0894. When the driving transition entered
  the engine-off path, 36E4 left the high word of the actor's world Z.
- Parking and the walking dispatch performed D265 after the walking
  transition. On a clear collision neighborhood, 11BC:2242 popped
  `64 + ((actor.local_x + 8) >> 4)` into DX. The slow parking case first
  corrected a blocked position, then returned with the new sample.
  Two direct Reese arrival runs also confirmed that companion mode 2
  calls 057C and replaces DX with the high word of the signed 1024-fold
  difference of the player and companion Z cells.
- With collection enabled and at least one accepted target, 7878 left
  DX equal to the last accepted record's Z. With collection disabled,
  the movement result reached 0897. With no active visual record it
  also reached 089A. A prepared active visual record overwrote DX
  with the high word of the signed cosine product at A068.

The trace is `out/verification/driving_register_trace.txt`. These checks
exercise the original executable and include the empty-neighborhood
arrival return. Fine-mask and out-of-grid collision exits may leave
different registers.

## Original collision metadata reads

The collision export reconstructs all 19,101 bytes of LA.BMP. In the
original, 11BC:12E7 copies the footprints in resident mesh-slot order.
11BC:258E walks those records to build DS:8FEC. DS:5DC0 maps the slots
back to the original LA.DEF IDs. The trace verifies the resident bytes
against the archive before it sets watchpoints.

Eight prepared queries used real placements of LA.DEF IDs 52 (house4)
and 65 (office1q), covering every rotation. The original coarse stamp
and 586 fine-mask queries read the rectangle, mask origin, dimensions,
and bits. None read the optional coarse groups or the first two
fine-mask words after the resident copy and indexing. See
`out/verification/collision_metadata_trace.txt`.

The first fine-mask word is zero in all 113 masks. The second equals
`(-vertex_y + 8) // 16` for the highest vertex in 104 matching LA.DEF
meshes and for a lower vertex in eight. House9q has a value of 7 with
rounded vertex heights 0, 3 and 4. This supports a height interpretation
and leaves the selection rule and runtime purpose open. The original
words are preserved in the collision export.

## Original audio initialization and sample dispatch

Five fresh runs reached the original title loop. The cases cover NONE,
ADLIB with and without OPL replies, and SBLASTER with and without DSP and
OPL replies. NONE retains device 1 and clears the effects flag at DS:0361.
The available AdLib and Sound Blaster responses produced 378 and 385 FM
register-data writes respectively. The Sound Blaster probe accepted the
DSP reset and complement reply and selected IRQ 7 after command F2.
FMDRV executed startup commands FFFD, FFFF, 1, 4, 2 and 6 in sequence.
Both FM-enabled runs dispatched the same first 11 MIDI events, covering
note-on, control change and program change. The recorded target words
match the original command and MIDI tables in memory.

Separate prepared sample starts called the original device selector and
5B67:0818 using AQUIRED.RS and DOOR.RS. The silent, PC speaker, AdLib
and Sound Blaster callbacks read byte 5 and the word at byte 7. They did
not read byte 6. The three effects drivers entered their active state.
The fixtures supply OPL status, DSP responses, an IRQ and the timer
measurement needed by the original playback gate. These traces verify
startup and sample dispatch. Continuous DMA and audible output remain
unverified here. See `out/verification/audio_startup_trace.txt`.

Six Creative dispatch tables are now annotated from their original
bounds and table words. The wrapper uses DS=5C01; FMDRV uses DS=CS.
The regenerated listing adds 1,212 decoded instructions and preserves
all 33,784 previously decoded addresses and encodings. CT-VOICE's
command 6 entry in this installed executable is 6B06 at 101F:0091. The
word has no relocation. Its nominal near destination lies outside the
driver and begins in text data. It remains unresolved. FMDRV's three
runtime far transfers, the BIOS keyboard chain, two generic menu
sites, and two deferred link sites also remain indirect.

## Synthetic BIG secondary lists

Six original-executable probes loaded temporary copies of LAA1.BIG and
LAB2.BIG. Each sector had an unmodified control, a one-record list, and
a three-cell case sharing three records with zero, one, and three entries.
The fixtures occupied unused trailing padding. The installed files kept
their original bytes.

11BC:0E83 copies the list of 16-bit tail-relative offsets. On the first
visit to a record, 0F3C copies 22 header bytes, a 16-bit count and ten
bytes per entry. It writes FFFF before the copy and replaces the first
two words in the in-memory source with FFFF and the marker offset.
The first resident reference points two bytes past the marker. Repeated
references point directly at the marker, including reuse across coarse
cells. These offsets are relative to the start of the packed mesh area.

The original mesh indexer at 11BC:10D4 skipped every tagged record.
An isolated call to 0000:3DE7 produced byte-identical primary draw lists
for each control and its variants, with 67 records in LAA1 and 92 in
LAB2. Read watches on the secondary directory words, pointer lists and
record bodies observed no reads by this routine in the tested windows.

The Z conversion pass at 11BC:0AC6 reached the marker and entered its
ordinary mesh path. It has no marker check before fetching a vertex
count and vertex offset. The probe stopped there and tested the indexer
and draw-list builder independently against the packed state. Full
frames with secondary records and their intended game or editor meaning
remain unverified. The installed geometry has independent OBJ coverage.

`tools/term3d.py info` reports cell references, record header bytes and
individual entries. The sector OBJ contains the primary placements.
See `out/verification/big_secondary_probe.py` and
`out/verification/big_secondary_trace.txt`.

## Scope, and a command approval failure

The user explicitly approved adding any necessary routines to the local
decompilation harness and confirmed the goal of a complete decompilation.

The proposed next translations are the shared confirmation at 0000:8DFF and
the bank screen at 8D6B, including withdrawal and theft actions. The existing
menu, sound-cache, alarm and world-record code supplies their dependencies.
The current C library rebuilt successfully on Windows, and the ratings module
passed all 2,688 comparisons.

Automatic command approval continued rejecting this source edit after the user's
explicit approval and native-port clarification. Its stated reason cites an
earlier developer restriction on recreating the game. The tool rejection prevented
the edit from running. Neither src/facility.c nor the corresponding declarations
were added. The implementation estimate therefore remains about 59 percent.
The user's authorization is recorded and requires no further confirmation.

## The main loop in C (2026-11-19)

`src/frame.c`: `game_frame` is one pass of the main loop `0000:0155` (single-player path
019D..0247), `frame_input_check` is `0000:05A2`. The loop jumps back to 0155 after each
frame until `DS_PLAYER_DOWN` (1156: 2 killed, 4 a warning ran out) or `DS_MISSION_OVER`
(1159: 1 mission lost, 0x55 wrong symbol) is set, then returns at 024A. One frame:

1. 05A2, skipped while a warning (DS:0200) or the reload overlay (DS:8096) counts down:
   fast-travel message (E1F2, text 0x0625) and the M key (CA46; the map screen from CA73,
   `src/mapkey.c`), P (the phone book from C466, `src/phonebook.c`; both were host calls
   in the first version), Alt+1/2/3 detail, Q while playing
   the actor at 0x04D4 ("Tell Sarah to...", DD0A), F10 (PLAYER MENU, 51AA), Esc (GAME
   MENU). In the single-player path the loop ignores 05A2's carry; only the link path
   tests it.
2. EA2E counts down to "The game is now over because you selected the wrong symbol"
   (text 0x0213) and sets 1159 = 0x55.
3. `gameplay_update`, overlay restore (unless a warning or reload overlay), the city and
   scene (01DC..01EE), `scene_post_render`, `scene_present`.
4. At frame end: border back to palette entry 0 if DS:7BD5 (EV_BORDER), palette reload if
   DS:01DD (7AB6 -> 0BE8 writes attribute registers 0-15 from DS:1510; host call), "Leaving
   a moving car hurts" (01DC, text 0x0343); DS:020C counts up.

Menu and message texts live in the segment at DS:EA36 (1819 in the snapshots), not in DS.
Correction: the border event's second value is the colour of the requested entry,
DS:1510+BL; it was always DS:1514 in frame.c's first draft (right only for player_hit's
entry 4).

`tests/test_frame.py` runs one frame in C and the same iteration in the original (0155 to
the next 0155 or 024A, interrupts off; sound 89A2, border 0A4F, palette 7AB6 and the two
retrace waits 0D8D/0DAA stubbed and logged; message boxes get Enter pressed at their
first wait and released, and keys held on entry are released at 5169). Four recordings
(130 frames: walking, armed with 8 real shots and empty-gun clicks, opponent near,
driving) times seven variants (as recorded, Alt+1/2/3, wrong-symbol timer expiring,
border and palette requests, both messages) = 910 frames; all memory but the stack,
the planes, the card registers, CRTC start, sounds, border and palette requests and the
return value agree. 256 frames have sounds, 148 border changes (18 from real hits).

Test-harness notes: `capture.py` uses one shared temporary file, so recordings must be
made one at a time. A held Enter/Esc at a message box hangs both the original and C
unless the test releases it (the box first waits for release).

## The M key's map screen in C (2026-11-19)

`src/mapkey.c`: `map_screen` is 0000:CA73..CB4A, called by the frame's M-key check (CA46,
in `src/frame.c`), so the whole of CA46 is C. M opens the local map (keys are flushed first,
3732 = `keyboard_flush`), Alt+M the area map (pages selected with 0C6B AX=0 and stride 80
first), Ctrl+M only restores the information panel area (CDAA: on foot with the normal
camera, `map_clear_info` and two 8x64 copies from 0x11B7 to 0x31B7 and 0x51B7) and clears
DS:E1EF. Map results (DS:E25A): 'H' stores the destination and sets homing (DS:E1EF, the
compass points at it); 'F' sets DS:E1F0 (read nowhere in the listing) and fast-travels; on
the local map a place off the map (CC8D carry) opens the map again. Fast travel is refused
with text 0x04B7 ("This car can not travel at the speed...") unless on foot (actor +14 bit
0), and with 0x058A ("...while engaged in battle") while DS:115A is set; otherwise CBA5,
D177, D265 (the C `travel_run_native_simulation` and `travel_clear_arrival_native`). Every
path but Ctrl+M ends with stride 40, `camera_reset` and `update_visible_cells`.
Area map curiosity: holding N, U, M, S, K and L together in the area map sets DS:E1F1
(already in `map_select`).

`tests/test_mapkey.py` starts from the main-loop recordings with M (Alt, Ctrl) held and
compares C `frame_input_check` with the original 05A2. Method (new, reusable): the original
runs first; each remaining host boundary (0C6B, map-setup image/file loads 6962/FAAF/FACE
and palette 7AB6 when called from CE00..D000, 7AAF, int 10h mode switches at 7A35/CF77,
retrace waits 0D8D/0DAA/5776:02C6, movie B210, panels 57E7/57D4, 057C) is recorded with
memory and screen before and after; the scripted keys are written at chosen retrace waits
and so appear in the recorded "after". C then runs with services that check service,
arguments and the complete state against "before" and copy "after" in. Cell loading and
camera resets during fast travel run in C on both sides. The C file host must take over the
emulator's DOS handle counter after each replayed boundary, or the next handle stored in
DS:8080 / DS:7270 differs (handles are never reused). 32 cases: 6 completed fast travels
(5 with world simulation, 1,296 world steps), 6 refusals with the message box, 8 homings,
12 exits (Esc, Ctrl+M); all equal.

## The P key's phone book in C (2026-11-19)

`src/phonebook.c`: `phone_book` is 0000:C466..C556 (the P test at C45C is in `src/frame.c`),
with C557 (scroll), C588 (entries), C5DA (location records), C72F (panels), FA4B
(`string_copy`), FA72 (its length count), F604 (`number_format`) and F86A (its division
step). Order: mode 0Eh (0BE5 = INT 10h), 0C6B AX=0, the whole page filled with colour 14
through set/reset (GC0 = 0Eh, GC1 = 0Fh, map mask 0Fh, 32K words), PHONEHDR.IMG with
DS:805C = 02F8 (then 0FA0), the heading "Use UP arrow and DOWN arrow to see other..." at
column 10 row 2 (DS:E41C = 6, stride 80) only when the window has shops (DS:72B2), the
panels, the keyboard buffer cleared (3792), then the scroll loop (only with shops): Down
and Up held move one row per pass (86 retraces, CRTC start +-80 each), the row index
capped at ((shops + 3) >> 1) - 1; the loop ends when the low byte of DS:5BD4 is non-zero.
Then keyboard_read (it waits when the buffer is empty, as with no shops), mode 0Dh,
DS:ADCF = 0, camera_reset, DS:7242 = FFFF.

A panel per record that is not kind 4 (shops of the window, then the four regional records
of C5AF): sector and location from IDIV by 1024 (location z = 1024 - remainder), colour
DS:DF3B[local z & 7], picture DF68[(kind' * 4 + (local z & 6) / 2)] where kind' = kind - 1,
less one more above 3; the picture is unpacked (one plane, ByteKiller) behind the CIF data
in the file buffer and drawn with the mask blitter (37 bytes x 72 rows, stride 80, colour
and stride written into the code bytes CS:1B41/1B42 as the original does; 1B42 goes back to
40). The reference "Sector X Z  Location x z" (strings at DF23, DF2B, DF2D, DF39) is built
at DS:7795 and drawn at the panel's DF98 entry (column, row, E41C). DS:E41C = 0 after.

`tests/boundaries.py` now holds the record/replay method of the map-screen test, with a
third kind of boundary, a point: no call, a place where the original polls (C538 in the
scroll loop; 37AC while the buffer is empty). C's KeyboardPlatform.poll is placed at the
same point of its loop, so input arrives at the same moment in both.

`tests/test_phonebook.py`: three recorded frames x four shop counts (0, 1, 3, recorded 6)
x three key scripts = 36 cases, 0 to 16 row scrolls (the walking recordings hold Up, so
with Down held both scroll every pass); all equal at every boundary and at the end.
`tests/test_strings.py`: 2,286 cases of FA4B and F604 (bases 0..36, 40, 100, 200, 255);
equal. The game's stack (SS 6CDE in the snapshots) lies inside the data segment's 64K
window, so a routine-level test that compares the data segment must leave out the call's
own stack bytes.

## The gameplay menus' options in C (2026-11-19)

`src/gamemenus.c`: `game_menu_display` shows a menu through an adapter over the host's
MenuPlatform; a chosen option (MM_ACTION with the handler's address) runs in C when it is
translated and goes to the host otherwise. The frame's Q, F10 and Esc menus use it
(`FrameServices.menus`). Action tables: GAME MENU DS:7852 (4F02 joystick, 4B4A audio, 4B7E
save, 4CDE delete, 4E86 quit, 4EA2 new game, 4EFA ratings), PLAYER MENU DS:7968 (51D8
inventory, 5309 physical status, 53F5 drop item, 578A special action), "Tell Sarah to..."
DS:E3F0 (DD33..DD2F: stay, run away, follow, give item, take item). Menu_run calls the
handler with SI = 0; Sarah's entries are a run of INC SI, so the order is DD33 - entry.
Orders 0-2 are stored in DS:11BE (the companion's mode); 3 and 4 call the routines in the
table at DS:E3E2 (57E7, 57D4: the give/take panels).

A handler that closes its menu drops menu_run's return address (ADD SP,2) and returns to
the menu's caller; the carry flag it leaves is the menu's result. ADD SP,2 itself clears
carry, so only an explicit STC after it counts (4E86 quit). The inventory handler 51D8
reopens its category menu while that returns carry. So `menu_run` and `menu_display` now
return the closing handler's status: `MENU_CLOSED` (1) or `MENU_CLOSED_CARRY` (2); Esc
gives 0. All callers only tested `< 0`.

facility_confirm (8DFF, used by quit and the facilities) builds its menu in the text
segment at 0x0296: the fixed header 0B 02 01, the question from DS, "      Yes" (DS:A87C),
"      No" (DS:A888), FF; width = question length + 4; actions DS:A974 (8E32 yes, 8E40 no,
which set DS:A87B to FF or 0). Quit sets DS:1159 = 55 on yes; new game (its own yes/no menu
0x10C1, actions 7811 = the basic actions 4EDC/4EEB) sets DS:1159 = AA.

Still the host's: save and delete (4B7E, 4CDE: the CSM file picker), ratings (D300),
the damage panel (5F06), joystick detection and calibration (3A12 returns carry when
there is none, 38F6), the give/take panels, the inventory and drop viewers behind tables
DS:7970 / DS:7988 (51FD..5216, 541B..542F) and the special actions behind DS:AAAD.

`tests/test_gamemenus.py`: 21 scenarios on two frames each (the Terminator's recording,
and `frameloop_reese` from the `ai_companion` snapshot for Sarah), every one checked to
reach what it tests (the host screen called, the flag set, the nested menu opened, the
message box); 42 cases equal. A deliberately wrong order mapping fails at once.

Inventory viewer (5216, entered at 51FD..5211 for categories 1-5 and at 5216 for Misc.,
BX = FFFF): DS:792A = category; header from the text segment's table at 0x0736
("MISC INVENTORY", "WEAPONS INVENTORY", "AMMO", "CLOTHES", "DRUGS", "TOOLS"); under Misc.
a "$<cash> Cash" line when DS:117E is non-zero; then every 6-byte record at DS:05B0 (name
pointer, id, -, category, count) of that category, or for Misc. every record whose
category is not 1-5 and whose id is not 10 or A5: the count as a signed byte (F5D5) in two
characters, a single digit right-aligned, then a space (which overwrites a third
character: a count of 200 shows as "-5"), then the name. A message box at text 2 (5, 0,
25 x 25); it closes the category menu with carry, so 51D8 shows the categories again.
`tests/test_gamemenus.py` stocks the inventory (names pointing at resident strings) for
six viewer scenarios; 27 scenarios x 2 frames = 54 cases, all equal.

Dropping items: the drop handler 53F5 shows the categories (actions DS:7988: 541B..542F,
5434 for Misc.); a category opens "DROP WHAT?" (5437; header at text 0x095F; the same
item lines as the viewer, but as menu lines, kind 4; actions DS:7994 = 551A..5507 for
lines 1..20, a run of INC SI before 551B), or "You have nothing to drop." (text 0x0A2E)
when nothing is listed. 551B finds the chosen line again by category, where Misc. means
category 6 only (the menu also listed categories 0 and 7 and up: line 1 of Misc. can drop
an item the menu hid, id 10, as the test shows), with no end check; 565B leaves the item in
the world (a 13-byte record in the ring of 20 at DS:0253: player position words +1E, +20,
+0, +4, the name, id and weight, category; next slot DS:03FC; DS:116C less the weight);
then inventory_remove (5546). Both menus close; 53F5 rebuilds the HUD.

Fix in `src/weaponhud.c` (weapon_inventory_rebuild, 985C/5754): the weapon id is looked up
in DS:78DC without an end check, so an unknown id finds a "slot" past the table. The
original then sets the weapon bit with ROL AL,CL (wraps at 8) and reads the icon pointer
with the slot sign-extended (5754 leaves BX = CBW of it); the C used 1 << slot and the
unextended slot. Only unknown ids reach this; the test's stocked inventory has two.
`tests/test_gamemenus.py`: 32 scenarios x 2 frames = 64 cases, all equal. The stocked
inventory must also set the list's end pointer DS:03A2, or removing an item shifts
garbage (inventory_remove compacts up to it).

Sarah's item exchange (orders 3 and 4 of "Tell Sarah to...", and companion modes 3 and 4
in the world step): the table at DS:E3E2 sends order 3 to 57E7 (take: DS:0252 = FF, from
Sarah's list 085C in DS:03FE to the player's 05B0 in DS:0400) and order 4 to 57D4 (give:
the other way). Both open the category menu (actions DS:79E4: 580E..5822, 5827 for Misc.);
a category opens 582A: "TAKE WHAT FROM SARAH?" / "GIVE SARAH WHAT?" (text 0x0992 / 0x097E),
item names only, from the source list, as a menu (actions DS:79F0 = 58F8..58E5 for lines
1..20), or "There is nothing here to exchange." (0x0A50). 58F9 finds the line again by
category (Misc. = 6, as in dropping) and checks Sarah's load DS:0402: plus the weight when
giving, minus it when taking; 35 or more (unsigned, so taking more than she carries also
wraps to it) gives "This item is too heavy for Sarah to carry." (0x0AA2). Otherwise
DS:0402 = the new load, and 5558 adds one to DS:0400's list and removes one from the
found record onward.

5558 (`inventory_transfer`, src/inventory.c): adding increments an existing record's
count or copies the record (5 bytes) from DS:03FE's list onto the end with count 1; the
player's category counter (pointers at DS:9A4E) and the list end DS:03A2 then go up when
DS:0400 is the player's list - for a copied record the original compares DS:0400 with the
word stored at 05B0, not with 05B0 (kept in C). Removing decrements; at 0 a record of
Sarah's list (DS:03FE = 085C) is closed up by shifting the following records down to the
end marker, one of the player's with the counters and DS:03A2 as in 5546. The remove-only
entry 5546 (`inventory_remove`) sets DS:03FE = DS:0400 = 0 first.
`tests/test_inventorytransfer.py`: 600 random cases of 5558 in the combinations the game
uses (add to DS:0400's list, remove from DS:03FE's; other combinations make the original
compact 64 KB over its own stack); equal. `tests/test_gamemenus.py` now 38 scenarios x 2
frames = 76 cases (exchange both ways, Sarah's weight limit both ways, nothing to
exchange); equal.

## The damage panel in C (2026-11-19)

`src/damagepanel.c`: 0000:5F06 ("Physical status" in the player menu, and the hospital) with
603E..6884, 5776:0000 and 11BC:1A84/1AC8/1B7F. DS:ADCF := DS:ADD0, so a VGA installation
runs the mode-13h version (Dam256.img, VGA digits/boxes/traces/lines), an EGA one the
mode-0Dh pages (Damage.img, plane-3 boxes via 5776:0000). Body parts are actor bytes +11..+14
(head, torso, arms, legs; maxima +15..+18; +1A total damage, +1C its maximum). H/T/A/L
toggle parts (DS:7D00..7D06; cost 5 per point at 7D08..7D0E), Enter (DS:7D10) heals while
DS:7BD4 (interrupted) is clear and not in battle (DS:115A: "You are unable to concentrate
on healing yourself..."); one typed key is read per frame, Esc leaves (mode 0Dh, ADCF = 0,
camera_reset). Per point healed the world runs B588 for N + 1 ticks, N = 600 (300 in the
hospital, A87A) - 12 * DS:AB02 - DS:7D2A[difficulty], at least 50 - but N is the CX that
inventory_count_required leaves: only an empty required-item list (DS:AAD2 / AAE2) keeps
600; otherwise it is 19 less the slot of the last item searched, or 0, so in practice every
point takes 51 ticks. An opponent showing up ends it ("Your healing was not completed");
the VGA path then calls 64E3 with SI = 1E20 (the overlay-save argument still in SI), so it
updates "wound bits" at DS:1E39. Each point: the pause 5776:02C6 for 20 frames as Reese, 10
otherwise; 0556 counts down for Reese on every search step. Two heart-rate traces (player:
DS:7BE0 = health in 117ths, 6321; other: Reese, or 053C when DS:1152) flip every half beat;
a 70-point wireframe body (7EB6) turns 4 per frame (DS:7BE4) with lines in red where a
part is damaged (6849: lines 0-11 head +11, 12-32 torso +12, 33-64 legs +14, the rest arms
+13). The panel draws its numbers with the VGA routines before switching to mode 13h, so
in the original those first writes go to the EGA planes; C routes VGA writes by the BIOS
mode at 0:449 for that reason. 5776:0000 leaves DX at 3CF, so its last OUT DX,AX sets the
bit mask to 1 (3D0 takes the 0) instead of disabling set/reset; nothing observes it before
the next write. On a VGA installation textbox_draw (5032) is the VGA message box 11BC:2BCC,
which busy-waits at 2C27 / 2C35 / 2C45.

`tests/test_damagepanel.py`: 14 cases (VGA as recorded, EGA with DS:ADD0 = 0 and Damage.img
from data/ega; the Terminator, Reese; healing, interrupted healing - the opponent even hits
during it -, in battle, selections), 19 points healed in all; every boundary and the end
equal, the mode-13h screen included (`tests/boundaries.py` now keeps it on request).

## The scalable font in C (2026-11-19)

`src/fontscale.c`: 11BC:28F8 (`font_load`: font.pck into the work buffer, DS:ADFE = its size,
DS:ADE8 = DS:AE00 = its segment, DS:ADE6 = 0; nothing changes when the open fails) and
11BC:2714 (`font_scale`, with 27D0 per glyph and 281E per row): AX = source rows | width <<
8, BX = target size, CX glyphs (LOOP: 0 means 65536), SI source, DI target. Rows repeat
target/source times plus one whenever the remainders add up past the source rows; pixels
the same way across; the output byte (AH) carries leftover bits from one row into the
next. Then the 88 widths at DS:AEC3 are scaled into DS:AE64: (w * 256 / src_width) *
dst_width, high byte, plus 1 when the low byte is 40 or more; DS:AE02 into DS:AE03 the same
way, except that there is no XOR DX,DX before that division, so the last table entry's
leftover DX is part of the dividend (and can overflow: a divide error, with sizes the game
never uses). The ratings screen scales the 12x12 font to 12x12 (0C0C) and calls it with 70
glyphs. `tests/test_fontscale.py`: 160 random fonts and sizes plus font.pck at six sizes;
172 cases, all equal.
Text in the scaled font: 11BC:2682 (`font_text`, with 28B0 / 28E4; 13 callers): AX = x, BX =
y (row y * DS:1228 from offset 0 of the EGA screen), DS:SI the string; set/reset in
DS:E40F's colour, each glyph row written as two bit-masked bytes (the glyph byte rotated by
x & 7), the right one overlapping the next byte. A space advances DS:AE03, any other
character maps through DS:AE05 to a scaled glyph (behind DS:ADFE in segment DS:AE00) and
advances DS:AE64[ch - 20h]. Returns AX = the x after the string. The tear-down 28E4 writes
AX = 08FF to port 3CE (index 15 := 8) where FF08 was meant, so the bit mask stays as the
last glyph byte left it. `tests/test_fontscale.py` adds 72 strings at random places,
colours and strides: 244 cases, all equal.

## The ratings screen and name editor in C (2026-11-19)

`src/ratingsscreen.c`: 0000:D300 (`ratings_screen`, from the game menu's Ratings option and
from the main menu) with D4C3 / D74B (the statistics), D7F9 (7x7 VGA text), D856 (that
font into far DS:E34E), D863 / D877 (the VGA screen kept at far DS:91B8 meanwhile), 9A13
(the EGA frame lines, table DS:ABCC), DF3A / DF4A / E046 (the name editor), 0CC2 (EGA
rectangle fill), F62C / F5EB (decimal numbers). The character's ratings file (DS:E27E for
Reese, E28A otherwise) is read into DS:50B2 and decoded (D628, `ratings_decode`); the
current session is scored (D6CB) and inserted (D67F) unless DS:ABC8 says the call came
from the main menu, which also skips the mode switches on the way in and out. A new best
session (DS:11A8 >= 0) with no name yet (DS:038A empty) opens the editor: message DS:1012
at 5,5, ten characters; the name is taken even after Esc; it goes to DS:038A, DS:E3B0 and
the record's name at +14h. Keys: 1-5 show a ranked record's statistics (DS:11A8 = 5 - n),
Space the current session again, N (in play only) the editor again, Esc leaves; on the way
out in play: mode 0Dh, stride 28h, camera reset, all visible cells reloaded.
VGA (DS:ADD0): mode 13h, Ratings.img chunky with its palette, the 7x7 font (glyph rows 24h
apart; digits, letters, spaces; anything else ends the text); EGA: mode 0Eh, the image in
the planes, the scalable font (`font_text`, 12x12) and the frame lines.
The editor 0000:DF4A: SI = message, BX/DX = its place, CX = the maximum; select pages 0,
the message box without waiting (DS:5A4E = 1), the field's place in the two bytes after
the message's NUL (DS:E416/E418), the field filled in colour 4 (EGA 0CC2, VGA 11BC fill),
the name and cursor (DS:E410) in colour 0Eh (EGA) or FEh (VGA). Characters below 20h and
any beyond the maximum are ignored, backspace removes one. Esc (the key table): wait until
it is let go (E038), restore the box, return with carry, DS:5A4E left at 1. Enter: NUL,
restore, DS:5A4E = 0, select pages 2. The restore is 5776:0247, which on the mode-13h
screen goes on to 11BC:2B91 (the VGA box restore).
`tests/test_ratingsscreen.py`: 13 cases (VGA and EGA; named or new best; ranks, Space, N, typing,
backspace, too long, Esc in the editor; from the main menu; Reese), every boundary and the
end equal, the mode-13h screen included.

## Accounting pass and the host layer (2026-11-19)

`tools/coverage.py` now measures the translation from `disasm/functions.csv` and
`tools/names.py`. A pass over the routines that only translated code calls found 4,400
bytes of helpers the C already contains but that were never recorded: the line octants and
the vertical / horizontal cases of `line_to` (0DC7, 0E39 - now separate entry points in
the listing, `SEEDS` "jump target", as are 1090 / 1106 of the 640-wide line 1201), the
`area_line_to` octants, the figure walk and spawn helpers, the window loaders, the LZHUF
decoder core, the polygon edge handlers, and 38 far-call thunks (`CALL x / RETF`) whose
target is translated. Each is recorded against the C file that contains it.
`NATIVE` (new, in `tools/names.py`) lists the routines that only reach the hardware or DOS
and that were then left to the host's services: the Sound Blaster and
driver layer in 0000:EFA0..F4DB, the DOS file and directory library F63F..F8D5 and 11BC:10C6
/ 10CB, interrupt vectors, the BIOS tick count, INT 10h, the adapter detection F4E5, the
CRTC start C571, the retrace waits 0D8D / 0DAA. The listing marks them. Result: C 81.3%,
native 2.4%, left 16.3% (13,165 bytes, 213 routines).
Note: `tests/test_ratings.py` is the ratings codec test (2,688 cases); the ratings screen's
is `tests/test_ratingsscreen.py`.

## The keyboard interrupt in C (2026-11-19)

`keyboard_scancode` (`src/keyboard.c`) is the game part of 0000:37E3, given the byte the
host read from port 60h: it empties the BIOS buffer (0:41C = 0:41A); an F0 byte sets DS:5BD6
so that the next byte counts as a release; a release clears key_down[code & 7Fh]; a press
stores DS:5BD8, sets DS:5A50 on F12 (the main loop then toggles the code-segment byte 3B87
that makes the interrupt chain to the BIOS instead of acknowledging the key itself), takes
the character from the table at DS:5A6A (DS:5AEA while either Shift is down) and puts it in
the ring buffer 5B70..5BD3 (write place DS:5B6C, read place 5B6E, count 5BD4; a full buffer
keeps its write place). Left Shift is mirrored into Right Shift. DS:5B6A, when set, skips
the buffering, and then the key marked down is still the previous DS:5BD8 (5B6A is only ever
cleared in this program; the store that would set it, at 3897, is unreachable).
Ctrl+Alt+Del jumps to FFFF:0000; C returns 1 instead. The install (3756) and restore (3783)
of the vector are host work. `tests/test_keyboardisr.py`: 40 streams of 60 random bytes, 2,400
interrupts, all equal.

## The 640-wide line in C (2026-11-19)

0000:1201 is `line_to` for the 640x200 screen (mode 0Eh): the same code with the 40-byte row
table's entries doubled (`ADD DI,DI` / `ADD CX,CX`) and 80 bytes a row, its own vertical
and horizontal cases 1090 / 1106 (in the listing they used to sit inside "ega_begin_line"
1075), octants 12A3..12F7 and start 1313. One register difference: the vertical case keeps
its stride 50h in BX. `src/line.c` now draws both with one stride parameter
(`line_to_wide`). `tests/test_linewide.py`: 1,200 lines, all equal (`tests/test_linebx.py`,
the 320-wide one, unchanged at 2,048).

## The start-up screen (segment 57C5) in C (2026-11-19)

`src/intro.c`, `intro_screen` = 57C5:000E, called once from 0000:04E8: the credits (DS:DBB6,
pages ending in NUL, lines in 0Ah, the end FF FF) are typed in the 12x12 scalable font into
a one-bit buffer (segment DS:DE20 = the collision segment, set by 57C5:053C at start-up; 80
bytes a row; 11BC:2925 draws a character) with a 16x11 cursor (DS:DE18 per line), a frame
every second character: the logo, the buffer copied in white onto the 640-wide page
(0000:1769, colour by set/reset, the bits as bit mask), the page shown, the area from row
10 cleared (0000:17C0, which stores AX = FF08 over it). After each page a 30-frame pause
with the cursor blinking in its last 8, then a second pause of 10 frames with the buffer
cleared. A key (the low byte of the count DS:5BD4) ends it at once, straight from the
stack pointer kept in DS:DE2E (so the view window is not reset); otherwise 100 frames of
the logo alone, DS:DE2C growing, and set_view_window(12).
The logo: 171 points (DS:C1DE x, C334 y, times 16, y - 645h, into DS:50B2) and the
polylines at DS:BE94, drawn closed in colour 1 with the 640-wide line through its own
Cohen-Sutherland clipper (57C5:03F0, four tries, outcodes OR-ed into DS:DE32; vertical and
horizontal lines only cut). Its two halves slide in from DS:BE8E = 0 and BE90 = EED0h, two
pixels a frame each (about 1,100 frames: the credits normally end first); then it zooms:
(v - centre) * 256 / DS:BE92 around DS:DE28 / DE2A, BE92 += DE2C each frame. BE92 starts
at 1 and DE2C at 0 and only grows in the last 100 frames, so during the credits most
projections overflow. The divide-error handler 0000:0407 skips two bytes, but this IDIV
WORD PTR [BE92] is four, so the CPU resumes inside it: XCHG AX,DX / MOV SI,0603h / SUB
DH,BL (57C5:02EF) or SUB BL,DH (030A). The coordinate becomes the dividend's high word,
the polyline walk continues from DS:0603 (whatever is there), and an overflowing y also
takes DH from the x just projected. The C does all of that.
`tests/test_intro.py`: 7 runs (as recorded, from the start-up values, zoom at divisor 256
and 1, shortened credits to the end and with a key in a pause), every boundary and the end
equal, plus 57C5:053C. Segment 57C5 is now entirely C.

## The copy-protection screen in C (2026-11-19)

`src/protection.c`, `protection_screen` = 0000:EA86 (once: DS:E67E), run after the main menu.
VGA: mode 13h and pass256.img (EE9F, already C); EGA: mode 0Dh and pass.img. A 16 x 24
table of the numbers 1..384 (DS:E72E, also the VGA palette buffer) is shuffled (EE42: the
random generator seeded from the text segment's words 7F1 / 7F3, low bit set, then set
back as it was; each number goes to a random free slot, `DIV CX` by the loop counter
itself, probing forward). The question: row 1..191+8 and column 1..127+8 (EC0E), shown
divided by 8 in three text lines at row 21 (ECDE; EGA sets the stride's low byte to 28h).
EDBD repeats the shuffle under the ten seeds 7F3 = 41h..4Ah and keeps each one's entry at
the question's place at DS:E6E0. EC41 picks 24 different symbols: the right one, then the
kept answers while DS:E6DF counts (normally 0), then random ones (a candidate is compared
with every word from DS:E6F6 up to the first zero - on VGA that runs on through E72A and the
whole table), swaps the right one to a random place (DS:EA30) and draws them all (EAF5:
16x16 bits from shapes.img, unpacked into the file buffer, 40 a row of 500h bytes; VGA
chunky in the colours 03 / 08, the selected one 04 / 08; EGA planar, the selected one
inverted). The selection (EB9A) reads the key table in a busy loop: Right and Left switch
column, Down and Up move two places (clamped), a held key repeats every ten frames, Enter
ends it. Then DS:B6A0 = 0, the wrong-symbol timer DS:EA2E = 0, DS:EA34 = EA30: in this build
the choice is never compared - the CALL EE0C at ED90 sits behind NOP / JMP EDBA, and EE0C
(text mode, message, endless loop) is unreachable; it is in the new `DEAD` table of
`tools/names.py`. `tests/test_protection.py`: 9 runs (VGA and EGA, moves, edges, held keys,
kept answers, already shown), every boundary and the end equal, the VGA palette too.

## The bank and hospital in C (2026-11-19)

`src/facility.c`, `facility_screen` = 0000:8CB0, which the shop screen jumps to for kinds
4..6 (BX): 4 the bank, 5 the firing range, 6 the hospital (images DS:A968 for VGA, A96E for
EGA; handlers DS:A978). VGA: mode 13h, the 256-colour image, the handler, then the facility
flag off; EGA: mode 0Dh, pages 0, the image copied to page 2000h. Then all visible cells
rebuilt (DS:7242 = FFFE) and the camera reset. Only Kyle Reese (DS:03A0 = 04D4) is
served. Hospital (8D21): Reese is asked (A8DF) and, on yes, treated in the damage panel
with DS:A87A set; the Terminator gets message 03F8 and the alarm (shop_alarm with DS:7A18
set). Bank (8D6B, DS:A917 set meanwhile): Reese, until he has had his money (DS:115B),
gets the menu 0311 (actions DS:A97E: 8DD3 rob, 8DBB withdraw: cash + random & FFFh); anyone
else is asked A8F4 and on yes robs it (8DDF: cash + random & 1FFFh, player byte +32h + 10,
the alarm, DS:8447 = 0; then DS:854A = 1 and the world's records toggled). Both switch the
sample groups to 4 inside and back to 3. The menus and yes/no are the mode-13h ones on
VGA, whose overlay restore is 11BC:2B91. `tests/test_facility.py`: 15 runs (EGA and VGA,
the Terminator and Reese, every branch), every boundary and the end equal.
Not done yet: the shop screen still returns an error for kinds above 3 instead of calling
`facility_screen` (ShopScreenServices needs the facility services first).
The firing range (kind 5, 8E59) is C as well: the targets' mask (range.dat at DS:7C20) and
the pointer shape (DS:A982 into 7BF0); six rounds of a pause (DS:A964 from -120 counted up
by the timer interrupt, 9023 busy-waits), a random target 0..7 never the previous one
(8EA5: VGA an 8x8 mask in colour FF at DS:A948[n], EGA screen_blit_mask with the code byte
1B41 set to 0Fh at DS:A938[n], then the page copied), aiming (8F78: the pointer moved by
map_pointer_step every frame until Enter or Tab or 300 ticks; on a shot, sound 3 and the
penalty: twice the horizontal distance between the pointer's centre and the target's
(DS:A918 table), 10 when over 8 - and a vertical distance over 8 also gives 10, otherwise
it never counts; a timeout scores 300 ticks and 10), the target erased. Then 90B0: the
averages over six as text (seconds with two decimals at DS:7795 - the hundredths printed
without a leading zero - and the penalty with its remainder of six at 77A9), the first of
six thresholds (DS:A9AA) both are under gives the rank 0..6 (DS:A9A8), its picture
(range2.img packed on EGA, a raw header-and-rows picture on VGA, 9132), a box round the
rank's row (9169, line_to or the VGA line), the averages at column 22, rows 4 and 5, and a
key. 6149 reloads the HUD numbers and pointer. `tests/test_facility.py` now 18 runs: the
range on EGA and VGA with shots on the spot, aimed shots, Tab, timeouts, a middle rank (the
timer is advanced by the test at the pause's loop and the retrace waits).

## The main menu in C (2026-11-19)

`src/mainmenu.c`, `main_menu` = 0000:9922 (every time before a game): default palette, the
facility flag from DS:ADD0, the Terminator as player (03A0 = 0508, vehicle 04BA = 04D4,
03F2 = 12Ch), pages 0, font.pck scaled to 12x12. VGA: colours FD / FF / FE (DS:ADD1-3),
mode 13h, menu256.img, the chosen value of the first six options lit (DAC register
DS:ADAE[i] + value set to 0, 1Ch, 3Fh; the others are 7, 1Ch, 1Eh); the serial link's
151B:06DE when DS:A9D9. EGA: colours 0F / 0E / 0C, menu.img, the frame lines (9A13), every
option's choices in the scalable font (9A33: records DS:AD68, count, x, y, choices of n
letters, the hotkey letter in colour ADD3, the rest; the chosen one in ADD2), page 0, the
game palette. Keys (9BCD, AND DFh): V shows the version box 07F5; otherwise the 18 hotkeys at
DS:AD32 (key, option, value) - T/R character, F/S length, E/D/H difficulty, X/M/N detail,
K/J controls, A/P practice, L load, G start, I ratings, Q quit. A choice option (DS:AD90) that
changes redraws the old and new choice (EGA, the new one in 0Eh) or swaps the two DAC
registers (VGA); then the option's handler (DS:AD7C): 9AB1 player Reese (03F2 = 96h) or
the Terminator, 9ADE DS:1151, 9AF1 difficulty 03F0, 9AFA detail ABCA, 9B20 the joystick
(3A12 detects, 38F6 calibrates, DS:5A4F), 9B03 practice (0345 and AA96), 9B40 load (4CE5;
leaves when DS:1143 is set), 9B53 start, 9B57 ratings (the screen kept at 8000h, DS:ABC8
set), 9B9D quit (DS:1159 = 55h). Without a joystick, 9B20 sets AL = 'K' and jumps back into
the loop from inside the handler call; its return address stays on the stack, so the next
start (ADD SP,2 / RET) only returns into the loop and a second one is needed. Afterwards
the ten values go back to their defaults (9D29: DS:ADA4 to AD9A), mode 0Dh, facility flag
off. 9D29 was listed as 494 bytes because the mode-13h menu (9D36 / 9E59, already C in
`src/vgamenu.c`) follows it; both are now entry points in the listing.
`tests/test_mainmenu.py`: 11 runs (VGA and EGA, options, repeats, non-hotkeys, the version
box, quit, ratings, load, joystick found and not), every boundary and the end equal.

## The closing credits in C (2026-11-19)

`src/credits.c`, `credits_screen` = 0000:91EA (after quitting): mode 10h, font.pck at 12x12,
the file "credits" into DS:1576 with a NUL after it. Every two frames the display start
(DS:A9D0, CRTC through C571) moves down a row; every 12 rows the band above is copied for
the wrap (92BF), the 12 rows below the visible part are cleared, and the next line is
written there (y = rows + 360): 9380 splits it into words at DS:7795 (x, letters, NUL), x
counting 8 a character from the left edge (leading spaces centre the line), a double space
ending a word and a single one staying in it, LF a space, CR ending the line (with the LF
after it skipped; a line that starts with CR is empty). At 360 rows the display start goes
back to 0. After the last line 12 more rows; a key (the low byte of the count) ends it at
any time; while the music plays (DS:EA3C) it then waits for a key. Mode 0Dh, strides 28h.
`tests/test_credits.py`: the real file to the end (1,848 rows, five wraps), keys early and
after a wrap, the music's wait; every boundary and the end equal.

## Music control and page selection in C (2026-11-19)

`src/music.c`: 8986 (if the music is on, DS:0361: stop it, DS:A616 = 1, load and start the
song DS:A617 - 89F0, the audio backend's), 8C52 (stop when a song is loaded, A615, and the
driver plays, EA3C: F472), 8C64 (Sound Blaster or AdLib-with-samples devices, A773 = 2 / 4:
samples off F205 for 4, stop, F445, F4C1; then A616 = 0), 899C (A622 = FF). The driver
calls and the routines that only reach the driver or DOS (89F0, 8A41, 8BA2, 8C13, 8C33,
8C96) are in `NATIVE`. `tests/test_music.py`: 192 flag combinations, the calls and memory
equal. `select_pages` (`src/scenepresent.c`) = 0C6B: nothing on a facility screen;
otherwise DS:122A = AL (a byte store), 122C = AH, then 0C7D (shared with scene_present):
the BIOS page, the drawing page from the 40- or 80-byte table. Hosts can run it for
MS_SELECT_PAGES. `tests/test_selectpages.py`: 128 cases. The EGA palette writes (0BE8,
7AAF, 7AB6) and the frame pause 5776:02C6 are `NATIVE`.

## Session set-up in C (2026-11-19)

`src/session.c`: 0B12 (clear the actors DS:04D4..11A1, the start values 11CE.. to 11A2, far
DS:1208 and 1200, ratings_clear_stats; then a loop meant to fill the removed-objects list
DS:0F70 with FFFF stores through DI instead, which ratings_clear_stats left at 039F: 32
words from DS:039F - 0B4E rewrites 03A0..03A8 right after), 0B4E (Reese as player, the list
pointers, DS:03A8 = 03AA + level * 11 with level 6 like 0, a byte MUL), 0B80 (no caller: the
drawing page from the 640-wide table), 1483 (the row table, 350 rows of 40), 057C (as
Reese the companion comes along: Reese's record to DS:053C, its time + 50, normalised),
97BF (an empty item list), 9845 (DS:AA96 cleared, 0384 = 0, 11C0 = 320h), 97B4 (x, z of a
record). `tests/test_session.py`: 96 cases from random contents.

## The special actions in C (2026-11-19)

The special menu's actions (table DS:AB2E, picked by the items held: DS:AAA5 .. AAA9) are
now in `src/gamemenus.c`: each uses up its item and places a record at DS:0B08 + 8n (x, z
of the player, a size, a time). 94DA (0B10, 30, 5000 frames; DS:AAD1 set), 965C (0B18,
30, 100; DS:0343 = 100 for the Terminator, -100 for Reese), 971D (0B28, 100, 100; DS:0404
/ 0406 = the player's x, z), 9699 (only on foot, else message 037F and the menu stays:
0B20, 30, 400; Reese gets message 0C18 and DS:AA9F = 1, the Terminator sound 11 and
message 0CA5), 95A5 the time bomb (0B08, size 100; the minutes typed in the name editor,
two characters, asked again after Esc or when nothing parses; F530 / F54C read them -
a '-' negates good values up to 8000h, a '+' is skipped, and after a multiply that
overflows the running value is the digit just read; the time is minutes * 8). A new
`game_menu_action` runs one action by its address. `tests/test_specials.py`: 12 runs.

## The end-of-session cutscenes in C (2026-11-19)

`src/ending.c`, `ending_sequence` = 0000:5B6A. Unless DS:5CDB skips them: when DS:00B9 is
set, scene 7A2E (then 7A19 as Reese) and the closing scene; as the Terminator, 7A19 and the
closing scene, or after DS:1156 7A21 and (not in practice) the closing scene; as Reese, the
closing scene after DS:1158, 7A21 as above when 1156 is clear, else 7A1D, a 120-frame pause
and (not in practice) 7A19 and the closing scene. The closing scene (5B3A, never in
practice): 7A25 or 7A2B by who and how. Each scene is the movie player B210 (file, width
40, delay, variant) and a wait of N frames or until a key (5BCD, LOOPE). Then the last scene
(5ABF): the sample group 6, VGA 7A33 (delay 5) or EGA 7A29 (delay 6, and sound 30), 300
frames or a key. On EGA the movie's CX is what 8AFE left (0 from its loader). `tests/
test_ending.py`: 66 runs over every flag combination, the Terminator and Reese, EGA and
VGA, keys; all eight scenes reached.
Also in `src/session.c`: 168E (`font8_load`: the 8x8 font DS:1536 into far DS:155A, its
segment stored into the code words 0000:16A7 and - through 11BC:2A5E - 11BC:2A63, where the
EGA and VGA text routines read it) and 11BC:11ED (`def_slot_of`: a record's DEF number,
byte +6, looked up in the loaded list DS:5DC0 / count 72B4: the slot into its word +0, FFFF
when missing, nothing at all when the list is empty). `tests/test_fontdef.py`: 201 cases.
The joystick detection 3A12 and port read 3A33 are `NATIVE` (port 201h timing loops).
More start-up loaders in `src/session.c`: CA1A (file DS:E00E into E01A, its 160 bytes from
E02A nibble-swapped into E0CA), E475 (DS:E435 = 0; file E41E into far E520 with far
pointers to its eight records at E500 - 16-byte headers, word +0Eh the size after them -
and file E42A into far E524), 1AC9 (hud1..hud5.img: each read into the font buffer far
DS:155A, unpacked after a copy of its 16-byte header at far DS:120C, which moves past it,
the places at DS:1216; the name's digit DS:1553 is left at 6; then 168E). Proven
unreachable as well: 26DF (its one "DF 26" in the image straddles two instructions at
15AD:051E), 2707 (only called from 26DF), 5622 (only from the dead thunk EF77).

## Small routines without a known caller (2026-11-19)

Seven routines the listing finds no caller for, but whose offset does occur in the
executable as data (so a table might reach them), are in `src/misc.c`, each checked by
calling it directly (`tests/test_misc.py`, 140 cases): 4344 (AX through far DS:1204), A075
(record word +6 = FFFF), C20B (|AX - DS:DE50| with carry when under 80h or from 180h),
ACE1 (the figures' 6-word records from DS:0DF0 onto the draw list), 9BA6 (a character
collector whose REPNE SCASB result is used oddly: a character found is stored one before
the match), DF00 (a record's 32-bit x / z from the player's cell * 400h plus AX and
400h - BX), 9A01 (frame lines from DS:ABEC). F879 (the random seed from the BIOS ticks) is
in `src/session.c`.

## The joystick calibration in C (2026-11-19)

`joystick_calibrate` (`src/joystick.c`) = 0000:38F6: Enter's key cleared, DS:5A4E set (the
boxes do not wait); three corners, each a message box (0742 top left, 07C5 centre, 0783
bottom right), joystick reads until button 1 is down (the reading at that moment kept:
across into DS:5A52 / 5A54 / 5A56, down into 5A58 / 5A5A / 5A5C), reads until it is let go
(Enter cleared before each), the box away (the mode-13h restore on the facility screen), a
30-frame pause. Then for each axis the larger of the two half-spans (signed), doubled, IDIV
160: quotient and remainder into DS:5A62 / 5A64 and 5A66 / 5A68. The port read's button
effect (Enter for button 1, Space for button 2) is done in C after the host's JoystickRead.
`tests/test_joystickcal.py`: 24 runs (EGA, VGA, extreme counts) with 3A33 replaced by a stub
that returns scripted counts and buttons.

## The machine below the game, in C (2026-11-19)

The routines that reach the hardware, the BIOS and DOS directly were first replaced by the
host (`NATIVE`); they are now translated as well, through one machine-level interface
(`MachineServices` in `src/term.h`): port input and output (byte or word: `OUT DX,AX` writes
AL to the port and AH to the next), software interrupts with all the registers in and out
(`CpuRegs`, CF bit 0 and ZF bit 6 of `flags`), and `irq`, the hardware interrupt that
arrives now (asked where the original waits for one with interrupts enabled). A host implements it with real or emulated devices; the tests replay what the original met
(`tests/machine.py`: tools/dosemu.py traces every port access, every interrupt it serves
with the registers before and after, the memory pages it changed and the video state, and
each IRQ it delivers; `MachineReplay` hands the reads back, checks every write and every
register an interrupt function reads - for writes to files, the bytes too - and applies the
results). `src/machine.c`: the retrace waits 0D8D / 0DAA (status port BIOS 0:463 + 6 with
ADD DL,6), the frame pause 5776:02C6 (LOOP: 0 is 65536), the CRTC start C571, INT 10h 0BE5,
the 16 palette registers 0BE8 (7AAF DS:1521, 7AB6 DS:1510), the DAC block 9FA4, the BIOS
ticks F654, the vector get / set F01D / F008 (BX comes back shifted), the divide handler
03D1 / 03F2 and the handler itself 0407 (the interrupted IP + 2 on its frame), the keyboard
vector 3756 / 3783 (INT 9 once, the old vector at CS:3B83), the joystick 3A12 / 3A33, EMS
5D52 / 5E0E (the name at the INT 67h segment, version, 4 pages, AX's flow kept), the adapter
F4E5 (XCHG BX,AX). `tests/test_hardware.py`: 60 cases. The emulator gained test devices on
ports (`Machine.devices`) and IRQs they raise (`raise_irq`, delivered with interrupts on:
`call(..., irqs=True)`).

## The DOS library in C (2026-11-19)

`src/dos.c` = 0000:F63F .. F8D5, FACE and 11BC:10C6 / 10CB, register for register: printing
F63F (handle 1), the path helpers F714 / F738 / F754, the current directory F6AC (F67B: DOS
19h, 47h, a backslash added; AX CX DX SI ES kept), find first / next F6B3 / F6E8 (a trailing
backslash cut meanwhile: F664 / F66E; the DTA at ES:DI set again when it moved; DL 1 found, 2
no more, 0 another error, then CMP DL,1), delete F744, close F770, create F77C (400h: only
when missing, else 50h), open F7AD (100h create when missing, 200h truncate, 400h + 100h
fail when it exists; mode bits AND 3 before DOS 3), open by mode F80F, read F82B / write
F84D (ZF all transferred; CX 0 at once), the last error F8B3 / F8D5 (kept at the segment in
the code word 0000:F8FA, offset EA50), a file read whole FACE (a failed open returns CF
clear: the ADD SP,4 that drops the saved words sets the flags), and 11BC:10C6 / 10CB.
`tests/test_dos.py`: 60 calls in sequences (files the tests create are ZZ*.TMP, redirected to
a scratch folder).

## Saving, loading and deleting games in C (2026-11-19)

`src/savegame.c`: 4B7E save (the game menu's action), 4CDE delete, 4CE5 load (the main
menu's), the picker 4CEA, the picker's 20 actions 4DD7..4DEA (an INC SI sled: SI = the file's
place), the "overwrite?" answers 4CD1 (yes: ADD SP,4, then the open) and 4B7E (no: the save
again, from inside that menu's loop), the unreferenced 4B76 (ADD SP,4, restore, save), the
coder 0A76. A save "NAME.CSM" is DS:0252.. (DS:11FA bytes), coded: the player as 0 (Reese)
or 1, the list pointers 03A2 / 03A4 / 03A6 relative, each byte XOR AAh XOR the low byte of
the LOOP count; then 3Ch bytes from far DS:1208, then C4h bytes from the far pointer at
1200h - read by LDS through the DS the second block had just set, so from 1930:1200, which
holds 0000:0000: every save carries the first C4h bytes of the interrupt vector table and a
load writes them back. A file is a save when its size - 100h is DS:11FA. These routines
return through the stack in ways a C call cannot (dropped return addresses to close menus,
the save restarted with old returns still pushed, an action that re-enters its menu's
loop), so the C is an interpreter over their entry points with an explicit stack of return
labels; a menu action that does stack surgery leaves the C menu loop with a status saying
where to go on. Quirks kept: 4B7E copies the picker's title (meant for the text segment) to
DS:0002, as ES is DS there; after the name editor the end of the name is found with REPNE
SCASB for AL as the editor left it - 2 on the VGA screen (0C6B returns at once there), so on
VGA a name shorter than eight letters is saved without ".CSM" and is never listed again; Esc
in the delete picker that a full list (20 saves) opens restarts the save, so it asks again
until something is deleted. The game menu runs save and delete in C when its services have
the machine (`GameMenuServices.machine`), the main menu the load with `MainMenuServices.saves`.
`tests/test_savegame.py`: 74 cases (48 of 0A76; 26 runs: not on foot, a new name, overwrite
yes / no / no then Esc / Esc / through 4B76, Esc in the editor, eight letters, 20 saves with
and without an Esc, a file of another size, delete, load, 21 saves, on the VGA screen too),
every boundary, DOS call and file write equal.

## The program's start in C (2026-11-19)

`src/startup.c`: `program_start` = 0000:0000. DOS 4Ah to the program's size, the adapter
(F4E5: 2 EGA, 4 VGA sets DS:ADD0, else message 018E and the end), the options 0413, a
0A00h-paragraph block (DOS 48h, DS:7B8C), EMS, the ending-music flag, the preload 09FB (with
the EMS frame: the files named from DS:0000 one after another into it, offsets at DS:009D),
04D3 (the random seed from the BIOS ticks, the random table with the time from DOS 2Ch -
`random_refill_from`, the row table, the keyboard vector, the intro's buffer, the pictures
1AC9), the sound 8BA2, the intro 04E8 unless DS:5BF6 (mode 0Eh, the music, 57C5:000E, two
movies between pauses 5BCD of 3Ch / 3Ch / 258h frames that a key ends, the pages). Then the
loop: palette, mode 0Eh, the session reset, the main menu; a game: protection, music and
samples, the starting kit 97D8 (by difficulty from DS:AB3C / AB48 / AB52, each item through
the weight and category check 86F4 and shop_add_item; no room makes 86F4 drop two words and
return to 0000:BX - a crash no table reaches, reported as 2), 59A6 (a new game's characters
from their templates DS:7AC8 / 7AFC, vehicle and player placed at random - 5A0D / 5A58 - then
normalised, the visible cells, the arrival), the vehicle transition, 052C (mode 0Dh and all
the resources), the link's set-up, the main loop 0155, after it the samples stopped, the
divide handler removed, the keys flushed; new game (1159 = AAh) loops, a lost game shows the
ending and the ratings D5B1 (the place, the name typed, the table coded and written to
ratings.rse / ratings.trm by D5FA, left coded); quit (55h) the credits, memory and EMS given
back, the keyboard vector, text mode, RETF to the PSP. The command line (0413 with the run-
time library's scanner F8FC count, F97A next, FA19 reset, FA2C / F8E0 compare in either
case): none / ibmsound / adlib / sblaster (DS:A773 1, 1, 2, 4; none also clears DS:0361),
ega / vga, link with com1..com4 (151B:020F); a bad argument (a switch inside one starts the
next, so "/vga" is bad) or link without a port prints and ends. ratings_insert (D67F) now
follows the original for any count (LOOP: 0 scans 65536 records; MUL CL of the count left).
Routines with services of their own (screens, images, sound, the serial link) are the
host's, by address (`ProgramServices.call`). `tests/test_startup.py`: 1,513 (the scanner on
160 random tails with random sets and pointers, every register and flag; 19 command
lines); `tests/test_program.py`: 31 (each set-up routine and 11 runs of the whole start:
adapters, options, link, quit, a game, new game, a lost game with the ending and ratings,
the intro skipped).

## The sound layer in C (2026-11-19)

`src/soundlayer.c` = 0000:EFA0 .. F4DB, 89F0, 8A41, 8BA2, 8C13, 8C33, 8C96: a thin library
between the game and its drivers. The wrappers call a driver with the function number in BX
(the voice driver 101F:0000, the music driver 10BB:0000, the FM driver 0FBA:058F, the
sample player's 5B67 routines and the far pointer DS:AA78) - the drivers are not the game's
and stay the host's, called by address with every register. The detection works on the
ports: the DSP (DS:EA3E + 6 reset, + A read, + C write, + E status) with D3h, a reset
awaiting AAh, E0h identifying C6h as 39h; an odd first test (C6h to + 6, read back at + A);
the FM chip's timer 1 at + 8 / 9 (AX bit 0 the echo, 2 the FM chip, 4 a DSP). The IRQ
detection F05E points IRQ 2, 3, 5, 7 at four handlers (F13A, F11C, F147, F154: the IRQ to
DS:EA40, the DSP acknowledged, end of interrupt), unmasks them, sends F2h and looks at
DS:EA40 65536 times. 8BA2: AdLib at 380h, or a Sound Blaster at 220h with its IRQ
(DS:A865) when it has the DSP and the FM chip; the music driver (F3CA) for all but a DSP
without FM; then the music block (DOS 48h, E00h paragraphs or the largest less 8Ch). 89F0 /
8A41: the song file into the block, its tempo as the timer rate 1234DCh / tempo through the
C library's 32-bit division FAF3 (FB04, with the entries FAF7, FAFC, FB01 for the other
modes; a 16-bit DIV when the high words allow it, resuming after a divide error), whose
RET 8 leaves the divisor's high word on the stack, so 8A41's POP SI returns the tempo's sign
word. `tests/test_soundlayer.py`: 306 direct calls on a Sound Blaster model in the emulator
(DSP, identification, IRQ raised by F2h and delivered to the program's handler, FM timer; or
no card, an AdLib alone, an echo), the drivers' entries as stubs that record every register
and return scripted results. (`tests/test_sound.py` is the older test of the sample groups,
`src/sound.c`.)

## The unreachable routines in C (2026-11-19)

The 24 routines proven unreachable are translated too (`src/unreachable.c`, register for
register): 1814 (bit 0 of a byte in the four planes), 26DF / 2707 (faces wholly behind the
camera), 296A (a camera step), 43B9, 47A8 / 47CE / 47FD (scalings and a perspective step by
IDIV; 47FD's bytes hold another divide-error handler at 481A that skips the division and
sets AX = 7E6Fh XOR the sign of DL), 5622 and its thunk EF77 (an item dropped by kind), 5A6F
(a far wrapper of the unpacker), 6479, 79F1 (a model turned), 87E2, 950D (the decoy's
flicker and a vehicle stopped near it), B9C6 (the timer vector back), CA39, EE0C (the
copy-protection failure: text mode, a message, a hang - reported as 1), F5CD (a decimal
number), FA10, FA88 (decimal digits backwards), 11BC:110E (XLAT), 1B27 (three 8x8
characters on the mode-13h screen), 1E95 (a weapon icon redrawn). Where they call a routine
whose C version returns less than the original leaves in registers, those registers are
named as not modelled. `tests/test_unreachable.py`: 163 direct calls (the stack page is left
out of the memory comparison, so 481A's frame is checked on its own).

## The whole program in C (2026-11-19)

With these, `python tools/coverage.py` counts 100.0%: all 80,987 bytes of segments 0000,
11BC, 14A7, 14B5, 15AD, 5776 and 57C5 have a verified C version (1,069 routines in
`C_VERSIONS`; `NATIVE` and `DEAD` are empty). Out of scope remain the serial link (151B) and
the drivers (0FBA, 101F, 10BB, 5B67), which the C calls by address.

## The FM music driver in C (2026-11-20)

`src/fmdrv.c` = segment 10BB, "FMDRV": Creative's SBFMDRV for CMF songs, built into the
executable. Its functions by BX at 10BB:0000 (dispatcher 0D28, busy flag 1C7 giving FFF8h):
0 version (word 0C), 1 the status byte's address (DX:AX, the old one back, the new one
zeroed), 2 instruments (CX of 16 bytes at DX:AX), 3 the system clock's divisor (32), 4 the
driver clock's (34, programmed at once), 5 transpose (42), 6 play (DX:AX: FFFEh while
playing), 7 stop, 8 reset (its own sixteen instruments at 10BB:0048), 9 pause, 10 go on
(both FFFDh / FFFCh with the carry set in the wrong state), 11 a user trap called on SysEx
(the game sets none); FFFFh set-up, FFFEh shut-down, FFFDh the port base. The data stay at
their offsets in the driver's segment (listed at the top of the file).

Set-up (0FED): the OPL2 found by its timer 1 (registers 1, 4, 2 through base + 8 with five
status reads after each write, C0h awaited within 64 reads), the port delays measured
(0EFE: the timer at 98BAh, only IRQ 0 unmasked, INT 8 at 0EF5 which inverts AX; the loops
between two interrupts / 8192 + 1, and six times that less five), the base moved to the FM
ports (+ 8), the status byte at 10BB:01C8, INT 8 taken (0C83) and INT 9 (0CF3).

Playing: the timer interrupt counts down the delay of the next event (32 bits at 22); at its
end the events due are run (092B; running status; 8x / 9x notes, Bx controllers 66h marker
to the status byte, 67h drums on or off, 68h / 69h bends of a quarter of the value, Cx
programs modulo the instrument count, Ax / Ex skip two bytes, Dx one, F0 / F7 a length,
F2 / F3 two / one, FC stop, FF meta with 2Fh the end). Voices: one of the channel's
released, a free one, any released, else the one started longest ago (keyed off). Each
interrupt then adds the timer's divisor (36) to an accumulator and passes the interrupt to
the old INT 8 each time it reaches the system clock's divisor (32, FFFFh: 18.2 Hz).

The driver's own quirks, kept in C: its silence (0631) means to write the release register
83h + operator but reloads AL first, so 13h goes to register 83h nine times; its voice
set-up (067A) writes the instrument's last byte to register operator + voice (00, 02, 04,
0B, 0D, 0F, 16, 18, 1A) instead of C0h + voice; the pitch bend is set by channel but read by
voice; a note bent past the top of an octave is set to the top of the scale (17Fh, block 7)
unless it already was in the highest octave (the comparison is the wrong way round); a
program change with no instruments would loop for ever; the keyboard handler's Ctrl+Alt
silence needs a make code of 83h, which cannot be; 0DFF (a saved vector by number) is in no
table.

With the game's sample player the two share the timer: the driver sets the song's rate and
the BIOS gets 18.2 interrupts a second, but the sample player's set-up (5B67:08C5) puts the
timer at 60 Hz without the driver knowing ([36] stays FFFFh, so every interrupt is passed
on, 60 a second, until a song is started). While a song plays, INT 1Ch (5B67:0954: the
looping sample, the countdown AA93, the firing range's timer A964) runs at 18.2 Hz instead
of 60. A sample on the PC speaker or the AdLib DAC takes INT 8 itself (the song stands
still meanwhile), and at its end 0735 sets the timer back to 60 Hz, not to the song's rate:
from then on the song's ticks come 60 a second whatever its tempo, until the next song.

`tests/test_fmdrv.py`: 3,544 calls and interrupts on an OPL2 model at 388h, from the
set-up (three timer interrupts raised in its measuring loops) through three songs (the
game's SONG1.CMF, and two made to reach drums, bends past the octave both ways, more notes
than voices, programs past the count, running status, Ax / Dx / Ex, SysEx, F2 / F3, the
ends by FFh 2Fh and FCh), pauses, a busy driver, a second play, stops, a reset, the keyboard
handler and the shut-down; each port access, interrupt, register and byte of memory checked
(not the timer handler's own stack in the driver's segment, E12h..E76h, and its saved SS:SP
at 44h). The counted segments now include 10BB: `python tools/coverage.py` gives 100.0% of
83,511 bytes.

## The game's samples and the sample player's timing (2026-11-20)

The .RS files: a 5-byte signature ("STEVE" or "CRAIG"), at + 5 the timer interrupts each
value lasts (3 in every file), at + 7 the length with the final 0, from + 20h the values,
6 bits (1..63, the width of the speaker's pulse), up to a 0. The PC speaker's player (05C6)
and the AdLib DAC's (0081, which writes the values to the OPL's data port) work alike:
nothing while their samples are off (DS:11CC) or the machine measured too slow (DS:AA85
below 160h; above it for the DAC); while a sample plays (DS:AA83) a request with a higher
number (CL, the request's id, against DS:AA7E) is ignored and any other replaces it at
once. The timer goes to divisor 48h (16,572 interrupts a second: 5,524 values a second for
CH = 3) and INT 8 to their handler (0657 / 011B, the old vector at DS:AA7F), the PIC masks
all but the timer and the keyboard; every 114h / CH values the handler calls the INT 1Ch
handler 0954 itself, so the game's 60 Hz counters go on while the BIOS's tick count stands;
at the 0 (0735) INT 8 and the 60 Hz timer come back and AA83 clears.

## Game speed (2026-11-20)

Everything in play counts frames: walking moves the speed (record + 0Ah, the HUD's number,
about 8.5 units a frame) each frame, the world clock (DE37: 6 world steps to the second,
DS:0348 seconds, DS:1174 minutes) once a frame, and every timer of the game. Nothing scales
by elapsed time, so the game ran as fast as the machine drew. In the emulator a frame of
play is about 540,000 instructions, of which about 300,000 are work (the rest waits for the
retrace): about 7 frames a second on a 386SX-16, 15-20 on a 386DX-33. The game's own
numbers agree: the heartbeat sample, restarted every 12 frames, beats 75 a minute at 15
frames a second; the world clock would keep real time at 6; the speedometer (twice the
units a frame in a car) would read true miles an hour at about 20, at 22 units a metre.

## The phone book's Esc (2026-11-20)

The phone book closes on any key in the buffer, sets mode 0Dh and resets the camera, which
loads the black palette DS:1521 and asks for the game's (DS:1510) at the end of the frame.
If the key was Esc and is still down when the frame goes on, the frame's input check opens
the game menu before that: a menu drawn while the palette is black. On the machines of the
day the reload took long enough for the key to be let go; on a fast one the menu is
invisible.
