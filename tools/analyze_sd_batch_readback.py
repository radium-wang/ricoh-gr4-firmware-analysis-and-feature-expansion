#!/usr/bin/env python3
"""Read an already copied XPAN batch directory; never access or modify a camera."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from build_sd_batch_probe import FIXED, OUTPUTS

SAMPLE_SHA = 'c4e597c7c9ca1bc181b30e35139ed90a4fd876ddcca14f12be0e00b6702233ae'


def analyze(root, sample):
    raw = sample.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SAMPLE_SHA:
        raise ValueError('wrong decoded firmware sample')
    files = {name: (root / name).read_bytes() for name in OUTPUTS
             if (root / name).is_file()}
    fixed = {}
    for name, address, size, _ in FIXED:
        data = files.get(name)
        item = {'present': data is not None, 'expected_bytes': size}
        if data is not None:
            item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            if address < 0x55000000:
                offset = address - 0x53000000 + 0x17D10
                item['matches_sample'] = data == raw[offset:offset+size]
        fixed[name] = item

    report = {'files': fixed, 'missing': [n for n in OUTPUTS if n not in files],
              'status': files.get('XPBATCH.TXT', b'').decode('ascii', errors='replace'),
              'finished': b'XPAN batch finished' in files.get('XPBATCH.TXT', b'')}
    states = {}
    for name in ('XPPROP.BIN', 'XPPEND.BIN'):
        data = files.get(name, b'')
        if len(data) == 192:
            states[name] = {'aspect_id': data[0x23],
                            'crop_factor': struct.unpack_from('<f', data, 0x24)[0]}
    report['imaging_properties'] = states
    logger = files.get('XPLOGST.BIN', b'')
    if len(logger) == 128:
        report['RTOS_logger_store_flag'] = struct.unpack_from('<I', logger, 0x2C)[0]
    for name in ('XPBPRE.BIN', 'XPBPOST.BIN'):
        data = files.get(name, b'')
        if len(data) == 117:
            report[name + '_response_flag'] = data[116]
    if 'XPBPRE.BIN_response_flag' in report and 'XPBPOST.BIN_response_flag' in report:
        report['response_flag_restored'] = (report['XPBPRE.BIN_response_flag'] ==
                                            report['XPBPOST.BIN_response_flag'])
    vtable = files.get('XPIMVT.BIN', b'')
    if len(vtable) == 64:
        report['image_calculator_methods'] = {
            hex(offset): hex(struct.unpack_from('<I', vtable, offset)[0])
            for offset in (8, 0x30, 0x34)}
        report['image_calculator_method_roles'] = {
            '0x8': 'dimensions: r1=resolution/size index, r2=aspect ID, s0=crop factor',
            '0x30': 'crop-factor to matching size-index classifier (used by DNG)',
            '0x34': 'size-index to matching crop factor'}
    boot = files.get('XPBOOT.BIN', b'')
    if len(boot) == 768:
        pointer = struct.unpack_from('<I', boot, 188)[0]
        report['bridge_object_pointer'] = hex(pointer)
        report['bridge_pointer_within_probe_guard'] = 0x59000000 <= pointer <= 0x5A000000-117
    commands = files.get('XPCMDS.BIN', b'')
    shell = files.get('XPSHELL.BIN', b'')
    if len(shell) >= 6:
        count = struct.unpack_from('<H', shell, 4)[0]
        report['engineering_command_count'] = count
        report['engineering_table_expected_bytes'] = count * 52
        if len(commands) == count * 52:
            # Each row stores a handler word and an inline 48-byte name.
            report['engineering_handlers'] = {
                row[4:].split(b'\0')[0].decode('ascii', errors='replace'):
                    hex(struct.unpack_from('<I', row)[0])
                for row in (commands[i:i+52] for i in range(0, len(commands), 52))
                if row[4:].split(b'\0')[0] in (b'SYS_md', b'lcmd', b'lcmd_resp',
                    b'is_linux_boot', b'camctl_set_still_aspect_ratio', b'VIEW_Crop')}
    marker = b'XPAN_SD_EXECUTED_REPLY'
    pre = files.get('XPRPRE.BIN', b'')
    post = files.get('XPRPOST.BIN', b'')
    report['computed_marker_new_in_output_buffer'] = marker in post and marker not in pre
    report['output_evidence_requires_review'] = True
    report['output_contexts'] = {}
    for token in (marker, b'resp : ', b'/run/SD', b'Linux'):
        index = post.find(token)
        if index >= 0:
            report['output_contexts'][token.decode()] = post[max(0, index-80):index+512].decode(
                'ascii', errors='replace')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('sample', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.directory, args.sample), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
