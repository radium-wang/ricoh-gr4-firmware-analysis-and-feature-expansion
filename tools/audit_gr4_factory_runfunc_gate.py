#!/usr/bin/env python3
"""Pin the offline GR IV RunFunc gate and its USB dispatch path.

This reads one known firmware image. It never contacts or modifies a camera.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_sd_shell_path import require_branch
from audit_xpan_paths import EXPECTED_SHA256, file_offset, require


def audit(raw: bytes) -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("only the pinned GR IV 01.11.10.07 image is supported")

    # Incoming factory request dispatch: case five calls ExecCommandRunFunc.
    require_branch(raw, 0x535A9F70, 0x535A9B1C)
    # RunFunc reads two request parameters as category and command bytes.
    require_branch(raw, 0x535A9B4C, 0x53795FAC)
    require_branch(raw, 0x535A9B60, 0x53795FAC)
    require_branch(raw, 0x535A9B88, 0x535AA068)

    # The gate starts at the immutable 3-byte command list and matches both
    # category and command. The third byte controls a request flag.
    require(raw, file_offset(0x535AA06C), bytes.fromhex(
        "44 4a 00 e3 f8 ca d0 e5 ea 43 45 e3 00 30 a0 e3"
    ), "RunFunc command-table base and category read")
    require(raw, file_offset(0x535AA0A0), bytes.fromhex(
        "01 e0 d2 e5 f9 3a d0 e5 03 00 5e e1"
    ), "RunFunc command byte comparison")
    table = raw[file_offset(0x53EA0A44):file_offset(0x53EA0A44) + 330 * 3]
    terminator = table.find(b"\xff")
    if terminator != 329 * 3:
        raise ValueError("factory command table has unexpected length")
    rows = [tuple(table[i:i + 3]) for i in range(0, terminator, 3)]
    if len({(a, b) for a, b, _ in rows}) != len(rows):
        raise ValueError("factory command table has duplicate IDs")

    # The known WLAN branch uses a ROM jump table keyed on command ID. These
    # are direct calls, not a caller-supplied function address.
    require(raw, file_offset(0x535ADC54), bytes.fromhex(
        "f8 3a d2 e5 0f 00 53 e3"
    ), "WLAN category comparison")
    require(raw, file_offset(0x535ADC70), bytes.fromhex(
        "f9 3a d2 e5 0a 30 43 e2 28 00 53 e3"
    ), "WLAN command range check")
    require_branch(raw, 0x535ADD44, 0x535AB614)
    require_branch(raw, 0x535ADD4C, 0x535AB5D0)
    require_branch(raw, 0x535ADD54, 0x535ADAC8)

    # The lazy root singleton is at 0x5509f370. Its +4 field owns the
    # FactoryCommandServer object allocated with 0xb60 bytes. The server
    # constructor finishes with the immutable vtable at 0x53ea0948.
    require(raw, file_offset(0x535A9414), struct.pack("<I", 0x53E9FFF8),
            "root singleton vtable literal")
    require_branch(raw, 0x535A92AC, 0x535A97D4)
    require(raw, file_offset(0x535A92B8), bytes.fromhex("04 60 87 e5"),
            "root +4 receives factory server object")
    require(raw, file_offset(0x535A987C), struct.pack("<I", 0x53EA0948),
            "factory server vtable literal")
    require(raw, file_offset(0x53EA0960), struct.pack("<I", 0x535A941C),
            "factory server type-discriminator slot")
    require(raw, file_offset(0x53EA0964), struct.pack("<I", 0x535A9F94),
            "factory server request setup slot")
    # This same object path dispatches GetData and SetData. A broken object
    # vtable could therefore remove the USB mechanism needed to undo it.
    require_branch(raw, 0x535A9FB0, 0x535A9E88)
    require_branch(raw, 0x535A9F30, 0x535A9CB8)
    require_branch(raw, 0x535A9F40, 0x535A9D98)

    return {
        "sample_sha256": digest,
        "usb_request_dispatch": "0x535a9f70 -> 0x535a9b1c",
        "runfunc_command_gate": "0x535aa068",
        "command_table": "0x53ea0a44",
        "command_table_entries": len(rows),
        "known_wlan_dispatch": "0x535adc24, ROM jump table",
        "factory_root": "0x5509f370",
        "factory_server_pointer_slot": "0x5509f374",
        "factory_server_vtable": "0x53ea0948",
        "factory_server_type_discriminator_slot": "0x53ea0960",
        "factory_server_request_setup_slot": "0x53ea0964",
        "request_setup_dispatch": "0x535a9f94 -> 0x535a9e88",
        "setdata_dispatch": "0x535a9f30 -> 0x535a9cb8",
        "getdata_dispatch": "0x535a9f40 -> 0x535a9d98",
        "same_usb_recovery_channel_depends_on_factory_object": True,
        "caller_supplied_execution_address_seen_in_audited_path": False,
        "conclusion": "RunFunc is an ID-based command channel; SetData plus RunFunc does not itself establish a RAM code loader.",
        "limits": [
            "Other factory commands and object dispatch paths are not exhaustively audited.",
            "This does not establish a safe RAM hook, code cache synchronization, or full XPAN recovery.",
            "No camera access or modification was performed.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.sample.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
