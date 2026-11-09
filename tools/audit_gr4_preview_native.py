#!/usr/bin/env python3
"""Pin original preview coordinate and guide-resource routes; no camera access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch

PINS = [
    (0x53216260, 308, '7dfd7ee0fcdb3202d9a3b646e8d6cd8d59cb19f350554fcdbd4c901082148823'),
    (0x53577BDC, 144, '20915cb377f1c8ac22315b70c68edd40eb34291495f653b24135470779f7a21f'),
    (0x53576E38, 20, '7d36b773723cb4566ccb9f2942c8c6c4b1ea13e7e0ae099ab02b67e56a0a6fa1'),
    (0x538876B8, 1680, 'b687a485203f82ef3fc8a212345dc7f061634f36455762b93920b7dcca1e4c3b'),
    (0x53887474, 116, 'fb8b0835b7898d08696e7ecad7497a69f107e8fa2c2cc8e9fe76674a721e37a6'),
    (0x5362E49C, 64, '7e6936bc12c6da1269082bcdc8c17201dd8a03afd2320ab146289871ba969018'),
    (0x53637E48, 52, '6ccb760621acc1a664e822c3dff40defe116fc73423aa5dc90bc26e8a999c005'),
    (0x5388A8C4, 144, 'ed79bfcb237ad138abda260d63fa9ce7ae7ff5b33b6c129edb4698269c223797'),
]


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported firmware sample')
    for address, length, digest in PINS:
        if hashlib.sha256(raw[file_offset(address):file_offset(address)+length]).hexdigest() != digest:
            raise ValueError('native preview pin changed: %08x' % address)
    for address, text in [(0x53DB2740, b'UpdateGuideChangeAspect\0'),
                          (0x53FD1860, b'UpdataCropVirtualWindow\0'),
                          (0x53FD1848, b'19LiveViewInformation\0')]:
        require(raw, file_offset(address), text, 'preview name')
    require(raw, file_offset(0x5362E53C), struct.pack('<f', 8192.0), 'crop scale literal')
    for origin, target in [(0x53216C2C, 0x53216260), (0x53216334, 0x53577BDC),
                           (0x53577C14, 0x53576E38), (0x53577C24, 0x53576E38),
                           (0x5362E4D4, 0x538876B8), (0x53637E78, 0x538876B8),
                           (0x538876D8, 0x53886694)]:
        require_branch(raw, origin, target)
    return {'schema': 'gr4-preview-native-audit-v1', 'firmware_sha256': EXPECTED_SHA256,
            'pins': [{'address': hex(a), 'bytes': n, 'sha256': s} for a, n, s in PINS],
            'guide': {'entry': '0x53216260', 'refresh_caller': '0x53216c2c',
                      'widget_offset': '0x170', 'base_resource': '0x1db',
                      'aspect_resources': ['0xf1', '0x15b', '0xf0', '0x15d'],
                      'aspect_4_asserts': True, 'aspect_5_hides': True,
                      'resource_leaf_stores_u16': True, 'custom_icon_installed': False},
            'virtual_window': {'entry': '0x538876b8', 'mutex_offset': '0x24e8',
                               'crop_input_scale': 8192, 'information_link_offset': '0x3a0',
                               'callers': ['0x5362e4d4', '0x53637e78'],
                               'window_offsets': ['0x24', '0x28', '0x2c', '0x30',
                                                  '0x34', '0x38', '0x3c', '0x40'],
                               'lcd_pixel_crop_proven': False, 'af_coordinate_effects_pending': True},
            'camera_access': False, 'preview_ready': False, 'icon_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, default=Path('samples/gr4_decoded.bin'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.sample.read_bytes())
    if args.out.exists():
        raise ValueError('refusing to replace prior evidence')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print('Original preview/guide route pins verified; not installed')


if __name__ == '__main__':
    main()
