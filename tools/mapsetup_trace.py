"""Record real resource effects of local map setup/initialization."""
from travel_trace import record
ENTRIES = [(0, off, False) for off in [0x0C6B, 0x6962, 0xFAAF, 0x7AB6]]
ARGS = {0x0C6B: ('ax',), 0x6962: ('dx',), 0xFAAF: ('dx', 'bx'), 0x7AB6: ()}
if __name__ == '__main__':
    record(capture_name='mapsetup', output_name='mapsetup_realtrace', entries=ENTRIES, arguments=ARGS)
    record(capture_name='mapbegin', output_name='mapbegin_realtrace', entries=ENTRIES, arguments=ARGS, stop=0xCC43)
    area_entries = [(0, off, False) for off in [0x7AAF, 0x6962, 0xFACE, 0x7AB6]]
    area_args = {0x7AAF: (), 0x6962: ('dx',), 0xFACE: ('dx', 'bx'), 0x7AB6: ()}
    video = [(0xCF77, 0xCF79, 0xFF10, ('ax',))]
    for name, stop in [('mapsetup_area', None), ('mapbegin_area', 0xD021)]:
        for overlay in [0, 1]:
            record(capture_name=name, output_name=name + str(overlay) + '_realtrace',
                   entries=area_entries, arguments=area_args, inline=video,
                   changes={0xE1EE: bytes([255 if overlay else 0])}, stop=stop)
