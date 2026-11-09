#!/usr/bin/env python3
# Copyright 2026 radium-wang
# License: see LICENSE (earlier Apache-2.0 grants remain in force)
"""Read-only PTP/MTP probe for a USB-connected RICOH GR IV.

Only GetDeviceInfo, OpenSession, GetStorageIDs, GetStorageInfo, and
CloseSession are implemented. No object upload or deletion is possible.
"""

import struct
import sys

import usb.core
import usb.util

VID, PID = 0x25FB, 0x2123
EP_IN, EP_OUT = 0x81, 0x01
# GR IV 25fb:2123 interface 0 reports 1024-byte bulk packets. Receive
# buffers must fit whole packets, including the final partial container read.
BULK_READ_UNIT = 1024


def read_container(device):
    chunk = bytes(device.read(EP_IN, BULK_READ_UNIT, timeout=5000))
    if len(chunk) < 12:
        raise RuntimeError(f"short MTP header: {chunk.hex()}")
    length, kind, code, transaction = struct.unpack_from("<IHHI", chunk)
    if length < 12 or length > 1_000_000:
        raise RuntimeError(f"invalid MTP length: {length}")
    while len(chunk) < length:
        remaining = length - len(chunk)
        receive = min(16384, ((remaining + BULK_READ_UNIT - 1) // BULK_READ_UNIT) * BULK_READ_UNIT)
        block = bytes(device.read(EP_IN, receive, timeout=5000))
        if not block:
            raise RuntimeError('empty transfer before the MTP container ended')
        chunk += block
    if len(chunk) != length:
        raise RuntimeError('received bytes beyond one MTP container; refuse to discard them')
    return kind, code, transaction, chunk[12:length]


def command(device, opcode, transaction, *parameters):
    packet = struct.pack("<IHHI", 12 + 4 * len(parameters), 1, opcode, transaction)
    packet += b"".join(struct.pack("<I", p) for p in parameters)
    device.write(EP_OUT, packet, timeout=5000)
    data = None
    while True:
        kind, code, received_transaction, payload = read_container(device)
        if received_transaction != transaction:
            raise RuntimeError(f"transaction mismatch: {received_transaction} != {transaction}")
        if kind == 2:
            data = payload
        elif kind == 3:
            return code, data, payload
        else:
            raise RuntimeError(f"unexpected MTP container type: {kind}")


def main():
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None:
        raise RuntimeError("GR IV is not connected")
    usb.util.claim_interface(device, 0)
    try:
        code, data, _ = command(device, 0x1001, 0)
        print(f"GetDeviceInfo response=0x{code:04x}, data={len(data or b'')} bytes")
        if code != 0x2001:
            return
        if data and len(data) >= 11:
            offset = 8 + 1 + 2 * data[8] + 2
            if len(data) >= offset + 4:
                op_count = struct.unpack_from("<I", data, offset)[0]
                if op_count <= 256 and len(data) >= offset + 4 + op_count * 2:
                    ops = struct.unpack_from(f"<{op_count}H", data, offset + 4)
                    print("Supported operations:", [f"0x{x:04x}" for x in ops])
                    offset += 4 + op_count * 2
                    labels = ("events", "device properties", "capture formats", "image formats")
                    for label in labels:
                        if len(data) < offset + 4:
                            break
                        count = struct.unpack_from("<I", data, offset)[0]
                        if count > 256 or len(data) < offset + 4 + count * 2:
                            break
                        values = struct.unpack_from(f"<{count}H", data, offset + 4)
                        print(f"Supported {label}:", [f"0x{x:04x}" for x in values])
                        offset += 4 + count * 2
        code, _, _ = command(device, 0x1002, 1, 1)
        print(f"OpenSession response=0x{code:04x}")
        opened_by_us = code == 0x2001
        if code not in (0x2001, 0x201E):
            return
        try:
            for prop_index, prop in enumerate((0xD406, 0xD407, 0xD303)):
                prop_code, prop_data, _ = command(device, 0x1014, 10 + prop_index, prop)
                print(f"GetDevicePropDesc 0x{prop:04x}: response=0x{prop_code:04x}, data={(prop_data or b'')[:96].hex()}")
            code, data, _ = command(device, 0x1004, 2)
            print(f"GetStorageIDs response=0x{code:04x}")
            if code != 0x2001 or data is None or len(data) < 4:
                return
            count = struct.unpack_from("<I", data)[0]
            if len(data) < 4 + count * 4:
                raise RuntimeError("truncated StorageIDs")
            ids = struct.unpack_from(f"<{count}I", data, 4)
            print("StorageIDs:", [f"0x{x:08x}" for x in ids])
            for number, storage_id in enumerate(ids, 3):
                code, info, _ = command(device, 0x1005, number, storage_id)
                print(f"GetStorageInfo 0x{storage_id:08x}: response=0x{code:04x}, bytes={len(info or b'')}")
                if code == 0x2001 and info and len(info) >= 26:
                    storage_type, filesystem_type, access = struct.unpack_from("<HHH", info)
                    capacity, free_bytes, free_images = struct.unpack_from("<QQI", info, 6)
                    print(f"  type={storage_type}, filesystem={filesystem_type}, access={access}, capacity={capacity}, free={free_bytes}, free_images={free_images}")
                code, handles, _ = command(device, 0x1007, 20 + number, storage_id, 0, 0)
                if code == 0x2001 and handles and len(handles) >= 4:
                    handle_count = struct.unpack_from("<I", handles)[0]
                    print(f"  exposed objects={handle_count}")
                    root_names = []
                    for index in range(handle_count):
                        handle = struct.unpack_from("<I", handles, 4 + index * 4)[0]
                        object_code, object_info, _ = command(device, 0x1008, 100 + number * 10 + index, handle)
                        if object_code == 0x2001 and object_info and len(object_info) > 53:
                            name_length = object_info[52]
                            name = object_info[53:53 + name_length * 2].decode("utf-16le", errors="replace").rstrip("\x00")
                            parent = struct.unpack_from("<I", object_info, 38)[0]
                            if parent == 0xFFFFFFFF:
                                root_names.append(name)
                            if name.upper() in ("00078560.636", "DEVELOP.MOD"):
                                print(f"    existing probe name: {name}, parent=0x{parent:08x}")
                    print(f"  root names: {root_names}")
        finally:
            if opened_by_us:
                code, _, _ = command(device, 0x1003, 100)
                print(f"CloseSession response=0x{code:04x}")
    finally:
        usb.util.release_interface(device, 0)
        usb.util.dispose_resources(device)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"MTP probe failed: {error}", file=sys.stderr)
        sys.exit(1)
