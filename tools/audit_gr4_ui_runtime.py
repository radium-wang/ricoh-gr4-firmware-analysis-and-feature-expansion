#!/usr/bin/env python3
# Copyright 2026 radium-wang. License: see LICENSE.
"""Read-only inventory of GR IV Linux ELF dependencies and RTOS UI markers.

Checks whether the portable Qt/Wayland application method used by the X2D II
reference has a matching entry point in this local GR IV payload. Absence of a
filename or dependency is not proof that all possible graphics code is absent.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from gr4_firmware_parts import load_payload, find_parts
from inspect_initfs_readonly import SquashFS
from audit_xpan_paths import EXPECTED_SHA256 as EXPECTED


def elf_dependencies(data):
    if not data.startswith(b"\x7fELF"):
        return None
    if len(data) < 52 or data[4:6] != b"\x01\x01":
        raise ValueError("expected a little-endian ELF32 file")
    table = struct.unpack_from("<I", data, 32)[0]
    stride, count = struct.unpack_from("<HH", data, 46)
    if count > 4096 or stride != 40 or table + count * stride > len(data):
        raise ValueError("invalid ELF section table")
    sections = [struct.unpack_from("<10I", data, table + i * stride) for i in range(count)]
    needed = []
    for section in sections:
        if section[1] != 6:
            continue
        if section[6] >= count or section[5] % 8 or section[4] + section[5] > len(data):
            raise ValueError("invalid dynamic section")
        strings = sections[section[6]]
        if strings[4] + strings[5] > len(data):
            raise ValueError("invalid dynamic strings")
        names = data[strings[4]:strings[4] + strings[5]]
        for offset in range(section[4], section[4] + section[5], 8):
            tag, value = struct.unpack_from("<II", data, offset)
            if tag == 1:
                if value >= len(names):
                    raise ValueError("invalid DT_NEEDED index")
                needed.append(names[value:names.index(b"\0", value)].decode("utf-8"))
    return {"machine": struct.unpack_from("<H", data, 18)[0], "needed": sorted(set(needed))}


def audit(source):
    payload, kind, version, digest = load_payload(source)
    if hashlib.sha256(payload).hexdigest() != EXPECTED:
        raise ValueError("RTOS mapping verified only for GR IV 1.11.10.7; payload hash differs")
    part = find_parts(payload)["initfs"]
    fs = SquashFS(part.data)
    entries = []
    def walk(ref, path, depth=0):
        if depth > 24 or len(entries) > 20000:
            raise ValueError("filesystem inventory exceeds limit")
        for name, (child, item_type) in sorted(fs.list_dir(ref).items()):
            child_path = path + "/" + name
            entries.append((child_path, child, item_type))
            if item_type == 1:
                walk(child, child_path, depth + 1)
    walk(fs.root, "")
    elf = {}
    for name, ref, item_type in entries:
        if item_type == 2:
            data = fs.read_file(ref)
            info = elf_dependencies(data)
            if info is not None:
                elf[name] = info
    patterns = ("libqt", "qml", "wayland", "weston", "camera-gui", "camera_gui")
    paths = [name for name, _, _ in entries if any(p in name.lower() for p in patterns)]
    dependencies = sorted({dep for item in elf.values() for dep in item["needed"]})
    graphics = [dep for dep in dependencies if any(p in dep.lower() for p in patterns)]
    markers = {}
    for name in ("FactoryEntranceController", "DevelopmentMenuController", "MenuItemModel"):
        at = payload.find(name.encode(), 0x17D10, 0x1417D10)
        if at >= 0:
            markers[name] = {"file_offset": hex(at), "rtos_mapped_address": hex(at - 0x17D10 + 0x53000000), "kind": "string, not a function entry"}
    return {"schema": "gr4-ui-runtime-audit-v1", "source_type": kind, "source_sha256": digest,
            "decoded_sha256": hashlib.sha256(payload).hexdigest(), "version": version,
            "filesystem_entries": len(entries), "regular_files": sum(t == 2 for _, _, t in entries),
            "elf_files": len(elf), "matching_paths": paths, "matching_dependencies": graphics,
            "linux_elf": elf, "rtos_ui_markers": markers,
            "interpretation": "No equivalent Qt/Wayland camera-gui found" if not paths and not graphics else "Inspect matched candidates",
            "limits": ["Checks filesystem names and ELF DT_NEEDED, not every possible graphics implementation",
                       "RTOS marker strings support prior controller tracing; strings alone do not prove reachability",
                       "No firmware execution or camera I/O"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if args.report and args.report.exists():
            raise ValueError("report already exists")
        result = audit(args.source)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2) + "\n")
        summary = {key: value for key, value in result.items() if key != "linux_elf"}
        summary["camera_services"] = {name: result["linux_elf"].get(name) for name in ("/usr/bin/camctld", "/usr/bin/sysmgrd")}
        print(json.dumps(summary, indent=2))
    except (ValueError, OSError, KeyError, struct.error) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
