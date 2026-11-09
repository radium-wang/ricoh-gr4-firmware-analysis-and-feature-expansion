#!/usr/bin/env python3
"""Audit direct GR IV ADJ descriptor references in the pinned RTOS.

Offline only. The result identifies a loader/hook design constraint; it does
not modify a firmware image, contact a camera, or establish runtime mapping.
"""

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import struct

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

from audit_xpan_memory_map import audit as audit_memory_map
from audit_xpan_paths import EXPECTED_SHA256, file_offset, require


EXPECTED_REFERENCES = (
    0x531BD954, 0x531BDAF0, 0x531BDB8C, 0x531BE088,
    0x531BEA9C, 0x531BEAF8, 0x531BEBF0, 0x531BEC7C,
    0x531BED08, 0x531BEDB0, 0x531BEEFC, 0x531BF09C,
    0x531BF4A4, 0x531BF5B0, 0x531BF65C, 0x531BF964,
    0x531BFB28, 0x531BFCE8,
)


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError("only the pinned GR IV 01.11.10.07 sample is supported")
    # The ADJ count dispatcher forms 0x53D9F714 + index*0x5C and
    # loads the count callback from descriptor offset +0x30.
    require(raw, file_offset(0x531BE088), bytes.fromhex(
        "14 27 0f e3 5c 30 a0 e3 d9 23 45 e3 93 20 20 e0"
    ), "main-menu descriptor base, stride and indexed address")
    require(raw, file_offset(0x531BE098), bytes.fromhex(
        "30 30 90 e5 30 00 80 e2"
    ), "count callback load from descriptor +0x30")
    memory = audit_memory_map(raw)
    aliases = memory["menu_and_callback_section_aliases"]
    if memory["writable_alias_found_in_initial_table"]:
        raise ValueError("unexpected writable alias in initial page table")

    lo, hi = 0x53000000, 0x53D00000
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    md.skipdata = True
    pending = deque()
    references = []
    for ins in md.disasm(raw[file_offset(lo):file_offset(hi)], lo):
        # MOVW/MOVT for a fixed 32-bit address can have one intervening
        # instruction. Match the same destination register within 3 slots.
        for address, register, remaining in tuple(pending):
            if ins.mnemonic == "movt" and ins.op_str.startswith(register + ",") \
                    and "#0x53d9" in ins.op_str:
                references.append(address)
                pending.remove((address, register, remaining))
            elif remaining <= 1:
                pending.remove((address, register, remaining))
            else:
                pending.remove((address, register, remaining))
                pending.append((address, register, remaining - 1))
        if ins.mnemonic == "movw" and "#0xf714" in ins.op_str:
            pending.append((ins.address, ins.op_str.split(",")[0], 3))
    if tuple(references) != EXPECTED_REFERENCES:
        raise ValueError(f"main-menu direct references changed: {references}")
    count_callers = []
    for address in range(lo, hi, 4):
        word = struct.unpack_from("<I", raw, file_offset(address))[0]
        if word & 0x0F000000 != 0x0B000000:
            continue
        displacement = word & 0xFFFFFF
        if displacement & 0x800000:
            displacement -= 0x1000000
        if address + 8 + displacement * 4 == 0x531BE070:
            count_callers.append(address)
    if len(count_callers) != 25:
        raise ValueError(f"unexpected count-dispatch call sites: {count_callers}")
    count_dispatch_pointer_occurrences = []
    needle = struct.pack("<I", 0x531BE070)
    start = 0
    while (offset := raw.find(needle, start)) != -1:
        count_dispatch_pointer_occurrences.append(offset)
        start = offset + 1
    if count_dispatch_pointer_occurrences:
        raise ValueError("unexpected static pointer to count dispatcher")
    return {
        "sample_sha256": EXPECTED_SHA256,
        "adj_menu_base": "0x53d9f714",
        "controller_class": "AdjModeController",
        "descriptor_stride": "0x5c",
        "aspect_descriptor": "0x53d9f8e0",
        "main_count_dispatch": "0x531be070",
        "direct_base_construction_count": len(references),
        "direct_base_constructions": [f"0x{x:08x}" for x in references],
        "direct_count_dispatch_callers": [f"0x{x:08x}" for x in count_callers],
        "static_pointer_occurrences_for_count_dispatch": 0,
        "initial_page_table_aliases": aliases,
        "writable_alias_found_in_initial_table": False,
        "conclusion": "The audited count path reads the immutable descriptor directly and has 25 direct calls with no static function-pointer slot; replacing one RAM pointer is not sufficient for a fifth menu item.",
        "limits": [
            "The 18 references are the pinned three-slot MOVW/MOVT subset, not an exhaustive reference inventory.",
            "The separate settings menu belongs to SelectMenuController; see audit_gr4_ui_native_routes.py.",
            "The active runtime translation table and other UI paths are not proven by this offline audit.",
            "No safe native interception, code loader, cache publication or recovery procedure is established.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.sample.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
