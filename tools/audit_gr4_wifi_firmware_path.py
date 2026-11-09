#!/usr/bin/env python3
"""Audit GR IV's Wi-Fi firmware upload receiver in a pinned local image.

This reads the decoded firmware file only; it never contacts the camera.
"""

import argparse
import hashlib
import io
import json
import struct
from pathlib import Path

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from elftools.elf.elffile import ELFFile

from audit_xpan_paths import EXPECTED_SHA256
from gr4_firmware_parts import find_parts
from inspect_initfs_readonly import SquashFS


def audit(sample):
    payload = sample.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("only pinned GR IV 01.11.10.07 firmware is supported")

    fs = SquashFS(find_parts(payload)["initfs"].data)
    binary = fs.read_file(fs.resolve("/usr/bin/webapid"))
    elf = ELFFile(io.BytesIO(binary))
    symbols = elf.get_section_by_name(".dynsym")
    relocations = elf.get_section_by_name(".rel.plt")
    plt = elf.get_section_by_name(".plt")
    if plt["sh_size"] != 20 + 12 * relocations.num_relocations():
        raise ValueError("unexpected ARM PLT layout")
    symbol_by_name = {symbol.name: symbol for symbol in symbols.iter_symbols()}
    disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

    def imports_called(fragment):
        matches = [symbol for name, symbol in symbol_by_name.items() if fragment in name]
        if len(matches) != 1:
            raise ValueError(f"expected one function matching {fragment!r}")
        symbol = matches[0]
        start = symbol["st_value"] & ~1
        size = symbol["st_size"]
        if not size:
            raise ValueError(f"empty function {fragment}")
        for segment in elf.iter_segments():
            if segment["p_type"] == "PT_LOAD" and segment["p_vaddr"] <= start and start + size <= segment["p_vaddr"] + segment["p_filesz"]:
                offset = segment["p_offset"] + start - segment["p_vaddr"]
                break
        else:
            raise ValueError(f"function not in load segment: {fragment}")
        calls = set()
        for instruction in disassembler.disasm(binary[offset:offset + size], start):
            if instruction.mnemonic != "blx" or not instruction.op_str.startswith("#0x"):
                continue
            target = int(instruction.op_str[1:], 16)
            index, remainder = divmod(target - (plt["sh_addr"] + 20), 12)
            if remainder == 0 and 0 <= index < relocations.num_relocations():
                relocation = relocations.get_relocation(index)
                calls.add(symbols.get_symbol(relocation["r_info_sym"]).name)
        return calls

    routes = (
        b"PUT /v1/configs/firmware",
        b"POST /v1/configs/firmware/prepare",
        b"POST /v1/configs/firmware/cancel",
    )
    for route in routes:
        if route + b"\0" not in binary:
            raise ValueError(f"missing firmware route: {route!r}")
    # At 0x6BB4A Open loads a PC-relative string pointer; at 0x6BB4C
    # it adds PC, then calls the imported open() at 0x6BB4E.
    if struct.unpack_from("<I", binary, 0x6BDBC)[0] != 0x481C4:
        raise ValueError("unexpected firmware memory path reference")
    path_at = 0x6BB50 + 0x481C4
    if binary[path_at:path_at + len(b"/dev/mem\0")] != b"/dev/mem\0":
        raise ValueError("firmware memory path is not /dev/mem")

    open_calls = imports_called("FirmwareMemoryManager4Open")
    put_calls = imports_called("FirmwareTransferManager7PutData")
    for required in ("open", "mmap"):
        if required not in open_calls:
            raise ValueError(f"firmware memory manager no longer calls {required}")
    if "memcpy" not in put_calls:
        raise ValueError("firmware transfer no longer copies into mapped memory")

    return {
        "sample_sha256": digest,
        "webapid_sha256": hashlib.sha256(binary).hexdigest(),
        "firmware_routes": [route.decode() for route in routes],
        "memory_manager_calls": sorted(open_calls),
        "transfer_manager_calls": sorted(put_calls),
        "fixed_dev_mem_string_present": True,
        "camera_probe_run": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.sample), indent=2))


if __name__ == "__main__":
    main()
