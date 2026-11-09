#!/usr/bin/env python3
"""Exact-sample JPEG source/destination routing evidence; no camera access."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported sample')
    require(raw, file_offset(0x53ECFCDC), b'22BackResizeMacroProcess\0', 'BackResize RTTI')
    require(raw, file_offset(0x53ECFC78), struct.pack('<I', 0x536FB8AC), 'module callback virtual +20')
    require_branch(raw, 0x536FB938, 0x536FB694, link=False)
    require_branch(raw, 0x536FB7DC, 0x536FB040)
    require_branch(raw, 0x536FB820, 0x536FB0DC)
    require_branch(raw, 0x536FB88C, 0x536FB0DC)
    pins = [(0x53711458, 8, 'source dimension dispatch'),
            (0x53711464, 40, 'source config B70/B72 stores'),
            (0x53711498, 12, 'separate full-source query'),
            (0x536FB224, 24, 'destination dimension dispatch/stores'),
            (0x536FB064, 108, 'source window and equal plane offsets')]
    expected = {0x53711458: '08c09ce53cff2fe1',
                0x53711498: '08c09ce5000ab7ee3cff2fe1',
                0x536FB224: '08c09ee53cff2fe1bc225be1ba325be1b021c7e1b231c7e1'}
    for address, encoded in expected.items():
        require(raw, file_offset(address), bytes.fromhex(encoded), 'native dispatch pin')
    return {'schema': 'gr4-jpeg-native-routing-audit-v1', 'sample_sha256': EXPECTED_SHA256,
            'BackResize_vtable': '0x53ecfc58', 'module_callback_slot': '0x20',
            'module_callback': '0x536fb8ac', 'processing_body': '0x536fb694',
            'source_config_pointer_in_request': '0x34',
            'source_config_pointer_in_process': '0x8a48',
            'source_window_config_fields': ['0xb70', '0xb72'],
            'source_window_dimension_return_address': '0x53711460',
            'destination_dimension_return_address': '0x536fb22c',
            'full_source_return_addresses_must_delegate': ['0x537114a4', '0x5387e1c4'],
            'pins': [{'address': hex(a), 'bytes': n, 'role': label,
                      'sha256': hashlib.sha256(raw[file_offset(a):file_offset(a)+n]).hexdigest()}
                     for a, n, label in pins],
            'descriptor_pixel_data_ownership_and_worker_synchronization_verified': False,
            'all_capture_types_and_thumbnail_routes_verified': False,
            'shared_calculator_clone_requires_all_users_drained': True,
            'camera_installable': False, 'camera_accessed': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): raise ValueError('immutable output exists')
    result = audit((Path(__file__).resolve().parents[1]/'samples/gr4_decoded.bin').read_bytes())
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print('Saved:', a.output)
