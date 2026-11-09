#!/usr/bin/env python3
"""Inspect the fixed TTL callback context. No callback changes or execution."""

import json
import struct
import sys

import usb.core
import usb.util

from audit_gr4_rom_call_adapter import (
    ADAPTER, ADAPTER_BYTES, SEND_SLOT, RESPONSE_SLOT, SEND_ORIGINAL,
    RESPONSE_ORIGINAL, RESPONSE_BUFFER, INTEGER_NAMES, INTEGER_VALUES,
)
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_probe_readonly import VID, PID, command


def collect(read):
    if read(ADAPTER, len(ADAPTER_BYTES)) != ADAPTER_BYTES:
        raise ValueError('ROM adapter does not match the pinned firmware')
    send = struct.unpack('<I', read(SEND_SLOT, 4))[0]
    response = struct.unpack('<I', read(RESPONSE_SLOT, 4))[0]
    if send not in (0, SEND_ORIGINAL) or response not in (0, RESPONSE_ORIGINAL):
        raise ValueError('unexpected script callbacks; this probe will not alter them')
    holder = read(INTEGER_NAMES, 6)
    table, count = struct.unpack('<IH', holder)
    variables = {}
    # The interpreter hides the pointer between commands and also clears it
    # at exit, retaining the count. Null alone cannot prove the table was freed.
    # Do not follow it or infer any live variables.
    if count and table:
        length = count * 32
        if count > 256 or table % 4 or not (
                0x55000000 <= table <= 0x56000000 - length or
                0x59000000 <= table <= 0x5C000000 - length):
            raise ValueError('script variable table outside checked RAM')
        names = read(table, length)
        if len(names) != length:
            raise ValueError('short script variable name table')
        for index in range(count):
            name = names[index*32:(index+1)*32].split(b'\0', 1)[0]
            if name in (b'result', b'xpg_state', b'xpg_return', b'xpg_calls', b'xpg_input_code',
                        b'xpb_state', b'xpb_go', b'xpb_done', b'xpb_return', b'xpb_input_code',
                        b'xpb_token', b'xpb_tick', b'xpb_stop'):
                if name.decode('ascii') in variables:
                    raise ValueError('duplicate selected script variable')
                address = INTEGER_VALUES + index * 4
                variables[name.decode('ascii')] = {
                    'address': hex(address), 'value': struct.unpack('<i', read(address, 4))[0]}
    if read(INTEGER_NAMES, 6) != holder:
        raise ValueError('script variable table changed while reading')
    if read(SEND_SLOT, 4) != struct.pack('<I', send) or read(RESPONSE_SLOT, 4) != struct.pack('<I', response):
        raise ValueError('script callbacks changed while reading')
    return {'operation': '0x9094 GetData only', 'adapter_bytes_match': True,
            'send_callback': hex(send), 'response_callback': hex(response),
            'integer_variable_count': count, 'names_holder_hex': holder.hex(),
            'integer_table_present': bool(table and count),
            'integer_table_released': None if table == 0 and count != 0 else False,
            'integer_table_hidden_or_released': table == 0 and count != 0,
            'selected_variables': variables,
            'response_buffer_first_20_hex': read(RESPONSE_BUFFER, 20).hex(),
            'script_callbacks_initialized': send == SEND_ORIGINAL and response == RESPONSE_ORIGINAL,
            'camera_memory_written': False, 'adapter_executed': False}


def main():
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None or device.bcdDevice != 0x0111:
        raise RuntimeError('expected connected GR IV firmware 01.11.10.07')
    usb.util.claim_interface(device, 0)
    transport = Transport(device)
    opened = False
    try:
        response, info, _ = command(device, 0x1001, 0)
        if response != 0x2001 or info is None or operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError('unexpected GetDeviceInfo result')
        response, _, _ = command(device, 0x1002, 1, 1)
        opened = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError('OpenSession failed')
        print(json.dumps(collect(transport.read), indent=2))
    finally:
        try:
            if opened:
                command(device, 0x1003, transport.transaction)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Read-only script context probe failed: {error}', file=sys.stderr)
        sys.exit(1)
