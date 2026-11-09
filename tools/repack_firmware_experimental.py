#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Experimental offline repack of a decoded GR IV update payload.

This verifies the frame container, decoded bytes and additive checksum only.
It does not establish that a camera will accept the package or that it is safe
to install. Never copy experimental output to a camera as an update.
"""

import argparse
import hashlib
import struct
from pathlib import Path

from inspect_firmware import unpack_frames


HEADER_SIZE = 0x80
EXPECTED_MODEL = b"GR IV\0"


def word_sum(data):
    if len(data) % 4:
        raise ValueError("package length is not a multiple of four")
    return sum(word for (word,) in struct.iter_unpack("<I", data)) & 0xFFFFFFFF


def changed_frames(original, replacement, frames):
    return {
        i for i, (_, _, first, last) in enumerate(frames)
        if original[first:last] != replacement[first:last]
    }


def frame_stream(package, replacement, frames, raw_indices):
    chunks = []
    for i, (src_first, src_last, dst_first, dst_last) in enumerate(frames):
        if i in raw_indices:
            data = replacement[dst_first:dst_last]
            if not 0 < len(data) <= 0x7FFF:
                raise ValueError(f"frame {i} cannot be represented as a raw frame")
            chunks.append(struct.pack(">H", 0x8000 | len(data)) + data)
        else:
            chunks.append(package[src_first:src_last])
    return b"".join(chunks)


def repack(package, replacement):
    if package[8:14] != EXPECTED_MODEL:
        raise ValueError("not a GR IV package")
    if word_sum(package) != 0:
        raise ValueError("original additive checksum failed")
    original, consumed, frames = unpack_frames(package)
    if len(replacement) != len(original):
        raise ValueError("decoded payload length must remain unchanged")
    if struct.unpack_from("<I", package, len(package) - 12)[0] != consumed - HEADER_SIZE:
        raise ValueError("compressed stream length field does not match decoder")
    if struct.unpack_from("<I", package, len(package) - 8)[0] != len(original):
        raise ValueError("decoded length field does not match decoder")
    if replacement == original:
        return package, set()

    raw_indices = changed_frames(original, replacement, frames)
    while True:
        stream = frame_stream(package, replacement, frames, raw_indices)
        candidate = package[:HEADER_SIZE] + stream + b"\0\0" + package[consumed:]
        result, _, _ = unpack_frames(candidate)
        if len(result) != len(replacement):
            raise ValueError("rebuilt stream changed decoded length")
        mismatched = changed_frames(result, replacement, frames)
        if not mismatched:
            break
        if mismatched <= raw_indices:
            raise ValueError("raw frame mismatch after rebuild")
        raw_indices |= mismatched

    tail = bytearray(package[consumed:])
    struct.pack_into("<I", tail, len(tail) - 12, len(stream) + 2)
    struct.pack_into("<I", tail, len(tail) - 8, len(replacement))
    # The original footer is located from EOF. Zero padding before it keeps the
    # total package word-aligned if a replacement frame changes stream length.
    padding = b"\0" * (-(HEADER_SIZE + len(stream) + 2 + len(tail)) % 4)
    rebuilt = bytearray(package[:HEADER_SIZE] + stream + b"\0\0" + padding + tail)
    struct.pack_into("<I", rebuilt, len(rebuilt) - 4, 0)
    struct.pack_into("<I", rebuilt, len(rebuilt) - 4, -word_sum(rebuilt) & 0xFFFFFFFF)
    if word_sum(rebuilt) != 0:
        raise AssertionError("rebuilt checksum is not zero")
    decoded, _, _ = unpack_frames(rebuilt)
    if decoded != replacement:
        raise AssertionError("rebuilt payload differs from requested bytes")
    return bytes(rebuilt), raw_indices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_update", type=Path)
    parser.add_argument("replacement_decoded", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    package, raw_indices = repack(
        args.original_update.read_bytes(), args.replacement_decoded.read_bytes()
    )
    args.output.write_bytes(package)
    print("SHA-256:", hashlib.sha256(package).hexdigest())
    print("size:", len(package), "raw replacement frames:", len(raw_indices))
    print("offline container checks passed; camera acceptance and safety unverified")


if __name__ == "__main__":
    main()
