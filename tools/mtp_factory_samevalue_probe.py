#!/usr/bin/env python3
"""Verify GR IV hidden MTP SetData framing with an unchanged RAM word.

The only SetData payload is the exact four bytes just read from the
SYS_buildinfo handler slot. This does not alter the handler value. It cannot
accept an arbitrary address or payload from the command line.
"""

import json
import struct
import sys

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_runtime_readonly import (
    BUILDINFO_HANDLER, BUILDINFO_INDEX, BUILDINFO_NAME, COMMAND_COUNT,
    COMMAND_SIZE, HOLDER,
)
from mtp_probe_readonly import PID, VID, command, read_container


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
                raise RuntimeError(f"GetData failed at 0x{address:08x}: 0x{response:04x}")
            return data

        holder = read(HOLDER, 8)
        table, count = struct.unpack_from("<IH", holder)
        if count != COMMAND_COUNT or table % 4 or not 0x59000000 <= table < 0x5A000000:
            raise RuntimeError("unexpected command table anchor")
        address = table + BUILDINFO_INDEX * COMMAND_SIZE
        if address + COMMAND_SIZE > 0x5A000000:
            raise RuntimeError("handler slot outside verified command RAM")
        row = read(address, 4 + len(BUILDINFO_NAME))
        original = struct.pack("<I", BUILDINFO_HANDLER)
        if row != original + BUILDINFO_NAME:
            raise RuntimeError("unexpected SYS_buildinfo handler or command name")

        opcode = 0x9095
        request = struct.pack("<IHHIII", 20, 1, opcode, transaction, address, 4)
        data_packet = struct.pack("<IHHI", 16, 2, opcode, transaction) + original
        device.write(0x01, request, timeout=5000)
        device.write(0x01, data_packet, timeout=5000)
        kind, response, received_transaction, response_parameters = read_container(device)
        if kind != 3 or received_transaction != transaction:
            raise RuntimeError("unexpected SetData response container")
        transaction += 1
        after = read(address, len(row))
        report = {
            "operation": "0x9095 SetData same-value only",
            "handler_slot": f"0x{address:08x}",
            "payload_hex": original.hex(),
            "response": f"0x{response:04x}",
            "response_parameters_hex": response_parameters.hex(),
            "before_hex": row.hex(),
            "after_hex": after.hex(),
            "unchanged": after == row,
        }
        print(json.dumps(report, indent=2))
        return 0 if response == 0x2001 and after == row else 1
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
        print(f"Same-value factory SetData probe failed: {error}", file=sys.stderr)
        sys.exit(1)
