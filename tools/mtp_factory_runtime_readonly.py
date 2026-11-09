#!/usr/bin/env python3
"""Read pinned GR IV RAM anchors through the proven hidden MTP GetData path.

This probe sends no SetData, RunFunc, SetValue, file, or firmware operation.
It refuses to follow an unexpected command-table pointer.
"""

import json
import struct
import sys

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_probe_readonly import PID, VID, command


HOLDER = 0x553A094C
COMMAND_COUNT = 651
COMMAND_SIZE = 52
BUILDINFO_INDEX = 533
BUILDINFO_HANDLER = 0x53054854
BUILDINFO_NAME = b"SYS_buildinfo\0"
TEST_LEAF = 0x538C9760
TEST_LEAF_BYTES = bytes.fromhex("03 00 a0 e3 1e ff 2f e1")
PROPERTIES = 0x55085D63


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
        if response != 0x2001 or info is None:
            raise RuntimeError(f"GetDeviceInfo failed: 0x{response:04x}")
        if operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError("unexpected MTP operation list")
        response, _, _ = command(device, 0x1002, 1, 1)
        opened_by_us = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError(f"OpenSession failed: 0x{response:04x}")

        def read(address, length):
            nonlocal transaction
            response, data, _ = command(device, 0x9094, transaction, address, length)
            transaction += 1
            if response != 0x2001 or data is None or len(data) != length:
                raise RuntimeError(
                    f"GetData 0x{address:08x}/{length} failed: "
                    f"response=0x{response:04x}, bytes={len(data or b'')}"
                )
            return data

        holder = read(HOLDER, 8)
        table, count = struct.unpack_from("<IH", holder)
        if count != COMMAND_COUNT or table % 4 or not 0x59000000 <= table < 0x5A000000:
            raise RuntimeError(f"unexpected command table anchor: {holder.hex()}")
        row_address = table + BUILDINFO_INDEX * COMMAND_SIZE
        if row_address + COMMAND_SIZE > 0x5A000000:
            raise RuntimeError("command table row outside the verified RAM range")
        row = read(row_address, 4 + len(BUILDINFO_NAME))
        handler = struct.unpack_from("<I", row)[0]
        if handler != BUILDINFO_HANDLER or row[4:] != BUILDINFO_NAME:
            raise RuntimeError(f"unexpected SYS_buildinfo row: {row.hex()}")
        leaf = read(TEST_LEAF, len(TEST_LEAF_BYTES))
        if leaf != TEST_LEAF_BYTES:
            raise RuntimeError(f"unexpected native diagnostic leaf: {leaf.hex()}")
        properties = read(PROPERTIES, 5)
        report = {
            "operation": "0x9094 GetData only",
            "holder_address": f"0x{HOLDER:08x}",
            "holder_hex": holder.hex(),
            "table_address": f"0x{table:08x}",
            "command_count": count,
            "buildinfo_row_address": f"0x{row_address:08x}",
            "buildinfo_row_hex": row.hex(),
            "native_test_leaf_hex": leaf.hex(),
            "capture_properties_address": f"0x{PROPERTIES:08x}",
            "capture_properties_hex": properties.hex(),
            "all_pinned_checks_passed": True,
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
        print(f"Read-only runtime probe failed: {error}", file=sys.stderr)
        sys.exit(1)
