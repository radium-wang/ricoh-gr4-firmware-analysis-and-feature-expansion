#!/usr/bin/env python3
"""Audit initial ARM section mappings in the pinned GR IV RTOS image."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from audit_xpan_paths import EXPECTED_SHA256, file_offset, require

TABLE = 0x53004000
SAMPLES = {
    0x53000000: 0x5301C826,
    0x53100000: 0x5311C826,
    0x53D00000: 0x53D1C826,
    0x55000000: 0x55014C26,
    0x59000000: 0x59014C26,
    0x5A000000: 0x5A014C26,
    0x5B000000: 0x5B014C26,
}


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported firmware sample')
    require(raw, file_offset(0x530002D0), struct.pack('<I', 0xEE020F10),
            'reset writes TTBR0')
    require(raw, file_offset(0x53000434), struct.pack('<I', TABLE),
            'initial TTBR0 points to in-image table')
    require(raw, file_offset(0x53000438), struct.pack('<I', 0x55555555),
            'initial domain access values')
    rows={}
    for va,expected in SAMPLES.items():
        descriptor=struct.unpack_from('<I',raw,file_offset(TABLE)+4*(va>>20))[0]
        if descriptor!=expected or descriptor&3!=2:
            raise ValueError(f'unexpected section descriptor for {va:#x}')
        rows[hex(va)]={'descriptor':hex(descriptor),
                       'identity_mapped':descriptor&0xfff00000==va,
                       'AP_bits':((descriptor>>15)&1)<<2 | (descriptor>>10)&3,
                       'XN_bit':(descriptor>>4)&1,
                       'domain':(descriptor>>5)&15}
    # Scan every first-level section, not just the sampled identity mappings,
    # for a writable virtual alias of the immutable menu/callback sections.
    target_physical_sections = (0x53100000, 0x53D00000)
    target_aliases = {hex(physical): [] for physical in target_physical_sections}
    for index in range(4096):
        descriptor = struct.unpack_from('<I',raw,file_offset(TABLE)+4*index)[0]
        if descriptor&3 != 2:
            continue
        physical = descriptor&0xfff00000
        if physical in target_physical_sections:
            target_aliases[hex(physical)].append({
                'virtual':hex(index<<20),
                'AP_bits':((descriptor>>15)&1)<<2 | (descriptor>>10)&3,
                'XN_bit':(descriptor>>4)&1,
            })
    return {'sample_sha256':EXPECTED_SHA256,
            'initial_TTBR0':hex(TABLE),'initial_DACR':hex(0x55555555),
            'section_samples':rows,
            'menu_and_callback_section_aliases':target_aliases,
            'writable_alias_found_in_initial_table':any(
                item['AP_bits'] in (1,2,3) for aliases in target_aliases.values() for item in aliases),
            'inference':'initial image maps 0x53 code/data read-only and 0x55/0x59/0x5A/0x5B as writable, with XN clear',
            'limits':['a task may switch TTBR0 later',
                      'writable and executable mapping does not grant ownership of any free RAM',
                      'does not establish cache publication, cross-core synchronization or safe hook installation',
                      'no device access or modification']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample',type=Path)
    args=parser.parse_args()
    print(json.dumps(audit(args.sample.read_bytes()),indent=2))
