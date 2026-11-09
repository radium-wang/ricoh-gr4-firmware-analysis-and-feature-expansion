#!/usr/bin/env python3
"""Read the current GR IV RTOS/Linux bridge object over factory MTP.

The pointer anchor and 117-byte object were previously read through SD.
This tool issues only GetDeviceInfo, OpenSession, GetData, CloseSession.
"""

import json
import struct
import sys

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_probe_readonly import PID, VID, command


POINTER_ANCHOR = 0x550A0300 + 188
OBJECT_SIZE = 117
EXPECTED_PREFIX = bytes.fromhex("e834ea531035ea532c35ea53")


def main():
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        raise RuntimeError("GR IV is not connected")
    if device.bcdDevice != 0x0111:
        raise RuntimeError(f"untested USB firmware version: 0x{device.bcdDevice:04x}")
    usb.util.claim_interface(device, 0)
    opened_by_us = False
    transaction = 2
    try:
        response, info, _ = command(device, 0x1001, 0)
        if response != 0x2001 or info is None or operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError("unexpected GetDeviceInfo result")
        response, _, _ = command(device, 0x1002, 1, 1)
        opened_by_us = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError(f"OpenSession failed: 0x{response:04x}")

        def read(address, length):
            nonlocal transaction
            response, data, _ = command(device, 0x9094, transaction, address, length)
            transaction += 1
            if response != 0x2001 or data is None or len(data) != length:
                raise RuntimeError(f"GetData 0x{address:08x}/{length} failed: 0x{response:04x}")
            return data

        pointer_bytes = read(POINTER_ANCHOR, 4)
        pointer = struct.unpack("<I", pointer_bytes)[0]
        # Both 0x59 and 0x5A are mapped writable RAM in the pinned image.
        # Prior SD snapshots showed a 0x5A allocation; this boot may differ.
        if not 0x59000000 <= pointer <= 0x5B000000 - OBJECT_SIZE:
            raise RuntimeError(f"unexpected bridge object pointer: 0x{pointer:08x}")
        prefix = read(pointer, len(EXPECTED_PREFIX))
        if prefix != EXPECTED_PREFIX:
            raise RuntimeError(f"unexpected bridge object header: {prefix.hex()}")
        obj = read(pointer, OBJECT_SIZE)
        report = {
            "operation": "0x9094 GetData only",
            "pointer_anchor": f"0x{POINTER_ANCHOR:08x}",
            "pointer": f"0x{pointer:08x}",
            "object_size": len(obj),
            "object_hex": obj.hex(),
            "response_flag_offset_116": obj[116],
            "observed_words_hex": {
                str(offset): obj[offset:offset+4].hex()
                for offset in (64, 72, 92, 96, 100, 107, 109)
            },
        }
        print(json.dumps(report, indent=2))
    finally:
        try:
            if opened_by_us:
                command(device, 0x1003, transaction)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Read-only bridge probe failed: {error}", file=sys.stderr)
        sys.exit(1)
