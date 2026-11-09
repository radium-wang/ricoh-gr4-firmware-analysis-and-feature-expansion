#!/usr/bin/env python3
"""Pin the original 16:9 window-selection and message-publication route offline."""
import argparse
import hashlib
import json
from pathlib import Path
from audit_xpan_paths import EXPECTED_SHA256, file_offset
from audit_sd_shell_path import require_branch
from audit_gr4_preview_native import audit as audit_coordinates

PINS = [
    (0x5362E3F0, 100, 'e70b17ccdf17e573134451d469c6bbe3105a67912c61d0f841bec003e3731b74'),
    (0x5362E454, 232, '03a60824b76c70d2b0961f0ca1254c086f8815467ea1c07ca39e8dcea2f1bf08'),
    (0x536342BC, 104, 'baaa7aadd65492372c6542cbde92021cb837643a6f6b5133a47d173fc1662a07'),
    (0x53887D48, 140, 'a1e547b327b6e0f7bd4b3698c6e64d267afdd8236c0443411dd2fe8ae26beec5'),
    (0x53887DD4, 176, 'ce0dc60f6cba4d4133b4a71b6bfa6361bcd5ba951988028bb82b40571ba4e338'),
    (0x53754730, 164, '9824258979344cab0d9946e819a8310ab4882c020d3e202a82e9fc30402e6178'),
    (0x5374D894, 56, '674dbb2738dfe2c5e006335b9c6451b2cc7e2ed0a605e63f3fabfc3ac1846117'),
    (0x537614F0, 48, 'a02bbca70bdafa3b4a61af150cd628433c88a3e1b041bb7ac09672b1db1c7e91'),
    (0x53761418, 216, 'e43c81880d93e0ea52f59057cb481c5bd76fec8a7265dd706c1175a41181db78'),
    (0x5375CD2C, 120, 'c4f593d4d63f98de07849c78ae771e5d9c85b338c6598a099bd559adf2596578'),
    (0x5377AD5C, 76, 'd5fe08adbc0aea588cbac220bd1aea7a098c43e3d5eec3791f4b4a0cde2b4132'),
]


def audit(raw):
    audit_coordinates(raw)
    for address, length, digest in PINS:
        if hashlib.sha256(raw[file_offset(address):file_offset(address)+length]).hexdigest() != digest:
            raise ValueError('selection/publication pin changed: %08x' % address)
    for origin, target in [(0x5362E4D4, 0x538876B8), (0x5362E4E4, 0x5362E3F0),
                           (0x5362E4F8, 0x53887D48), (0x53634304, 0x53887D48),
                           (0x53634320, 0x53887D48), (0x53887D5C, 0x53886694),
                           (0x53887DEC, 0x53886694), (0x53887E34, 0x53754730),
                           (0x5375475C, 0x538E09B0), (0x537547A4, 0x538DD430),
                           (0x5374D8AC, 0x537614F0), (0x537614F0+0x14, 0x53761418),
                           (0x53761514, 0x5375CD2C), (0x5376144C, 0x5377AD5C)]:
        require_branch(raw, origin, target,
                       link=origin not in (0x5362E4F8, 0x53634304, 0x53634320))
    return {'schema': 'gr4-preview-selection-audit-v1', 'firmware_sha256': EXPECTED_SHA256,
            'pins': [{'address': hex(a), 'bytes': n, 'sha256': s} for a, n, s in PINS],
            'selector': {'chooser': '0x5362e3f0', 'process_chooser': '0x536342bc',
                         'store': '0x53887d48', 'full': 0, 'crop_including_16_9': 1,
                         'special': 2, 'source_offsets': ['0x4', '0x24', '0x54'],
                         'selected_offset': '0x64', 'word_order': ['W', 'H', 'X', 'Y']},
            'publication': {'entry': '0x53887dd4', 'producer': '0x53754730',
                            'service_offset': '0x253c', 'message': '0x84',
                            'payload_bytes': 16, 'payload_alloc': '0x538e09b0',
                            'send': '0x538dd430', 'LCD_consumer_verified': False},
            'property_receiver': {'runtime_set_slot': '0x55019318',
                                  'expected_set_method': '0x5374d894',
                                  'manager_link': '0x518', 'pending_reference': '0x4',
                                  'current_window_offset': '0x6c0',
                                  'latest_input_window_offset': '0xf08',
                                  'changed_token': '0x28501f01',
                                  'commit': '0x5375cd2c', 'copy_bytes': '0x1090',
                                  'runtime_dispatch_read_required': True,
                                  'notification_delivery_verified': False},
            'camera_access': False, 'PREVIEW_READY': False, 'xpan_installed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, default=Path('samples/gr4_decoded.bin'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.sample.read_bytes())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as handle:
        handle.write(json.dumps(report, indent=2)+'\n')
    print('Original 16:9 selection and publication pins verified; no camera access')


if __name__ == '__main__':
    main()
