"""Record actual binocular/scope file loads and complete overlay drawing."""
import gzip
import os
import pickle
import capture
import dosemu
import travel_trace


def main():
    base = pickle.load(gzip.open(os.path.join(capture.CAPDIR, 'systemhud.pkl.gz'), 'rb'))[0]
    states = []
    for scope in range(2):
        m = capture.restore(base)
        m.cs, m.ip = dosemu.LOAD_SEG, 0x76B4
        for off, value in [(0x8161, 0), (0x5C09, 255), (0x812A, 0),
                           (0xAAA0, 255), (0x114F, 0), (0x1150, scope)]:
            m.ds_write(off, bytes([value]))
        states.append(capture.state_of(m))
    path = os.path.join(capture.CAPDIR, 'hudoptics_services.pkl.gz')
    with gzip.open(path, 'wb') as f:
        pickle.dump(states, f)
    for i in range(2):
        travel_trace.record(i, 'hudoptics_services', f'hudoptics{i}_realtrace',
                            entries=[(0, 0xFACE, False)], arguments={0xFACE: ['dx']})


if __name__ == '__main__':
    main()
