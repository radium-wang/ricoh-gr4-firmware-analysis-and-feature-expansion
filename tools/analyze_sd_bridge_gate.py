#!/usr/bin/env python3
"""Analyze a copied one-boot bridge gate; never treat lcmd=0 as execution."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

MARKER = b'XPAN_BRIDGE_EXECUTED\n'


def analyze(directory):
    def read(name):
        path = directory / name
        return path.read_bytes() if path.is_file() else None

    status = read('BRTEST.TXT')
    boot = read('BRBOOT.BIN')
    pre, post = read('BRPRE.BIN'), read('BRPOST.BIN')
    marker = read('BRDONE.TXT')
    lines = status.decode('ascii', 'replace').splitlines() if status else []
    fields = {}
    for i in range(len(lines)-1):
        if lines[i] in ('BRBOOT.BIN', 'BRPRE.BIN', 'BRPOST.BIN',
                        'Linux readiness',
                        'lcmd handler result, not execution proof',
                        'bridge object read available',
                        'Linux script marker exists'):
            try: fields[lines[i]] = int(lines[i+1])
            except ValueError: pass
    pointer = struct.unpack_from('<I', boot, 188)[0] if boot and len(boot) == 768 else None
    pointer_in_guard = pointer is not None and 0x5A000000 <= pointer <= 0x5B000000-117
    pre_ok = pre is not None and len(pre) == 117
    post_ok = post is not None and len(post) == 117
    return {
        'started': bool(lines and lines[0] == 'bridge gate started'),
        'finished': bool(lines and lines[-1] == 'bridge gate finished'),
        'status_fields': fields,
        'boot_size_ok': boot is not None and len(boot) == 768,
        'bridge_pointer': hex(pointer) if pointer is not None else None,
        'bridge_pointer_in_guard': pointer_in_guard,
        'bridge_pre_size_ok': pre_ok,
        'bridge_post_size_ok': post_ok,
        'response_flag_unchanged': (pre[116] == post[116]) if pre_ok and post_ok else None,
        'response_flag_before': pre[116] if pre_ok else None,
        'response_flag_after': post[116] if post_ok else None,
        'marker_exact': marker == MARKER,
        'marker_sha256': hashlib.sha256(marker).hexdigest() if marker is not None else None,
        'linux_execution_proven': marker == MARKER and fields.get('Linux readiness') == 1,
        'camera_patch_or_XPAN_installed': False,
    }


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('readback',type=Path)
    args=parser.parse_args()
    print(json.dumps(analyze(args.readback),ensure_ascii=False,indent=2))
