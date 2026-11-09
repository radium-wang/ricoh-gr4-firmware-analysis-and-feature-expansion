#!/usr/bin/env python3
"""One supervised ROM return-3 adapter test; default mode is read-only.

Requires the companion SD script to be waiting. This tool only calls the
immutable native return-3 leaf, through the pinned ROM adapter. It never
allocates memory, uploads code, touches the USB service vtable or flashes.
"""

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

import usb.core
import usb.util

from audit_gr4_rom_call_adapter import (
    ADAPTER, ADAPTER_BYTES, SEND_SLOT, RESPONSE_SLOT, SEND_ORIGINAL,
    RESPONSE_ORIGINAL, RESPONSE_BUFFER, INTEGER_NAMES, INTEGER_VALUES,
)
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_factory_runtime_readonly import TEST_LEAF, TEST_LEAF_BYTES, PROPERTIES
from mtp_factory_script_context_readonly import collect
from mtp_probe_readonly import VID, PID, command


# A nonzero return skips the interpreter's response-string consumer as well
# as leaving its buffer untouched. Use the already pinned return-3 leaf.
RESPONSE_GUARD = TEST_LEAF
RECORD_BYTES = struct.pack('<5I', TEST_LEAF, 0, 17, 13, 11)
INPUT_CODE = struct.unpack('>i', struct.pack('<I', RESPONSE_BUFFER))[0]
JOURNAL = Path('devkit-output/usb-factory-20261001/rom-adapter-trial.json')


def word(value):
    return struct.pack('<I', value)


def save(record):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    temporary = JOURNAL.with_suffix('.json.tmp')
    with temporary.open('w') as handle:
        json.dump(record, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, JOURNAL)


def set_word(io, address, value):
    if address not in (SEND_SLOT, RESPONSE_SLOT, *range(RESPONSE_BUFFER, RESPONSE_BUFFER + 20, 4)):
        raise ValueError('write address outside the seven pinned RAM words')
    io.write_four(address, word(value))
    if io.read(address, 4) != word(value):
        raise RuntimeError('RAM word readback failed')


def validate_record(record):
    if (record.get('adapter') != hex(ADAPTER) or record.get('target') != hex(TEST_LEAF) or
            record.get('record_hex') != RECORD_BYTES.hex()):
        raise ValueError('unexpected journal identity')
    if len(bytes.fromhex(record['buffer_before_hex'])) != 20:
        raise ValueError('journal must contain the complete original buffer')
    holder = bytes.fromhex(record['names_holder_hex'])
    table, count = struct.unpack('<IH', holder)
    length = count * 32
    if not 4 <= count <= 256 or table % 4 or not (
            0x55000000 <= table <= 0x56000000 - length or
            0x59000000 <= table <= 0x5C000000 - length):
        raise ValueError('journal variable table outside checked RAM')
    addresses = record['control_addresses']
    if set(addresses) != {'xpg_state', 'xpg_return', 'xpg_calls', 'xpg_input_code'}:
        raise ValueError('unexpected control variable names')
    values = [int(a, 16) for a in addresses.values()]
    if len(set(values)) != 4 or any(a % 4 or not INTEGER_VALUES <= a < INTEGER_VALUES + count*4
                                   for a in values):
        raise ValueError('journal variable addresses outside integer table')
    return holder, table


def control(io, record):
    holder, table = validate_record(record)
    if io.read(INTEGER_NAMES, 6) != holder:
        raise RuntimeError('script variable generation changed')
    values = {}
    for name, address in record['control_addresses'].items():
        address = int(address, 16)
        index = (address - INTEGER_VALUES) // 4
        if io.read(table + index*32, 32).split(b'\0', 1)[0] != name.encode('ascii'):
            raise RuntimeError('script variable identity changed')
        values[name] = struct.unpack('<i', io.read(address, 4))[0]
    if io.read(INTEGER_NAMES, 6) != holder:
        raise RuntimeError('script variable generation changed while reading')
    if values['xpg_input_code'] != INPUT_CODE:
        raise RuntimeError('script binary payload does not match the pinned holder word')
    return values


def wait_for(io, record, condition, seconds=8):
    deadline = time.monotonic() + seconds
    while True:
        state = control(io, record)
        if condition(state):
            return state
        if time.monotonic() >= deadline:
            raise RuntimeError('script handshake timed out')
        time.sleep(0.2)


def restore(io, record):
    validate_record(record)
    original = bytes.fromhex(record['buffer_before_hex'])
    # Restore the send callback before touching the record. A later loop
    # counter increment proves any single in-flight old callback has returned.
    send = struct.unpack('<I', io.read(SEND_SLOT, 4))[0]
    response = struct.unpack('<I', io.read(RESPONSE_SLOT, 4))[0]
    if send not in (SEND_ORIGINAL, ADAPTER) or response not in (RESPONSE_ORIGINAL, RESPONSE_GUARD):
        raise RuntimeError('callbacks have an unrelated value; refuse overwrite')
    if (send == SEND_ORIGINAL and response == RESPONSE_ORIGINAL and
            io.read(RESPONSE_BUFFER, 20) == original):
        # A completed interpreter releases its variable table. Restoration
        # already visible at every modified word needs no live handshake.
        record['restoration_verified'] = True
        record['stage'] = 'restored'
        save(record)
        return
    set_word(io, SEND_SLOT, SEND_ORIGINAL)
    initial = control(io, record)
    if initial['xpg_state'] not in (1702, 1703):
        wait_for(io, record, lambda s: s['xpg_state'] in (1702, 1703) or
                 (s['xpg_state'] == 1701 and s['xpg_calls'] > initial['xpg_calls']))
    for offset in range(0, 20, 4):
        current = io.read(RESPONSE_BUFFER + offset, 4)
        replacement = RECORD_BYTES[offset:offset+4]
        if current not in (original[offset:offset+4], replacement):
            raise RuntimeError('response record has an unrelated value; refuse overwrite')
    for offset in range(0, 20, 4):
        set_word(io, RESPONSE_BUFFER + offset, struct.unpack_from('<I', original, offset)[0])
    set_word(io, RESPONSE_SLOT, RESPONSE_ORIGINAL)
    if (io.read(SEND_SLOT, 4) != word(SEND_ORIGINAL) or
            io.read(RESPONSE_SLOT, 4) != word(RESPONSE_ORIGINAL) or
            io.read(RESPONSE_BUFFER, 20) != original):
        raise RuntimeError('restoration readback mismatch')
    record['restoration_verified'] = True
    record['stage'] = 'restored'
    save(record)


def trial(io):
    if JOURNAL.exists():
        raise RuntimeError('trial journal already exists; inspect it before another run')
    context = collect(io.read)
    selected = context['selected_variables']
    required = ('xpg_state', 'xpg_return', 'xpg_calls', 'xpg_input_code')
    if not context['script_callbacks_initialized'] or not all(k in selected for k in required):
        raise RuntimeError('companion SD script is not active')
    if (selected['xpg_state']['value'] != 1701 or selected['xpg_return']['value'] != -1 or
            not 1 <= selected['xpg_calls']['value'] <= 540):
        raise RuntimeError('companion script is not in the checked waiting window')
    if io.read(TEST_LEAF, 8) != TEST_LEAF_BYTES:
        raise RuntimeError('immutable diagnostic leaf mismatch')
    record = {'stage': 'prepared', 'target': hex(TEST_LEAF), 'adapter': hex(ADAPTER),
              'names_holder_hex': context['names_holder_hex'],
              'control_addresses': {k: selected[k]['address'] for k in required},
              'buffer_before_hex': context['response_buffer_first_20_hex'],
              'record_hex': RECORD_BYTES.hex(),
              'properties_before_hex': io.read(PROPERTIES, 5).hex(),
              'write_attempted': False, 'native_return_observed': False,
              'restoration_verified': False, 'camera_installable_xpan': False}
    state = control(io, record)
    if state['xpg_state'] != 1701 or state['xpg_return'] != -1:
        raise RuntimeError('script state changed before trial')
    save(record)
    try:
        record['write_attempted'] = True
        save(record)
        set_word(io, RESPONSE_SLOT, RESPONSE_GUARD)
        # Let two serial script calls finish before using the response buffer;
        # an already-loaded original response callback may still be in flight.
        state = control(io, record)
        target_count = state['xpg_calls'] + 2
        wait_for(io, record, lambda s: s['xpg_state'] == 1701 and
                 s['xpg_return'] == -1 and s['xpg_calls'] >= target_count)
        if io.read(RESPONSE_BUFFER, 20).hex() != record['buffer_before_hex']:
            raise RuntimeError('response buffer changed before exclusive use')
        for offset in range(0, 20, 4):
            set_word(io, RESPONSE_BUFFER + offset,
                     struct.unpack_from('<I', RECORD_BYTES, offset)[0])
        set_word(io, SEND_SLOT, ADAPTER)
        record['stage'] = 'adapter_armed'
        save(record)
        observed = wait_for(io, record, lambda s: s['xpg_state'] == 1702)
        record['script_observation'] = observed
        record['native_return_observed'] = observed['xpg_return'] == 3
        if not record['native_return_observed']:
            raise RuntimeError('native adapter did not return expected diagnostic value')
    except Exception as error:
        record['trial_error'] = str(error)
        save(record)
        raise
    finally:
        # On failure the immutable record stays valid until callback return
        # is established. Failure to prove quiescence leaves restoration false.
        try:
            restore(io, record)
        except Exception as error:
            record['stage'] = 'recovery_needed'
            record['restore_error'] = str(error)
            save(record)
            raise
    record['properties_after_hex'] = io.read(PROPERTIES, 5).hex()
    record['capture_properties_unchanged'] = record['properties_after_hex'] == record['properties_before_hex']
    save(record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--trial', action='store_true')
    modes.add_argument('--restore-only', action='store_true')
    args = parser.parse_args()
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None or device.bcdDevice != 0x0111:
        raise RuntimeError('expected connected GR IV firmware 01.11.10.07')
    usb.util.claim_interface(device, 0)
    opened = False
    io = Transport(device)
    try:
        response, info, _ = command(device, 0x1001, 0)
        if response != 0x2001 or info is None or operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError('unexpected GetDeviceInfo result')
        response, _, _ = command(device, 0x1002, 1, 1)
        opened = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError('OpenSession failed')
        if (io.read(ADAPTER, len(ADAPTER_BYTES)) != ADAPTER_BYTES or
                io.read(TEST_LEAF, 8) != TEST_LEAF_BYTES):
            raise RuntimeError('ROM adapter mismatch')
        if args.restore_only:
            record = json.loads(JOURNAL.read_text())
            validate_record(record)
            restore(io, record)
        elif args.trial:
            record = trial(io)
        else:
            record = collect(io.read)
        print(json.dumps(record, indent=2))
    finally:
        try:
            if opened:
                command(device, 0x1003, io.transaction)
        finally:
            usb.util.release_interface(device, 0)
            usb.util.dispose_resources(device)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'ROM adapter trial failed: {error}', file=sys.stderr)
        sys.exit(1)
