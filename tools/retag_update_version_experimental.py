#!/usr/bin/env python3
"""Retag GR IV update metadata for offline research only.

The installed camera firmware performs the initial version check. Changing
code inside a candidate update cannot affect that check. This tool changes
only the candidate's known header and GR IV trailer version copies, then
repairs the additive checksum. It does not prove that a camera accepts the
package, nor that installing it is safe.
"""

import argparse
import hashlib
import struct
from pathlib import Path

from inspect_firmware import unpack_frames
from repack_firmware_experimental import word_sum


HEADER_COPIES = (0x38, 0x50)
HEADER_REVERSED_COPY = 0x4C
RECORD_SIZE = 0x80
GR_IV_RECORD_VERSION_OFFSETS = (4, 8, 12)


def parse_version(value):
    parts = value.split(".")
    if len(parts) != 4 or any(not part.isdecimal() for part in parts):
        raise argparse.ArgumentTypeError("version must have four decimal bytes, e.g. 1.11.10.7")
    numbers = tuple(map(int, parts))
    if any(number > 255 for number in numbers):
        raise argparse.ArgumentTypeError("each version component must be 0..255")
    return bytes(numbers)


def versions_and_locations(package):
    if package[8:14] != b"GR IV\0":
        raise ValueError("not a GR IV update")
    if word_sum(package) != 0:
        raise ValueError("input additive checksum failed")
    decoded, consumed, _ = unpack_frames(package)
    # Model records and stream metadata are anchored at EOF. The official
    # sample has one zero byte after the frame stream; an offline repack can
    # add up to three more bytes to keep the package word-aligned.
    first_record = len(package) - 24 - 3 * RECORD_SIZE
    prefix = package[consumed:first_record]
    if not 1 <= len(prefix) <= 4 or any(prefix):
        raise ValueError("unrecognized trailer layout")
    if package[first_record + 28:first_record + 33] != b"GR IV":
        raise ValueError("first model record is not GR IV")
    if package[first_record + RECORD_SIZE + 28:first_record + RECORD_SIZE + 44] != b"GR IV Monochrome":
        raise ValueError("second model record is not GR IV Monochrome")
    if package[first_record + 2 * RECORD_SIZE + 28:first_record + 2 * RECORD_SIZE + 37] != b"GR IV HDF":
        raise ValueError("third model record is not GR IV HDF")
    locations = list(HEADER_COPIES)
    locations += [first_record + offset for offset in GR_IV_RECORD_VERSION_OFFSETS]
    versions = [package[offset:offset + 4] for offset in locations]
    reversed_version = package[HEADER_REVERSED_COPY:HEADER_REVERSED_COPY + 4][::-1]
    if len(set(versions + [reversed_version])) != 1:
        raise ValueError("GR IV version copies disagree; refusing to retag")
    if struct.unpack_from("<I", package, len(package) - 12)[0] != consumed - 0x80:
        raise ValueError("compressed stream length mismatch")
    if struct.unpack_from("<I", package, len(package) - 8)[0] != len(decoded):
        raise ValueError("decoded payload length mismatch")
    return versions[0], locations, decoded


def retag(package, target):
    original, locations, decoded_before = versions_and_locations(package)
    result = bytearray(package)
    for offset in locations:
        result[offset:offset + 4] = target
    result[HEADER_REVERSED_COPY:HEADER_REVERSED_COPY + 4] = target[::-1]
    struct.pack_into("<I", result, len(result) - 4, 0)
    struct.pack_into("<I", result, len(result) - 4, -word_sum(result) & 0xFFFFFFFF)
    result = bytes(result)
    observed, _, decoded_after = versions_and_locations(result)
    if observed != target or decoded_after != decoded_before:
        raise AssertionError("retagging changed the decoded payload or versions")
    expected = set(range(len(result) - 4, len(result)))
    for offset in locations + [HEADER_REVERSED_COPY]:
        expected.update(range(offset, offset + 4))
    changed = {i for i, (a, b) in enumerate(zip(package, result)) if a != b}
    if not changed <= expected:
        raise AssertionError("unexpected bytes changed")
    return result, original, len(changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_update", type=Path)
    parser.add_argument("target_version", type=parse_version)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.original_update.resolve() == args.output.resolve():
        parser.error("output must not overwrite the official input package")
    result, original, changed = retag(args.original_update.read_bytes(), args.target_version)
    args.output.write_bytes(result)
    print("original:", ".".join(map(str, original)))
    print("target:", ".".join(map(str, args.target_version)))
    print("changed bytes:", changed)
    print("SHA-256:", hashlib.sha256(result).hexdigest())
    print("offline checks passed; camera acceptance and installation safety unverified")


if __name__ == "__main__":
    main()
