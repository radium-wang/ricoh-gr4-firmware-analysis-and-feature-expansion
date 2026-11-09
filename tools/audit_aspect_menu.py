#!/usr/bin/env python3
"""Read-only audit of separate ADJ/settings aspect menus; no camera or SD access."""
import argparse
import json
import struct
from pathlib import Path

from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch
import hashlib


def audit_aspect_menu(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('only the pinned GR IV 01.11.10.07 sample is supported')
    base = 0x53D9F714
    stride = 0x5C
    aspect = base + 5 * stride
    crop = base + 19 * stride
    assert aspect == 0x53D9F8E0 and crop == 0x53D9FDE8
    aspect_callbacks = {
        0x18:0x531BE2EC, 0x20:0x531BB250,
        0x28:0x531BAF70, 0x30:0x531BA14C,
    }
    for offset, callback in aspect_callbacks.items():
        require(raw, file_offset(aspect+offset), struct.pack('<II',callback,0),
                f'aspect menu callback at +{offset:#x}')
    secondary=0x53DA3744
    secondary_callbacks={
        0x00:0x531CF298, 0x08:0x531D0CCC,
        0x18:0x531D2F70, 0x20:0x531D4898,
        0x28:0x531D8FFC, 0x30:0x531D2FA0,
    }
    for offset,callback in secondary_callbacks.items():
        require(raw,file_offset(secondary+offset),struct.pack('<II',callback,0),
                f'secondary aspect descriptor callback at +{offset:#x}')
    require(raw,file_offset(0x531CF298),bytes.fromhex('04 00 a0 e3 1e ff 2f e1'),
            'secondary aspect path also exposes four options')
    require(raw,file_offset(0x531D2F88),bytes.fromhex('34 30 0b e3'),
            'secondary setter reads same four-entry order table')
    require(raw,file_offset(0x531D0CE8),bytes.fromhex('34 30 0b e3'),
            'secondary label reads same four-entry order table')
    require_branch(raw,0x531D0CF8,0x5337FBAC)
    require_branch(raw,0x531D2F9C,0x532F8490,link=False)
    require_branch(raw,0x531D900C,0x531D2F70)
    require_branch(raw,0x531D48B8,0x5329C09C)
    crop_count=0x531BA154
    require(raw,file_offset(crop+0x30),struct.pack('<II',crop_count,0),
            'separate crop menu count callback')
    require(raw,file_offset(crop_count),bytes.fromhex('03 00 a0 e3 1e ff 2f e1'),
            'crop remains three options')
    require(raw,file_offset(aspect_callbacks[0x30]),
            bytes.fromhex('04 00 a0 e3 1e ff 2f e1'),
            'aspect currently exposes four options')
    order=raw[file_offset(0x53DBB034):file_offset(0x53DBB034)+4]
    if order != bytes((0,1,3,2)):
        raise ValueError('original aspect menu order differs')
    require_branch(raw,0x531BE330,0x5338143C)
    require_branch(raw,0x531BAF9C,0x532F8490,link=False)
    require(raw,file_offset(0x531BE31C),bytes.fromhex('34 30 0b e3'),
            'label callback reads original four-entry order table')
    require(raw,file_offset(0x531BB26C),bytes.fromhex('34 30 0b e3'),
            'selected callback reads original four-entry order table')
    require(raw,file_offset(0x531BAF88),bytes.fromhex('34 30 0b e3'),
            'setter callback reads original four-entry order table')
    require(raw,file_offset(0x5325AE58),bytes.fromhex('03 20 d3 e5'),
            'aspect cycle reads only the fourth entry')
    require(raw,file_offset(0x5325AE60),bytes.fromhex('05 00 a0 13'),
            'unrecognized aspect ID selects index five, outside original table')
    return {
        'sample_sha256': EXPECTED_SHA256,
        'adj_aspect_descriptor':hex(aspect),'adj_aspect_row_index':5,
        'settings_aspect_row':hex(0x53DA3738),'settings_aspect_row_index':34,
        'settings_aspect_callbacks_start':hex(secondary),
        'controller_identity_audit':'tools/audit_gr4_ui_native_routes.py',
        'original_menu_order_ids': list(order),
        'original_menu_order_labels': ['3:2','4:3','1:1','16:9'],
        'requested_menu_order_labels': ['3:2','4:3','1:1','16:9','XPAN'],
        'aspect_callbacks': {hex(k):hex(v) for k,v in aspect_callbacks.items()},
        'settings_aspect_callbacks':{hex(k):hex(v) for k,v in secondary_callbacks.items()},
        'separate_crop_menu': hex(crop), 'crop_options': ['OFF','35mm','50mm'],
        'adding_one_to_original_count_alone_is_unsafe': True,
        'native_aspect_consumers_accept_only_0_to_3': True,
        'required_native_adapters': [
            'settings and ADJ aspect menu count/label/selection/set and cycle',
            'guarded XPAN state with native aspect 3:2 projection',
            'preview, JPEG, DNG, status/icon and persistence',
            'loader, synchronization and independent recovery'],
        'patched_or_installed': False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sample',type=Path)
    args=p.parse_args()
    print(json.dumps(audit_aspect_menu(args.sample.read_bytes()),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
