#!/usr/bin/env python3
"""Verify original main/ADJ crop-menu callbacks offline; never write a device."""
import argparse
import json
import struct
from pathlib import Path

from audit_xpan_paths import audit, file_offset, require
from audit_sd_shell_path import require_branch


def audit_menu(raw):
    # Full sample identity and existing aspect/crop paths are verified first.
    audit(raw)
    main_base = 0x53D9F714
    main = main_base + 19 * 0x5C
    assert main == 0x53D9FDE8
    callbacks = {0x18: 0x531BE354, 0x20: 0x531BB288,
                 0x28: 0x531BAFA0, 0x30: 0x531BA154}
    for delta, target in callbacks.items():
        require(raw, file_offset(main+delta), struct.pack('<II', target, 0),
                'main crop menu member callback')
    require(raw, file_offset(0x531BE08C), bytes.fromhex('5c 30 a0 e3'),
            'main menu descriptor stride')
    require(raw, file_offset(0x531BE098), bytes.fromhex('30 30 90 e5'),
            'main menu count member offset')
    require(raw, file_offset(0x531BA154), bytes.fromhex('03 00 a0 e3 1e ff 2f e1'),
            'main crop option count three')
    require_branch(raw, 0x531BAFD0, 0x532F862C, link=False)
    require_branch(raw, 0x531BE394, 0x53398538)
    require(raw, file_offset(0x53DA3790), struct.pack('<II', 0x531CF2A0, 0),
            'secondary crop count callback')
    require(raw, file_offset(0x531CF2A0), bytes.fromhex('03 00 a0 e3 1e ff 2f e1'),
            'secondary crop option count three')
    require(raw, file_offset(0x53DA37A8), struct.pack('<II', 0x531D2FA8, 0),
            'secondary crop selection callback')
    require_branch(raw, 0x531D2FD8, 0x532F862C, link=False)
    require_branch(raw, 0x532F8664, 0x532F8548)
    require_branch(raw, 0x53276F74, 0x53759EF0, link=False)
    require(raw, file_offset(0x53759F10), bytes.fromhex('e0 20 a0 e3'),
            'crop update event ID')
    table = struct.unpack_from('<4I', raw, file_offset(0x53DBAC10))
    assert table == (0x3F800000, 0x3FA04F89, 0x3FE23119, 30)
    count_uses = raw[:file_offset(0x5437B640)].count(struct.pack('<I', 0x531BA154))
    return {'requested_crop_options': ['OFF', '35mm', '50mm'],
            'main_descriptor': hex(main), 'main_descriptor_stride': '0x5c',
            'main_crop_index': 19, 'existing_count': 3,
            'main_callbacks': {hex(k): hex(v) for k, v in callbacks.items()},
            'secondary_crop_callbacks': {'count': '0x531cf2a0', 'set': '0x531d2fa8'},
            'main_count_callback_pointer_occurrences': count_uses,
            'table_fourth_word': '0x0000001e; not a fourth crop factor',
            'crop_property_setter': '0x532f862c',
            'crop_update_event': '0xe0',
            'implementation_direction': 'keep the native crop menu at three options; '
                'add XPAN only as the fifth aspect-menu option, with guarded '
                'projection to a native 3:2 source',
            'patched_or_installed': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('sample', type=Path)
    args = p.parse_args()
    print(json.dumps(audit_menu(args.sample.read_bytes()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
