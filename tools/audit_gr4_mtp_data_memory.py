#!/usr/bin/env python3
"""Offline audit of GR IV hidden MTP factory data memory operations.

Never contacts the camera and never emits a writable MTP request.
"""

import argparse
import hashlib
import json
from pathlib import Path

from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch


def audit(sample):
    payload = sample.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("only the pinned GR IV 01.11.10.07 image is supported")

    # ExecCommandSetData: parameters 0/1/2 are destination, length, source.
    # The source was copied to shmem by libcamera-controller before this call.
    require_branch(payload, 0x535A9CD4, 0x53795FAC)
    require_branch(payload, 0x535A9CE4, 0x53795FAC)
    require_branch(payload, 0x535A9CF4, 0x53795FAC)
    require(payload, file_offset(0x535A9D80), bytes.fromhex(
        "07 20 a0 e1 08 00 a0 e1 06 10 a0 e1"
    ), "SetData memcpy destination/source/length registers")
    require_branch(payload, 0x535A9D8C, 0x53156140)

    # ExecCommandGetData: parameters 0/1 are source and length; RTOS
    # allocates a response buffer and copies from the supplied source.
    require_branch(payload, 0x535A9DB4, 0x53795FAC)
    require_branch(payload, 0x535A9DC4, 0x53795FAC)
    require(payload, file_offset(0x535A9E74), bytes.fromhex(
        "06 20 a0 e1 08 10 a0 e1"
    ), "GetData memcpy source/length registers")
    require_branch(payload, 0x535A9E7C, 0x53156140)
    require(payload, file_offset(0x53156158), bytes.fromhex("0d 07 21 f4"),
            "RTOS copy routine begins with byte-vector load")

    return {
        "sample_sha256": digest,
        "rtos_set_data_copy": {
            "address": "0x535a9d8c",
            "copy_routine": "0x53156140",
            "destination": "factory request parameter 0",
            "length": "factory request parameter 1",
            "source": "host-supplied shared-memory pointer, parameter 2",
        },
        "rtos_get_data_copy": {
            "address": "0x535a9e7c",
            "copy_routine": "0x53156140",
            "source": "factory request parameter 0",
            "length": "factory request parameter 1",
        },
        "arbitrary_safe_address_proven": False,
        "camera_probe_run": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.sample), indent=2))


if __name__ == "__main__":
    main()
