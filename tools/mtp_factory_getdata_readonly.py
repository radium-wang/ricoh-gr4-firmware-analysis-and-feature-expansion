#!/usr/bin/env python3
"""Read one pinned, known GR IV RTOS string through hidden USB GetData.

Uses only MTP GetDeviceInfo, OpenSession, 0x9094 GetData and, if needed,
CloseSession. It cannot accept arbitrary addresses or lengths from the CLI.
This exact GetData operation has not yet been tested on a camera.
"""

import json
import sys

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_probe_readonly import PID, VID, command


ADDRESS = 0x53EA38FC
EXPECTED = b'issue ifcmd "ExecLinuxCommand"'


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
        if response != 0x2001 or info is None:
            raise RuntimeError(f"GetDeviceInfo failed: 0x{response:04x}")
        if operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError("unexpected MTP operation list")
        response, _, _ = command(device, 0x1002, 1, 1)
        opened_by_us = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError(f"OpenSession failed: 0x{response:04x}")
        response, data, parameters = command(device, 0x9094, 2, ADDRESS, len(EXPECTED))
        actual = data or b""
        report = {
            "operation": "0x9094 GetData",
            "address": f"0x{ADDRESS:08x}",
            "requested_bytes": len(EXPECTED),
            "response": f"0x{response:04x}",
            "data_hex": actual.hex(),
            "response_parameters_hex": parameters.hex(),
            "exact_known_string": response == 0x2001 and actual == EXPECTED,
        }
        print(json.dumps(report, indent=2))
        return 0 if report["exact_known_string"] else 1
    finally:
        try:
            if opened_by_us:
                command(device, 0x1003, 3)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Read-only factory GetData probe failed: {error}", file=sys.stderr)
        sys.exit(1)
