"""Curated knowledge about exe/TERM_unpacked.exe, applied by tools/disasm.py.

Everything here was established by reading the code or by running it in the emulator.
Keys are (file segment, offset). Keep entries factual; put doubts in the note text.
"""

# Extra entry points the static pass cannot find by itself: (seg, off) -> why
SEEDS = {
    (0x0000, 0xF11C): 'interrupt handler',   # Sound Blaster IRQ probes (vectors set at F0B8-F111)
    (0x0000, 0xF13A): 'interrupt handler',
    (0x0000, 0xF147): 'interrupt handler',
    (0x0000, 0xF154): 'interrupt handler',
    (0x0000, 0x0407): 'interrupt handler',   # INT 0, installed at 0000:03D1
    (0x0000, 0x37E3): 'interrupt handler',   # INT 9, installed through DOS at start-up
    (0x0000, 0x8CB0): 'shop screen tail entry',
    (0x0000, 0x0DC7): 'jump target',         # line_to's vertical and horizontal cases (0F32)
    (0x0000, 0x0E39): 'jump target',
    (0x0000, 0x1090): 'jump target',         # the same for the 640-wide line at 1201
    (0x0000, 0x1106): 'jump target',
    (0x0000, 0x9D36): 'jump target',         # the mode-13h menu, jumped to from menu_display (48FD)
    (0x0000, 0x9E59): 'jump target',
    (0x5B67, 0x05C6): 'stored pointer',      # sample player back ends, stored at 5B67:0786
    (0x5B67, 0x070D): 'stored pointer',
    (0x5B67, 0x0081): 'stored pointer',
    (0x5B67, 0x02FC): 'stored pointer',
    (0x5B67, 0x054D): 'stored pointer',
    (0x5B67, 0x082E): 'stored pointer',
    (0x5B67, 0x0954): 'interrupt handler',   # INT 1Ch replacement, installed at 5B67:08F0
    (0x5B67, 0x03D0): 'interrupt handler',   # Sound Blaster IRQ handler, installed at 5B67:0365
}

# Jump/call tables the automatic scan cannot delimit: (code seg, DS offset) -> entry count.
# Zero entries are unused slots.
EXTRA_TABLES = {
    (0x151B, 0xAFB6): 16,
    (0x0000, 0x7970): 6,   # inventory categories
    (0x0000, 0xA974): 2,   # confirmation actions
    (0x0000, 0xA978): 3,   # facility dispatch
    (0x0000, 0xA97E): 2,   # adjacent bank actions
}

# Calls that never return (linear address of the call instruction)
NORETURN_CALLS = set()

# Enumerated target sets for indirect calls, traced to their pointer writers.
INDIRECT_TARGETS = {
    # 201A, 203C, 205E, 2080 pass the four window-edge handlers to 208F.
    (0x0000, 0x20B8): ((0x0000, 0x20DC), (0x0000, 0x2181), (0x0000, 0x2226), (0x0000, 0x22CB)),
    (0x0000, 0x20D9): ((0x0000, 0x20DC), (0x0000, 0x2181), (0x0000, 0x2226), (0x0000, 0x22CB)),
    (0x0000, 0x46FA): ((0x0000, 0x4772),),  # BP set at 46DD
    # Polygon edge handlers are assigned inside poly_chain_b_next and poly_chain_a_next.
    (0x11BC, 0x002A): ((0x11BC, 0x007C), (0x11BC, 0x0080), (0x11BC, 0x009C), (0x11BC, 0x00A0)),
    (0x11BC, 0x002E): ((0x11BC, 0x008C), (0x11BC, 0x0090), (0x11BC, 0x00AC), (0x11BC, 0x00B0)),
    # The ground and street callers at 0A5B and 0FCA share the four-quadrant loop.
    (0x11BC, 0x0C49): ((0x11BC, 0x0D8A), (0x11BC, 0x0FD1)),
    (0x11BC, 0x0CB0): ((0x11BC, 0x0D8A), (0x11BC, 0x0FD1)),
    (0x11BC, 0x0D26): ((0x11BC, 0x0D8A), (0x11BC, 0x0FD1)),
    (0x11BC, 0x0D87): ((0x11BC, 0x0D8A), (0x11BC, 0x0FD1)),
    # Bounded Creative command tables. 0FBA uses DS=5C01; FMDRV uses DS=CS.
    # 101F:077C remains separate because CT-VOICE command 6 points outside its segment.
    (0x0FBA, 0x05C4): tuple((0x0FBA, off) for off in (0x02D4, 0x0584, 0x02FC, 0x0318)),
    (0x10BB, 0x0D5A): tuple((0x10BB, off) for off in
                           (0x0D86, 0x0D8A, 0x0D9D, 0x0DDF, 0x0DE3, 0x0DEC,
                            0x08A5, 0x0DCF, 0x0881, 0x0904, 0x0919, 0x0DF2)),
    (0x10BB, 0x0D69): tuple((0x10BB, off) for off in (0x0FED, 0x1000, 0x1009)),
    # FMDRV maps the MIDI status high nibble 8..F to an index at DS:003E.
    (0x10BB, 0x096C): tuple((0x10BB, off) for off in
                           (0x0995, 0x0A0D, 0x0BBE, 0x0B5E, 0x0BC1, 0x0BBF, 0x0BBE, 0x0C3B)),
    # The B-status handler selects controls 66h..69h; F uses the low nibble.
    (0x10BB, 0x0B6F): tuple((0x10BB, off) for off in (0x0B74, 0x0B7A, 0x0BAC, 0x0BAA)),
    (0x10BB, 0x0C43): tuple((0x10BB, off) for off in
                           (0x0C48, 0x0BC0, 0x0BBE, 0x0BBF, 0x0BC0, 0x0BC0, 0x0BC0, 0x0C5E,
                            0x0BC0, 0x0BC0, 0x0BC0, 0x0BC0, 0x0C69, 0x0BC0, 0x0BC0, 0x0C6D)),
    # Device selection at 5B67:0786 writes the playback and cleanup addresses.
    (0x5B67, 0x0829): ((0x5B67, 0x0081), (0x5B67, 0x02FC), (0x5B67, 0x05C6), (0x5B67, 0x082E)),
    (0x0000, 0x8CA3): ((0x5B67, 0x054D), (0x5B67, 0x070D), (0x5B67, 0x082E)),
}

FUNCS = {
    (0x0000, 0x36D0): 'player_position_backup',
    (0x0000, 0x36EF): 'player_position_restore',
    (0x0000, 0x370E): 'player_keep_inside',
    (0x0000, 0x36A9): 'driving_reset',
    (0x0000, 0x2E9E): 'player_movement_gate',
    (0x0000, 0x300B): 'walking_speed_keys',
    (0x0000, 0x302E): 'walking_speed_step',
    (0x0000, 0x331D): 'driving_steer',
    (0x0000, 0x33A5): 'driving_accelerate',
    (0x0000, 0x354E): 'driving_gear_key',
    (0x0000, 0x30A0): 'walking_step',
    (0x0000, 0x3269): 'driving_step',
    (0x0000, 0x3402): 'driving_transmission',
    (0x0000, 0x3584): 'driving_brake',
    (0x0000, 0x35C0): 'driving_smooth_speed',
    (0x0000, 0x3646): 'driving_displace',
    (0x0000, 0x3684): 'driving_damage_exit',
    (0x0000, 0xC21F): 'opponent_controller_fast',
    (0x0000, 0xB7B6): 'opponent_controller_slow',
    (0x0000, 0xBFB3): 'opponent_fire_at_companion',
    (0x0000, 0xB5F9): 'world_step',
    (0x0000, 0xDB26): 'companion_ai',
    (0x0000, 0xC1CB): 'opponent_destination_query',
    (0x0000, 0xC1B0): 'opponent_pick_destination',
    (0x0000, 0xB91F): 'opponent_has_openings',
    (0x0000, 0xB94A): 'opponent_choose_follow_mode',
    (0x0000, 0xB973): 'opponent_follow_destination',
    (0x0000, 0xC42F): 'opponent_check_travel_interrupt',
    (0x0000, 0xBBF1): 'opponent_place_ahead',
    (0x0000, 0xC35F): 'opponent_place_flank',
    (0x0000, 0xDC7B): 'opponent_place_companion',
    (0x0000, 0xDD67): 'companion_wait',
    (0x0000, 0xDDBE): 'companion_evade',
    (0x0000, 0xDE05): 'companion_follow',
    (0x0000, 0xDE46): 'companion_move',
    (0x0000, 0xDD56): 'companion_step',
    (0x0000, 0xB5B4): 'opponent_init_difficulty',
    (0x0000, 0xAA81): 'collision_steer',
    (0x0000, 0xB755): 'vehicle_choose_destination',
    (0x0000, 0xB6AA): 'vehicle_follow_route',
    (0x0000, 0xB790): 'world_update_delay',
    (0x0000, 0xC125): 'opponent_find_item',
    (0x0000, 0xC0F5): 'opponent_sound_for_item',
    (0x0000, 0xC0A7): 'opponent_build_choices',
    (0x0000, 0xC068): 'opponent_select_choice',
    (0x0000, 0xC16D): 'opponent_add_item',
    (0x0000, 0xC14C): 'opponent_cycle_item',
    (0x0000, 0xBC68): 'opponent_fire_at_player',
    (0x0000, 0xBF1B): 'opponent_burst_slow',
    (0x0000, 0xC397): 'opponent_burst_fast',
    (0x0000, 0x77F6): 'weapon_collect_targets',
    (0x0000, 0x7852): 'weapon_target_candidate',
    (0x0000, 0x794A): 'camera_full_height',
    (0x0000, 0x7989): 'camera_full_image',
    (0x0000, 0x79C3): 'camera_key_step',
    (0x0000, 0xBA60): 'world_clamp_actor',
    (0x0000, 0xDEB5): 'position_normalize_companion',
    (0x0000, 0xBB03): 'world_follow_companion',
    (0x0000, 0xBA1C): 'world_wander_vehicle',
    (0x0000, 0xBAB7): 'world_displace_vehicle',
    (0x0000, 0xB9D2): 'world_clock_step',
    (0x0000, 0xBB2B): 'position_relative_vehicle',
    (0x11BC, 0x1D03): 'weapon_hotkeys',
    (0x11BC, 0x1D59): 'weapon_reload_slot',
    (0x11BC, 0x1DD8): 'weapon_deselect_slot',
    (0x11BC, 0x1E1A): 'weapon_select_slot',
    (0x11BC, 0x1E6B): 'weapon_refresh_selection',
    (0x0000, 0x0998): 'player_look_keys',
    (0x11BC, 0x1796): 'player_companion_indicator',
    (0x0000, 0x091F): 'player_sample_warning',
    (0x0000, 0x7088): 'world_toggle_records',
    (0x0000, 0x596C): 'player_update_threat',
    (0x0000, 0xA426): 'figure_retry_deferred',
    (0x0000, 0x3B54): 'debug_vector_toggle',
    (0x0000, 0x0809): 'gameplay_update',
    (0x0000, 0x37AC): 'keyboard_read',
    (0x0000, 0x37D5): 'keyboard_read_available',
    (0x0000, 0x4609): 'player_check_map_edge',
    (0x0000, 0x4495): 'vehicle_refuel_nearby',
    (0x0000, 0x4F4B): 'hud_init_normal',
    (0x0000, 0x985C): 'weapon_inventory_rebuild',
    (0x11BC, 0x1BE1): 'hud_weapon_icon',
    (0x11BC, 0x1C7D): 'hud_weapon_slots',
    (0x11BC, 0x1EEB): 'hud_weapon_selection',
    (0x5776, 0x00E5): 'screen_blit_five_plane_bytes',
    (0x5776, 0x012A): 'hud_choose_panel',
    (0x0000, 0x735A): 'hud_armor_overlay',
    (0x0000, 0x745B): 'hud_field_marker',
    (0x0000, 0xAEC4): 'scene_contact_test',
    (0x0000, 0xAE2E): 'scene_contact_update',
    (0x0000, 0x18D3): 'scene_flash',
    (0x0000, 0x9756): 'scene_timed_effect',
    (0x0000, 0x41C4): 'hud_vehicle_remaining',
    (0x5776, 0x0247): 'scene_overlay_restore',
    (0x0000, 0x07D1): 'scene_overlay_replay',
    (0x5776, 0x01E0): 'scene_overlay_save',
    (0x0000, 0xE0C0): 'screen_text8',
    (0x5776, 0x0346): 'textbox_border',
    (0x5776, 0x03ED): 'textbox_border_layer',
    (0x0000, 0x5032): 'textbox_draw',
    (0x0000, 0x093A): 'scene_warning',
    (0x0000, 0x0758): 'scene_post_render',
    (0x0000, 0x5546): 'inventory_remove',
    (0x0000, 0xC898): 'hud_message',
    (0x0000, 0xC957): 'hud_message_hide',
    (0x0000, 0xC976): 'hud_message_clear',
    (0x0000, 0x643E): 'player_damage_region',
    (0x0000, 0x7A28): 'camera_reset',
    (0x0000, 0x0C47): 'camera_clear_pages',

    (0x0000, 0x6F99): 'weapon_charge_projectile_step',
    (0x0000, 0xD8D2): 'weapon_guided_projectiles_step',
    (0x0000, 0xD8F2): 'weapon_guided_record_step',

    (0x0000, 0xA840): 'figure_select_position',
    (0x0000, 0xAA3B): 'figure_grid_to_world',
    (0x0000, 0xAD00): 'figure_spawn_armed',
    (0x0000, 0xAD37): 'figure_spawn_civilian',
    (0x0000, 0xB05E): 'figure_init_movement',
    (0x0000, 0x5BDB): 'figure_feedback',
    (0x0000, 0xC9A5): 'figure_feedback_draw',
    (0x0000, 0x6D49): 'weapon_fire',
    (0x0000, 0x6B54): 'weapon_frame',
    (0x0000, 0x6F70): 'weapon_firing_alert',

    (0x0000, 0x5CFA): 'figure_map_sample',
    (0x0000, 0xA480): 'figure_spawn_grid_block',
    (0x0000, 0xA46F): 'figure_spawn_grid',

    (0x0000, 0xA00C): 'weapon_visual_insert',
    (0x0000, 0xA036): 'weapon_visual_step',

    (0x0000, 0x6B23): 'weapon_images_load',
    (0x0000, 0xDA2C): 'weapon_projectile_turn',
    (0x0000, 0xDABC): 'weapon_projectile_outside',

    (0x0000, 0x6C93): 'weapon_update_sight',
    (0x0000, 0x15F4): 'weapon_draw_crosshair',
    (0x0000, 0xDAD6): 'weapon_projectile_slot',
    (0x0000, 0xD896): 'weapon_projectile_create',

    (0x0000, 0x7158): 'weapon_draw_autoaim',
    (0x0000, 0x720C): 'weapon_lock_colour',
    (0x0000, 0x7884): 'weapon_cycle_target',
    (0x0000, 0x789B): 'weapon_select_target',
    (0x0000, 0x78D6): 'weapon_target_rejected',

    (0x0000, 0x6AFC): "weapon_classify_source",
    (0x0000, 0x7008): "weapon_draw_numbers",
    (0x0000, 0x70AA): 'vehicle_hud_load',
    (0x0000, 0x7250): 'vehicle_hud_draw',
    (0x0000, 0x731D): 'image_unpack_four_lzhuf',
    (0x5776, 0x00A6): 'screen_blit_five_planes',
    (0x0000, 0x6962): 'image_load_screen',
    (0x0000, 0x6994): 'image_draw_loaded',
    (0x0000, 0x6A0F): 'image_next_plane',
    (0x0000, 0x6AAE): 'image_prepare',
    (0x0000, 0xFAAF): 'file_load_ds',
    (0x11BC, 0x25B0): 'collision_line_blocker',
    (0x0000, 0xA2B3): 'hud_target_contains_sight',
    (0x0000, 0xA07B): 'hud_scan_target',
    (0x0000, 0x766A): 'hud_load_optics',
    (0x0000, 0x7683): 'hud_init_optics',
    (0x0000, 0x76B4): 'hud_draw_optics',
    (0x0000, 0xE5A3): 'hud_hit_mask',
    (0x0000, 0xE589): 'hud_lock_mask',
    (0x0000, 0xE56F): 'hud_target_mask',
    (0x0000, 0x4FE5): 'hud_refresh_pages',
    (0x0000, 0xE170): 'hud_draw_system',
    (0x0000, 0xE4AE): 'hud_draw_target',
    (0x0000, 0xE542): 'hud_draw_target_frame',
    (0x0000, 0xE5E9): 'hud_draw_warnings',
    (0x0000, 0xE6E0): 'hud_draw_target_info',
    (0x0000, 0xE813): 'hud_clear_target_info',
    (0x0000, 0x1A4D): 'screen_blit_planar',
    (0x0000, 0x1B19): 'hud_restore_background',
    (0x0000, 0xD6CB): 'score_update',
    (0x0000, 0xE26D): 'hud_format_score',
    (0x0000, 0xE348): 'hud_draw_sweep',
    (0x0000, 0xE44A): 'hud_sweep_clear',
    (0x0000, 0xE280): 'hud_draw_status',
    (0x0000, 0xE29B): 'hud_collect_status',
    (0x0000, 0xE307): 'hud_cycle_status',
    (0x11BC, 0x181B): 'hud_draw_indicators',
    (0x11BC, 0x195C): 'hud_bearing_x',
    (0x11BC, 0x19AE): 'hud_bearing_tick',
    (0x11BC, 0x19E1): 'hud_indicator_erase',
    (0x0000, 0xE5BD): 'hud_zoom_key',
    (0x0000, 0xE638): 'hud_flash_bitmap',
    (0x0000, 0xE66E): 'hud_draw_system_frame',
    (0x0000, 0x19CC): 'image_unpack_compressed',
    (0x0000, 0xCF74): 'map_setup_area',
    (0x0000, 0x1985): 'screen_blit_mask',
    (0x0000, 0xD177): 'travel_run',
    (0x0000, 0xB588): 'travel_simulate',
    (0x0000, 0xD265): 'travel_clear_arrival',
    (0x0000, 0xD2BE): 'travel_apply_destination',
    (0x0000, 0xCE2B): 'map_setup_local',
    (0x0000, 0xCBF8): 'map_local_dialog',
    (0x0000, 0xD0A6): 'map_area_viewport',
    (0x0000, 0xD102): 'area_line_clipped',
    (0x0000, 0x1343): 'area_line_to',
    (0x0000, 0x3792): 'map_clear_key_buffer',
    (0x5776, 0x0154): 'hud_clear_bytes',
    (0x5776, 0x018A): 'hud_clear_number',
    (0x5776, 0x04BC): 'screen_copy_rect',
    (0x0000, 0x1492): 'screen_draw_mask16',
    (0x0000, 0x4F2A): 'hud_draw_compass',
    (0x0000, 0x5998): 'heading_degrees',
    (0x0000, 0x73C1): 'hud_draw_speed',
    (0x0000, 0x7428): 'hud_draw_vehicle_counter',
    (0x0000, 0x772B): 'hud_draw_counters',
    (0x11BC, 0x1A01): 'hud_compass_needle',
    (0x0000, 0x60FD): 'map_restore_pointer',
    (0x0000, 0x6128): 'map_draw_pointer',
    (0x0000, 0x830F): 'map_pointer_step',
    (0x0000, 0xCBA5): 'map_destination_measure',
    (0x0000, 0xCC8D): 'map_local_destination',
    (0x0000, 0xCD05): 'map_area_destination',
    (0x0000, 0xCD4A): 'map_draw_info',
    (0x0000, 0xCDE1): 'map_clear_info',
    (0x0000, 0x43C6): 'map_draw_markers',
    (0x11BC, 0x2DBB): 'map_draw_grid',
    (0x0000, 0xC766): 'hud_draw_number',
    (0x0000, 0xC7ED): 'hud_draw_text',
    (0x0000, 0xC872): 'hud_format_number',
    (0x11BC, 0x2E46): 'map_draw_grid_labels',
    (0x0000, 0x0000): 'start',
    (0x0000, 0x036E): 'build_frame_draw_list',
    (0x0000, 0x0407): 'divide_error_handler',
    (0x0000, 0x0DC7): 'line_vertical',
    (0x0000, 0x0E39): 'line_horizontal',
    (0x0000, 0x0F32): 'line_to',
    (0x0000, 0x1049): 'line_begin',
    (0x0000, 0x1075): 'ega_begin_line',
    (0x0000, 0x1B46): 'rotate_bc',
    (0x0000, 0x1B7D): 'rotate_xz',
    (0x0000, 0x1BB0): 'rotate_xz_inverse',
    (0x0000, 0x1BE5): 'rotate_ab',
    (0x0000, 0x1F50): 'build_dither_table',
    (0x0000, 0x1F6A): 'mesh_clip_window',
    (0x0000, 0x1FE9): 'clip_window_store_face',
    (0x0000, 0x1FFE): 'clip_window_face',
    (0x0000, 0x208F): 'clip_window_face_edge',
    (0x0000, 0x20DC): 'clip_window_point_right',
    (0x0000, 0x2181): 'clip_window_point_left',
    (0x0000, 0x2226): 'clip_window_point_top',
    (0x0000, 0x22CB): 'clip_window_point_bottom',
    (0x0000, 0x2370): 'cross_right',
    (0x0000, 0x23CB): 'cross_left',
    (0x0000, 0x2426): 'cross_top',
    (0x0000, 0x2488): 'cross_bottom',
    (0x0000, 0x24EA): 'mesh_clip_near',
    (0x0000, 0x2564): 'clip_near_face',
    (0x0000, 0x25B3): 'clip_near_vertex',
    (0x0000, 0x2673): 'clip_near_intersect',
    (0x0000, 0x06C3): 'draw_frame_background',
    (0x0000, 0x06FF): 'draw_scene',
    (0x0000, 0x159D): 'draw_ground_fill',
    (0x0000, 0x1707): 'horizon_strip',
    (0x0000, 0x196B): 'sun_rows',
    (0x0000, 0xA3D7): 'sort_targets_by_depth',
    (0x0000, 0x5E62): 'angle_between',
    (0x0000, 0x7EC8): 'append_debris',
    (0x0000, 0x1C1A): 'matrix_from_angles',
    (0x0000, 0x1C33): 'matrix_apply',
    (0x0000, 0x1CA7): 'matrix_identity',
    (0x0000, 0x1CDC): 'matrix_turn_rows_0_1',
    (0x0000, 0x1DA9): 'matrix_turn_rows_1_2',
    (0x0000, 0x1E76): 'matrix_turn_rows_0_2',
    (0x0000, 0x4581): 'object_blown',
    (0x0000, 0x4586): 'note_removed',
    (0x0000, 0x45E6): 'hide_visible_record',
    (0x0000, 0x5E1E): 'ground_list_park',
    (0x0000, 0x5E48): 'ground_list_restore',
    (0x0000, 0x6386): 'player_hit',
    (0x0000, 0x7A83): 'restore_view_window',
    (0x0000, 0x7A92): 'set_view_window',
    (0x0000, 0x7B28): 'debris_start',
    (0x0000, 0x7D2B): 'debris_update',
    (0x0000, 0x7EF0): 'explosion_damage',
    (0x0000, 0x8075): 'queue_blast',
    (0x0000, 0x808E): 'blast_ordinary_object',
    (0x0000, 0x80B6): 'blast_queue_step',
    (0x0000, 0x80EE): 'random_word',
    (0x0000, 0x8117): 'random_refill',
    (0x0000, 0x89A2): 'sound_start',
    (0x0000, 0xAFD0): 'figure_kill',
    (0x0000, 0xCF33): 'draw_map_view',
    (0x0000, 0xF88A): 'random_step',
    (0x0000, 0x87FC): 'append_pickups',
    (0x0000, 0x881F): 'pickup_record',
    (0x0000, 0x88A3): 'pickup_position',
    (0x0000, 0x95F2): 'append_timed_object',
    (0x0000, 0x960F): 'timed_object_expire',
    (0x0000, 0x9625): 'timed_object_record',
    (0x0000, 0x9FB2): 'append_projectiles',
    (0x0000, 0xB1F1): 'append_figures',
    (0x0000, 0xBD64): 'append_opponent_and_companion',
    (0x0000, 0xBE47): 'animation_bearing',
    (0x0000, 0xBE68): 'figure_mesh_5',
    (0x0000, 0xBECE): 'figure_mesh_8',
    (0x0000, 0xCE12): 'map_page_update',
    (0x0000, 0xCEED): 'map_page_redraw',
    (0x0000, 0xD9FB): 'append_guided_projectiles',
    (0x0000, 0xDA96): 'guided_projectile_record',
    (0x11BC, 0x1BBC): 'append_special_object',
    (0x0000, 0x271E): 'draw_object_list',
    (0x0000, 0x285A): 'mesh_prepare',
    (0x0000, 0x28E4): 'record_mesh_number',
    (0x0000, 0x2921): 'draw_list_camera',
    (0x0000, 0x2986): 'camera_from_player',
    (0x0000, 0x2BFF): 'mesh_fetch',
    (0x0000, 0x7921): 'rotate_vertices',
    (0x0000, 0x7E28): 'debris_fetch',
    (0x0000, 0x7E86): 'debris_rotate',
    (0x0000, 0xDA6E): 'rotate_vertices_2',
    (0x0000, 0xDAE9): 'camera_mode1_record',
    (0x0000, 0xE83E): 'draw_flat_mesh',
    (0x0000, 0xE8B9): 'flat_gather_vertices',
    (0x0000, 0xE903): 'flat_transform',
    (0x0000, 0xE978): 'flat_project',
    (0x0000, 0xEA3E): 'flat_two_sided',
    (0x0000, 0xEA68): 'flat_draw',
    (0x0000, 0x2D2A): 'mesh_order_faces',
    (0x0000, 0x2E59): 'mesh_group_faces',
    (0x0000, 0x29C4): 'object_transform_vertices',
    (0x0000, 0x2A6B): 'rotate_xz_by_index',
    (0x0000, 0x2A99): 'object_translate_only',
    (0x0000, 0x2AF2): 'draw_object',
    (0x0000, 0x2BBD): 'pipeline_sanity_check',
    (0x0000, 0x37E3): 'keyboard_isr',
    (0x0000, 0x3D87): 'collect_cell_objects',
    (0x0000, 0x3DE7): 'build_ground_list',
    (0x0000, 0x3E5E): 'ground_row_records',
    (0x0000, 0x3E8F): 'ground_cell_records',
    (0x0000, 0x3F4D): 'ground_mesh_too_far',
    (0x0000, 0x3FAB): 'ground_remove_duplicates',
    (0x0000, 0x3F0F): 'player_cell_index',
    (0x0000, 0x3F33): 'set_heading_sector',
    (0x0000, 0x41F8): 'cell_to_local',
    (0x0000, 0x42C0): 'collect_cell_extras',
    (0x0000, 0x42EF): 'extra_to_record',
    (0x0000, 0x45B8): 'record_removed',
    (0x0000, 0x46AC): 'project_vertices',
    (0x0000, 0x4772): 'project_point',
    (0x0000, 0x481A): 'projection_divide_handler',
    (0x0000, 0x482B): 'draw_visible_faces',
    (0x0000, 0x48A5): 'polygon_outline',
    (0x0000, 0x5EEE): 'approx_distance',
    (0x0000, 0x70FB): 'character_animations_index',
    (0x0000, 0x712B): 'character_animations_append',
    (0x0000, 0x72E5): 'image_unpack_shared',
    (0x0000, 0x8B1E): 'sound_load_set',
    (0x0000, 0x9F17): 'load_256_image_and_palette',
    (0x0000, 0x9F7C): 'set_palette_after_image',
    (0x0000, 0x9F8B): 'set_palette_8bit',
    (0x0000, 0x9FA4): 'set_palette_6bit',
    (0x0000, 0xA2D5): 'track_target',
    (0x0000, 0xB0A6): 'people_select_frames',
    (0x0000, 0xB0D7): 'person_frame_armed',
    (0x0000, 0xB13D): 'person_frame_civilian',
    (0x0000, 0xB1C1): 'character_models_load_body',
    (0x0000, 0xB425): 'bytekiller_unpack',
    (0x0000, 0xB519): 'cutscene_apply_frame',
    (0x0000, 0xEAF5): 'protection_draw_symbol',
    (0x0000, 0xEB9A): 'protection_select_symbol',
    (0x0000, 0xFACE): 'load_file',
    (0x11BC, 0x0000): 'fill_polygon',
    (0x11BC, 0x00BC): 'poly_chain_b_next',
    (0x11BC, 0x0136): 'poly_chain_a_next',
    (0x11BC, 0x01AD): 'polygon_setup',
    (0x11BC, 0x0294): 'poly_degenerate_line',
    (0x11BC, 0x02CC): 'poly_span_reset',
    (0x11BC, 0x02D8): 'poly_span_store',
    (0x11BC, 0x0305): 'poly_fill_solid',
    (0x11BC, 0x03B6): 'ega_begin_solid',
    (0x11BC, 0x03D0): 'ega_end_solid',
    (0x11BC, 0x03D9): 'poly_fill_dither',
    (0x11BC, 0x04B4): 'ega_fill_run',
    (0x11BC, 0x04C8): 'ega_begin_dither',
    (0x11BC, 0x04DB): 'ega_end_dither',
    (0x11BC, 0x04E4): 'poly_get_dither_pair',
    (0x11BC, 0x0950): 'load_window_if_needed',
    (0x11BC, 0x097E): 'load_window',
    (0x11BC, 0x0A16): 'load_window_ground_and_cells',
    (0x11BC, 0x0AC6): 'ground_meshes_negate_z',
    (0x11BC, 0x0EA8): 'ground_placements_map_meshes',
    (0x11BC, 0x10A2): 'mesh_highest_point',
    (0x11BC, 0x0E83): 'ground_copy_secondary_list',
    (0x11BC, 0x0F3C): 'ground_resolve_secondary_refs',
    (0x11BC, 0x10D4): 'ground_index_meshes',
    (0x11BC, 0x1117): 'load_window_objects',
    (0x11BC, 0x120A): 'copy_def_mesh_to_slot',
    (0x11BC, 0x124C): 'prepare_all_cell_records',
    (0x11BC, 0x1292): 'prepare_cell_records',
    (0x11BC, 0x1386): 'note_special_object',
    (0x11BC, 0x12E7): 'la_bmp_load',
    (0x11BC, 0x14D3): 'ground_sort_layers',
    (0x11BC, 0x1FCC): 'collision_test',
    (0x11BC, 0x21CA): 'collision_grid_address',
    (0x11BC, 0x2251): 'collision_map_build',
    (0x11BC, 0x258E): 'index_resident_footprints',
    (0x11BC, 0x239D): 'collision_stamp_object',
    (0x11BC, 0x157C): 'mesh_reverse_all_faces',
    (0x11BC, 0x159C): 'mesh_face_visibility',
    (0x11BC, 0x161B): 'face_reverse_winding',
    (0x11BC, 0x163D): 'face_edge_vectors',
    (0x11BC, 0x168B): 'face_is_hidden',
    (0x11BC, 0x175F): 'slope_code',
    (0x11BC, 0x2491): 'collision_stamp_setup',
    (0x14B5, 0x000A): 'cutscene_play',
    (0x15AD, 0x0006): 'sort_draw_list',
    (0x15AD, 0x001F): 'sort_write_sorted',
    (0x15AD, 0x0049): 'sort_build_nodes',
    (0x15AD, 0x00CE): 'sort_by_depth',
    (0x15AD, 0x010F): 'sort_fix_order',
    (0x15AD, 0x014A): 'sort_fix_order_step',
    (0x15AD, 0x01BC): 'sort_remove_hidden',
    (0x15AD, 0x01FA): 'sort_building_extent',
    (0x15AD, 0x024F): 'sort_footprint_corners',
    (0x15AD, 0x034F): 'sort_project',
    (0x15AD, 0x0386): 'sort_extent_from_points',
    (0x15AD, 0x03C6): 'sort_compare_nodes',
    (0x15AD, 0x0426): 'sort_cutout_extent',
    (0x15AD, 0x0480): 'sort_hidden_behind',
    (0x15AD, 0x04FA): 'sort_never_hides',
    (0x15AD, 0x054F): 'sort_extent_nearer_at',
    (0x15AD, 0x0582): 'sort_node_centre',
    (0x0000, 0x3B88): 'update_visible_cells',
    (0x14B5, 0x0216): 'lzhuf_unpack',
    (0x5B67, 0x0786): 'sample_select_device',
    (0x5B67, 0x0818): 'sample_play',
    (0x0000, 0xB187): 'character_models_civilian',
    (0x0000, 0xB199): 'character_models_cop',
    (0x0000, 0xB1AD): 'character_models_soldier',
    (0x0000, 0xB1DE): 'character_models_init_faces',
    (0x0000, 0xAE13): 'character_resources_variant',
    (0x0000, 0x70DF): 'character_resources_load',
    (0x0000, 0x02B5): 'vehicle_transition',
    (0x0000, 0xB558): 'cutscene_background',
    (0x0000, 0xB36D): 'cutscene_ega_background',
    (0x0000, 0xB3BC): 'cutscene_ega_frame',
    (0x0000, 0xD628): 'ratings_load_decode',
    (0x0000, 0xD5FA): 'ratings_encode_save',
    (0x0000, 0xD64C): 'ratings_stats_save',
    (0x0000, 0xD658): 'ratings_stats_restore',
    (0x0000, 0xD66C): 'ratings_select',
    (0x0000, 0xD67F): 'ratings_insert',
    (0x0000, 0xD739): 'ratings_update_time',
    (0x0000, 0xD740): 'ratings_clear_stats',
}

# Routines that have a verified C version in src/ (shown in the listing)
C_VERSIONS = {
    # helper routines translated inside larger C functions (registered 2026-11-18)
    (0x0000, 0x164E): 'helper sub_0000_164E, inside src/mapscreen.c',
    (0x0000, 0x1FE9): 'helper clip_window_store_face, inside src/clip2d.c',
    (0x0000, 0x1FFE): 'helper clip_window_face, inside src/clip2d.c',
    (0x0000, 0x208F): 'helper clip_window_face_edge, inside src/clip2d.c',
    (0x0000, 0x20DC): 'helper clip_window_point_right, inside src/clip2d.c',
    (0x0000, 0x2181): 'helper clip_window_point_left, inside src/clip2d.c',
    (0x0000, 0x2226): 'helper clip_window_point_top, inside src/clip2d.c',
    (0x0000, 0x22CB): 'helper clip_window_point_bottom, inside src/clip2d.c',
    (0x0000, 0x2370): 'helper cross_right, inside src/clip2d.c',
    (0x0000, 0x23CB): 'helper cross_left, inside src/clip2d.c',
    (0x0000, 0x2426): 'helper cross_top, inside src/clip2d.c',
    (0x0000, 0x2488): 'helper cross_bottom, inside src/clip2d.c',
    (0x0000, 0x3FCD): 'helper sub_0000_3FCD, inside src/cells.c',
    (0x0000, 0x3FF5): 'helper sub_0000_3FF5, inside src/cells.c',
    (0x0000, 0x4418): 'helper sub_0000_4418, inside src/mapscreen.c',
    (0x0000, 0x4428): 'helper sub_0000_4428, inside src/mapscreen.c',
    (0x0000, 0x445A): 'helper sub_0000_445A, inside src/mapscreen.c',
    (0x0000, 0x4476): 'helper sub_0000_4476, inside src/mapscreen.c',
    (0x0000, 0x960F): 'helper timed_object_expire, inside src/framelist.c',
    (0x0000, 0xDAE9): 'helper camera_mode1_record, inside src/drawlist.c',
    (0x11BC, 0x007C): 'helper sub_11BC_007C, inside src/polyfill.c',
    (0x11BC, 0x00BC): 'helper poly_chain_b_next, inside src/polyfill.c',
    (0x11BC, 0x0136): 'helper poly_chain_a_next, inside src/polyfill.c',
    (0x11BC, 0x0294): 'helper poly_degenerate_line, inside src/polyfill.c',
    (0x11BC, 0x02D8): 'helper poly_span_store, inside src/polyfill.c',
    (0x11BC, 0x0305): 'helper poly_fill_solid, inside src/polyfill.c',
    (0x11BC, 0x03B6): 'helper ega_begin_solid, inside src/polyfill.c',
    (0x11BC, 0x03D0): 'helper ega_end_solid, inside src/polyfill.c',
    (0x11BC, 0x03D9): 'helper poly_fill_dither, inside src/polyfill.c',
    (0x11BC, 0x04B4): 'helper ega_fill_run, inside src/polyfill.c',
    (0x11BC, 0x04C8): 'helper ega_begin_dither, inside src/polyfill.c',
    (0x11BC, 0x04DB): 'helper ega_end_dither, inside src/polyfill.c',
    (0x11BC, 0x04E4): 'helper poly_get_dither_pair, inside src/polyfill.c',
    (0x15AD, 0x001F): 'helper sort_write_sorted, inside src/sortlist.c',
    (0x15AD, 0x0049): 'helper sort_build_nodes, inside src/sortlist.c',
    (0x15AD, 0x00CE): 'helper sort_by_depth, inside src/sortlist.c',
    (0x15AD, 0x010F): 'helper sort_fix_order, inside src/sortlist.c',
    (0x15AD, 0x014A): 'helper sort_fix_order_step, inside src/sortlist.c',
    (0x15AD, 0x01BC): 'helper sort_remove_hidden, inside src/sortlist.c',
    (0x15AD, 0x01FA): 'helper sort_building_extent, inside src/sortlist.c',
    (0x15AD, 0x024F): 'helper sort_footprint_corners, inside src/sortlist.c',
    (0x15AD, 0x034F): 'helper sort_project, inside src/sortlist.c',
    (0x15AD, 0x0386): 'helper sort_extent_from_points, inside src/sortlist.c',
    (0x15AD, 0x03C6): 'helper sort_compare_nodes, inside src/sortlist.c',
    (0x15AD, 0x0426): 'helper sort_cutout_extent, inside src/sortlist.c',
    (0x15AD, 0x046C): 'helper sub_15AD_046C, inside src/sortlist.c',
    (0x15AD, 0x0480): 'helper sort_hidden_behind, inside src/sortlist.c',
    (0x15AD, 0x04FA): 'helper sort_never_hides, inside src/sortlist.c',
    (0x15AD, 0x053F): 'helper sub_15AD_053F, inside src/sortlist.c',
    (0x15AD, 0x054F): 'helper sort_extent_nearer_at, inside src/sortlist.c',
    (0x15AD, 0x0582): 'helper sort_node_centre, inside src/sortlist.c',
    (0x0000, 0x36D0): 'player_position_backup (src/playercontrols.c)',
    (0x0000, 0x36EF): 'player_position_restore (src/playercontrols.c)',
    (0x0000, 0x370E): 'player_keep_inside (src/playercontrols.c); original map bounds',
    (0x0000, 0x36A9): 'driving_reset (src/playercontrols.c)',
    (0x0000, 0x2E9E): 'player_movement_gate (src/playercontrols.c); AX/carry retained',
    (0x0000, 0x300B): 'walking_speed_step (src/playercontrols.c), scan=1',
    (0x0000, 0x302E): 'walking_speed_step (src/playercontrols.c), scan=0; byte DIV remainder retained',
    (0x0000, 0x331D): 'driving_steer (src/playercontrols.c)',
    (0x0000, 0x33A5): 'driving_accelerate (src/playercontrols.c)',
    (0x0000, 0x354E): 'driving_gear_key (src/playercontrols.c); AX/carry retained',
    (0x0000, 0x30A0): 'walking_step (src/playercontrols.c); native input, position normalization/bounds',
    (0x0000, 0x3269): 'driving_step (src/driving.c); native HUD/damage, 02B5 exit body external',
    (0x0000, 0x3402): 'driving_transmission (src/driving.c)',
    (0x0000, 0x3584): 'driving_brake (src/driving.c)',
    (0x0000, 0x35C0): 'driving_smooth_speed (src/driving.c); acceleration/deceleration timer asymmetry',
    (0x0000, 0x3646): 'driving_displace (src/driving.c)',
    (0x0000, 0x3684): 'driving_damage_exit (src/driving.c); five native player hits, 02B5 exit external',
    (0x0000, 0xC21F): 'opponent_controller (src/opponentai.c); native foot/vehicle targets; explicit resource/platform services',
    (0x0000, 0xB7B6): 'opponent_controller_slow (src/opponentai.c); native foot/vehicle targets; explicit resource/platform services',
    (0x0000, 0xBFB3): 'opponent_fire_at_companion / state (src/opponentai.c); AX/DX outputs retained',
    (0x0000, 0xB5F9): 'world_step (src/worldstep.c); native foot/vehicle targets; explicit resource/platform services',
    (0x0000, 0xDB26): 'companion_ai (src/companionai.c); native foot/vehicle targets; explicit resource/platform services',
    (0x0000, 0xC1CB): 'opponent_destination_query (src/opponentdest.c); AX/BX/CX outputs retained',
    (0x0000, 0xC1B0): 'opponent_pick_destination (src/opponentdest.c)',
    (0x0000, 0xB91F): 'opponent_has_openings (src/opponentdest.c); returns original carry',
    (0x0000, 0xB94A): 'opponent_choose_follow_mode (src/opponentdest.c)',
    (0x0000, 0xB973): 'opponent_follow_destination (src/opponentdest.c)',
    (0x0000, 0xC42F): 'opponent_check_travel_interrupt (src/opponentdest.c); inventory and spawn grid native',
    (0x0000, 0xBBF1): 'opponent_place_ahead (src/opponentplace.c)',
    (0x0000, 0xC35F): 'opponent_place_flank (src/opponentplace.c)',
    (0x0000, 0xDC7B): 'opponent_place_companion (src/opponentplace.c); failed search and companion-local Z retained',
    (0x0000, 0xDD67): 'companion_choose_behavior (src/companion.c), mode=0',
    (0x0000, 0xDDBE): 'companion_choose_behavior (src/companion.c), mode=1',
    (0x0000, 0xDE05): 'companion_choose_behavior (src/companion.c), mode=2',
    (0x0000, 0xDE46): 'companion_move (src/companion.c)',
    (0x0000, 0xDD56): 'companion_step (src/companion.c), modes 0..2; with_services (src/worldstep.c), modal panels external',
    (0x0000, 0xB5B4): 'opponent_init_difficulty (src/companion.c)',
    (0x0000, 0xAA81): 'collision_steer (src/motion.c); alternating offsets and exhausted-search carry retained',
    (0x0000, 0xB755): 'vehicle_choose_destination (src/motion.c)',
    (0x0000, 0xB6AA): 'vehicle_follow_route (src/motion.c); native destination, collision and movement',
    (0x0000, 0xB790): 'world_update_delay (src/motion.c); 16-bit shift count behavior',
    (0x0000, 0xC125): 'opponent_find_item (src/opponentitems.c); AX/DI/ES/carry output',
    (0x0000, 0xC0F5): 'opponent_sound_for_item (src/opponentitems.c); 21-byte source search',
    (0x0000, 0xC0A7): 'opponent_build_choices (src/opponentitems.c); paired far inventory, holes and AX retained',
    (0x0000, 0xC068): 'opponent_select_choice (src/opponentitems.c); unavailable-choice state flag retained',
    (0x0000, 0xC16D): 'opponent_add_item (src/opponentitems.c)',
    (0x0000, 0xC14C): 'opponent_cycle_item (src/opponentitems.c)',
    (0x0000, 0xBC68): 'opponent_fire_state (src/opponentfire.c); native foot/vehicle targets; explicit resource/platform services',
    (0x0000, 0xBF1B): 'opponent_burst (src/opponentfire.c); native foot/vehicle targets; explicit resource/platform services',
    (0x0000, 0xC397): 'opponent_burst (src/opponentfire.c); native foot/vehicle targets; explicit resource/platform services',
    (0x0000, 0x77F6): 'weapon_collect_targets (src/targetlist.c); two-list limit/index quirks retained',
    (0x0000, 0x7852): 'weapon_target_candidate (src/targetlist.c)',
    (0x0000, 0x794A): 'camera_full_height (src/camera.c); palette platform, native resources/copies/collision',
    (0x0000, 0x7989): 'camera_full_image (src/camera.c); real image IO and collision rebuild',
    (0x0000, 0x79C3): 'camera_key_step (src/camera.c); full-height/normal entries and no-op gates',
    (0x0000, 0xBA60): 'world_clamp_actor (src/worldclock.c); source signed-half-word comparisons',
    (0x0000, 0xDEB5): 'position_normalize_companion (src/worldclock.c); DIV fault-skip behavior',
    (0x0000, 0xBB03): 'world_follow_companion (src/worldclock.c)',
    (0x0000, 0xBA1C): 'world_wander_vehicle (src/worldclock.c)',
    (0x0000, 0xBAB7): 'world_displace_vehicle (src/worldclock.c)',
    (0x0000, 0xB9D2): 'world_clock_step (src/worldclock.c); native wandering and position updates',
    (0x0000, 0xBB2B): 'position_relative_vehicle (src/position.c); both collision queries native',
    (0x11BC, 0x1D03): 'weapon_hotkeys (src/weaponkeys.c); native selection, inventory, optics and reload text',
    (0x11BC, 0x1D59): 'weapon_reload_slot (src/weaponkeys.c); inventory/UI native, preserves SI for hotkey loop',
    (0x11BC, 0x1DD8): 'weapon_deselect_slot (src/weaponkeys.c)',
    (0x11BC, 0x1E1A): 'weapon_select_slot (src/weaponkeys.c); retains AL low segment-byte effect',
    (0x11BC, 0x1E6B): 'weapon_refresh_selection (src/weaponkeys.c); actual scope image IO',
    (0x0000, 0x0998): 'player_look_keys (src/weaponkeys.c)',
    (0x11BC, 0x1796): 'player_companion_indicator (src/playerstate.c); sound event',
    (0x0000, 0x091F): 'player_sample_warning (src/playerstate.c)',
    (0x0000, 0x7088): 'world_toggle_records (src/playerstate.c)',
    (0x0000, 0x596C): 'player_update_threat (src/playerstate.c)',
    (0x0000, 0xA426): 'figure_retry_deferred (src/playerstate.c); native spawn dependencies',
    (0x0000, 0x3B54): 'debug_vector_toggle (src/playerstate.c); code byte and modal text native',
    (0x0000, 0x0809): 'gameplay_update_controls_dx + gameplay_update_projectiles (src/gameplay.c); complex transition DX remains open',
    (0x0000, 0x37AC): 'keyboard_read (src/keyboard.c); input wait platform-owned',
    (0x0000, 0x37D5): 'keyboard_read_available (src/keyboard.c)',
    (0x0000, 0x4609): 'player_check_map_edge (src/playerstatus.c); modal input platform-owned',
    (0x0000, 0x4495): 'vehicle_refuel_nearby (src/playerstatus.c); complete entry with native text and keyboard ring',
    (0x0000, 0x4F4B): 'hud_init_normal (src/weaponhud.c); actual image IO and inventory/icon reconstruction',
    (0x0000, 0x985C): 'weapon_inventory_rebuild (src/weaponhud.c); includes 98EF/5754 slot construction',
    (0x11BC, 0x1BE1): 'hud_weapon_icon (src/weaponhud.c)',
    (0x11BC, 0x1C7D): 'hud_weapon_slots (src/weaponhud.c)',
    (0x11BC, 0x1EEB): 'hud_weapon_selection (src/weaponhud.c); also 1F17 colour entry',
    (0x5776, 0x00E5): 'screen_blit_five_plane_bytes (src/vehiclehud.c)',
    (0x5776, 0x012A): 'hud_choose_panel (src/weaponhud.c)',
    (0x0000, 0x735A): 'hud_armor_overlay (src/weaponhud.c); real asset bytes',
    (0x0000, 0x745B): 'hud_field_marker (src/weaponhud.c)',
    (0x0000, 0xAEC4): 'scene_contact_test (src/sceneeffects.c)',
    (0x0000, 0xAE2E): 'scene_contact_update (src/sceneeffects.c)',
    (0x0000, 0x18D3): 'scene_flash (src/sceneeffects.c)',
    (0x0000, 0x9756): 'scene_timed_effect (src/sceneeffects.c)',
    (0x0000, 0x41C4): 'hud_vehicle_remaining (src/sceneeffects.c)',
    (0x5776, 0x0247): 'scene_overlay_restore (src/sceneeffects.c); planar branch',
    (0x0000, 0x07D1): 'scene_overlay_replay (src/sceneeffects.c); planar branch',
    (0x5776, 0x01E0): 'scene_overlay_save (src/textbox.c); planar branch',
    (0x0000, 0xE0C0): 'screen_text8 (src/textbox.c); planar branch, loaded 8x8 font',
    (0x5776, 0x0346): 'textbox_border (src/textbox.c)',
    (0x5776, 0x03ED): 'textbox_border_layer (src/textbox.c)',
    (0x0000, 0x5032): 'textbox_draw (src/textbox.c); complete planar path, input/retrace platform callbacks',
    (0x0000, 0x093A): 'scene_warning (src/textbox.c)',
    (0x0000, 0x0758): 'scene_post_render (src/scenecompose.c); HUD, weapon frame and instruments; guided DX carried from overlays',
    (0x0000, 0x5546): 'inventory_remove (src/inventory.c); remove entry, ES=DS',
    (0x0000, 0xC898): 'hud_message (src/hudmessage.c); native text/copies, sound event',
    (0x0000, 0xC957): 'hud_message_hide (src/hudmessage.c)',
    (0x0000, 0xC976): 'hud_message_clear (src/hudmessage.c)',
    (0x0000, 0x6386): 'player_hit_native / player_hit_native_state (src/playerdamage.c); AX retained, border/sound events',
    (0x0000, 0x643E): 'player_damage_region (src/playerdamage.c)',
    (0x0000, 0x7A28): 'camera_reset (src/camera.c); modes 0/1/2, normal HUD native, BIOS/palette host',
    (0x0000, 0x7946): 'camera_reset_full_view wrapper; modes 1/2',
    (0x0000, 0x0C47): 'camera_clear_pages (src/camera.c)',
    (0x11BC, 0x2251): 'collision_map_build (src/collisionbuild.c)',
    (0x11BC, 0x233F): 'stamp_extras, static in src/collisionbuild.c',
    (0x11BC, 0x239D): 'collision_stamp_object (src/collisionbuild.c)',
    (0x11BC, 0x2491): 'collision_stamp_setup (src/collisionbuild.c)',

    (0x0000, 0x6F99): 'src/weaponflight.c: weapon_charge_projectile_step',
    (0x0000, 0xD8D2): 'src/weaponflight.c: weapon_guided_projectiles_step',
    (0x0000, 0xD8F2): 'src/weaponflight.c: guided_step, static; camera 0/2, serial disabled',

    (0x0000, 0xA840): 'figure_select_position (src/figurespawn.c)',
    (0x0000, 0xAA3B): 'figure_grid_to_world (src/figurespawn.c)',
    (0x0000, 0xAD00): 'figure_spawn(civilian=0) (src/figurespawn.c)',
    (0x0000, 0xAD37): 'figure_spawn(civilian=1) (src/figurespawn.c)',
    (0x0000, 0xB05E): 'figure_init_movement (src/figurespawn.c)',
    (0x0000, 0xB0A6): 'figure_select_frames (src/figurespawn.c)',
    (0x0000, 0xB0D7): 'part of figure_select_frames (src/figurespawn.c)',
    (0x0000, 0xB13D): 'part of figure_select_frames (src/figurespawn.c)',
    (0x0000, 0x5BDB): 'figure_feedback (src/figure.c)',
    (0x0000, 0xC9A5): 'figure_feedback_draw (src/figure.c)',
    (0x0000, 0x6D49): 'weapon_fire (src/weapondamage.c); serial mode rejected, sound events',
    (0x0000, 0x6B54): 'weapon_frame (src/weapondamage.c); single-player, sound/player-hit events',
    (0x0000, 0x6F70): 'firing_alert, static in src/weapondamage.c',

    (0x0000, 0x5CFA): 'src/figure.c: figure_map_sample',
    (0x0000, 0xA480): 'src/figure.c: figure_spawn_grid_block',
    (0x0000, 0xA46F): 'src/figure.c: figure_spawn_grid',

    (0x0000, 0xAFD0): "figure_remove_complete (src/figurespawn.c); native AD37 replacement; ES=DS",
    (0x0000, 0xA00C): 'src/weaponsight.c: weapon_visual_insert',
    (0x0000, 0xA036): 'src/weaponsight.c: weapon_visual_step',

    (0x0000, 0x6B23): 'src/weaponsight.c: weapon_images_load',
    (0x0000, 0xDA2C): 'src/weaponsight.c: weapon_projectile_turn',
    (0x0000, 0xDABC): 'src/weaponsight.c: weapon_projectile_outside',

    (0x0000, 0x6C93): 'src/weaponsight.c: weapon_update_sight',
    (0x0000, 0x15F4): 'src/weaponsight.c: weapon_draw_crosshair',
    (0x0000, 0xDAD6): 'src/weaponsight.c: weapon_projectile_slot',
    (0x0000, 0xD896): 'src/weaponsight.c: weapon_projectile_create',
    (0x0000, 0x6EE0): 'src/weaponsight.c: weapon_charge_step (6D49 tail)',
    (0x0000, 0x6B70): 'src/weaponsight.c: weapon_draw_sights (post-firing suffix)',

    (0x0000, 0x7158): 'src/weaponsight.c: weapon_draw_autoaim',
    (0x0000, 0x720C): 'src/weaponsight.c: weapon_lock_colour',
    (0x0000, 0x7884): 'src/weaponsight.c: weapon_select_target(cycle=1)',
    (0x0000, 0x789B): 'src/weaponsight.c: weapon_select_target',
    (0x0000, 0x78D6): 'src/weaponsight.c: weapon_target_rejected',

    (0x0000, 0x6AFC): "src/weaponsight.c: weapon_classify_source",
    (0x0000, 0x7008): "src/weaponsight.c: weapon_draw_numbers",
    (0x0000, 0x70AA): 'vehicle_hud_load (src/vehiclehud.c)',
    (0x0000, 0x7250): 'vehicle_hud_draw (src/vehiclehud.c)',
    (0x0000, 0x731D): 'image_unpack_shared with lzhuf=1 (src/vehiclehud.c); source-segment 8510 lookup retained',
    (0x5776, 0x00A6): 'screen_blit_five_planes (src/vehiclehud.c)',
    (0x0000, 0x72E5): 'image_unpack_shared (src/vehiclehud.c)',
    (0x0000, 0x6962): 'image_load_screen (src/imageload.c); DOS open/read/close host only',
    (0x0000, 0x6994): 'image_draw_loaded (src/imageload.c); DOS open/read/close host only',
    (0x0000, 0x6A0F): 'image_next_plane (src/imageload.c); DOS open/read/close host only',
    (0x0000, 0x6AAE): 'image_prepare (src/imageload.c); DOS open/read/close host only',
    (0x0000, 0xFAAF): 'file_load with dest_seg=main DS (src/imageload.c); normal non-wrapping DOS stack',
    (0x0000, 0xFACE): 'file_load (src/imageload.c); normal non-wrapping DOS stack',
    (0x11BC, 0x25B0): 'collision_line_blocker (src/hudquery.c)',
    (0x0000, 0xA2B3): 'hud_target_contains_sight (src/hudquery.c)',
    (0x0000, 0xA07B): 'hud_scan_target (src/hudquery.c), weapon_scan_damage (src/weapondamage.c); single-player damage, sound/player-hit events',
    (0x11BC, 0x21CA): 'collision_grid_address (src/hudquery.c)',
    (0x0000, 0x766A): 'hud_load_optics (src/hudoptics.c); file IO remains external',
    (0x0000, 0x7683): 'hud_init_optics (src/hudoptics.c); file IO remains external',
    (0x0000, 0x76B4): 'hud_draw_optics (src/hudoptics.c); file IO remains external',
    (0x0000, 0xE5A3): 'mask_slot, static in src/hudcompose.c; verified through target composition',
    (0x0000, 0xE589): 'mask_slot, static in src/hudcompose.c; verified through target composition',
    (0x0000, 0xE56F): 'mask_slot, static in src/hudcompose.c; verified through target composition',
    (0x0000, 0x4FE5): 'hud_refresh_pages (src/hudcompose.c); bitmap IO/sound remain external; HUD scan native',
    (0x0000, 0xE170): 'hud_draw_system (src/hudcompose.c); bitmap IO/sound remain external; HUD scan native',
    (0x0000, 0xE4AE): 'hud_draw_target (src/hudcompose.c); bitmap IO/sound remain external; HUD scan native',
    (0x0000, 0xE542): 'hud_draw_target_frame (src/hudcompose.c)',
    (0x0000, 0xE5E9): 'hud_draw_warnings (src/hudcompose.c); bitmap IO/sound remain external; HUD scan native',
    (0x0000, 0xE6E0): 'hud_draw_target_info (src/hudcompose.c)',
    (0x0000, 0xE813): 'hud_clear_target_info (src/hudcompose.c)',
    (0x0000, 0x1A4D): 'screen_blit_planar (src/planarblit.c)',
    (0x0000, 0x1B19): 'hud_restore_background (src/planarblit.c)',
    (0x0000, 0xD6CB): 'score_update (src/hudscore.c)',
    (0x0000, 0xE26D): 'hud_format_score (src/hudscore.c)',
    (0x0000, 0xE348): 'hud_draw_sweep (src/hudsweep.c)',
    (0x0000, 0xE44A): 'hud_sweep_clear (src/hudsweep.c)',
    (0x0000, 0xE280): 'hud_draw_status (src/hudstatus.c)',
    (0x0000, 0xE29B): 'hud_collect_status (src/hudstatus.c)',
    (0x0000, 0xE307): 'hud_cycle_status (src/hudstatus.c)',
    (0x11BC, 0x181B): 'hud_draw_indicators (src/indicators.c), including 195C/19AE/19E1',
    (0x11BC, 0x195C): 'hud_bearing_x (src/indicators.c)',
    (0x11BC, 0x19AE): 'hud_bearing_tick (src/indicators.c)',
    (0x11BC, 0x19E1): 'hud_indicator_erase (src/indicators.c)',
    (0x0000, 0xE5BD): 'hud_zoom_key (src/systemhud.c)',
    (0x0000, 0xE638): 'hud_flash_bitmap (src/systemhud.c)',
    (0x0000, 0xE66E): 'hud_draw_system_frame (src/systemhud.c)',
    (0x0000, 0x19CC): 'image_unpack_compressed (src/unpack.c), decoder-private adaptive/bit-reader scratch stays local',
    (0x0000, 0xCF74): 'map_setup_area (src/mapsetup_area.c), BIOS/IO/palette callbacks remain external',
    (0x0000, 0x1985): 'screen_blit_mask (src/maskblit.c); patchable colour/stride passed explicitly',
    (0x0000, 0xD177): 'travel_run / native_opponents / native_world (src/travel.c); latter uses native B588/B5F9, cell IO and world presentation external',
    (0x0000, 0xB588): 'travel_simulate (src/travel.c), world-step body remains external',
    (0x0000, 0xD265): 'travel_clear_arrival (src/travel.c), collision/IO callbacks remain external',
    (0x0000, 0xCE2B): 'map_setup_local (src/mapsetup.c), resource/platform callbacks remain external',
    (0x0000, 0xCBF8): 'through CC43: map_begin_local; CC43 onward: map_select (src/mapsetup.c, src/mapui.c)',
    (0x0000, 0xCFEC): 'map_begin_area through D021 (src/mapsetup_area.c), then map_select area branch through D0A5 (src/mapui.c)',
    (0x0000, 0xD0A6): 'map_area_viewport (src/maparea.c)',
    (0x0000, 0xD102): 'area_line_clipped (src/maparea.c)',
    (0x0000, 0x1343): 'area_line_to (src/maparea.c), including 13E3..1482',
    (0x0000, 0x3792): 'map_clear_key_buffer memory effects (src/mapsetup.c), interrupt masking remains platform-owned',
    (0x0000, 0xB660): 'position_relative_actor (src/position.c)',
    (0x0000, 0xCB4B): 'map_draw_homing (src/mapscreen.c)',
    (0x0000, 0xD2BE): 'travel_apply_destination (src/travel.c), using map_write_destination_position; cell IO callback external',
    (0x0000, 0x2F1C): 'position_normalize (src/position.c)',
    (0x0000, 0x2FB2): 'rebase, static in src/position.c',
    (0x0000, 0xDB01): 'part of rebase (src/position.c)',
    (0x5776, 0x0154): 'hud_clear_bytes (src/hud.c)',
    (0x5776, 0x018A): 'hud_clear_number (src/hud.c)',
    (0x5776, 0x04BC): 'screen_copy_rect (src/mapscreen.c)',
    (0x0000, 0x1492): 'planar branch: screen_draw_mask16 (src/mapscreen.c); chunky branch remains untranslated',
    (0x0000, 0x4F2A): 'hud_draw_compass (src/hud.c)',
    (0x0000, 0x5998): 'heading_degrees (src/hud.c)',
    (0x0000, 0x73C1): 'hud_draw_speed (src/hud.c)',
    (0x0000, 0x7428): 'hud_draw_vehicle_counter (src/hud.c)',
    (0x0000, 0x772B): 'hud_draw_counters (src/hud.c)',
    (0x11BC, 0x1A01): 'hud_compass_needle (src/hud.c)',
    (0x0000, 0x60FD): 'map_restore_pointer (src/mapscreen.c)',
    (0x0000, 0x6128): 'planar branch: map_draw_pointer (src/mapscreen.c)',
    (0x0000, 0x830F): 'planar branch: map_pointer_step (src/mapscreen.c)',
    (0x0000, 0xCBA5): 'map_destination_measure (src/mapscreen.c)',
    (0x0000, 0xCC8D): 'map_local_destination (src/mapscreen.c)',
    (0x0000, 0xCD05): 'map_area_destination (src/mapscreen.c)',
    (0x0000, 0xCD4A): 'map_draw_info (src/mapscreen.c)',
    (0x0000, 0xCDE1): 'map_clear_info (src/mapscreen.c)',
    (0x0000, 0x43C6): 'map_draw_markers (src/mapscreen.c), with 4418..4494 and C5AF',
    (0x11BC, 0x2DBB): 'map_draw_grid (src/mapscreen.c)',
    (0x0000, 0xC766): 'hud_draw_number (src/hud.c)',
    (0x0000, 0xC7ED): 'hud_draw_text (src/hud.c)',
    (0x0000, 0xC872): 'hud_format_number (src/hud.c)',
    (0x11BC, 0x2E46): 'map_draw_grid_labels (src/hud.c), through 2EBB',
    (0x0000, 0x0F32): 'line_to (src/line.c), including the vertical and horizontal cases at 0DC7 / 0E39',
    (0x0000, 0x06C3): 'from 06DE: draw_background (src/background.c)',
    (0x0000, 0x159D): 'draw_ground_fill (src/background.c)',
    (0x0000, 0x16A9): 'horizon_load (src/background.c); conditional HORIZON.IMG reload',
    (0x0000, 0x16BE): 'draw_horizon (src/background.c); view angle, sky strips and sun',
    (0x0000, 0x1707): 'horizon_strip, static in src/background.c',
    (0x0000, 0x196B): 'part of draw_horizon (src/background.c)',
    (0x0000, 0x036E): 'build_frame_draw_list (src/framelist.c)',
    (0x0000, 0x5E62): 'angle_between / angle_between_state (src/framelist.c); AX heading and DX remainder',
    (0x0000, 0x7EC8): 'part of build_frame_draw_list (src/framelist.c)',
    (0x0000, 0x87FC): 'append_pickups, static in src/framelist.c',
    (0x0000, 0x881F): 'part of append_pickups (src/framelist.c)',
    (0x0000, 0x88A3): 'part of append_pickups (src/framelist.c)',
    (0x0000, 0x95F2): 'part of build_frame_draw_list (src/framelist.c), up to the point where the countdown ends',
    (0x0000, 0x9625): 'part of build_frame_draw_list (src/framelist.c)',
    (0x0000, 0x9FB2): 'append_projectiles, static in src/framelist.c',
    (0x0000, 0xB1F1): 'part of build_frame_draw_list (src/framelist.c)',
    (0x0000, 0xBD64): 'append_opponent_and_companion, static in src/framelist.c',
    (0x0000, 0xBE47): 'animation_bearing, static in src/framelist.c',
    (0x0000, 0xBE68): 'figure_mesh_5, static in src/framelist.c',
    (0x0000, 0xBECE): 'figure_mesh_8, static in src/framelist.c',
    (0x0000, 0xD9FB): 'append_guided_projectiles, static in src/framelist.c',
    (0x0000, 0xDA96): 'part of append_guided_projectiles (src/framelist.c)',
    (0x11BC, 0x1BBC): 'part of build_frame_draw_list (src/framelist.c)',
    (0x0000, 0x1C1A): 'matrix_from_angles (src/math3d.c)',
    (0x0000, 0x1C33): 'matrix_apply (src/math3d.c)',
    (0x0000, 0x1CA7): 'matrix_identity, static in src/math3d.c',
    (0x0000, 0x1CDC): 'part of matrix_from_angles (src/math3d.c)',
    (0x0000, 0x1DA9): 'part of matrix_from_angles (src/math3d.c)',
    (0x0000, 0x1E76): 'part of matrix_from_angles (src/math3d.c)',
    (0x0000, 0x4586): 'note_removed, static in src/blast.c',
    (0x0000, 0x45E6): 'part of queue_blast (src/blast.c)',
    (0x0000, 0x5E1E): 'part of map_page_update (src/mappage.c)',
    (0x0000, 0x5E48): 'part of map_page_update (src/mappage.c)',
    (0x0000, 0x7A83): 'restore_view_window, static in src/mappage.c',
    (0x0000, 0x7A92): 'set_view_window (src/mappage.c)',
    (0x0000, 0x7B28): 'debris_start (src/blast.c)',
    (0x0000, 0x7D2B): 'debris_update (src/blast.c)',
    (0x0000, 0x7E28): 'debris_fetch, static in src/drawlist.c',
    (0x0000, 0x7E86): 'debris_rotate, static in src/drawlist.c',
    (0x0000, 0x7EF0): 'explosion_damage (src/blast.c); sound, player damage, figure deaths and one bookkeeping call are reported as events, not performed',
    (0x0000, 0x8075): 'queue_blast, static in src/blast.c',
    (0x0000, 0x808E): 'ordinary_object, static in src/blast.c',
    (0x0000, 0x80B6): 'blast_queue_step / blast_queue_step_native (src/blast.c); legacy events or native figure/player damage',
    (0x0000, 0x80EE): 'random_word (src/blast.c)',
    (0x0000, 0x8117): 'part of random_word (src/blast.c)',
    (0x0000, 0xCE12): 'map_page_update (src/mappage.c)',
    (0x0000, 0xCEED): 'part of map_page_update (src/mappage.c)',
    (0x0000, 0xCF33): 'draw_map_view (src/mappage.c)',
    (0x0000, 0xF88A): 'random_step, static in src/blast.c',
    (0x0000, 0x1B46): 'rotate_bc (src/math3d.c)',
    (0x0000, 0x1B7D): 'rotate_xz (src/math3d.c)',
    (0x0000, 0x1BB0): 'rotate_xz_inverse (src/math3d.c)',
    (0x0000, 0x1BE5): 'rotate_ab (src/math3d.c)',
    (0x0000, 0x1F50): 'build_dither_table (src/math3d.c)',
    (0x0000, 0x1F6A): 'mesh_clip_window (src/clip2d.c), with its helpers 1FE9-2488',
    (0x0000, 0x24EA): 'mesh_clip_near (src/clipnear.c)',
    (0x0000, 0x2564): 'clip_face, static in src/clipnear.c',
    (0x0000, 0x25B3): 'clip_vertex, static in src/clipnear.c',
    (0x0000, 0x2673): 'clip_intersect, static in src/clipnear.c',
    (0x0000, 0x271E): 'draw_object_list (src/drawlist.c)',
    (0x0000, 0x285A): 'mesh_prepare (src/drawlist.c)',
    (0x0000, 0x28E4): 'record_mesh_number, static in src/drawlist.c',
    (0x0000, 0x2921): 'draw_list_camera, static in src/drawlist.c',
    (0x0000, 0x2986): 'part of draw_list_camera (src/drawlist.c)',
    (0x0000, 0x29C4): 'object_transform_vertices (src/object.c)',
    (0x0000, 0x2A99): 'object_translate_only (src/drawlist.c)',
    (0x0000, 0x2BFF): 'mesh_fetch (src/drawlist.c)',
    (0x0000, 0x7921): 'rotate_vertices, static in src/drawlist.c',
    (0x0000, 0xDA6E): 'rotate_vertices, static in src/drawlist.c',
    (0x0000, 0xE83E): 'draw_flat_mesh (src/drawlist.c)',
    (0x0000, 0xE8B9): 'flat_gather_vertices, static in src/drawlist.c',
    (0x0000, 0xE903): 'flat_transform, static in src/drawlist.c',
    (0x0000, 0xE978): 'flat_project, static in src/drawlist.c',
    (0x0000, 0xEA3E): 'flat_two_sided, static in src/drawlist.c',
    (0x0000, 0xEA68): 'flat_draw, static in src/drawlist.c',
    (0x0000, 0x2AF2): 'draw_object (src/drawobject.c)',
    (0x0000, 0x2BBD): 'pipeline_sanity_failed (src/drawobject.c)',
    (0x0000, 0x2D2A): 'mesh_order_faces (src/order.c), except its unreachable depth-sort branch',
    (0x0000, 0x2E59): 'group_faces, static in src/order.c',
    (0x0000, 0x3B88): 'second half (3C18-3D61) is collect_visible_objects (src/cells.c); the first half decides whether to rebuild and loads sectors',
    (0x0000, 0x3D87): 'collect_cell_objects, static in src/cells.c',
    (0x0000, 0x3DE7): 'build_ground_list (src/cells.c)',
    (0x0000, 0x3E5E): 'ground_row_records, static in src/cells.c',
    (0x0000, 0x3E8F): 'ground_cell_records, static in src/cells.c',
    (0x0000, 0x3F4D): 'ground_mesh_too_far, static in src/cells.c',
    (0x0000, 0x3FAB): 'ground_remove_duplicates, static in src/cells.c',
    (0x0000, 0x41F8): 'part of collect_cell_extras (src/cells.c)',
    (0x0000, 0x42C0): 'collect_cell_extras, static in src/cells.c',
    (0x0000, 0x42EF): 'part of collect_cell_extras (src/cells.c)',
    (0x0000, 0x45B8): 'record_removed, static in src/cells.c',
    (0x0000, 0x46AC): 'project_vertices (src/project.c)',
    (0x0000, 0x4772): 'project_point (src/project.c)',
    (0x0000, 0x482B): 'draw_visible_faces (src/drawfaces.c)',
    (0x0000, 0x5EEE): 'approx_distance (src/target.c)',
    (0x0000, 0xA2D5): 'track_target (src/target.c)',
    (0x0000, 0x48A5): 'polygon_outline (src/line.c)',
    (0x0000, 0xB425): 'bytekiller_unpack (src/unpack.c)',
    (0x11BC, 0x0000): 'fill_polygon (src/polyfill.c)',
    (0x11BC, 0x01AD): 'polygon_setup (src/polyfill.c)',
    (0x11BC, 0x14D3): 'ground_sort_layers, static in src/cells.c',
    (0x11BC, 0x159C): 'mesh_face_visibility (src/visibility.c)',
    (0x11BC, 0x161B): 'face_reverse_winding (src/visibility.c)',
    (0x11BC, 0x163D): 'face_edge_vectors (src/visibility.c)',
    (0x11BC, 0x168B): 'face_is_hidden (src/facing.c)',
    (0x11BC, 0x175F): 'slope_code, static in src/facing.c',
    (0x14B5, 0x0216): 'lzhuf_unpack (src/unpack.c)',
    (0x15AD, 0x0006): 'sort_draw_list (src/sortlist.c); every routine of this segment is a static function there',
    (0x0000, 0xB187): 'character_models_load (src/characterresources.c), kind=0; MANWOM.CSF',
    (0x0000, 0xB199): 'character_models_load (src/characterresources.c), kind=1; COP.CSF',
    (0x0000, 0xB1AD): 'character_models_load (src/characterresources.c), kind=2; SOL.CSF',
    (0x0000, 0xB1C1): 'part of character_models_load (src/characterresources.c); valid installed CSF streams',
    (0x0000, 0xB1DE): 'face initialization in character_models_load (src/characterresources.c)',
    (0x0000, 0x70FB): 'character_animations_index (src/characterresources.c); concatenated CAF groups',
    (0x0000, 0x712B): 'character_animations_append (src/characterresources.c)',
    (0x0000, 0xAE13): 'character_resources_variant (src/characterresources.c); low byte of 11CD',
    (0x0000, 0x70DF): 'character_resources_load (src/characterresources.c); MANWOM plus COP/SOL CAF/model',
    (0x0000, 0x02B5): 'vehicle_transition / vehicle_exit_state (src/vehicletransition.c); mode=1 BX verified; audio groups adapt to native sound.c',
    (0x0000, 0xB519): 'cutscene_apply_frame (src/cutscene.c); VGA delta to native linear buffer',
    (0x0000, 0xB558): 'cutscene_background (src/cutscene.c); VGA background/palette/key clear',
    (0x0000, 0xB36D): 'cutscene_ega_background (src/cutscene.c); all four planes including copied scratch tail',
    (0x0000, 0xB3BC): 'cutscene_ega_frame (src/cutscene.c); vertical plane runs, B423+1 stride',
    (0x0000, 0xD628): 'ratings_decode (src/ratings.c); transform body native, file read external',
    (0x0000, 0xD5FA): 'ratings_encode (src/ratings.c); transform body native, file write external',
    (0x0000, 0xD64C): 'ratings_stats_save (src/ratings.c)',
    (0x0000, 0xD658): 'ratings_stats_restore (src/ratings.c)',
    (0x0000, 0xD66C): 'ratings_select (src/ratings.c)',
    (0x0000, 0xD67F): 'ratings_insert (src/ratings.c); source-valid counts 1..5',
    (0x0000, 0xD739): 'ratings_update_time (src/ratings.c)',
    (0x0000, 0xD740): 'ratings_clear_stats (src/ratings.c)',
    (0x0000, 0x8B1E): 'sound_group_load (src/sound.c); native real files, host stat metadata',
    (0x0000, 0x8A9E): 'sound_group_select (src/sound.c), mode=1 vehicle samples',
    (0x0000, 0x8ABE): 'sound_group_select (src/sound.c), mode=3 on-foot samples',
    (0x0000, 0x8ADE): 'sound_group_select (src/sound.c), mode=4',
    (0x0000, 0x8AFE): 'sound_group_select (src/sound.c), mode=6',
    (0x0000, 0x89A2): 'sound_request (src/sound.c); native routing/loop metadata, device/AX external',
    (0x0000, 0x89C5): 'part of sound_request (src/sound.c); first 14 of 15 scanned IDs usable',

    (0x0000, 0x48E6): 'menu_display / menu_prepare (src/menu.c); planar setup and native modal navigation; option handlers explicit',
    (0x0000, 0x4A96): 'menu_run (src/menu.c); native shortcuts/wrap/selection/Escape; timing/input and option bodies host',
    (0x5776, 0x02D5): 'menu_highlight (src/menu.c); four-plane save and plane-3 highlight',
    (0x5776, 0x0330): 'menu_unhighlight (src/menu.c); source fifth disabled plane retained',
    (0x0000, 0x4B4A): 'menu_basic_action (src/menu.c); native audio state/close; CMF driver stop/resume external',
    (0x0000, 0x4ED2): 'menu_basic_action (src/menu.c); close saved overlay',
    (0x0000, 0x4EDC): 'menu_basic_action (src/menu.c); yes result and close',
    (0x0000, 0x4EEB): 'menu_basic_action (src/menu.c); no result and close',

    (0x0000, 0xB31C): 'cutscene_ega_sequence (src/cutscene.c); complete EGA frame/repeat/retrace/key loop',
    (0x0000, 0xB210): 'cutscene_play (src/cutscene.c); native EGA/VGA dispatch and movie playback, explicit platform/IO',
    (0x0000, 0xF7AD): 'file_open_existing (src/imageload.c); AX=0 read-only subset only; other flags untranslated',

    (0x14B5, 0x000A): 'cutscene_vga_play (src/cutscene.c); full VGA movie including optional mask, intro image and sound request',
    (0x14B5, 0x018A): 'movie_load_large (src/cutscene.c); 65535+1 chunks and 64 KB segment advance',
    (0x14B5, 0x01C2): 'cutscene_vga_overlay (src/cutscene.c); FE masked text from first ATF plane',
    (0x14B5, 0x0093): 'cutscene_vga_sequence (src/cutscene.c); frame/repeat/retrace/key loop',
    (0x14B5, 0x0115): 'packet normalization inside cutscene_vga_sequence (src/cutscene.c)',
    (0x14B5, 0x012D): 'optional ATF load/decode/overlay in cutscene_vga_play (src/cutscene.c)',
    (0x14B5, 0x01F9): 'ATF prefix conditions in cutscene_ega_play / cutscene_vga_play (src/cutscene.c)',
    (0x0000, 0x9F17): 'image_vga_load (src/cutscene.c); LZHUF pixels, conditional in-place palette conversion',
    (0x0000, 0x9F7C): 'palette location in image_vga_load (src/cutscene.c)',
    (0x0000, 0x9F8B): 'palette conversion in image_vga_load (src/cutscene.c)',

    (0x0000, 0x9D36): 'menu_vga_display / menu_vga_prepare (src/vgamenu.c); VGA setup and native modal navigation',
    (0x0000, 0x9E59): 'menu_vga_run (src/vgamenu.c); XOR highlight, shortcuts, wrap and Escape',
    (0x11BC, 0x29CE): 'screen_text8_vga (src/vgaui.c); cell/pixel coordinates, loaded font, AX start address',
    (0x11BC, 0x29A9): 'screen_vga_fill (src/vgaui.c)',
    (0x11BC, 0x2A65): 'screen_vga_line_to (src/vgaui.c); reverse endpoint iteration and source error bias',
    (0x11BC, 0x2B1D): 'menu_vga_highlight (src/vgaui.c); XOR A5, nine rows',
    (0x11BC, 0x2B48): 'scene_vga_overlay_save (src/vgaui.c); restore previous single background before save',
    (0x11BC, 0x2B91): 'scene_vga_overlay_restore (src/vgaui.c)',
    (0x11BC, 0x2BCC): 'textbox_vga_draw (src/vgaui.c); 5A4E immediate, otherwise input-only busy polls',
    (0x11BC, 0x2C58): 'textbox_vga_base (src/vgaui.c); scaled cell window/background/bevel',
    (0x11BC, 0x2CBE): 'textbox_vga_border (src/vgaui.c); six source bevel layers',
    (0x11BC, 0x2D53): 'vga_border_layer, static in src/vgaui.c',

    (0x0000, 0x089E): 'gameplay_check_losses (src/losses.c); native movie/models/promotion; streaming/camera/network explicit',
    (0x0000, 0xA28A): 'companion_promote_record (src/losses.c); forward 52-byte copy and source flag transfer',
    (0x0000, 0x8C45): 'sound_stop_and_wait (src/sound.c); clear AA94, wait through completion service',
    (0x0000, 0x9132): 'image_vga_blit_raw (src/vgaui.c); absolute pixel source offset 16 retained',
    (0x0000, 0xEE9F): 'image_vga_protection_load (src/vgaui.c); image only, original security challenge retained',

}

NOTES = {
    (0x0000, 0x0407): """INT 0 handler: adds 2 to the return address (skips the DIV) and returns. The 3D code
overflows its divides constantly and relies on this.""",
    (0x0000, 0x7EF0): """in: the record of what goes off (stack argument). Its strength (low byte of the
last word) is the damage; four times that is the radius. Everything of the frame list in
the radius: figures are killed; ordinary objects lose the damage from their strength
(255 = untouched) and throw debris when the result is negative as a signed byte; cars,
pumps and special objects are queued to go off themselves and removed (cell record last
word = FFFF through the source list at DS:72DC). Forces a rebuild of the visible list.""",
    (0x0000, 0x7B28): """in: SI = record, BX = mesh number. Every face of the mesh becomes a piece of debris
in the debris segment (file segment 531E): draw records at 0000, 20-byte motion records at
0960, one-face mesh headers at 1900, face data at 2580, a copy of the vertices at 3580.""",
    (0x0000, 0xCE12): """When the lists have just been rebuilt (DS:5CD8), redraws the picture of the
surroundings seen from above on video page 6000: clears it, then draws the ground list in
map view (b_map_view) from a height of 12000. The ground list is parked meanwhile.""",
    (0x0000, 0x0F32): """Sets the bit mask and set/reset, and for sloped lines also the function and write
mode, but never the plane mask: a line is drawn in whatever planes the last routine left
enabled (only plane 3 after the horizon picture).
in: AX = x, BX = y. Draws from the current position (DS:122E, 1230) to (x, y) in
fill_colour and makes (x, y) current. Vertical lines include both ends, horizontal ones
leave out the larger x, sloped ones leave out their lower end. Lines lying exactly on a
view-window edge are not drawn.""",
    (0x0000, 0x2D2A): """Draw-order control from mesh header word 6: 0 = keep file order; N below the face
count = pivot on face N-1: if it is hidden, the face groups are written out in reverse.
A group is a face whose facing-table entry is 0 or FF plus the detail faces after it.
The branch at 2DA5 (sort groups by depth, for a negative order) cannot be reached:
the unsigned check at 2D34 returns first for any mesh with fewer than 32768 faces.""",
    (0x0000, 0x06FF): """Full draw pass: ground list, danger sample and figure placement, then object list
and target ordering. A temporary blank/noisy view replaces both lists when obscured.""",
    (0x0000, 0x271E): """in: SI = first 12-byte record, CX = count. Record: x, y, z, flags, id, extra.
Skips a record if extra is negative, if flag 0040 is set, or for 0024 records while the
player is on foot. Flag 0008 is written back when the object is found to be off screen.
One-face meshes go to draw_flat_mesh, everything else through mesh_prepare, the
transform (object_translate_only for flag 4000) and draw_object.""",
    (0x0000, 0x3B88): """Rebuilds the visible-object list (DS:5F80, count visible_object_count) when the
player has entered another cell or turned into another of 8 heading sectors; otherwise
returns at once. May load sectors from disk first (11BC:0950). From 3C18: walks the
cells named by the view table for the heading sector (DS:74B8) in the 24x24 cell window
(seg_cells), copying each cell list with x += cell west edge, z += cell south edge,
relative to the player cell; then builds the ground list (build_ground_list).""",
    (0x0000, 0x3E8F): """One coarse ground cell: each 14-byte placement (i32 x, y, z; mesh) becomes a 12-byte
ground record with x - player column * 1024 and (player row + 1) * 1024 - z.""",
    (0x0000, 0x2BFF): """in: BX = mesh number. Copies the mesh into the work buffer at DS:50B2 (stored meshes
start with a size word), adds 50B2 to header words 0, 3, 4, 5 and 7, and copies the
vertices to the vertex buffer. Source by record flags: 0100 alone = debris tables;
4000 without 0020 = model record BX/2 (DS:0B30, 22 bytes each, mesh offset at +14h) in
seg_models; 0020 with 0004 or 4000 = offset BX in seg_models; otherwise building number
through DS:91DA in seg_objects, or ground number through DS:92DA (+ DS:727E) in seg_ground.""",
    (0x0000, 0x2921): """Camera = player position, heading = body heading + head turn (player words 3 and 4).
In the map view (b_map_view) the camera is at the origin. Camera mode 1 is never set by
the game; that branch also destroys SI.""",
    (0x0000, 0xE83E): """in: BX = mesh with one face (ground polygons). Own short pipeline: gather the face's
vertices, transform, near clip, project (flat_project pins overflowing x to +32000 /
-32256), window clip, fill and optional outline.""",
    (0x0000, 0x1B7D): 'in: AX = x, CX = z, DX = angle (0..511). out: AX = x*cos - z*sin, CX = x*sin + z*cos.',
    (0x0000, 0x1F50): 'Fills DS:4A6D with the 120 two-colour dither pairs (a = 0..14, b = a+1..15).',
    (0x0000, 0x29C4): """Applies the object quarter turn (obj_quarter_turns), adds the object position, subtracts
the camera position and rotates by the camera heading.""",
    (0x0000, 0x37E3): """INT 9 handler. key_down[scancode] (DS:5BD9+) is FF while a key is held; typed characters
go through the tables at DS:5A6A / 5AEA into a ring buffer at DS:5B70.""",
    (0x0000, 0x46AC): """Projects the 3D vertex buffer to the screen: sx = x*256/(z+40) + centre_x, same for y.
Temporarily installs projection_divide_handler. Returns carry set if the object is off screen.""",
    (0x0000, 0x481A): """INT 0 handler used only while projecting: skips the IDIV and returns 7E6F for a
non-negative dividend, 8190 for a negative one (saturation).""",
    (0x0000, 0xB425): 'cdecl (src_off, src_seg, dst_off, dst_seg, packed_len). Returns AX = 0 if the checksum matches.',
    (0x0000, 0xEB9A): """Copy-protection symbol picker: left/right toggle the column, up/down move one row,
Enter confirms. 24 candidates, index = row*2 + column.""",
    (0x11BC, 0x0000): """in: SI = address of the face's vertex count, colour in fill_colour. Builds two edge
chains from the topmost point (polygon_setup), walks them one scanline at a time into a
span list at DS:4738, then fills the spans through the EGA registers: solid colour
(set/reset) or a two-colour checkerboard (write mode 2, masks 55/AA swapped per row).""",
    (0x11BC, 0x097E): """Loads the 24 x 24 cell window around the player: window origin = the coarse cell
(8 cells) west/north of the one the player is in, never below 0; the map is 192 x 128
cells. Reloaded when the player comes within 6 cells of the window edge.""",
    (0x11BC, 0x0AC6): """Negates the z of every vertex of every ground mesh just loaded from a .BIG file:
the files store z south, the game works with z north.""",
    (0x11BC, 0x1292): """Per cell record: last word low byte = strength of the object (table DS:5EFA by
LA.DEF number), then note_special_object, then the LA.DEF number in word +8 is replaced
by the slot the mesh is loaded into (list of loaded LA.DEF numbers at DS:5DC0, count
DS:72B4).""",
    (0x11BC, 0x1386): """in: AX = LA.DEF number, ES:SI = cell record. Cars (10 car2q, 100 vanq, 74 pckupq)
get a colour variant 0-3 from their position in the high byte of the last word and a
14-byte entry in the vehicle list (far pointer DS:72B6; x, z as 32-bit world values with
z = cell z + 1024 - z_in_cell). Special locations (31 gunq, 24 drugq, 89 sportq, 113 ArmoryQ) get an
entry of type 1-4 in the list at DS:5CE4.""",
    (0x11BC, 0x1117): """After the cells are loaded: prepares every cell record, then copies each LA.DEF
mesh in use into seg_objects in slot order (offsets to DS:91DA), stores the highest
point of each in mesh_heights (DS:75EC), and loads LA.BMP.""",
    (0x11BC, 0x2251): """Fills the 192 x 192 byte collision map (segment DS:[91B2], 16 units per byte) for
the 3 x 3 cells around the player: each object stamps its LA.BMP rectangle with its
number + 1. Map row = 64 * (cell row + 1) - (z + 8) / 16, i.e. rows run south.""",
    (0x11BC, 0x1FCC): """Collision test against the map; where a byte is set, the object bitmap from LA.BMP
decides: bit index = (dz + centre_z) * w + (dx + centre_x) with dx, dz the offset from
the object in 16-unit steps, z north. So bitmap rows run from south to north.""",
    (0x11BC, 0x159C): """Per face: writes a hidden flag into the buffer at [p_face_hidden_flags]. The per-face
table (mesh header word 5) says how: 0 = test this face, N = same as face N-1,
FF = two-sided (when it faces away its vertex order is reversed instead of hiding it).""",
    (0x11BC, 0x168B): 'in: AX,BX and CX,DX = two screen-space edge vectors. out: AL = 1 if the face is hidden.',
    (0x15AD, 0x0006): """Culls and orders the object records at DS:1576 (count draw_list_count). One 16-byte
node per visible record at DS:C552 (next, centre x, centre depth, left x, depth, right x,
depth, record). Buildings get their screen extent from the four footprint corners in
the mesh (header word 7), cut-outs 24 units either side. Then: bubble sort by centre
depth, drop records hidden behind a nearer building (not behind trees/palms, by mesh
name), fix the order of overlapping pairs, write out farthest first below DS:DB26.
out: SI = first record; draw_list_count = records kept.""",
    (0x14B5, 0x0216): 'in: DS:SI = packed data (u16 size prefix), ES:DI = destination, CX = packed length.',
}

# DS (5C27) variables: offset -> name
VARS = {
    0xE414: 'text_row',
    0xE412: 'text_column',
    0xE40F: 'text_colour',
    0xE3EE: 'companion_z',
    0xE3EC: 'companion_x',
    0xE172: 'number_digits',
    0xE16A: 'number_colour',
    0xDE54: 'opponent_z',
    0xDE52: 'opponent_x',
    0xB666: 'point_z',
    0xB662: 'point_x',
    0xADCF: 'facility_screen',
    0x9A72: 'screen_stride',
    0x91C6: 'work_buffer_seg',
    0x91C0: 'load_buffer',
    0x91BE: 'file_buffer_seg',
    0x91BC: 'file_buffer',
    0x9154: 'grid_cell_z',
    0x9152: 'grid_cell_x',
    0x9148: 'stamp_h',
    0x9146: 'stamp_w',
    0x9144: 'stamp_half_h',
    0x9142: 'stamp_half_w',
    0x913E: 'stamp_value',
    0x9138: 'stamp_z',
    0x9136: 'stamp_x',
    0x912A: 'grid_z',
    0x9128: 'grid_x',
    0x8510: 'unpack_dst_seg',
    0x850E: 'unpack_src_seg',
    0x7C92: 'pointer_y',
    0x7C90: 'pointer_x',
    0x784E: 'menu_item',
    0x775A: 'box_y',
    0x7758: 'box_x',
    0x5F72: 'fuel',
    0x5BD4: 'keybuf_count',
    0x5B6E: 'keybuf_read',
    0x4188: 'sine_table',
    0x1232: 'probe_z',
    0x122C: 'page_drawn',
    0x122A: 'page_shown',
    0x11C6: 'view_height',
    0x11A4: 'sight_y',
    0x11A2: 'sight_x',
    0x1190: 'weapon_slot',
    0x1172: 'screen_noise',
    0x1154: 'companion_active',
    0x1153: 'opponent_active',
    0x114F: 'zoom_2',
    0x114D: 'zoom_1',
    0x0418: 'target_record',
    0x03F0: 'difficulty',
    0x0345: 'practice_mode',
    0x01DE: 'link_game',
    0x00BB: 'ground_pass',
    0x03A0: 'player',
    0x03F4: 'view_left',
    0x03F6: 'view_top',
    0x03F8: 'view_right',
    0x03FA: 'view_bottom',
    0x0408: 'view_centre_x',
    0x040A: 'view_centre_y',
    0x4B70: 'outcode_union',
    0x4B7E: 'clip_next_ref',
    0x4B84: 'p_clip_count',
    0x4B86: 'vertex_buffer_end',
    0x76DE: 'any_point_inside',
    0x3CDC: 'vertex_buffer_ptr',
    0x40DE: 'vertex_buffer_2d_ptr',
    0x40E0: 'face_hidden_ptr',
    0x4A6D: 'dither_pairs',
    0x4688: 'poly_count',
    0x468C: 'fill_colour',
    0x468D: 'outline_colour',
    0x4734: 'span_count',
    0x4A58: 'poly_top_y',
    0x4B6C: 'dither_pair',
    0x1234: 'draw_page',
    0x122E: 'pen_x',
    0x1230: 'pen_y',
    0x50B1: 'faces_drawn',
    0x7756: 'p_colour_table',
    0x4B6E: 'any_vert_behind',
    0x50AC: 'draw_count',
    0x50AF: 'obj_quarter_turns',
    0x57BA: 'verts_behind',
    0x57BC: 'cam_heading',
    0x57BE: 'cam_x',
    0x57C0: 'cam_y',
    0x57C2: 'cam_z',
    0x57C6: 'obj_flags',
    0x57CC: 'obj_x',
    0x57CE: 'obj_y',
    0x57D0: 'obj_z',
    0x57DA: 'p_order_buffer',
    0x59DC: 'order_group_count',
    0x59DE: 'draw_record',
    0x03A6: 'p_removed_write',
    0x1178: 'debris_piece_counter',
    0x4164: 'matrix',
    0x96F4: 'p_blast_queue',
    0x96F6: 'blast_queue',
    0x97B6: 'blast_queue_count',
    0x9948: 'p_random',
    0xEA42: 'random_state',
    0x0253: 'pickups',
    0x0B08: 'timed_object',
    0x0DF0: 'figure_records',
    0x10F0: 'guided_projectiles',
    0x117A: 'debris_count',
    0x119A: 'figure_count',
    0x11A0: 'guided_count',
    0x5CD8: 'lists_rebuilt',
    0x9156: 'p_list_write',
    0xB520: 'projectiles',
    0x1533: 'ground_colour',
    0x154D: 'sun_column',
    0x91B6: 'seg_horizon',
    0x5DC0: 'loaded_defs',
    0x5EE6: 'ground_layer_by_colour',
    0x5EFA: 'def_strength',
    0x72B0: 'vehicle_count',
    0x72B2: 'shop_count',
    0x72B4: 'loaded_def_count',
    0x91B2: 'seg_collision',
    0x04C4: 'heading_sector_x2',
    0x04C6: 'extra_count',
    0x0F70: 'removed_objects',
    0x5EDF: 'walk_column',
    0x5EE1: 'walk_row',
    0x7242: 'visible_cell',
    0x7272: 'window_col',
    0x7274: 'window_row',
    0x72DA: 'p_record_source',
    0x74B8: 'view_tables',
    0x75EC: 'mesh_heights',
    0xABCA: 'detail_level',
    0xC550: 'sort_head',
    0x91D4: 'seg_cells',
    0x04BA: 'vehicle',
    0x11CA: 'camera_mode',
    0x50B0: 'force_redo',
    0x57C4: 'record_id',
    0x59E4: 'record_extra',
    0x72CA: 'player_vehicle_mesh',
    0x727E: 'ground_mesh_base',
    0x7AB6: 'map_view',
    0x91CE: 'seg_models',
    0x91D0: 'seg_objects',
    0x91D2: 'seg_ground',
    0x91D8: 'ground_count',
    0x96DC: 'seg_debris',
    0x01FE: 'draw_list',
    0xE3D2: 'guided_mesh',
    0xE5FC: 'flat_any_inside',
    0x59E2: 'pipeline_stage',
    0x118E: 'weapon',
    0xB64E: 'target_count',
    0x5BD8: 'last_scancode',
    0x5BD9: 'key_down',
    0x7240: 'visible_count',
    0x91B0: 'seg_la_bmp',
    0x91C4: 'work_buffer',
    0xADDC: 'seg_screen',
}

FUNCS.update({(0x0000, 0x48E6):'menu_display', (0x0000, 0x4A96):'menu_run',
              (0x5776, 0x02D5):'menu_highlight', (0x5776, 0x0330):'menu_unhighlight'})

FUNCS.update({(0x0000, 0xB210):'cutscene_play_dispatch'})

# Verified nearby interactions and player-control composition (2026-11-17).
C_VERSIONS.update({
    (0x0000, 0x884B): 'pickup_interaction (src/pickup.c); inventory panel service',
    (0x0000, 0x889D): 'pickup_query_state (src/pickup.c); 20-record entry',
    (0x0000, 0x88A3): 'pickup_query_state (src/pickup.c); per-record BP reset',
    (0x0000, 0x8922): 'pickup_check_active (src/pickup.c); native HUD dismissal',
    (0x0000, 0x74CE): 'shop_interaction (src/shop.c); purchase panel service',
    (0x0000, 0x75B5): 'shop_try_record_state (src/shop.c); AX/BX/SI/ZF preserved',
    (0x0000, 0x75FD): 'shop_check_active (src/shop.c); native HUD/page cleanup',
    (0x0000, 0x764B): 'shop_distance (src/shop.c)',
    (0x0000, 0xC5AF): 'shop_fallback_records (src/shop.c); DIV fault semantics',
    (0x11BC, 0x1FCC): 'player_collision_test (src/playercollision.c); bitmaps/rollback/sound',
    (0x0000, 0xD265): 'travel_clear_arrival_native (src/playercollision.c + travel.c); cell streaming external',
    (0x0000, 0x400E): 'vehicle_interaction / vehicle_interaction_native (src/vehicleinteraction.c)',
    (0x0000, 0x4177): 'vehicle_initial_fuel (src/vehicleinteraction.c)',
    (0x0000, 0x421B): 'vehicle_remove_parked (src/vehicleinteraction.c); byte-copy count retained',
    (0x0000, 0x4248): 'vehicle_find_parked (src/vehicleinteraction.c)',
    (0x0000, 0x434E): 'vehicle_park (src/vehicleinteraction.c); single-player only',
    (0x0000, 0x4586): 'map_note_removed (src/blast.c); serial notification excluded',
    (0x0000, 0x0255): 'player_control_step (src/playerdispatch.c); native parking/transitions/collision; stream service',
    (0x0000, 0x6386): 'player_hit_native_registers / player_hit_native_state (src/playerdamage.c); AX/BX verified',
})
FUNCS.update({(0x0000, 0x400E):'vehicle_interaction', (0x0000, 0x434E):'vehicle_park',
              (0x0000, 0x4248):'vehicle_find_parked', (0x0000, 0x421B):'vehicle_remove_parked',
              (0x0000, 0x4177):'vehicle_initial_fuel', (0x0000, 0x0255):'player_control_step',
              (0x0000, 0x884B):'pickup_interaction', (0x0000, 0x889D):'pickup_query',
              (0x0000, 0x8922):'pickup_check_active', (0x0000, 0x74CE):'shop_interaction',
              (0x0000, 0x75B5):'shop_try_record', (0x0000, 0x75FD):'shop_check_active',
              (0x0000, 0x764B):'shop_distance', (0x0000, 0xC5AF):'shop_fallback_records'})

C_VERSIONS.update({
    (0x0000, 0x531C): 'pickup_inventory_panel / pickup_menu_text (src/pickupmenu.c); native planar menu + actual HUD IO',
    (0x0000, 0x5397): 'pickup_take_selected (src/pickupmenu.c); source nonzero-index ordering retained',
    (0x0000, 0x5384): 'pickup_menu_service (src/pickupmenu.c); INC-entry handler range 5384..5397',
    (0x0000, 0x8451): 'shop_item_hit (src/shop.c); uncompressed first-plane mask',
    (0x0000, 0x893F): 'shop_record_visit (src/shop.c); six-slot pointer wrap, uncapped source count',
    (0x0000, 0x8962): 'shop_was_visited (src/shop.c); first ten bytes only',
    (0x0000, 0x93CA): 'inventory_refresh_equipment (src/equipment.c); flags/components/dynamic equipment menu',
    (0x0000, 0x943E): 'inventory_combine_components (src/equipment.c); native inventory removal',
    (0x0000, 0x946C): 'inventory_equipment_menu (src/equipment.c); actual far text and action tables',
    (0x0000, 0x9407): 'inventory_count_required (src/equipment.c); nineteen slots, ignores quantity',
    (0x11BC, 0x157C): 'mesh_reverse_all_faces (src/visibility.c); now 256 synthetic point/line/polygon comparisons',
})
FUNCS.update({(0x0000, 0x531C):'pickup_inventory_panel', (0x0000, 0x893F):'shop_record_visit',
              (0x0000, 0x8962):'shop_was_visited', (0x0000, 0x8451):'shop_item_hit',
              (0x0000, 0x93CA):'inventory_refresh_equipment', (0x0000, 0x943E):'inventory_combine_components',
              (0x0000, 0x946C):'inventory_equipment_menu', (0x0000, 0x9407):'inventory_count_required'})

C_VERSIONS.update({
    (0x0000, 0x855A): 'shop_add_regular_item (src/shopactions.c); excludes 23/26 weapon-upgrade menu paths',
    (0x0000, 0x865C): 'shop_check_permit (src/shopactions.c); native EGA/VGA notice',
    (0x0000, 0x868C): 'shop_pay_item (src/shopactions.c); strict funds comparison + native EGA/VGA notices',
    (0x0000, 0x86EA): 'shop_check_capacity (src/shopactions.c); structured return for DOS stack unwind',
})
FUNCS.update({(0x0000, 0x855A):'shop_add_item', (0x0000, 0x865C):'shop_check_permit',
              (0x0000, 0x868C):'shop_pay_item', (0x0000, 0x86EA):'shop_check_capacity'})

C_VERSIONS.update({
    (0x0000, 0x56B2): 'inventory_choose_weapon (src/weaponpicker.c); native EGA/VGA picker, structured unwind outcomes',
    (0x0000, 0x56B7): 'inventory_weapon_menu_text (src/weaponpicker.c); far title and native inventory lines',
    (0x0000, 0x5737): 'inventory_weapon_menu_choice (src/weaponpicker.c); ID-to-slot mapping',
    (0x0000, 0x5724): 'picker_service (src/weaponpicker.c); INC-entry handler range 5724..5737',
    (0x0000, 0x855A): 'shop_add_item (src/shopactions.c); regular purchases and both weapon upgrades; structured caller-unwind result',
    (0x0000, 0x1492): 'screen_draw_mask16 (src/mapscreen.c) + screen_draw_mask16_vga (src/vgapointer.c)',
    (0x0000, 0x1517): 'screen_restore_mask16_vga (src/vgapointer.c); fixed 16-row save-under',
    (0x0000, 0x153A): 'screen_draw_mask16_vga (src/vgapointer.c); AX=FF00, zero sentinel, word-boundary semantics',
    (0x0000, 0x6128): 'map_draw_pointer_display (src/vgapointer.c); native planar/VGA dispatch',
    (0x0000, 0x830F): 'map_pointer_step_display (src/vgapointer.c); native planar/VGA movement',
})
FUNCS.update({(0x0000, 0x56B2):'inventory_choose_weapon', (0x0000, 0x5737):'inventory_weapon_menu_choice',
              (0x0000, 0x1517):'screen_restore_mask16_vga', (0x0000, 0x153A):'screen_draw_mask16_vga'})

C_VERSIONS.update({
    (0x0000, 0x873D): 'shop_check_theft (src/shopalarm.c); native random probability and alarm',
    (0x0000, 0x874C): 'shop_alarm (src/shopalarm.c); native resources, EGA/VGA figure spawning, sound events',
    (0x0000, 0x87E9): 'shop_randomize_balances (src/shopalarm.c)',
    (0x0000, 0x5CFA): 'figure_map_sample / figure_map_sample_display (src/figure.c); explicit planar/indexed semantics',
    (0x0000, 0xA46F): 'figure_spawn_grid / figure_spawn_grid_display (src/figure.c)',
    (0x0000, 0xAD00): 'figure_spawn / figure_spawn_display (src/figurespawn.c), civilian=0; native planar/VGA sampling',
    (0x5776, 0x0295): 'scene_overlay_restore_all (src/textbox.c); EGA stack plus VGA saved window',
    (0x5776, 0x02AF): 'scene_overlay_reset (src/textbox.c)',
    (0x0000, 0x83A6): 'shop_confirm_item (src/shopconfirm.c); real file/cache masks, native actions; 82C4 exit body separate',
    (0x0000, 0x84B5): 'shop_option_action (src/shopconfirm.c), Continue',
    (0x0000, 0x84BF): 'shop_option_action (src/shopconfirm.c), Buy',
    (0x0000, 0x850E): 'shop_option_action (src/shopconfirm.c), Steal',
})
FUNCS.update({(0x0000, 0x873D):'shop_check_theft', (0x0000, 0x874C):'shop_alarm',
              (0x0000, 0x87E9):'shop_randomize_balances', (0x0000, 0x83A6):'shop_confirm_item',
              (0x0000, 0x84B5):'shop_option_continue', (0x0000, 0x84BF):'shop_option_buy',
              (0x0000, 0x850E):'shop_option_steal', (0x5776, 0x0295):'scene_overlay_restore_all',
              (0x5776, 0x02AF):'scene_overlay_reset'})

FUNCS.update({
    (0, 0x0B97):'draw_view_fill', (0, 0x0C7D):'select_visible_page',
    (0, 0x16A9):'horizon_load', (0, 0x16BE):'draw_horizon',
    (0, 0x17E6):'scene_present', (0, 0x1840):'scene_obscured',
    (0, 0x3A6E):'joystick_apply', (0, 0x5C40):'figure_feedback_step',
    (0, 0x0641):'player_pre_draw_collision',
    (0, 0x06EF):'scene_update_world', (0, 0xA54E):'armed_figures_move',
    (0, 0xAB77):'civilians_move', (0, 0xABF1):'armed_figure_fire',
    (0, 0xAEE9):'civilian_prepare_move', (0x14A7, 0x000C):'civilian_steer',
    (0, 0x813E):'shop_screen', (0, 0x82C4):'shop_screen_exit',
})
FUNCS.update({
    (0, 0x0A76):'csm_transform_main_block',
    (0, 0x4CDE):'csm_select_for_delete',
    (0, 0x4CE5):'csm_select_for_load',
    (0, 0x59A6):'initialize_new_or_loaded_position',
    (0, 0x9B40):'main_menu_load_game',
})
NOTES.update({
    (0, 0x0A76): 'AX=0 prepares the main CSM block at DS:0252. Nonzero AX decodes it and restores runtime pointers and window state.',
    (0, 0x4CE5): 'Enumerate CSM files matching the main block plus 256 far-memory bytes, then display a file picker.',
    (0, 0x59A6): 'DS:1143 distinguishes a loaded position from a new game. Both paths normalize and validate arrival.',
})
FUNCS.update({
    (0, 0x51C0): 'inventory_category_menu',
    (0, 0x51D8): 'player_menu_inventory_categories',
    (0, 0x5F06): 'damage_panel',
    (0, 0x6149): 'reload_numbers_and_pointer',
    (0, 0x65D0): 'damage_panel_treat_selected',
    (0, 0x8CB0): 'facility_screen',
    (0, 0x8D21): 'hospital_screen',
    (0, 0x8D6B): 'bank_screen',
    (0, 0x8DBB): 'bank_withdraw',
    (0, 0x8DD3): 'bank_steal_action',
    (0, 0x8DDF): 'bank_steal_cash',
    (0, 0x8DFF): 'facility_confirm',
    (0, 0x8E32): 'facility_confirm_yes',
    (0, 0x8E40): 'facility_confirm_no',
    (0, 0x8E59): 'range_screen',
    (0, 0x8EA5): 'range_draw_target',
    (0, 0x8F1C): 'range_restore_target',
    (0, 0x8F78): 'range_aim_and_score',
    (0, 0x9023): 'range_intermission',
    (0, 0x9032): 'range_format_averages',
    (0, 0x90B0): 'range_display_results',
    (0, 0xC45C): 'phonebook_screen',
    (0, 0xC557): 'phonebook_scroll_row',
    (0, 0xC571): 'set_crtc_display_start',
    (0, 0xC588): 'phonebook_draw_entries',
    (0, 0xC5DA): 'phonebook_draw_location_records',
    (0, 0xC72F): 'phonebook_load_panels',
    (0, 0x9B03): 'main_menu_apply_practice_mode',
    (0, 0x9B57): 'main_menu_ratings',
    (0, 0xD300): 'ratings_screen',
    (0, 0xD4C3): 'ratings_draw_stats',
    (0, 0xD5B1): 'ratings_commit_session',
    (0, 0xDF3A): 'ratings_prompt_name',
    (0, 0x91EA): 'credits_scroll',
})
NOTES.update({
    (0, 0x51C0): 'Read-only category viewer. An item panel returns carry to reopen the category menu.',
    (0, 0x8CB0): 'BX 4 through 6 select bank, range, or hospital. The two EGA/VGA resource tables precede the three-entry dispatch.',
    (0, 0x65D0): 'Treatment steps the world before healing each point. The hospital flag halves the base wait.',
    (0, 0x8F78): 'AX is elapsed ticks and BX is the penalty. A shot must be within four pixels in both axes. Timeout penalty is 10.',
    (0, 0xC45C): 'P opens mode 0Eh. Lists resident shops followed by four location records for the current region.',
    (0, 0xC557): 'Advance the CRTC display start by plus or minus 80 bytes per retrace, 86 times.',
    (0, 0xD300): '1-5 select ranked records, Space restores the current record. N opens the name editor during play.',
    (0, 0xDF3A): 'Accepts up to ten characters. The caller copies the typed buffer even when the editor returns carry on Escape.',
})
VARS.update({
    0x115B: 'bank_withdrawn',
    0xA87A: 'hospital_treatment',
    0xA87B: 'facility_confirmed',
    0xA917: 'bank_alarm_context',
    0xA958: 'range_target_index_times_two',
    0xA95A: 'range_target_video_offset',
    0xA95C: 'range_average_ticks',
    0xA95E: 'range_average_penalty',
    0xA960: 'range_sum_ticks',
    0xA962: 'range_sum_penalty',
    0xA964: 'range_timer',
    0xA966: 'range_previous_target',
    0xA9A8: 'range_result_class',
    0xDEE8: 'phonebook_scroll_row_index',
    0xDEE9: 'phonebook_scroll_limit',
    0xDF42: 'phonebook_display_start',
})
C_VERSIONS.update({
    (0, 0x06C3):'draw_frame_background (src/background.c); alternate-camera fill and obscured-view gates',
    (0, 0x0641):'player_pre_draw_collision (src/playercollision.c); warning or ejection; high-speed branch not in fixtures',
    (0, 0x06EF):'scene_update_world (src/figurewalk.c); CAF, guidance, both figure loops and debris',
    (0, 0xA54E):'armed_figures_move (src/figurewalk.c)',
    (0, 0xAB77):'civilians_move (src/figurewalk.c)',
    (0, 0xABF1):'armed_figure_fire (src/figurewalk.c)',
    (0, 0xAEE9):'civilian_prepare_move (src/figurewalk.c)',
    (0x14A7, 0x000C):'civilian_steer (src/figurewalk.c)',
    (0, 0x3B88):'update_visible_cells (src/cellwindow.c); native sector reload, object lists and collision',
    (0x11BC, 0x097E):'load_window (src/cellwindow.c); derive window origin and thresholds',
    (0x11BC, 0x0A16):'load_window_ground_and_cells (src/windowground.c); installed BIG and SCT files',
    (0x11BC, 0x0AE7):'split_axis (src/windowground.c)',
    (0x11BC, 0x0BE0):'pack_quadrants (src/windowground.c)',
    (0x11BC, 0x0D8A):'ground_quadrant (src/windowground.c)',
    (0x11BC, 0x0E2D):'ground_list (src/windowground.c)',
    (0x11BC, 0x0EA8):'resident_slot (src/windowground.c)',
    (0x11BC, 0x0FD1):'street_quadrant (src/windowground.c)',
    (0x11BC, 0x0FEA):'read_sector (src/windowground.c)',
    (0x11BC, 0x1117):'load_window_objects (src/windowobjects.c)',
    (0x11BC, 0x1292):'prepare_records (src/windowobjects.c)',
    (0x11BC, 0x1386):'special_object (src/windowobjects.c)',
    (0, 0x7ABE):'refresh_meshes (src/cellwindow.c); resident signed minimum Y',
    (0, 0x7B00):'append_mesh (src/cellwindow.c); installed SPN resources',
    (0, 0x06FF):'draw_scene (src/scenedraw.c); full ground/object stages and interrupted-vision effect',
    (0, 0x0B97):'draw_view_fill (src/background.c)',
    (0, 0x17E6):'scene_present (src/scenepresent.c); retrace and BIOS page operation use host',
    (0, 0x1840):'scene_obscured (src/scenedraw.c); blank/noise effect and host retrace waits',
    (0, 0x3A6E):'joystick_apply (src/joystick.c); source analog pulse counts provided by host',
    (0, 0x5C40):'figure_feedback_step (src/figure.c); six EGA deltas and hold timeout',
    (0, 0x813E):'shop_screen (src/shopscreen.c); four full shops, inventory category is a service',
    (0, 0x82C4):'shop_screen_exit (src/shopscreen.c); restore resources, HUD and display',
    (0, 0xA3D7):'sort_targets_by_depth (src/scenedraw.c); stable signed depth and swap slot',
    (0, 0xB3E4):'cutscene_ega_runs (src/cutscene.c); shared cinematic/CAF runs',
})

# the main loop (src/frame.c, 2026-11-19)
FUNCS.update({
    (0, 0x0155): 'main_loop',
    (0, 0x05A2): 'frame_input_check',
    (0, 0x0A4F): 'border_colour',
    (0, 0x51AA): 'player_menu',
    (0, 0xDD0A): 'tell_sarah_menu',
    (0, 0x7AB6): 'palette_load_game',
    (0, 0x0BE8): 'palette_load',
    (0, 0xCA46): 'map_key',
})
NOTES.update({
    (0, 0x0155): 'One frame per pass; jumps back to itself until DS:1156 or DS:1159 is set. A link game takes the 151B path first.',
    (0, 0x05A2): 'Skipped while a warning (DS:0200) or the reload overlay (DS:8096) is up. M, P, Alt+1/2/3, Q, F10, Esc.',
    (0, 0x0A4F): 'Border (attribute register 11h) := palette entry BL of DS:1510.',
    (0, 0x51AA): 'F10: PLAYER MENU (text 0x08CC, actions 0x7968).',
    (0, 0xDD0A): 'Q while playing the actor at 0x04D4: "Tell Sarah to..." (text 0x06E1, actions 0xE3F0).',
    (0, 0x0BE8): 'DX = 16-byte table; writes attribute registers 0-15 through port 3C0.',
    (0, 0xCA46): 'Shows the unfinished-fast-travel message (0x0625) when DS:E1F2 is set. M local map, Alt+M area map, '
                 'Ctrl+M restores the info panel area; F fast-travels (refused in a car or in battle), H sets homing.',
})
C_VERSIONS.update({
    (0, 0x0155): 'game_frame (src/frame.c); single-player path; link play (151B) is not translated',
    (0, 0x05A2): 'frame_input_check (src/frame.c); the phone book (C466) is a host call',
    (0, 0x0A4F): 'border_colour (src/frame.c); EV_BORDER event, the host sets the border register',
    (0, 0x51AA): 'helper player_menu, inside src/frame.c (frame_input_check)',
    (0, 0xDD0A): 'helper tell_sarah_menu, inside src/frame.c (frame_input_check)',
})

# the M key's map screen (src/mapkey.c, 2026-11-19)
FUNCS.update({
    (0, 0x3732): 'keyboard_flush',
    (0, 0xCDAA): 'map_restore_info_panel',
})
NOTES.update({
    (0, 0x3732): 'Clears the key table and drains the keyboard buffer, repeating until the table stays clear.',
    (0, 0xCDAA): 'Ctrl+M on foot, normal camera: clear the info panel, copy 8x64 bytes at 0x11B7 to the other two pages.',
})
C_VERSIONS.update({
    (0, 0xCA46): 'map_key (src/frame.c) and map_screen (src/mapkey.c); fast travel is travel_run_native_simulation',
    (0, 0x3732): 'keyboard_flush (src/mapkey.c)',
    (0, 0xCDAA): 'helper restore_info_panel, inside src/mapkey.c (map_screen)',
})

# the P key's phone book (src/phonebook.c, 2026-11-19)
FUNCS.update({
    (0, 0xFA4B): 'string_copy',
    (0, 0xFA72): 'string_length',
    (0, 0xF604): 'number_format',
    (0, 0xF86A): 'number_divide_step',
    (0, 0x0BE5): 'bios_video',
})
NOTES.update({
    (0, 0xFA4B): 'Copies the string at DS:SI to ES:DI with its NUL; DI is left on the NUL, SI and CX kept.',
    (0, 0xF604): 'AX in base BL (digits 0-9 then A-Z) at DS:SI, no NUL; SI advanced. Nothing for BL < 2.',
    (0, 0x0BE5): 'INT 10h; RET.',
})
C_VERSIONS.update({
    (0, 0xC45C): 'phone_book_key (src/frame.c) and phone_book (src/phonebook.c); video, CRTC start and input are host services',
    (0, 0xC557): 'helper scroll_row, inside src/phonebook.c',
    (0, 0xC588): 'helper draw_entries, inside src/phonebook.c',
    (0, 0xC5DA): 'helper draw_records, inside src/phonebook.c',
    (0, 0xC72F): 'helper load_panels, inside src/phonebook.c',
    (0, 0xFA4B): 'string_copy (src/phonebook.c)',
    (0, 0xFA72): 'helper, the length count inside string_copy (src/phonebook.c)',
    (0, 0xF604): 'number_format (src/phonebook.c)',
    (0, 0xF86A): 'helper, the division step inside number_format (src/phonebook.c)',
})

# the gameplay menus' options (src/gamemenus.c, 2026-11-19)
FUNCS.update({
    (0, 0x4F02): 'menu_joystick',
    (0, 0x4E86): 'menu_quit',
    (0, 0x4EA2): 'menu_new_game',
    (0, 0x4EFA): 'menu_ratings',
    (0, 0x5309): 'menu_physical_status',
    (0, 0x53F5): 'menu_drop_item',
    (0, 0x578A): 'menu_special_action',
    (0, 0xDD2F): 'menu_tell_sarah',
    (0, 0x8E4E): 'text_copy_string',
})
NOTES.update({
    (0, 0x4F02): 'GAME MENU, joystick on/off: off if on; else 3A12 (carry: none) and 38F6 calibrate, then DS:5A4F = 1.',
    (0, 0x4E86): 'GAME MENU, quit: facility_confirm "Are you sure ?"; yes sets DS:1159 = 55. Closes with carry.',
    (0, 0x4EA2): 'GAME MENU, new game: yes/no menu (0x10C1, actions 7811); yes sets DS:1159 = AA.',
    (0, 0x5309): 'PLAYER MENU, physical status: damage_panel, DS:7242 = FFFF.',
    (0, 0x53F5): 'PLAYER MENU, drop item: category menu (actions 7988), then the HUD is rebuilt.',
    (0, 0x578A): 'PLAYER MENU, special action: the menu built at text 0x0AF9 (actions AAAD), or "There is nothing special here."',
    (0, 0xDD2F): 'Tell Sarah to...: entered at DD33 - order. Orders 0-2 go to DS:11BE; 3 and 4 call the give/take panels.',
})
C_VERSIONS.update({
    (0, 0x4F02): 'helper in game_menu option(), src/gamemenus.c; detection and calibration are host calls',
    (0, 0x4E86): 'helper in game_menu option(), src/gamemenus.c',
    (0, 0x4EA2): 'helper in game_menu option(), src/gamemenus.c',
    (0, 0x4EFA): 'helper in game_menu option(), src/gamemenus.c; the ratings screen is a host call',
    (0, 0x51D8): 'helper in game_menu option(), src/gamemenus.c; the category viewers are host calls',
    (0, 0x5309): 'helper in game_menu option(), src/gamemenus.c; the damage panel is a host call',
    (0, 0x53F5): 'helper in game_menu option(), src/gamemenus.c',
    (0, 0x578A): 'helper in game_menu option(), src/gamemenus.c',
    (0, 0xDD2F): 'helper in game_menu option(), src/gamemenus.c; the give/take panels are host calls',
    (0, 0x8DFF): 'facility_confirm (src/gamemenus.c)',
    (0, 0x8E32): 'helper in game_menu option(), src/gamemenus.c (yes)',
    (0, 0x8E40): 'helper in game_menu option(), src/gamemenus.c (no)',
    (0, 0x8E4E): 'helper copy_to_text, inside src/gamemenus.c',
})

# the inventory viewer (src/gamemenus.c, 2026-11-19)
FUNCS.update({
    (0, 0x5216): 'inventory_view',
    (0, 0xF5D5): 'byte_decimal_signed',
    (0, 0xF58D): 'byte_format_nul',
    (0, 0xF596): 'byte_format',
})
NOTES.update({
    (0, 0x5216): 'Category BX (1-5; FFFF = misc.) in a message box: header, misc. cash, then count and name per item; closes with carry.',
    (0, 0xF5D5): 'Signed AL in decimal with a NUL at DS:SI; SI kept. Counts above 127 print negative.',
})
C_VERSIONS.update({
    (0, 0x5216): 'helper inventory_view, inside src/gamemenus.c',
    (0, 0x51FD): 'helper inventory_view (weapons), inside src/gamemenus.c',
    (0, 0x5202): 'helper inventory_view (ammunition), inside src/gamemenus.c',
    (0, 0x5207): 'helper inventory_view (clothes), inside src/gamemenus.c',
    (0, 0x520C): 'helper inventory_view (drugs), inside src/gamemenus.c',
    (0, 0x5211): 'helper inventory_view (tools), inside src/gamemenus.c',
    (0, 0xF5D5): 'helper byte_decimal, inside src/gamemenus.c',
    (0, 0xF58D): 'helper byte_decimal, inside src/gamemenus.c',
    (0, 0xF596): 'helper byte_decimal, inside src/gamemenus.c',
})

# dropping items (src/gamemenus.c, 2026-11-19)
FUNCS.update({
    (0, 0x542F): 'drop_menu',
    (0, 0x5507): 'drop_item',
    (0, 0x565B): 'drop_in_world',
})
NOTES.update({
    (0, 0x542F): '"DROP WHAT?" menu of a category (BX, entered at 541B..5434), actions DS:7994; or "You have nothing to drop."',
    (0, 0x5507): 'Entered at 551A..5507 for lines 1..20. Finds the line again by category (misc. = 6 only), unbounded.',
    (0, 0x565B): 'A 13-byte pickup record at the player (ring of 20 at DS:0253, next DS:03FC); DS:116C less the weight.',
})
C_VERSIONS.update({
    (0, 0x541B): 'helper drop_menu (weapons), inside src/gamemenus.c',
    (0, 0x5420): 'helper drop_menu (ammunition), inside src/gamemenus.c',
    (0, 0x5425): 'helper drop_menu (clothes), inside src/gamemenus.c',
    (0, 0x542A): 'helper drop_menu (drugs), inside src/gamemenus.c',
    (0, 0x542F): 'helper drop_menu, inside src/gamemenus.c',
    (0, 0x5507): 'helper drop_item, inside src/gamemenus.c',
    (0, 0x565B): 'helper drop_in_world, inside src/gamemenus.c',
})

# Sarah's item exchange and the shared add/remove (2026-11-19)
FUNCS.update({
    (0, 0x5558): 'inventory_transfer',
    (0, 0x57D4): 'companion_give',
    (0, 0x57E7): 'companion_take',
    (0, 0x5822): 'exchange_menu',
    (0, 0x58E5): 'exchange_item',
})
NOTES.update({
    (0, 0x5558): 'DI = list, AL = id, BP = 0 add (copy from the list at DS:03FE) / FFFF remove. See src/inventory.c.',
    (0, 0x57D4): 'Give: DS:0252 = 0, from 05B0 (DS:03FE) to Sarah 085C (DS:0400); the category menu, actions DS:79E4.',
    (0, 0x57E7): 'Take: DS:0252 = FF, from Sarah 085C to 05B0.',
    (0, 0x5822): '"GIVE SARAH WHAT?" / "TAKE WHAT FROM SARAH?" (entered at 580E..5827), actions DS:79F0.',
    (0, 0x58E5): 'Entered at 58F8..58E5 for lines 1..20. Sarah\'s load DS:0402 must stay below 35.',
})
C_VERSIONS.update({
    (0, 0x5558): 'inventory_transfer (src/inventory.c)',
    (0, 0x57D4): 'companion_exchange (src/gamemenus.c), give',
    (0, 0x57E7): 'companion_exchange (src/gamemenus.c), take',
    (0, 0x580E): 'helper exchange_menu (weapons), inside src/gamemenus.c',
    (0, 0x5813): 'helper exchange_menu (ammunition), inside src/gamemenus.c',
    (0, 0x5818): 'helper exchange_menu (clothes), inside src/gamemenus.c',
    (0, 0x581D): 'helper exchange_menu (drugs), inside src/gamemenus.c',
    (0, 0x5822): 'helper exchange_menu, inside src/gamemenus.c',
    (0, 0x58E5): 'helper exchange_item, inside src/gamemenus.c',
})

# the damage panel (src/damagepanel.c, 2026-11-19)
FUNCS.update({
    (0, 0x603E): 'damage_boxes_clear', (0, 0x6075): 'damage_any_cost', (0, 0x6085): 'damage_animate',
    (0, 0x615C): 'damage_input', (0, 0x6176): 'damage_box_toggle', (0, 0x61C2): 'damage_box_clear',
    (0, 0x6209): 'damage_part_cost', (0, 0x621D): 'damage_trace_step', (0, 0x6274): 'damage_init_traces',
    (0, 0x62E6): 'damage_retime_traces', (0, 0x6321): 'actor_health', (0, 0x6330): 'damage_traces',
    (0, 0x64E3): 'actor_update_wound_bits', (0, 0x652A): 'damage_draw_parts', (0, 0x6564): 'damage_draw_costs',
    (0, 0x657E): 'damage_draw_totals', (0, 0x6671): 'damage_heal_point', (0, 0x66CA): 'damage_draw_readouts',
    (0, 0x6710): 'damage_draw_number', (0, 0x6793): 'damage_draw_body', (0, 0x6849): 'damage_line_colour',
    (0, 0x6884): 'damage_key',
    (0x5776, 0x0000): 'ega_clear_plane3_box',
    (0x11BC, 0x1A84): 'damage_vga_box', (0x11BC, 0x1AC8): 'damage_vga_digits', (0x11BC, 0x1B7F): 'damage_vga_trace_step',
})
NOTES.update({
    (0, 0x5F06): 'H/T/A/L select parts, Enter heals them while the world runs (B588), Esc leaves. VGA when DS:ADD0.',
    (0, 0x6321): '(max - damage) * 117 / max of the actor at SI (+1C max, +1A damage).',
    (0, 0x65D0): 'CX after inventory_count_required is what it left (600 only for an empty required list), so usually 51 ticks.',
    (0x5776, 0x0000): 'Clears plane 3 in a rectangle. Ends with DX = 3CF, so its OUT DX,AX sets the bit mask to 1.',
})
C_VERSIONS.update({k: 'helper in damage_panel, src/damagepanel.c' for k in [
    (0, 0x603E), (0, 0x6075), (0, 0x6085), (0, 0x615C), (0, 0x6176), (0, 0x61C2), (0, 0x6209), (0, 0x621D),
    (0, 0x6274), (0, 0x62E6), (0, 0x6321), (0, 0x6330), (0, 0x64E3), (0, 0x652A), (0, 0x6564), (0, 0x657E),
    (0, 0x65D0), (0, 0x6671), (0, 0x66CA), (0, 0x6710), (0, 0x6793), (0, 0x6849), (0, 0x6884),
    (0x5776, 0x0000), (0x11BC, 0x1A84), (0x11BC, 0x1AC8), (0x11BC, 0x1B7F)]})
C_VERSIONS[(0, 0x5F06)] = 'damage_panel (src/damagepanel.c); EGA and VGA; healing runs the native world step'

# the scalable font (src/fontscale.c, 2026-11-19)
FUNCS.update({
    (0x11BC, 0x28F8): 'font_load', (0x11BC, 0x2714): 'font_scale',
    (0x11BC, 0x27D0): 'font_scale_glyph', (0x11BC, 0x281E): 'font_scale_row',
})
NOTES.update({
    (0x11BC, 0x2714): 'AX = source rows | width << 8, BX = target likewise, CX glyphs, SI -> DI. Then widths AEC3 -> AE64, AE02 -> AE03.',
    (0x11BC, 0x28F8): 'DX = file name: read (65535 max) into the work buffer; ADFE = size, ADE8 = AE00 = its segment, ADE6 = 0.',
})
C_VERSIONS.update({
    (0x11BC, 0x28F8): 'font_load (src/fontscale.c)',
    (0x11BC, 0x2714): 'font_scale (src/fontscale.c)',
    (0x11BC, 0x27D0): 'helper scale_glyph, inside src/fontscale.c',
    (0x11BC, 0x281E): 'helper scale_row, inside src/fontscale.c',
})
FUNCS.update({(0x11BC, 0x2682): 'font_text', (0x11BC, 0x28B0): 'font_text_begin', (0x11BC, 0x28E4): 'font_text_end'})
NOTES.update({
    (0x11BC, 0x2682): 'AX = x, BX = y, DS:SI = string; returns AX = x after it. EGA set/reset in DS:E40F, stride DS:1228.',
    (0x11BC, 0x28E4): 'Writes AX = 08FF to 3CE (index 15 := 8) where FF08 was meant: the bit mask is not reset.',
})
C_VERSIONS.update({
    (0x11BC, 0x2682): 'font_text (src/fontscale.c)',
    (0x11BC, 0x28B0): 'helper, the set-up inside font_text (src/fontscale.c)',
    (0x11BC, 0x28E4): 'helper, the tear-down inside font_text (src/fontscale.c)',
})

# the ratings screen and name editor (src/ratingsscreen.c, 2026-11-19)
FUNCS.update({
    (0, 0x0CC2): 'ega_fill_rect', (0, 0x9A13): 'ratings_frame_lines', (0, 0xD74B): 'ratings_vga_stats',
    (0, 0xD7F9): 'small_text_vga', (0, 0xD856): 'small_font_load', (0, 0xD863): 'ratings_screen_save',
    (0, 0xD877): 'ratings_screen_restore', (0, 0xDF4A): 'name_editor', (0, 0xE046): 'name_editor_redraw',
    (0, 0xF5EB): 'number_decimal_signed', (0, 0xF62C): 'number_decimal',
})
NOTES.update({
    (0, 0xDF4A): 'SI = message (text segment), BX/DX = place, CX = max. Field place follows the message NUL. '
                 'Esc: wait for it up, restore, carry (5A4E stays 1). Enter: NUL, restore, 5A4E = 0, pages 2.',
    (0, 0xD7F9): '7x7 font from far [E34E], glyph rows 24h apart, straight into A000 (mode 13h).',
})
C_VERSIONS.update({
    (0, 0xD300): 'ratings_screen (src/ratingsscreen.c); EGA and VGA, in play and from the main menu',
    (0, 0xD4C3): 'helper draw_stats in ratings_screen (src/ratingsscreen.c)',
    (0, 0xD628): 'ratings_decode (src/ratings.c), the read in load_table (src/ratingsscreen.c)',
    (0, 0xDF3A): 'helper enter_name in ratings_screen (src/ratingsscreen.c)',
    (0, 0xDF4A): 'name_editor (src/ratingsscreen.c)',
    (0, 0x0CC2): 'ega_fill_rect (src/ratingsscreen.c)',
    (0, 0xF62C): 'number_decimal (src/ratingsscreen.c)',
    (0, 0xF5EB): 'number_decimal_signed (src/ratingsscreen.c)',
})
C_VERSIONS.update({k: 'helper in ratings_screen, src/ratingsscreen.c' for k in [
    (0, 0x9A13), (0, 0xD74B), (0, 0xD7F9), (0, 0xD856), (0, 0xD863), (0, 0xD877), (0, 0xE046)]})

# Accounting pass (2026-11-19): routines whose only callers are translated and whose work
# those C functions already do (helpers written inline, far-call thunks the C replaces by
# a direct call, empty RETs). Each was read against the C named here.
C_VERSIONS.update({k: 'helper inside line_to, src/line.c' for k in [
    (0, 0x0DC7), (0, 0x0E39), (0, 0x0FD9), (0, 0x0FF5), (0, 0x1011), (0, 0x102D), (0, 0x1049)]})
C_VERSIONS[(0, 0x1075)] = 'helper (card set-up for lines) inside src/line.c and src/maparea.c'
C_VERSIONS.update({k: 'helper inside area_line_to, src/maparea.c' for k in [
    (0, 0x13E3), (0, 0x13FF), (0, 0x141B), (0, 0x1437), (0, 0x1453)]})
C_VERSIONS.update({
    (0, 0x0C0E): 'helper (clear one page) inside camera_clear_pages, src/camera.c',
    (0, 0x024B): 'helper (speed, counter, compass) inside src/scenecompose.c and src/weaponhud.c',
    (0, 0x2A6B): 'helper rotate_xz_by_index inside src/object.c and src/drawlist.c',
    (0, 0x3AAA): 'helper joystick_axis, src/joystick.c',
    (0, 0x3F0F): 'helper window_cell inside update_visible_cells, src/cellwindow.c',
    (0, 0x3F33): 'helper inside update_visible_cells, src/cellwindow.c',
    (0, 0xD88C): 'helper inside refresh_meshes, src/cellwindow.c (the missile mesh)',
    (0, 0x6FFE): 'helper inside refresh_meshes, src/cellwindow.c',
    (0, 0x8841): 'helper inside refresh_meshes, src/cellwindow.c',
    (0, 0xA002): 'helper inside refresh_meshes, src/cellwindow.c',
    (0, 0x5754): 'helper inside weapon_inventory_rebuild, src/weaponhud.c',
    (0, 0x98EF): 'helper inside weapon_inventory_rebuild, src/weaponhud.c',
    (0x11BC, 0x1F17): 'helper (the selection box) inside hud_weapon_selection, src/weaponhud.c',
    (0, 0x781F): 'helper inside weapon_collect_targets, src/targetlist.c',
    (0, 0x8C3F): 'helper inside walking_speed_step, src/playercontrols.c',
    (0, 0xB4F4): 'helper inside bytekiller_unpack, src/unpack.c',
    (0, 0xB501): 'helper inside bytekiller_unpack, src/unpack.c',
    (0x14B5, 0x0325): 'helper inside lzhuf_unpack, src/unpack.c',
    (0x14B5, 0x034C): 'helper inside lzhuf_unpack, src/unpack.c',
    (0x14B5, 0x0393): 'helper inside lzhuf_unpack, src/unpack.c',
    (0, 0xBD63): 'empty routine (RET) called by opponent_controller_slow',
    (0, 0xC396): 'empty routine (RET) called by opponent_controller_fast',
    (0x11BC, 0x21C9): 'empty routine (RET) called by collision_test',
    (0, 0xD099): 'helper inside the map area branch, src/mapui.c',
    (0, 0xF639): 'helper (decimal, no NUL) inside hud_format_score, src/hudscore.c',
    (0, 0x51C0): 'inventory category menu, inside the Inventory option of src/gamemenus.c (shop_screen still asks its host)',
    (0x11BC, 0x02CC): 'helper poly_span_reset inside fill_polygon, src/polyfill.c',
    (0x11BC, 0x1D47): 'helper inside weapon_hotkeys, src/weaponkeys.c',
    (0x11BC, 0x0950): 'helper inside update_visible_cells, src/cellwindow.c',
    (0x11BC, 0x0AC6): 'helper inside src/windowground.c',
    (0x11BC, 0x0FAA): 'helper inside src/windowground.c',
    (0x11BC, 0x10D4): 'helper inside src/windowground.c',
    (0x11BC, 0x0DA2): 'helper inside ground_quadrant, src/windowground.c',
    (0x11BC, 0x100D): 'helper inside street_quadrant, src/windowground.c',
    (0x11BC, 0x10BB): 'helper inside read_sector, src/windowground.c',
    (0x11BC, 0x10A2): 'helper mesh_highest_point inside src/windowobjects.c',
    (0x11BC, 0x120A): 'helper inside src/windowobjects.c',
    (0x11BC, 0x124C): 'helper inside src/windowobjects.c',
    (0x11BC, 0x12E7): 'helper (LA.BMP through ImageIO) inside src/windowobjects.c',
    (0x11BC, 0x258E): 'helper inside src/windowobjects.c',
    (0x14A7, 0x0013): 'helper inside civilian_steer, src/figurewalk.c',
    (0x14A7, 0x0058): 'helper inside civilian_steer, src/figurewalk.c',
    (0x5776, 0x0465): 'helper inside textbox_border_layer, src/textbox.c',
    (0x5776, 0x0476): 'helper (four-plane copy) inside menu_highlight, src/menu.c',
    (0, 0x4581): 'object_blown: the serial-link notice (151B, not translated) then map_note_removed, src/blast.c',
})
C_VERSIONS.update({k: 'helper inside armed_figures_move, src/figurewalk.c' for k in [
    (0, 0xA667), (0, 0xA681), (0, 0xA69E), (0, 0xA70C), (0, 0xA773), (0, 0xA788), (0, 0xA7A8), (0, 0xA7E5),
    (0, 0xAFA2)]})
C_VERSIONS.update({k: 'helper inside select_position, src/figurespawn.c' for k in [
    (0, 0xA94B), (0, 0xA987), (0, 0xA9B4), (0, 0xA9F5), (0, 0xAA17)]})
C_VERSIONS.update({k: 'edge handler inside fill_polygon, src/polyfill.c' for k in [
    (0x11BC, 0x0080), (0x11BC, 0x008C), (0x11BC, 0x0090), (0x11BC, 0x009C), (0x11BC, 0x00A0), (0x11BC, 0x00AC),
    (0x11BC, 0x00B0)]})
C_VERSIONS.update({k: f'far-call thunk to {target}; the C calls it directly' for k, target in [
    ((0, 0x1F66), 'line_to'), ((0, 0xEEEA), 'angle_between'), ((0, 0xEEFE), 'rotate_xz'),
    ((0, 0xEF12), 'weapon_inventory_rebuild'), ((0, 0xEF36), 'string_copy'), ((0, 0xEF3E), 'hud_draw_number'),
    ((0, 0xEF42), 'random_word'), ((0, 0xEF4E), 'load_256_image_and_palette'),
    ((0, 0xEF56), 'image_unpack_shared / image_unpack_four_lzhuf'), ((0, 0xEF6B), 'inventory_remove'),
    ((0, 0xEF73), 'hud_init_optics'), ((0, 0xEF8B), 'load_file'), ((0, 0xEF9B), 'collect_cell_extras'),
    ((0, 0xEF7B), 'line_to'), ((0, 0xEF7F), 'area_line_to'), ((0x11BC, 0x1570), 'face_reverse_winding'),
    ((0x11BC, 0x1574), 'face_edge_vectors'), ((0x11BC, 0x1578), 'face_is_hidden')]})
C_VERSIONS.update({
    (0, 0x3F28): 'helper inside update_visible_cells, src/cellwindow.c',
    (0, 0x7872): 'helper (distance to the player) inside weapon_collect_targets, src/targetlist.c',
    (0x11BC, 0x0E83): 'helper ground_copy_secondary_list inside src/windowground.c',
    (0x11BC, 0x107F): 'helper inside street_quadrant, src/windowground.c',
    (0x11BC, 0x1317): 'helper inside the LA.BMP load, src/windowobjects.c',
    (0x11BC, 0x1351): 'helper inside src/windowobjects.c',
    (0x14A7, 0x0042): 'helper inside civilian_steer, src/figurewalk.c',
    (0x14A7, 0x0098): 'helper inside civilian_steer, src/figurewalk.c',
    (0x14B5, 0x0515): 'helper inside lzhuf_unpack, src/unpack.c',
    (0x14B5, 0x05D8): 'helper inside lzhuf_unpack, src/unpack.c',
    (0x14B5, 0x0632): 'helper inside lzhuf_unpack, src/unpack.c',
    (0x5776, 0x04A9): 'helper (rows of one plane) inside menu_highlight, src/menu.c',
})
C_VERSIONS.update({k: f'far-call thunk to {target}; the C calls it directly' for k, target in [
    ((0, 0x400A), 'load_file'), ((0, 0xEF46), 'figure_map_sample')]})
C_VERSIONS.update({
    (0x11BC, 0x0F3C): 'helper ground_resolve_secondary_refs inside src/windowground.c',
    (0x11BC, 0x1358): 'helper (skip an image record) inside src/windowobjects.c',
    (0x14B5, 0x0401): 'helper (the Huffman decoder) inside lzhuf_unpack, src/unpack.c',
    (0x14B5, 0x05F7): 'helper inside lzhuf_unpack, src/unpack.c',
    (0, 0xEF4A): 'far-call thunk to figure_kill; the C calls it directly',
})
C_VERSIONS[(0x14B5, 0x0651)] = 'helper inside lzhuf_unpack, src/unpack.c'

# thunks (CALL target then RET/RETF) to translated routines (2026-11-19)
C_VERSIONS.update({k: f'thunk to {target} (CALL, RET/RETF); the C calls it directly' for k, target in [
    ((0x0000, 0xb584), 'scene_present'),
    ((0x0000, 0xeeee), 'note_removed'),
    ((0x0000, 0xeef2), 'player_hit'),
    ((0x0000, 0xeef6), 'file_load_ds'),
    ((0x0000, 0xeefa), 'name_editor'),
    ((0x0000, 0xef02), 'approx_distance'),
    ((0x0000, 0xef06), 'explosion_damage'),
    ((0x0000, 0xef0a), 'object_blown'),
    ((0x0000, 0xef0e), 'weapon_visual_insert'),
    ((0x0000, 0xef1e), 'sub_0000_0C0E'),
    ((0x0000, 0xef26), 'keyboard_read'),
    ((0x0000, 0xef32), 'set_view_window'),
    ((0x0000, 0xef3a), 'map_clear_key_buffer'),
    ((0x0000, 0xef52), 'random_step'),
    ((0x0000, 0xef6f), 'textbox_draw'),
    ((0x0000, 0xef8f), 'sound_start'),
    ((0x0000, 0xef93), 'sub_0000_2F1C'),
    ((0x0000, 0xef97), 'travel_clear_arrival'),
]})

# Routines not translated because they only reach the hardware or DOS: the host
# replaces them through its host services. Their callers' game logic is translated.
SOUND_LAYER = 'Sound Blaster / driver access (EA3E port, 0FBA / 101F / 10BB calls): the host audio'
NATIVE = {(0, off): SOUND_LAYER for off in (
    0xEFA0, 0xEFBE, 0xEFDD, 0xEFF2, 0xF030, 0xF048, 0xF05E, 0xF11C, 0xF13A, 0xF147, 0xF154, 0xF162,
    0xF19E, 0xF1A7, 0xF1D8, 0xF1E8, 0xF1FC, 0xF205, 0xF20E, 0xF22B, 0xF23F, 0xF248, 0xF251, 0xF262, 0xF2FA,
    0xF384, 0xF3A5, 0xF3B8, 0xF3CA, 0xF409, 0xF41C, 0xF42F, 0xF445, 0xF452, 0xF462, 0xF472, 0xF47B, 0xF484,
    0xF494, 0xF4A1, 0xF4AE, 0xF4C1, 0xF4DB)}
NATIVE.update({(0, off): 'DOS file and directory call (open/create/read/write/close/delete/find, paths, '
                         'error code): the host file service (ImageIO)' for off in (
    0xF63F, 0xF664, 0xF66E, 0xF6AC, 0xF6B3, 0xF6E8, 0xF714, 0xF738, 0xF744, 0xF754, 0xF770, 0xF77C, 0xF80F,
    0xF82B, 0xF84D, 0xF8B3, 0xF8BE, 0xF8D5)})
NATIVE.update({(0x11BC, 0x10C6): 'DOS close: the host file service (ImageIO)',
               (0x11BC, 0x10CB): 'DOS read: the host file service (ImageIO)'})
NATIVE.update({
    (0, 0xF008): 'set an interrupt vector (CLI, IVT write): host',
    (0, 0xF01D): 'read an interrupt vector: host',
    (0, 0xF654): 'BIOS tick count 0:46C: the host clock',
    (0, 0x03D1): 'installs the divide-error handler 0407: host (C divisions follow the original instead)',
    (0, 0x03F2): 'restores the divide-error vector: host',
    (0, 0x0407): 'divide-error handler (skips the instruction): C reproduces each division\'s result',
    (0, 0x0BE5): 'INT 10h: the host video service',
    (0, 0xF4E5): 'display adapter detection (INT 10h 1A00 / 12h): the host',
    (0, 0x9FA4): 'INT 10h 1012, 256 DAC registers: the host palette',
    (0, 0xC571): 'CRTC display start: the host video service (PB_SET_DISPLAY_START)',
    (0, 0x0D8D): 'wait for vertical retrace to start: the host (MapPlatform wait)',
    (0, 0x0DAA): 'wait for vertical retrace to end: the host (MapPlatform wait)',
})

# the keyboard interrupt (src/keyboard.c, 2026-11-19)
C_VERSIONS[(0, 0x37E3)] = 'keyboard_scancode (src/keyboard.c); the host reads port 60h, acknowledges and chains'
NOTES[(0, 0x37E3)] = ('F0 makes the next byte a release. Presses: DS:5BD8 = code, F12 sets 5A50, character from '
                      '5A6A (5AEA with Shift) into the ring 5B70..5BD3 unless full. While 5B6A is set the key '
                      'marked down is the previous 5BD8. Left Shift is mirrored into Right Shift. Ctrl+Alt+Del: '
                      'FFFF:0000.')
NATIVE.update({(0, 0x3756): 'installs the keyboard interrupt (INT 9 through DOS): the host keyboard',
               (0, 0x3783): 'restores the old keyboard interrupt: the host keyboard'})

# the 640-wide line (src/line.c, 2026-11-19)
FUNCS.update({(0, 0x1201): 'line_to_wide', (0, 0x1090): 'line_vertical_wide', (0, 0x1106): 'line_horizontal_wide',
              (0, 0x1313): 'line_begin_wide'})
C_VERSIONS[(0, 0x1201)] = 'line_to_wide (src/line.c): line_to with rows doubled and 80 bytes a row'
C_VERSIONS.update({k: 'helper inside line_to_wide, src/line.c' for k in [
    (0, 0x1090), (0, 0x1106), (0, 0x12A3), (0, 0x12BF), (0, 0x12DB), (0, 0x12F7), (0, 0x1313)]})
C_VERSIONS[(0, 0xEF22)] = 'thunk to line_to_wide (CALL, RETF); the C calls it directly'
NOTES[(0, 0x1090)] = 'Leaves BX = 50h (its stride register), where 0DC7 leaves the smaller y.'

# the start-up screen, segment 57C5 (src/intro.c, 2026-11-19)
FUNCS.update({
    (0x57C5, 0x000E): 'intro_screen', (0x57C5, 0x00F7): 'intro_type_page', (0x57C5, 0x01BF): 'intro_present',
    (0x57C5, 0x01D1): 'intro_key_check', (0x57C5, 0x01E3): 'intro_clear_buffer', (0x57C5, 0x01F0): 'intro_cursor',
    (0x57C5, 0x020C): 'intro_prepare_points', (0x57C5, 0x0236): 'intro_logo_step', (0x57C5, 0x0282): 'intro_draw_logo',
    (0x57C5, 0x02EF): 'intro_project_x', (0x57C5, 0x030A): 'intro_project_y', (0x57C5, 0x0325): 'intro_clipped_line',
    (0x57C5, 0x03F0): 'intro_clip_line', (0x57C5, 0x0459): 'intro_outcode', (0x57C5, 0x0488): 'intro_clip_point',
    (0x57C5, 0x053C): 'intro_set_buffer', (0, 0x1769): 'buffer_to_screen_wide', (0, 0x17C0): 'intro_clear_area',
    (0x11BC, 0x2925): 'font_char_to_buffer',
})
C_VERSIONS[(0x57C5, 0x000E)] = 'intro_screen (src/intro.c); entry SP from the host, as the original keeps it'
C_VERSIONS[(0x57C5, 0x053C)] = 'intro_set_buffer (src/intro.c)'
C_VERSIONS.update({k: 'helper in intro_screen, src/intro.c' for k in [
    (0x57C5, 0x00F7), (0x57C5, 0x01BF), (0x57C5, 0x01D1), (0x57C5, 0x01E3), (0x57C5, 0x01F0), (0x57C5, 0x020C),
    (0x57C5, 0x0236), (0x57C5, 0x0282), (0x57C5, 0x02EF), (0x57C5, 0x030A), (0x57C5, 0x0325), (0x57C5, 0x03F0),
    (0x57C5, 0x0459), (0x57C5, 0x0488), (0, 0x1769), (0, 0x17C0), (0x11BC, 0x2925)]})
C_VERSIONS.update({(0, 0xEF16): 'thunk to 1769 (CALL, RETF); the C calls it directly',
                   (0, 0xEF2A): 'thunk to 17C0 (CALL, RETF); the C calls it directly'})
NOTES[(0x57C5, 0x02EF)] = ('IDIV WORD PTR [BE92] is four bytes; on overflow 0407 skips two, so the CPU runs '
                           'XCHG AX,DX / MOV SI,0603h / SUB DH,BL: the polyline walk jumps to DS:0603.')
NOTES[(0x57C5, 0x030A)] = 'The same overflow path, with SUB BL,DH: the x just projected (in BX) loses DH from BL.'

# the copy-protection screen (src/protection.c, 2026-11-19)
FUNCS.update({
    (0, 0xEA86): 'protection_screen', (0, 0xEABB): 'random_from_1', (0, 0xEACC): 'random_below',
    (0, 0xEADC): 'protection_symbol_source', (0, 0xEB86): 'protection_symbol_place', (0, 0xEC0E): 'protection_question',
    (0, 0xEC25): 'protection_table_entry', (0, 0xEC41): 'protection_choose_symbols', (0, 0xECAF): 'protection_load_symbols',
    (0, 0xECDE): 'protection_show_question', (0, 0xED35): 'protection_body', (0, 0xEDBD): 'protection_ten_answers',
    (0, 0xEE37): 'protection_clear_table', (0, 0xEE42): 'protection_shuffle_table', (0, 0xEE0C): 'protection_fail',
    (0, 0xF5C0): 'byte_decimal_unsigned',
})
C_VERSIONS[(0, 0xEA86)] = 'protection_screen (src/protection.c); EGA and VGA'
C_VERSIONS[(0, 0x8117)] = 'random_refill (src/blast.c)'
C_VERSIONS.update({k: 'helper in protection_screen, src/protection.c' for k in [
    (0, 0xEABB), (0, 0xEACC), (0, 0xEADC), (0, 0xEAF5), (0, 0xEB86), (0, 0xEB9A), (0, 0xEC0E), (0, 0xEC25),
    (0, 0xEC41), (0, 0xECAF), (0, 0xECDE), (0, 0xED35), (0, 0xEDBD), (0, 0xEE37), (0, 0xEE42), (0, 0xF5C0)]})
NOTES[(0, 0xED35)] = ('The check of the chosen symbol (CALL EE0C at ED90) is skipped by NOP / JMP EDBA in this build; '
                      'only the wrong-symbol timer EA2E is cleared.')

# Code proven unreachable: no call, jump, table or stored pointer reaches it. Not translated.
DEAD = {
    (0, 0xEE0C): 'copy-protection failure (text mode, message E6B1, hang): its only call, at ED90, is skipped',
}

# the facility screens (src/facility.c, 2026-11-19)
C_VERSIONS[(0, 0x8CB0)] = 'facility_screen (src/facility.c); EGA and VGA; the firing range still the host\'s (FA_RANGE)'
C_VERSIONS.update({k: 'helper in facility_screen, src/facility.c' for k in [
    (0, 0x8D21), (0, 0x8D6B), (0, 0x8DBB), (0, 0x8DD3), (0, 0x8DDF)]})
NOTES[(0, 0x8CB0)] = 'BX = kind 4 bank, 5 firing range, 6 hospital (tables A968 VGA images, A96E EGA images, A978 handlers).'
C_VERSIONS[(0, 0x8CB0)] = 'facility_screen (src/facility.c); bank, firing range and hospital, EGA and VGA'
C_VERSIONS.update({k: 'helper in the firing range, src/facility.c' for k in [
    (0, 0x8E59), (0, 0x8EA5), (0, 0x8F1C), (0, 0x8F6C), (0, 0x8F78), (0, 0x9023), (0, 0x9032), (0, 0x907C),
    (0, 0x90B0), (0, 0x9132), (0, 0x9169), (0, 0x6149)]})
NOTES[(0, 0x8F78)] = ('Penalty: twice the horizontal distance, 10 when over 8; a vertical distance over 8 also sets AX = 10 '
                      '(it never counts otherwise). Returns AX = ticks, BX = penalty.')

# the main menu (src/mainmenu.c, 2026-11-19)
FUNCS.update({(0, 0x9922): 'main_menu', (0, 0x9BCD): 'main_menu_keys', (0, 0x9A33): 'main_menu_draw_options',
              (0, 0x9CBE): 'main_menu_draw_choice', (0, 0x9CA4): 'main_menu_choice_at', (0, 0x99E8): 'main_menu_light',
              (0, 0x9D29): 'main_menu_reset_values', (0, 0x9D36): 'menu_vga_prepare', (0, 0x9E59): 'menu_vga_run'})
C_VERSIONS[(0, 0x9922)] = 'main_menu (src/mainmenu.c); EGA and VGA'
C_VERSIONS.update({k: 'helper in main_menu, src/mainmenu.c' for k in [
    (0, 0x99E8), (0, 0x9A0E), (0, 0x9A33), (0, 0x9AB1), (0, 0x9ADE), (0, 0x9AF1), (0, 0x9AFA), (0, 0x9B03),
    (0, 0x9B20), (0, 0x9B40), (0, 0x9B53), (0, 0x9B57), (0, 0x9B9D), (0, 0x9BCD), (0, 0x9C86), (0, 0x9C95),
    (0, 0x9CA4), (0, 0x9CBE), (0, 0x9D29), (0, 0x0B8F)]})
C_VERSIONS[(0, 0x9D36)] = 'menu_vga_prepare / menu_vga_display (src/vgamenu.c)'
C_VERSIONS[(0, 0x9E59)] = 'menu_vga_run (src/vgamenu.c)'
NOTES[(0, 0x9B20)] = ('No joystick: AL = K and a jump back into the key loop (9BEA) from inside the handler call, so its '
                      'return address stays on the stack and the next start (ADD SP,2 / RET) only returns into the loop.')

# the closing credits (src/credits.c, 2026-11-19)
C_VERSIONS[(0, 0x91EA)] = 'credits_screen (src/credits.c)'
C_VERSIONS.update({k: 'helper in credits_screen, src/credits.c' for k in [
    (0, 0x9294), (0, 0x92A8), (0, 0x92BF), (0, 0x92D9), (0, 0x92FE), (0, 0x9320), (0, 0x9368), (0, 0x9380)]})

# music control (src/music.c, 2026-11-19)
FUNCS.update({(0, 0x8986): 'music_start', (0, 0x8C52): 'music_stop', (0, 0x8C64): 'music_close',
              (0, 0x899C): 'music_mark_ending'})
C_VERSIONS.update({(0, 0x8986): 'music_start (src/music.c)', (0, 0x8C52): 'music_stop (src/music.c)',
                   (0, 0x8C64): 'music_close (src/music.c)', (0, 0x899C): 'music_mark_ending (src/music.c)'})
NATIVE.update({(0, off): SOUND_LAYER for off in (0x89F0, 0x8A41, 0x8BA2, 0x8C13, 0x8C33, 0x8C96)})
NATIVE.update({(0, 0xEF83): 'thunk to the retrace wait 0D8D: the host', (0, 0xEF87): 'thunk to the retrace wait 0DAA: the host'})

# page selection (src/scenepresent.c, 2026-11-19)
C_VERSIONS.update({
    (0, 0x0C6B): 'select_pages (src/scenepresent.c); what a host runs for MS_SELECT_PAGES',
    (0, 0x0C7D): 'helper show_pages, inside scene_present and select_pages (src/scenepresent.c)',
    (0, 0xEF1A): 'thunk to 0C7D (CALL, RETF); the C calls it directly',
    (0, 0xEF2E): 'thunk to select_pages (CALL, RETF); the C calls it directly',
})
NATIVE.update({
    (0, 0x0BE8): 'the 16 EGA palette registers from DS:DX through the attribute controller: the host palette',
    (0, 0x7AAF): 'the default palette DS:1521 (0BE8): the host (MS_DEFAULT_PALETTE)',
    (0, 0x7AB6): 'the game palette DS:1510 (0BE8): the host (MS_PALETTE)',
    (0x5776, 0x02C6): 'CX frames of retrace waits: the host (MM_WAIT / OS_WAIT)',
})
NATIVE.update({(0, 0x5D52): 'EMS set-up (INT 67h: detect, 4 pages, map; DS:7ABF / 7B80 / 7B84): the host '
                            'has no EMS, the host sets the results',
               (0, 0x5E0E): 'EMS release (INT 67h 45h): the host'})

# session set-up (src/session.c, 2026-11-19)
C_VERSIONS.update({
    (0, 0x0B12): 'session_reset (src/session.c); fills 32 words at DS:039F, where DI was left',
    (0, 0x0B4E): 'session_pointers (src/session.c)',
    (0, 0x0B80): 'session_draw_page_wide (src/session.c)',
    (0, 0x1483): 'session_row_table (src/session.c)',
    (0, 0x057C): 'session_arrival_followup (src/session.c); the travel host op TR_ARRIVAL_FOLLOWUP can run it',
    (0, 0x97BF): 'session_clear_items (src/session.c)',
    (0, 0x9845): 'session_clear_flags (src/session.c)',
    (0, 0x97B4): 'point_copy (src/session.c)',
})

# the special actions (src/gamemenus.c, 2026-11-19)
C_VERSIONS.update({k: 'special action in game_menu option(), src/gamemenus.c' for k in [
    (0, 0x94DA), (0, 0x95A5), (0, 0x965C), (0, 0x9699), (0, 0x971D)]})
C_VERSIONS.update({(0, 0xF530): 'helper parse_number (the sign), inside src/gamemenus.c',
                   (0, 0xF54C): 'helper parse_number, inside src/gamemenus.c'})

# No call, jump or fall-through reaches these in the listing (found only by scanning unreached
# bytes), and their offset appears nowhere in the unpacked executable as a word: no table or
# stored pointer can hold them. Static evidence, checked 2026-11-19.
UNREFERENCED = 'no reference: unreached in the listing, and its offset is no word anywhere in the executable'
DEAD.update({k: UNREFERENCED for k in [
    (0, 0x1814), (0, 0x296A), (0, 0x43B9), (0, 0x47A8), (0, 0x47CE), (0, 0x47FD), (0, 0x5A6F), (0, 0x6479),
    (0, 0x79F1), (0, 0x87E2), (0, 0x950D), (0, 0xB9C6), (0, 0xCA39), (0, 0xEF77), (0, 0xF5CD), (0, 0xFA10),
    (0, 0xFA88), (0, 0xFAF7), (0x11BC, 0x110E), (0x11BC, 0x1B27), (0x11BC, 0x1E95)]})

# the end-of-session cutscenes (src/ending.c, 2026-11-19)
C_VERSIONS[(0, 0x5B6A)] = 'ending_sequence (src/ending.c)'
C_VERSIONS.update({k: 'helper in ending_sequence, src/ending.c' for k in [
    (0, 0x5A7B), (0, 0x5A93), (0, 0x5AA9), (0, 0x5ABF), (0, 0x5AEF), (0, 0x5B10), (0, 0x5B25), (0, 0x5B3A),
    (0, 0x5BCD)]})
NOTES[(0, 0x5ABF)] = ('EGA: the movie gets CX as 8AFE left it: 0 from its loader, or the caller\'s CX when the sample '
                      'group already was 6 (only 8AFE selects 6, so not in practice).')
NATIVE.update({
    (0, 0x3A12): 'joystick detection (a timing loop on port 201h; carry when none): the host (GM_JOYSTICK_DETECT)',
    (0, 0x3A33): 'joystick read (port 201h pulse counts, the buttons into the key table): the host (JoystickRead, '
                 'joystick_apply sets the keys)',
})
C_VERSIONS.update({
    (0, 0x168E): 'font8_load (src/session.c)',
    (0x11BC, 0x2A5E): 'helper inside font8_load, src/session.c (the segment into the code word 2A63)',
    (0x11BC, 0x11ED): 'def_slot_of (src/session.c)',
})
DEAD.update({
    (0, 0x26DF): UNREFERENCED + ' (the one DF 26 in the image straddles two instructions at 15AD:051E)',
    (0, 0x2707): 'only called from 26DF, which is unreachable',
    (0, 0x5622): 'only called from the thunk EF77, which is unreachable',
})
C_VERSIONS.update({(0, 0xCA1A): 'session_load_swapped (src/session.c)', (0, 0xE475): 'session_load_records (src/session.c)'})
C_VERSIONS[(0, 0x1AC9)] = 'session_load_pictures (src/session.c)'
C_VERSIONS[(0, 0xF879)] = 'random_seed_from_clock (src/session.c)'

# small routines without a known caller, their address in the executable's data (src/misc.c)
C_VERSIONS.update({
    (0, 0x4344): 'misc_store_1204 (src/misc.c)', (0, 0xA075): 'misc_mark_record (src/misc.c)',
    (0, 0xC20B): 'misc_band_test (src/misc.c)', (0, 0xACE1): 'misc_append_figures (src/misc.c)',
    (0, 0x9BA6): 'misc_collect_char (src/misc.c)', (0, 0xDF00): 'misc_cell_position (src/misc.c)',
    (0, 0x9A01): 'misc_frame_lines_abec (src/misc.c)',
})
C_VERSIONS[(0, 0x38F6)] = 'joystick_calibrate (src/joystick.c); the port read 3A33 is the host\'s JoystickRead'

# the hardware routines against the machine interface (src/machine.c, 2026-11-19): no longer NATIVE
MACHINE_C = {
    (0, 0x0D8D): 'retrace_wait_start', (0, 0x0DAA): 'retrace_wait_end', (0x5776, 0x02C6): 'pause_frames',
    (0, 0xEF83): 'thunk to retrace_wait_start', (0, 0xEF87): 'thunk to retrace_wait_end',
    (0, 0xC571): 'crtc_display_start', (0, 0x0BE5): 'bios_video_call', (0, 0x0BE8): 'palette_registers',
    (0, 0x7AAF): 'palette_registers (DS:1521)', (0, 0x7AB6): 'palette_registers (DS:1510)', (0, 0x9FA4): 'dac_block',
    (0, 0xF654): 'bios_ticks', (0, 0xF008): 'vector_set', (0, 0xF01D): 'vector_get',
    (0, 0x03D1): 'divide_handler_install', (0, 0x03F2): 'divide_handler_remove', (0, 0x0407): 'divide_error_resume',
    (0, 0x3756): 'keyboard_install', (0, 0x3783): 'keyboard_remove', (0, 0x3A12): 'joystick_absent',
    (0, 0x3A33): 'joystick_read_port', (0, 0x5D52): 'ems_setup', (0, 0x5E0E): 'ems_release',
    (0, 0xF4E5): 'adapter_detect',
}
for key, name in MACHINE_C.items():
    C_VERSIONS[key] = f'{name} (src/machine.c), through MachineServices'
    NATIVE.pop(key, None)

# the DOS file library against the machine interface (src/dos.c, 2026-11-19): no longer NATIVE
DOS_C = {
    (0, 0xF63F): 'dos_print', (0, 0xF664): 'helper strip_for_search', (0, 0xF66E): 'helper restore_for_search',
    (0, 0xF6AC): 'dos_current_directory', (0, 0xF6B3): 'dos_find_first', (0, 0xF6E8): 'dos_find_next',
    (0, 0xF714): 'dos_strip_backslash', (0, 0xF738): 'dos_drive_letter', (0, 0xF744): 'dos_delete',
    (0, 0xF754): 'dos_add_backslash', (0, 0xF770): 'dos_close', (0, 0xF77C): 'dos_create', (0, 0xF7AD): 'dos_open',
    (0, 0xF80F): 'dos_open_mode', (0, 0xF82B): 'dos_read', (0, 0xF84D): 'dos_write', (0, 0xF8B3): 'dos_store_error',
    (0, 0xF8BE): 'helper set_dta', (0, 0xF8D5): 'dos_last_error', (0, 0xFA5D): 'dos_string_end',
}
for key, name in DOS_C.items():
    C_VERSIONS[key] = f'{name} (src/dos.c), registers in and out, through MachineServices'
    NATIVE.pop(key, None)

# saving, loading and deleting games (src/savegame.c, through the DOS library)
C_VERSIONS.update({
    (0, 0x0A76): 'savegame_code_block (src/savegame.c)',
    (0, 0x4B76): 'savegame_save_action (src/savegame.c): 4B7E as a menu action; the entry 4B76 (ADD SP,4 first, '
                 'unreferenced) as an action of the save\'s own menus',
    (0, 0x4CD1): 'helper in src/savegame.c: "overwrite?" yes (ADD SP,4, then the open)',
    (0, 0x4CDE): 'savegame_delete_action (src/savegame.c)',
    (0, 0x4CE5): 'savegame_load (src/savegame.c); the picker 4CEA',
    (0, 0x4DD7): 'helper in src/savegame.c: the picker\'s 20 actions (an INC SI sled), then the load or delete',
})

# the program's start and set-up (src/startup.c)
C_VERSIONS.update({
    (0, 0x0000): 'program_start (src/startup.c); the routines with services of their own are the host\'s by address',
    (0, 0x0413): 'startup_options (src/startup.c); the link set-up 151B:020F the host\'s',
    (0, 0x04D3): 'startup_init (src/startup.c); 8117 with the time from DOS (random_refill_from)',
    (0, 0x04E8): 'startup_intro (src/startup.c), with the pauses 5BCD',
    (0, 0x052C): 'startup_game_setup (src/startup.c)',
    (0, 0x09FB): 'startup_preload (src/startup.c)',
    (0, 0x0A2C): 'helper preload_file in startup_preload, src/startup.c',
    (0, 0x97D8): 'startup_inventory (src/startup.c); shop_add_item the host\'s',
    (0, 0x86F4): 'helper item_room in startup_inventory, src/startup.c (no room: the original returns to 0000:BX)',
    (0, 0x59A6): 'startup_position (src/startup.c)',
    (0, 0x5A0D): 'helper in startup_position (the vehicle placed), src/startup.c',
    (0, 0x5A58): 'helper in startup_position (the characters\' templates), src/startup.c',
    (0, 0xD5B1): 'ratings_commit (src/startup.c)',
    (0, 0xD5FA): 'helper ratings_save in ratings_commit (src/startup.c), with ratings_encode (src/ratings.c)',
    (0, 0xD67F): 'ratings_insert (src/ratings.c); any count, as the original\'s LOOP',
    (0, 0xF8E0): 'char_compare_nocase (src/startup.c)',
    (0, 0xF8FC): 'args_count (src/startup.c)',
    (0, 0xF97A): 'args_next (src/startup.c)',
    (0, 0xFA19): 'args_reset (src/startup.c)',
    (0, 0xFA2C): 'string_compare_nocase (src/startup.c)',
})

# the sound layer (src/soundlayer.c): the drivers' entries are the host's (ProgramServices.call)
SOUND_C = {
    (0, 0xEFA0): 'sb_dsp_read', (0, 0xEFBE): 'sb_dsp_write', (0, 0xEFDD): 'sb_dsp_read_wait',
    (0, 0xEFF2): 'sb_dsp_write_wait', (0, 0xF030): 'sb_irq_unmask', (0, 0xF048): 'sb_irq_mask',
    (0, 0xF05E): 'sb_irq_detect (the IRQ through MachineServices.irq)', (0, 0xF11C): 'sb_irq_handler (IRQ 3)',
    (0, 0xF13A): 'sb_irq_handler (IRQ 2)', (0, 0xF147): 'sb_irq_handler (IRQ 5)', (0, 0xF154): 'sb_irq_handler (IRQ 7)',
    (0, 0xF162): 'sb_dsp_reset', (0, 0xF2FA): 'sb_detect', (0, 0xF384): 'adlib_wait_status', (0, 0xF3A5): 'adlib_write',
    (0, 0xF3B8): 'adlib_delay', (0, 0xF3CA): 'music_driver_init', (0, 0xF4C1): 'music_driver_close',
    (0, 0xF4AE): 'music_flag_take', (0, 0x89F0): 'music_load', (0, 0x8A41): 'music_song_start',
    (0, 0x8BA2): 'sound_init', (0, 0x8C13): 'sample_init', (0, 0x8C33): 'sound_memory_free', (0, 0x8C96): 'sample_stop',
}
SOUND_C.update({(0, off): f'sound_wrapper (entry {off:04X})' for off in (
    0xF19E, 0xF1A7, 0xF1D8, 0xF1E8, 0xF1FC, 0xF205, 0xF20E, 0xF22B, 0xF23F, 0xF248, 0xF251, 0xF262, 0xF409, 0xF41C,
    0xF42F, 0xF445, 0xF452, 0xF462, 0xF472, 0xF47B, 0xF484, 0xF494, 0xF4A1, 0xF4DB)})
SOUND_C.update({
    (0, 0xFAF3): 'long_division, mode 0 (signed quotient)',
    (0, 0xFAF7): 'long_division, mode 1 (unsigned quotient); the entry is unreferenced',
    (0, 0xFAFC): 'long_division, mode 2 (signed remainder; unreferenced entry), with FB01 (mode 3) and the body FB04',
    (0x11BC, 0x10C6): 'dos_close_handle', (0x11BC, 0x10CB): 'dos_read_at_si',
})
for key, name in SOUND_C.items():
    C_VERSIONS[key] = f'{name} ({"src/dos.c" if key[0] == 0x11BC else "src/soundlayer.c"}), verified by tests/test_soundlayer.py'
    NATIVE.pop(key, None)
    DEAD.pop(key, None)
C_VERSIONS[(0x11BC, 0x10C6)] = 'dos_close_handle (src/dos.c)'
C_VERSIONS[(0x11BC, 0x10CB)] = 'dos_read_at_si (src/dos.c)'

# the unreachable routines, translated too (src/unreachable.c, tests/test_unreachable.py)
UNREACHABLE_C = {
    (0, 0x1814): 'unused_plane_bits', (0, 0x26DF): 'unused_faces_behind', (0, 0x2707): 'helper face_behind in unused_faces_behind',
    (0, 0x296A): 'unused_camera_offset', (0, 0x43B9): 'unused_extras_clear', (0, 0x47A8): 'unused_scale_down',
    (0, 0x47CE): 'unused_project', (0, 0x47FD): 'unused_scale_half; the handler in its bytes (481A) unused_divide_handler',
    (0, 0x5622): 'unused_drop_kind', (0, 0xEF77): 'far thunk to unused_drop_kind', (0, 0x5A6F): 'unused_unpack_far',
    (0, 0x6479): 'unused_marks_undo', (0, 0x79F1): 'unused_model_turn', (0, 0x87E2): 'unused_add_50',
    (0, 0x950D): 'unused_decoy_step', (0, 0xB9C6): 'unused_timer_restore', (0, 0xCA39): 'unused_count_up',
    (0, 0xEE0C): 'unused_protection_fail (the hang reported as 1)', (0, 0xF5CD): 'unused_parse_decimal',
    (0, 0xFA10): 'unused_args_restart', (0, 0xFA88): 'unused_decimal_backwards', (0x11BC, 0x110E): 'unused_translate',
    (0x11BC, 0x1B27): 'unused_text3_vga', (0x11BC, 0x1E95): 'unused_weapon_icon_redraw',
}
for key, name in UNREACHABLE_C.items():
    C_VERSIONS[key] = f'{name} (src/unreachable.c); unreachable: {DEAD.get(key, "no path reaches it")}'
    DEAD.pop(key, None)

# The FM music driver of segment 10BB (Creative's SBFMDRV for CMF songs, built into TERM.EXE),
# translated against the machine interface (src/fmdrv.c, tests/test_fmdrv.py, 2026-11-20)
FMDRV_C = {
    0x0000: ('fmdrv_entry', 'fmdrv_call (the dispatcher 0D28 by BX)'),
    0x05D2: ('fmdrv_set_vector', 'vector_set, inside fmdrv_call'),
    0x05E7: ('fmdrv_get_vector', 'vector_get, inside fmdrv_call'),
    0x05FA: ('fmdrv_set_timer', 'helper set_timer'),
    0x060B: ('fmdrv_opl_write', 'helper opl (the delay loops after each port write left out)'),
    0x0631: ('fmdrv_silence', 'helper silence (writes register 83h nine times: AL reloaded before use)'),
    0x067A: ('fmdrv_voices_init', 'helper voices_init (the C0h registers missed: op + voice written)'),
    0x06E3: ('fmdrv_set_status', 'helper set_status'),
    0x06EE: ('fmdrv_load_instrument', 'helper load_instrument'),
    0x07A0: ('fmdrv_read_number', 'helper read_number (MIDI variable length)'),
    0x07D0: ('fmdrv_skip', 'helper skip'),
    0x07EF: ('fmdrv_voice_for', 'helper voice_for (released, free, any released, else the oldest)'),
    0x086F: ('fmdrv_melodic', 'helper melodic'),
    0x0881: ('fmdrv_reset', 'helper reset (function 8)'),
    0x08A5: ('fmdrv_play', 'helper play (function 6)'),
    0x0904: ('fmdrv_pause', 'function 9 in fmdrv_call'),
    0x0919: ('fmdrv_resume', 'function 10 in fmdrv_call'),
    0x092B: ('fmdrv_tick', 'helper tick (the events due)'),
    0x0995: ('fmdrv_note_off_event', 'event kind 0 in helper event'),
    0x0A0D: ('fmdrv_note_on_event', 'event kind 1 in helper event'),
    0x0A96: ('fmdrv_drum_on', 'helper drum_on'),
    0x0AF9: ('fmdrv_note_fnum', 'helper note_fnum (the bend by voice; the octave overflow inverted)'),
    0x0B5E: ('fmdrv_controller_event', 'event kind 3 in helper event'),
    0x0B74: ('fmdrv_marker', 'controller 66h in helper event'),
    0x0B7A: ('fmdrv_drums', 'controller 67h in helper event'),
    0x0BAA: ('fmdrv_bend_down', 'controller 69h in helper event'),
    0x0BAC: ('fmdrv_bend_up', 'controller 68h in helper event'),
    0x0BBE: ('fmdrv_skip2', 'event kinds 2 and 6 in helper event'),
    0x0BBF: ('fmdrv_skip1', 'event kind 5 in helper event'),
    0x0BC0: ('fmdrv_skip0', 'the ignored system events in helper event'),
    0x0BC1: ('fmdrv_program_event', 'event kind 4 in helper event'),
    0x0C3B: ('fmdrv_system_event', 'event kind 7 in helper event'),
    0x0C48: ('fmdrv_sysex', 'F0h in helper event (the user trap: the game sets none)'),
    0x0C5E: ('fmdrv_sysex_more', 'F7h in helper event'),
    0x0C69: ('fmdrv_reset_event', 'FCh in helper event'),
    0x0C6D: ('fmdrv_meta', 'FFh in helper event'),
    0x0C83: ('fmdrv_timer_isr', 'fmdrv_timer (its own stack at E12h..E76h not modelled)'),
    0x0CF3: ('fmdrv_keyboard_isr', 'fmdrv_keyboard'),
    0x0D86: ('fmdrv_version', 'function 0 in fmdrv_call'),
    0x0D8A: ('fmdrv_status_address', 'function 1 in fmdrv_call'),
    0x0D9D: ('fmdrv_instruments', 'function 2 in fmdrv_call'),
    0x0DB1: ('fmdrv_stop', 'helper stop'),
    0x0DCF: ('fmdrv_stop_function', 'function 7 in fmdrv_call'),
    0x0DDF: ('fmdrv_system_clock', 'function 3 in fmdrv_call'),
    0x0DE3: ('fmdrv_driver_clock', 'function 4 in fmdrv_call'),
    0x0DEC: ('fmdrv_transpose', 'function 5 in fmdrv_call'),
    0x0DF2: ('fmdrv_user_trap', 'function 11 in fmdrv_call'),
    0x0E76: ('fmdrv_detect_status', 'helper detect_status'),
    0x0E97: ('fmdrv_detect_write', 'helper detect_write'),
    0x0EAA: ('fmdrv_detect_delay', 'the five status reads in helper detect_write'),
    0x0EBB: ('fmdrv_detect', 'helper detect'),
    0x0EF5: ('fmdrv_count_isr', 'the interrupt handler in helper calibrate (MachineServices.irq)'),
    0x0EFE: ('fmdrv_calibrate', 'helper calibrate'),
    0x0F70: ('fmdrv_setup', 'part of helper init'),
    0x0FA1: ('fmdrv_take_interrupts', 'part of helper init'),
    0x0FD2: ('fmdrv_give_interrupts', 'function FFFEh in fmdrv_call'),
    0x0FED: ('fmdrv_init', 'helper init (function FFFFh)'),
    0x1000: ('fmdrv_shutdown', 'function FFFEh in fmdrv_call'),
    0x1009: ('fmdrv_port_base', 'function FFFDh in fmdrv_call'),
}
for off, (name, c) in FMDRV_C.items():
    FUNCS.setdefault((0x10BB, off), name)
    C_VERSIONS[(0x10BB, off)] = f'{c} (src/fmdrv.c), verified by tests/test_fmdrv.py'
DEAD[(0x10BB, 0x0DFF)] = ('no reference: a function that would give back a saved vector (10BB:000E + 4 AL), '
                          'in no table of the driver')
