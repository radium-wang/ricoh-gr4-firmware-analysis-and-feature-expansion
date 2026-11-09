#!/usr/bin/env python3
"""Read the pinned heap service object. No allocation, write or code execution."""

import json
import struct
import sys

import usb.core
import usb.util

from audit_gr4_native_memory_abi import ALLOCATOR_SLOT, ALLOCATOR_VTABLE, ALLOCATOR_METHODS
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_probe_readonly import PID, VID, command


def collect(read):
    slot = read(ALLOCATOR_SLOT, 4)
    if len(slot) != 4:
        raise ValueError("short allocator registry entry")
    address = struct.unpack("<I", slot)[0]
    if address % 4 or not (0x55000000 <= address <= 0x56000000 - 40 or
                          0x59000000 <= address <= 0x5C000000 - 40):
        raise ValueError("allocator object outside known RAM ranges")
    header = read(address, 8)
    if len(header) != 8 or struct.unpack_from("<I", header)[0] != ALLOCATOR_VTABLE:
        raise ValueError("allocator object does not match pinned heap class")
    if header[4] != 2:
        raise ValueError("allocator object has unexpected registry ID")
    table = read(ALLOCATOR_VTABLE, 16)
    if table != struct.pack("<4I", *ALLOCATOR_METHODS):
        raise ValueError("allocator method table mismatch")
    ownership_method = read(ALLOCATOR_VTABLE + 24, 4)
    if ownership_method != struct.pack('<I', 0x538DDF1C):
        raise ValueError('allocator ownership predicate mismatch')
    state = read(address, 40)
    if len(state) != 40 or state[:8] != header or read(ALLOCATOR_SLOT, 4) != slot:
        raise ValueError("allocator registry changed during read")
    arena_length = struct.unpack_from('<I', state, 28)[0]
    arena_base = struct.unpack_from('<I', state, 36)[0]
    if not (arena_length >= 8192 and 0x59000000 <= arena_base < arena_base + arena_length <= 0x5C000000):
        raise ValueError('allocator arena outside checked RAM')
    return {"operation": "0x9094 GetData only", "registry_slot": hex(ALLOCATOR_SLOT),
            "object_address": hex(address), "object_hex": state.hex(),
            "vtable_hex": table.hex(), "heap_class_verified": True,
            "arena_base": arena_base, "arena_length": arena_length,
            "ownership_predicate_verified": True,
            "allocation_called": False, "camera_memory_written": False,
            "module_load_supported": False}


def main():
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        raise RuntimeError("GR IV is not connected")
    if device.bcdDevice != 0x0111:
        raise RuntimeError("untested USB firmware version")
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
            raise RuntimeError("OpenSession failed")
        print(json.dumps(collect(transport.read), indent=2))
    finally:
        try:
            if opened_by_us:
                command(device, 0x1003, transport.transaction)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Read-only allocator probe failed: {error}", file=sys.stderr)
        sys.exit(1)
