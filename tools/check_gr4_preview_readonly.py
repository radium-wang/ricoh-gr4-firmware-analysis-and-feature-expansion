#!/usr/bin/env python3
"""Bounded pointer/identity/failure models for optional preview observations."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from audit_xpan_paths import EXPECTED_SHA256, file_offset
from mtp_factory_capture_state_readonly import preview_information, ROOT


def check(raw):
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256
    preview, pointer, vtable = 0x59CD6290, 0x59A550F0, 0x53FD1830
    links = struct.pack('<4I', 0x59A589F8, 0x59A55048, pointer, 0x59A4C000)
    cases = []
    ranges = {(pointer+offset, size) for offset, size in
              ((4, 0x40), (0x78, 0x18), (0x1CD4, 4), (0x24E8, 0x14), (0x2540, 0x30))}
    for fault in ('normal', 'wrong-class', 'wrong-ROM', 'short-field', 'changed-owner', 'null-pointer'):
        reads = []; supplied = bytearray(links)
        if fault == 'null-pointer': supplied[8:12] = bytes(4)
        def read(address, size):
            reads.append((address, size))
            if (address, size) == (pointer, 4):
                return struct.pack('<I', 0 if fault == 'wrong-class' else vtable)
            if (address, size) == (vtable, 0x18):
                data = raw[file_offset(vtable):file_offset(vtable)+0x18]
                return bytes(0x18) if fault == 'wrong-ROM' else data
            if (address, size) == (preview+0x398, 0x10):
                return bytes(0x10) if fault == 'changed-owner' else links
            if (address, size) not in ranges:
                raise AssertionError('unexpected read: %x + %x' % (address, size))
            return bytes(size-1 if fault == 'short-field' else size)
        rejected = False
        try: result = preview_information(read, raw, preview, bytes(supplied))
        except ValueError: rejected = True
        if fault == 'normal':
            assert not rejected and len(result['fields']) == 5
            assert not result['atomic_snapshot_verified'] and not result['mutex_acquired']
            assert not result['units_and_LCD_pixel_mapping_verified']
            assert sum(n for a, n in reads if (a, n) in ranges) == 160
        else:
            assert rejected
            if fault == 'null-pointer': assert not reads
            if fault in ('wrong-class', 'wrong-ROM'):
                assert not any((a, n) in ranges for a, n in reads)
        cases.append({'case': fault, 'read_requests': len(reads),
                      'rejected': rejected, 'camera_access': False})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cases = check((ROOT/'samples/gr4_decoded.bin').read_bytes())
    with args.out.open('x') as handle:
        json.dump({'schema': 'gr4-preview-readonly-model-v1', 'passed': True,
                   'cases': cases, 'hardware_checked': False}, handle, indent=2)
        handle.write('\n')
    print('6 bounded preview read models passed; no camera access')


if __name__ == '__main__':
    main()
