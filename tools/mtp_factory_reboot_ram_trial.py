#!/usr/bin/env python3
"""Check whether a pinned diagnostic RAM pointer resets after a normal reboot.

--arm writes only the already-tested SYS_buildinfo handler slot, replacing it
with an immutable ROM return-3 leaf until reboot. --verify reads the slot and
restores the original through USB if the trial value remains. No camera file,
firmware, menu, capture setting or factory service pointer is modified.
"""

import argparse
import json
import os
from pathlib import Path
import sys

import usb.core
import usb.util

from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import (
    ORIGINAL, TRIAL, Transport, checked_row, restore, row_address,
)
from mtp_factory_runtime_readonly import BUILDINFO_NAME, PROPERTIES, TEST_LEAF, TEST_LEAF_BYTES
from mtp_probe_readonly import PID, VID, command


RECORD = Path("devkit-output/usb-factory-20261001/reboot-ram-trial.json")


def persist(report):
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    with RECORD.open("w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def run(mode):
    if mode == "arm" and RECORD.exists():
        raise RuntimeError(f"trial record already exists: {RECORD}")
    if mode == "verify":
        if not RECORD.exists():
            raise RuntimeError("no armed trial record")
        report = json.loads(RECORD.read_text())
        if report.get("stage") not in ("prepared", "armed", "recovery_uncertain"):
            raise RuntimeError("trial record is not in a recoverable stage")
        prior_stage = report["stage"]
    else:
        report = {"stage": "prepared", "operation": "fixed four-byte RAM diagnostic trial",
                  "target": "SYS_buildinfo handler, not USB service", "firmware_modified": False}

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
        row = checked_row(transport, address)
        if transport.read(TEST_LEAF, len(TEST_LEAF_BYTES)) != TEST_LEAF_BYTES:
            raise RuntimeError("diagnostic ROM leaf changed")
        properties = transport.read(PROPERTIES, 5)
        report.update({"holder_hex": holder.hex(), "handler_slot": f"0x{address:08x}",
                       "before_hex": row.hex(), "capture_properties_hex": properties.hex()})

        if mode == "arm":
            if row != ORIGINAL + BUILDINFO_NAME:
                raise RuntimeError("handler is not original; refusing to arm")
            persist(report)
            try:
                transport.write_four(address, TRIAL)
                changed = checked_row(transport, address)
                if changed != TRIAL + BUILDINFO_NAME:
                    raise RuntimeError("trial pointer readback mismatch")
                if transport.read(PROPERTIES, 5) != properties:
                    raise RuntimeError("capture properties changed")
                report.update({"stage": "armed", "trial_readback_hex": changed.hex(),
                               "usb_readback_after_write": True,
                               "next_action": "normal power-off and power-on, then --verify"})
                persist(report)
            except BaseException:
                try:
                    report["emergency_restore_hex"] = restore(transport, address).hex()
                    report["stage"] = "restored_after_arm_error"
                except BaseException as restore_error:
                    report["stage"] = "recovery_uncertain"
                    report["restore_error"] = str(restore_error)
                persist(report)
                raise
        else:
            report["post_reboot_holder_hex"] = holder.hex()
            report["post_reboot_row_hex"] = row.hex()
            report["post_reboot_capture_properties_hex"] = properties.hex()
            if row == ORIGINAL + BUILDINFO_NAME:
                report["reboot_reset_observed"] = prior_stage == "armed"
                report["stage"] = "verified_original_after_reboot" if prior_stage == "armed" else "original_after_uncertain_arm"
            elif row == TRIAL + BUILDINFO_NAME:
                report["reboot_reset_observed"] = False
                report["restore_hex"] = restore(transport, address).hex()
                report["stage"] = "restored_by_usb_after_reboot"
            else:
                raise RuntimeError("unexpected handler row")
            persist(report)
        print(json.dumps(report, indent=2))
    finally:
        try:
            if opened_by_us:
                command(device, 0x1003, transport.transaction)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--arm", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    run("arm" if args.arm else "verify")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Reboot RAM trial failed: {error}", file=sys.stderr)
        sys.exit(1)
