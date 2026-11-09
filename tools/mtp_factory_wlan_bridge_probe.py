#!/usr/bin/env python3
"""Probe two pinned, temporary GR IV WLAN factory commands over USB.

Only firmware 01.11.10.07 is supported. The offline image proves that
RunFunc(0x0f, 0x2c) calls the fixed command `iperf3 -s &` and that
RunFunc(0x0f, 0x2d) calls `killall iperf3`. Neither accepts a host shell
string. The stop command is attempted in a finally block, and rebooting
also ends any temporary iperf3 process. No camera file upload is sent.
"""

import sys
import time

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_probe_readonly import PID, VID, command


def print_reply(label, reply):
    response, data, parameters = reply
    print(f"{label}: response=0x{response:04x} data={(data or b'').hex()} parameters={parameters.hex()}", flush=True)
    return response


def main():
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None or device.bcdDevice != 0x0111:
        raise RuntimeError("expected connected GR IV firmware 01.11.10.07")
    usb.util.claim_interface(device, 0)
    opened_by_us = False
    start_sent = False
    next_transaction = 2

    def send(label, opcode, *params):
        nonlocal next_transaction
        reply = command(device, opcode, next_transaction, *params)
        next_transaction += 1
        return print_reply(label, reply)

    try:
        response, info, _ = command(device, 0x1001, 0)
        if response != 0x2001 or info is None or operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError("unexpected device or MTP operation list")
        response, _, _ = command(device, 0x1002, 1, 1)
        opened_by_us = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError(f"OpenSession failed: 0x{response:04x}")
        print(f"OpenSession: 0x{response:04x}", flush=True)
        start_sent = True
        send("fixed iperf start", 0x9091, 0x0F, 0x2C)
        send("start completion", 0x9092)
        time.sleep(0.5)
    finally:
        try:
            if start_sent:
                try:
                    send("fixed iperf stop", 0x9091, 0x0F, 0x2D)
                    send("stop completion", 0x9092)
                except Exception as error:
                    print(f"STOP COMMAND FAILED: {error}; power-cycle camera to end iperf3", file=sys.stderr)
                    raise
            if opened_by_us:
                send("CloseSession", 0x1003)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Factory WLAN bridge probe failed: {error}", file=sys.stderr)
        sys.exit(1)
