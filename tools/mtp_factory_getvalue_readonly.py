#!/usr/bin/env python3
"""Read-only probe of the GR IV's hidden MTP factory GetValue handler.

Firmware 01.11.10.07 dispatches opcode 0x9093 to
RicohCommand::doGeneralPurposeGetValue. This tool sends only GetDeviceInfo,
OpenSession, factory GetValue(1, 0), and CloseSession when it opened the
session itself. It never sends a factory RunFunc, SetValue, or SetData request.
The two MTP parameters are (value count, starting index); this probe asks
for one value at index zero.
"""

import sys
import struct

import usb.core
import usb.util

from mtp_probe_readonly import PID, VID, command

EXPECTED_OPERATIONS = (
    0x1001, 0x1002, 0x1003, 0x1004, 0x1005, 0x1006, 0x1007,
    0x1008, 0x1009, 0x100A, 0x1014, 0x1015, 0x1016, 0x101B,
)


def operations_from_device_info(data):
    if len(data) < 11:
        raise ValueError("short GetDeviceInfo payload")
    offset = 8 + 1 + 2 * data[8] + 2
    if len(data) < offset + 4:
        raise ValueError("missing operation count")
    count = struct.unpack_from("<I", data, offset)[0]
    if count > 256 or len(data) < offset + 4 + count * 2:
        raise ValueError("invalid operation list")
    return struct.unpack_from(f"<{count}H", data, offset + 4)


def main():
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        raise RuntimeError("GR IV is not connected")
    if device.bcdDevice != 0x0111:
        raise RuntimeError(f"untested USB firmware version: 0x{device.bcdDevice:04x}")
    usb.util.claim_interface(device, 0)
    opened_by_us = False
    try:
        response, info, _ = command(device, 0x1001, 0)
        print(f"GetDeviceInfo: 0x{response:04x}")
        if response != 0x2001 or info is None:
            return 1
        if operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError("unexpected MTP operation list; factory probe withheld")
        response, _, _ = command(device, 0x1002, 1, 1)
        print(f"OpenSession: 0x{response:04x}")
        opened_by_us = response == 0x2001
        if response not in (0x2001, 0x201E):
            return 1
        response, data, parameters = command(device, 0x9093, 2, 1, 0)
        print(f"Factory GetValue(count=1, index=0): response=0x{response:04x}")
        print(f"  data={(data or b'').hex()}")
        print(f"  response_parameters={parameters.hex()}")
        return 0
    finally:
        try:
            if opened_by_us:
                response, _, _ = command(device, 0x1003, 3)
                print(f"CloseSession: 0x{response:04x}")
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Read-only factory probe failed: {error}", file=sys.stderr)
        sys.exit(1)
