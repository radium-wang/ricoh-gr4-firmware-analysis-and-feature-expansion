#!/usr/bin/env python3
# Copyright 2026 radium-wang. License: see LICENSE.
"""Inspect local GR firmware metadata and shutdown-name evidence; never generate TTL."""
import argparse
import hashlib
import json
from pathlib import Path
import re

LIMIT = 128 * 1024 * 1024


def local_bytes(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= LIMIT:
        raise ValueError('Use a regular local file of at most 128 MiB.')
    return path.read_bytes()


def inspect(firmware, decoded=None):
    data = local_bytes(Path(firmware))
    if len(data) < 128 or data[:8] != b'RICOH\0\0\0':
        raise ValueError('Not a recognized RICOH update-container header.')
    model = data[8:20].split(b'\0', 1)[0].decode('ascii')
    if model not in ('GR III', 'GR IIIx', 'GR IV'):
        raise ValueError('The update header is outside the GR III / IIIx / IV research scope.')
    report = {'format': 'gr-shutdown-firmware-audit-v1',
              'container_model': model, 'container_sha256': hashlib.sha256(data).hexdigest(),
              'container_bytes': len(data),
              'header_version_components': list(data[0x38:0x3c]),
              'header_version': '.'.join(map(str, data[0x38:0x3c])),
              'resource_name_evidence': [],
              'installed_body_identified': False, 'installation_qualified': False,
              'interpretation': 'A shared update package and resource-name strings do not identify the body, target drive, script compatibility or JPEG decoder behavior.'}
    if decoded:
        payload = local_bytes(Path(decoded))
        report['decoded_sha256'] = hashlib.sha256(payload).hexdigest()
        names = {}
        for match in re.finditer(rb'(?<![A-Za-z0-9_])(?:GoodBye|GB_[A-Za-z0-9_]{1,40})\.jpe?g\b', payload, re.I):
            name = match.group().decode('ascii')
            offsets = names.setdefault(name, [])
            if len(offsets) < 32:
                offsets.append(match.start())
        report['resource_name_evidence'] = [{'name': name, 'decoded_offsets': offsets} for name, offsets in sorted(names.items())]
        report['decoded_correspondence_verified'] = False
        report['decoded_note'] = 'Decoded bytes are supplied separately; this audit does not attest that they correspond to the container.'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('firmware', type=Path)
    parser.add_argument('--decoded', type=Path, help='optional existing decoded payload; no extraction performed')
    parser.add_argument('--output', type=Path, help='new JSON filename; never overwritten')
    args = parser.parse_args()
    try:
        report = json.dumps(inspect(args.firmware, args.decoded), indent=2) + '\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(report)
        else:
            print(report, end='')
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f'error: {error}\n')


if __name__ == '__main__':
    main()
