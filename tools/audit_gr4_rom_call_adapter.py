#!/usr/bin/env python3
"""Offline evidence for a native three-argument callback adapter. No installation."""

import argparse
import hashlib
import json
import struct
from pathlib import Path

from audit_sd_shell_path import require_branch
from audit_xpan_paths import EXPECTED_SHA256, file_offset, require


ADAPTER = 0x53202AF0
ADAPTER_BYTES = bytes.fromhex(
    '003090e5042093e5100093e5010012e3c2008000c2c0901700109315'
    'c200801001c09c1700c093050c1093e5082093e51cff2fe1')
SEND_SLOT = 0x553B1948
RESPONSE_SLOT = 0x553B1A30
SEND_ORIGINAL = 0x538EF3C8
RESPONSE_ORIGINAL = 0x538EF9F0
RESPONSE_BUFFER = 0x553B1990
INTEGER_NAMES = 0x553B2AB8
INTEGER_VALUES = 0x553B26A4


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported firmware sample')
    require(raw, file_offset(ADAPTER), ADAPTER_BYTES, 'native callback adapter')
    require(raw, file_offset(0x53B15808), bytes.fromhex(
        '3b2545e300c094e53b3545e3000082e518c00be5001083e5'),
        'script initialization writes both runtime callback slots')
    require(raw, file_offset(0x53B19820), bytes.fromhex(
        '483901e3460f4be23b3545e3003093e533ff2fe1'),
        'sendln callback receives its 256-byte stack string as r0')
    require_branch(raw, 0x53B19834, 0x53B18018)
    require(raw, file_offset(0x53B19838), bytes.fromhex(
        '303a01e3900901e33b3545e33b0545e3003093e533ff2fe1'
        '000050e32000000a'), 'nonzero response callback skips response-string consumer')
    require(raw, file_offset(0x53B1E978), bytes.fromhex('001183e71eff2fe1'),
            'integer result storage')
    require_branch(raw, 0x53B15854, 0x53B1E608)
    require(raw, file_offset(0x53EA2FC4), b'result\0', 'first integer variable name')
    require(raw, file_offset(0x538C9760), bytes.fromhex('0300a0e31eff2fe1'),
            'immutable return-3 leaf')
    require_branch(raw, 0x53B1FEE4, 0x53B1FDE8, link=False)
    require_branch(raw, 0x53B1FE40, 0x53B1E124)
    require_branch(raw, 0x53B173CC, 0x53B1FEE0)
    require(raw, file_offset(0x53B17444), bytes.fromhex(
        '0100f2e5013053e2011480e0fbffff1a'), 'str2code packs bytes most-significant first')
    return {'sample_sha256': EXPECTED_SHA256, 'adapter': hex(ADAPTER),
            'record': ['target', 'member_adjustment=0 for direct call', 'argument_r2',
                       'argument_r1', 'argument_r0'],
            'entry_argument_r0': 'pointer to one word holding the record address',
            'direct_call': 'loads r0/r1/r2 from record +16/+12/+8; tail-calls record[0]',
            'script_send_slot': hex(SEND_SLOT), 'script_response_slot': hex(RESPONSE_SLOT),
            'script_response_buffer': hex(RESPONSE_BUFFER),
            'integer_names_holder': hex(INTEGER_NAMES), 'integer_values': hex(INTEGER_VALUES),
            'binary_payload_self_check': 'str2code shares sendln literal parser; 0x90193B55 signed integer',
            'candidate_transport': 'TTL sendln supplies a stack string; USB can inspect RAM',
            'adapter_executed_on_camera': False, 'camera_installable': False,
            'limits': ['Binary TTL input and callback synchronization not verified on camera.',
                       'Response buffer is used by the interpreter; it is not unowned scratch RAM.',
                       'Ordinary shell command handlers receive argc/argv, not this record ABI.',
                       'A new ROM adapter test needs a controlled script and callback restoration.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.sample.read_bytes()), indent=2))
