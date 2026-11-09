#!/usr/bin/env python3
"""Offline audit of hidden factory MTP dispatch in GR IV 01.11.10.07.

Reads a local decoded firmware sample. It never contacts the camera.
"""

import argparse
import hashlib
import io
import json
import struct
from collections import Counter
from pathlib import Path

from elftools.elf.elffile import ELFFile

from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch
from gr4_firmware_parts import find_parts
from inspect_initfs_readonly import SquashFS


def virtual_bytes(elf, raw, address, count):
    for segment in elf.iter_segments():
        if segment["p_type"] != "PT_LOAD":
            continue
        start = segment["p_vaddr"]
        if start <= address and address + count <= start + segment["p_filesz"]:
            offset = segment["p_offset"] + address - start
            return raw[offset:offset + count]
    raise ValueError(f"ELF address not found: {address:#x}")


def audit(sample):
    payload = sample.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("only the pinned GR IV 01.11.10.07 sample is supported")
    fs = SquashFS(find_parts(payload)["initfs"].data)
    mtpd = fs.read_file(fs.resolve("/usr/bin/mtpd"))
    elf = ELFFile(io.BytesIO(mtpd))
    symbols = {sym.name: sym for sym in elf.get_section_by_name(".dynsym").iter_symbols()}

    def symbol(fragment):
        hits = [sym for name, sym in symbols.items() if fragment in name]
        if len(hits) != 1:
            raise ValueError(f"symbol lookup {fragment!r}: {len(hits)} matches")
        return hits[0]["st_value"] & ~1

    handlers = {
        0x9090: (0x409DE, "doGeneralPurposeSetValue"),
        0x9091: (0x408A2, "doGeneralPurposeRunFunc"),
        0x9092: (0x408AC, "doGeneralPurposeEndCheck"),
        0x9093: (0x408BA, "doGeneralPurposeGetValue"),
        0x9094: (0x40886, "doGeneralPurposeGetData"),
        0x9095: (0x40894, "doGeneralPurposeSetData"),
    }
    table = virtual_bytes(elf, mtpd, 0x40758, 5)
    for index, code in enumerate(range(0x9091, 0x9096)):
        actual = 0x40758 + table[index] * 2
        if actual != handlers[code][0]:
            raise ValueError(f"unexpected dispatch target for {code:#x}: {actual:#x}")
    if virtual_bytes(elf, mtpd, 0x20FA4, 4) != bytes.fromhex("00 20 70 47"):
        raise ValueError("beginSendObject is no longer the expected zero-return stub")
    # The ordinary MTP property setter compares only 0x5011 and 0xD406
    # before taking its unsupported-property branch. Neither is WLAN SSID/key.
    if virtual_bytes(elf, mtpd, 0x53F5C, 18) != bytes.fromhex(
        "45 f2 11 03 31 80 99 42 7c d0 4d f2 06 43 99 42 24 d0"
    ):
        raise ValueError("unexpected ordinary MTP property setter gate")
    expected_extended_ops = (
        0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006, 0x1007,
        0x1008, 0x1009, 0x100A, 0x1014, 0x1015, 0x1016, 0x101B,
        0x9001, 0x9002, 0x9003, 0x9004, 0x9006, 0x9007, 0x9009,
        0x900B, 0x900C, 0x900D, 0x900E, 0x900F, 0x9011, 0x9012,
        0x9013, 0x9015, 0x9017, 0x9018,
    )
    if mtpd[0x60C58:0x60C58 + 64] != struct.pack("<32H", *expected_extended_ops):
        raise ValueError("unexpected extended MTP operation list")
    for _code, (_target, name) in handlers.items():
        symbol(name)
    command_table = payload[0xEB8754:0xEB8B2F]
    if len(command_table) != 329 * 3 or payload[0xEB8B2F] != 0xFF:
        raise ValueError("unexpected RTOS factory command table bounds")
    factory_commands = [tuple(command_table[i:i + 3]) for i in range(0, len(command_table), 3)]
    if len({(category, command) for category, command, _ in factory_commands}) != len(factory_commands):
        raise ValueError("duplicate RTOS factory command IDs")
    category_counts = Counter(category for category, _, _ in factory_commands)
    route_counts = Counter(route for _, _, route in factory_commands)
    for command in (0x2C, 0x2D):
        if (0x0F, command, 0x04) not in factory_commands:
            raise ValueError(f"missing WLAN factory command 0x0f:{command:02x}")
    if (0x0F, 0x2A, 0x04) not in factory_commands:
        raise ValueError("missing WLAN configuration factory command 0x0f:2a")
    require_branch(payload, 0x535ADD54, 0x535ADAC8)
    require_branch(payload, 0x535ADB18, 0x535AB714)
    require_branch(payload, 0x535ADBD4, 0x535AB714)
    require_branch(payload, 0x535ADD4C, 0x535AB5D0)
    require_branch(payload, 0x535ADD44, 0x535AB614)
    require_branch(payload, 0x535AB5E8, 0x535AB528)
    require_branch(payload, 0x535AB62C, 0x535AB528)
    require_branch(payload, 0x535AB570, 0x535CFF8C)
    require(payload, file_offset(0x53EA01D8), b"iperf3 -s &\0", "fixed factory Linux start command")
    require(payload, file_offset(0x53EA01E4), b"killall iperf3\0", "fixed factory Linux stop command")
    direct_linux_bridge_calls = []
    for address in range(0x53000000, 0x53D00000, 4):
        word = struct.unpack_from("<I", payload, file_offset(address))[0]
        if word & 0x0F000000 != 0x0B000000:
            continue
        displacement = word & 0xFFFFFF
        if displacement & 0x800000:
            displacement -= 0x1000000
        if address + 8 + displacement * 4 == 0x535CFF8C:
            direct_linux_bridge_calls.append(address)
    if direct_linux_bridge_calls != [0x5301C714, 0x535AB570]:
        raise ValueError("unexpected direct Linux command bridge callers")
    return {
        "sample_sha256": digest,
        "mtpd_sha256": hashlib.sha256(mtpd).hexdigest(),
        "factory_dispatch": {
            f"0x{code:04x}": {"target": f"0x{target:x}", "handler": name}
            for code, (target, name) in handlers.items()
        },
        "factory_get_value_is_read_handler": True,
        "rtos_factory_command_table": {
            "file_offset": "0xeb8754",
            "entries": len(factory_commands),
            "category_counts": {f"0x{k:02x}": category_counts[k] for k in sorted(category_counts)},
            "route_counts": {f"0x{k:02x}": route_counts[k] for k in sorted(route_counts)},
            "command_semantics_identified": False,
        },
        "standard_mtp_send_object_is_stubbed": True,
        "ordinary_mtp_property_setter_only_recognizes": ["0x5011", "0xd406"],
        "extended_mtp_operations": [f"0x{op:04x}" for op in expected_extended_ops],
        "extended_mode_advertises_standard_upload": False,
        "factory_linux_bridge_examples": {
            "0x0f:0x2c": "fixed iperf3 -s & command",
            "0x0f:0x2d": "fixed killall iperf3 command",
            "0x0f:0x2a": "factory WLAN configuration invokes shell command builder; not probed on camera",
            "arbitrary_shell_input_confirmed": False,
            "camera_probe_run": False,
            "direct_bridge_callers": [f"0x{x:08x}" for x in direct_linux_bridge_calls],
        },
        "camera_probe_run": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.sample), indent=2))


if __name__ == "__main__":
    main()
