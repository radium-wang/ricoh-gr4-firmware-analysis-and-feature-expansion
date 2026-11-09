#!/usr/bin/env python3
"""One bounded GR IV RAM handler trial with an immediate USB restore.

Default mode is read-only. --trial temporarily replaces only the current
SYS_buildinfo handler with a pinned, side-effect-free native return-3 leaf,
then restores the original four bytes in a finally block. --restore-only
accepts only those two known handler values and never installs the trial leaf.
No addresses, bytes, or lengths are accepted from the command line.
"""

import argparse
import json
import os
from pathlib import Path
import struct
import sys

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_runtime_readonly import (
    BUILDINFO_HANDLER, BUILDINFO_INDEX, BUILDINFO_NAME, COMMAND_COUNT,
    COMMAND_SIZE, HOLDER, PROPERTIES, TEST_LEAF, TEST_LEAF_BYTES,
)
from mtp_probe_readonly import PID, VID, command, read_container


RECORD = Path("devkit-output/usb-factory-20261001/reversible-pointer-trial.json")
ORIGINAL = struct.pack("<I", BUILDINFO_HANDLER)
TRIAL = struct.pack("<I", TEST_LEAF)


class Transport:
    def __init__(self, device):
        self.device = device
        self.transaction = 2

    def read(self, address, length):
        response, data, _ = command(
            self.device, 0x9094, self.transaction, address, length
        )
        self.transaction += 1
        if response != 0x2001 or data is None or len(data) != length:
            raise RuntimeError(
                f"GetData 0x{address:08x}/{length}: "
                f"response=0x{response:04x}, bytes={len(data or b'')}"
            )
        return data

    def write_four(self, address, value):
        if len(value) != 4:
            raise ValueError("only four-byte writes are implemented")
        tx = self.transaction
        self.transaction += 1
        request = struct.pack("<IHHIII", 20, 1, 0x9095, tx, address, 4)
        data = struct.pack("<IHHI", 16, 2, 0x9095, tx) + value
        self.device.write(0x01, request, timeout=5000)
        self.device.write(0x01, data, timeout=5000)
        kind, response, received_tx, parameters = read_container(self.device)
        if kind != 3 or received_tx != tx or parameters:
            raise RuntimeError("unexpected SetData response container")
        if response != 0x2001:
            raise RuntimeError(f"SetData failed: 0x{response:04x}")
        return response


def save_record(record):
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    with RECORD.open("w") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def row_address(transport):
    holder = transport.read(HOLDER, 8)
    table, count = struct.unpack_from("<IH", holder)
    if count != COMMAND_COUNT or table % 4 or not 0x59000000 <= table < 0x5A000000:
        raise RuntimeError("unexpected command table anchor")
    address = table + BUILDINFO_INDEX * COMMAND_SIZE
    if address + COMMAND_SIZE > 0x5A000000:
        raise RuntimeError("handler slot outside verified command RAM")
    return address, holder


def checked_row(transport, address):
    row = transport.read(address, 4 + len(BUILDINFO_NAME))
    if row[4:] != BUILDINFO_NAME or row[:4] not in (ORIGINAL, TRIAL):
        raise RuntimeError(f"unexpected SYS_buildinfo row: {row.hex()}")
    return row


def restore(transport, address):
    row = checked_row(transport, address)
    if row[:4] == TRIAL:
        transport.write_four(address, ORIGINAL)
    after = transport.read(address, len(row))
    if after != ORIGINAL + BUILDINFO_NAME:
        raise RuntimeError(f"handler restoration not verified: {after.hex()}")
    return after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--trial", action="store_true")
    modes.add_argument("--restore-only", action="store_true")
    args = parser.parse_args()
    if args.trial and RECORD.exists():
        raise RuntimeError(f"trial record already exists: {RECORD}")

    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        raise RuntimeError("GR IV is not connected")
    if device.bcdDevice != 0x0111:
        raise RuntimeError(f"untested USB firmware version: 0x{device.bcdDevice:04x}")
    usb.util.claim_interface(device, 0)
    opened_by_us = False
    transport = Transport(device)
    try:
        response, info, _ = command(device, 0x1001, 0)
        if response != 0x2001 or info is None or operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError("unexpected GetDeviceInfo result")
        response, _, _ = command(device, 0x1002, 1, 1)
        opened_by_us = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError(f"OpenSession failed: 0x{response:04x}")

        address, holder = row_address(transport)
        before = checked_row(transport, address)
        leaf = transport.read(TEST_LEAF, len(TEST_LEAF_BYTES))
        if leaf != TEST_LEAF_BYTES:
            raise RuntimeError("native return-3 leaf does not match original firmware")
        properties_before = transport.read(PROPERTIES, 5)
        record = {
            "mode": "trial" if args.trial else "restore-only" if args.restore_only else "preflight",
            "holder_hex": holder.hex(),
            "handler_slot": f"0x{address:08x}",
            "before_hex": before.hex(),
            "properties_before_hex": properties_before.hex(),
            "write_attempted": False,
            "restoration_verified": False,
        }
        if args.restore_only:
            after = restore(transport, address)
            record["after_hex"] = after.hex()
            record["restoration_verified"] = True
        elif args.trial:
            if before != ORIGINAL + BUILDINFO_NAME:
                raise RuntimeError("handler is not at the original value")
            save_record(record)
            try:
                record["write_attempted"] = True
                save_record(record)
                transport.write_four(address, TRIAL)
                changed = checked_row(transport, address)
                if changed != TRIAL + BUILDINFO_NAME:
                    raise RuntimeError(f"trial pointer readback mismatch: {changed.hex()}")
                record["trial_readback_hex"] = changed.hex()
            finally:
                after = restore(transport, address)
                record["after_hex"] = after.hex()
                record["restoration_verified"] = True
                save_record(record)
        else:
            record["preflight_passed"] = before == ORIGINAL + BUILDINFO_NAME
        properties_after = transport.read(PROPERTIES, 5)
        record["properties_after_hex"] = properties_after.hex()
        record["capture_properties_unchanged"] = properties_after == properties_before
        if args.trial:
            save_record(record)
        print(json.dumps(record, indent=2))
        return 0 if record.get("capture_properties_unchanged") and (
            not args.trial or record["restoration_verified"]
        ) else 1
    finally:
        try:
            if opened_by_us:
                command(device, 0x1003, transport.transaction)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"Factory pointer trial failed: {error}", file=sys.stderr)
        sys.exit(1)
