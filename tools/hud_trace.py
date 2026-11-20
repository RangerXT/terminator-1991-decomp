"""Record complete E170 with actual bitmap IO and target-scan effects.

Sound bodies are replaced by RET, as in the HUD unit comparisons. Their requests
remain in the trace and must match native EV_SOUND events. Input cases explicitly
force page restoration and the no-contact and visible-contact scans; they are not natural gameplay input.
"""
import gzip
import os
import pickle
import struct
import capture
import dosemu
import travel_trace


def main():
    originals = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'systemhud.pkl.gz'), 'rb'))
    states = []
    for i in range(4):
        m = capture.restore(originals[i])
        def byte(off, value):
            m.ds_write(off, bytes([value]))
        m.wb(dosemu.LOAD_SEG, 0x89A2, b'\xc3')
        for off, value in [(0x5BE6, 255 if i else 0), (0x5C0F, 0), (0xE434, 0),
                           (0x114E, 255 if i else 0), (0x115D, 0), (0x1140, 0),
                           (0x118E, 1 if i >= 2 else 0), (0xE4FD, 1),
                           (0xE437, 1), (0xE438, 0), (0x1141, 0)]: byte(off, value)
        m.ds_write(0xB64E, struct.pack('<H', 1 if i == 3 else 0))
        if i == 3:
            # Controlled visible contact and empty collision map: actual scan/line bodies run.
            m.wb(m.rw(m.DATA_SEG, 0x91B2), 0, bytes(0x9000))
            m.ds_write(0xB18E, struct.pack('<9H', 0x8100, 0, 128, 8, 311, 8, 110, 0, 0))
            m.ds_write(0x8100, struct.pack('<6H', 0, 0, 0, 0x2000, 0, 100))
        states.append(capture.state_of(m))
    path = os.path.join(capture.CAPDIR, 'systemhud_services.pkl.gz')
    with gzip.open(path, 'wb') as f:
        pickle.dump(states, f)
    for i in range(4):
        travel_trace.record(i, 'systemhud_services', f'systemhud{i}_realtrace',
                            entries=[(0, off, False) for off in [0x6962, 0xA07B, 0x89A2]],
                            arguments={0x6962: ['dx'], 0xA07B: [], 0x89A2: ['ax']},
                            result_registers={0xA07B: 'si'})


if __name__ == '__main__':
    main()
