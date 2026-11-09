#!/usr/bin/env python3
"""Read one pinned GR IV factory service object through hidden MTP GetData.

No write, RunFunc, SetValue, file, or firmware operation is sent. The dynamic
pointer is followed only after checking its range and the expected vtable.
"""

import json
import struct
import sys

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_probe_readonly import PID, VID, command


ROOT = 0x5509F370
ROOT_VTABLE = 0x53E9FFF8
SERVER_VTABLE = 0x53EA0948
SERVER_TYPE_DISCRIMINATOR = 0x535A941C
SERVER_REQUEST_SETUP = 0x535A9F94
SERVER_MIN = 0x59000000
SERVER_MAX = 0x5C000000


def checked_server_pointer(root):
    if len(root) != 12:
        raise ValueError("short factory root")
    vtable, server, _other = struct.unpack("<III", root)
    if vtable != ROOT_VTABLE:
        raise ValueError(f"unexpected factory root vtable: {vtable:#x}")
    if server % 4 or not SERVER_MIN <= server <= SERVER_MAX - 12:
        raise ValueError(f"factory server pointer outside pinned RAM: {server:#x}")
    return server


def main():
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        raise RuntimeError("GR IV is not connected")
    if device.bcdDevice != 0x0111:
        raise RuntimeError(f"untested USB firmware version: 0x{device.bcdDevice:04x}")
    usb.util.claim_interface(device, 0)
    opened_by_us = False
    tx = 2
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
            nonlocal tx
            result, data, _ = command(device, 0x9094, tx, address, length)
            tx += 1
            if result != 0x2001 or data is None or len(data) != length:
                raise RuntimeError(
                    f"GetData {address:#x}/{length} failed: "
                    f"response=0x{result:04x}, bytes={len(data or b'')}"
                )
            return data

        root = read(ROOT, 12)
        server_address = checked_server_pointer(root)
        server = read(server_address, 12)
        vtable, second_vtable, third_vtable = struct.unpack("<III", server)
        if vtable != SERVER_VTABLE:
            raise RuntimeError(f"unexpected factory server vtable: {vtable:#x}")
        if second_vtable != SERVER_VTABLE + 0x28 or third_vtable != SERVER_VTABLE + 0x44:
            raise RuntimeError("unexpected factory server subobject vtables")
        table = read(SERVER_VTABLE, 32)
        discriminator, setup = struct.unpack_from("<II", table, 0x18)
        if discriminator != SERVER_TYPE_DISCRIMINATOR or setup != SERVER_REQUEST_SETUP:
            raise RuntimeError("unexpected factory service method table")

        print(json.dumps({
            "operation": "0x9094 GetData only",
            "root_address": f"0x{ROOT:08x}",
            "root_hex": root.hex(),
            "server_address": f"0x{server_address:08x}",
            "server_first_12_hex": server.hex(),
            "server_vtable_hex": table.hex(),
            "type_discriminator": f"0x{discriminator:08x}",
            "request_setup": f"0x{setup:08x}",
            "pinned_checks_passed": True,
            "camera_modified": False,
        }, indent=2))
    finally:
        try:
            if opened_by_us:
                command(device, 0x1003, tx)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Read-only factory server probe failed: {error}", file=sys.stderr)
        sys.exit(1)
