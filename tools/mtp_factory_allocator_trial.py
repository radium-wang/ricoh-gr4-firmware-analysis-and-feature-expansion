#!/usr/bin/env python3
"""Default read-only. --trial tests allocation/data/free; --cache-trial adds cache.

One 8192-byte allocation per batch, no code upload/execution or flash.
Requires SD companion protocol 1801. Recovery never repeats a completed free.
"""

import argparse
import json
import sys
from pathlib import Path

import usb.core
import usb.util

from audit_gr4_native_memory_abi import audit as audit_memory
from audit_gr4_rom_call_adapter import audit as audit_adapter
from gr4_usb_call_session import (Session, ADAPTER, ADAPTER_BYTES, TEST_LEAF, TEST_LEAF_BYTES,
    MALLOC, MALLOC_BYTES, FREE, FREE_BYTES, CACHE_SVC, CACHE_BYTES, QUERY_SVC, QUERY_BYTES)
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_factory_script_context_readonly import collect
from mtp_probe_readonly import VID, PID, command

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / 'devkit-output/usb-factory-20261001/allocator-session-trial.json'
CACHE_JOURNAL = ROOT / 'devkit-output/usb-factory-20261001/cache-session-trial.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--trial', action='store_true')
    modes.add_argument('--recover', action='store_true')
    modes.add_argument('--cache-trial', action='store_true')
    modes.add_argument('--recover-cache', action='store_true')
    args = parser.parse_args()
    raw = (ROOT / 'samples/gr4_decoded.bin').read_bytes()
    audit_memory(raw); audit_adapter(raw)
    device = usb.core.find(idVendor=VID, idProduct=PID)
    if device is None or device.bcdDevice != 0x0111:
        raise RuntimeError('expected connected GR IV 01.11.10.07')
    usb.util.claim_interface(device, 0)
    io = Transport(device)
    opened = False
    try:
        response, info, _ = command(device, 0x1001, 0)
        if response != 0x2001 or info is None or operations_from_device_info(info) != EXPECTED_OPERATIONS:
            raise RuntimeError('unexpected MTP device information')
        response, _, _ = command(device, 0x1002, 1, 1)
        opened = response == 0x2001
        if response not in (0x2001, 0x201E):
            raise RuntimeError('OpenSession failed')
        for address, expected in ((ADAPTER, ADAPTER_BYTES), (TEST_LEAF, TEST_LEAF_BYTES),
                                  (MALLOC, MALLOC_BYTES), (FREE, FREE_BYTES),
                                  (CACHE_SVC, CACHE_BYTES), (QUERY_SVC, QUERY_BYTES)):
            if io.read(address, len(expected)) != expected:
                raise RuntimeError('pinned native code mismatch')
        if args.recover or args.recover_cache:
            selected_journal = CACHE_JOURNAL if args.recover_cache else JOURNAL
            session = Session(io, selected_journal, json.loads(selected_journal.read_text()))
            try:
                session.cleanup()
            except Exception as error:
                session.record.update(stage='recovery_needed', recovery_error=str(error))
                session.save()
                raise
            result = session.record
        elif args.trial:
            result = Session.begin(io, JOURNAL).batch()
        elif args.cache_trial:
            result = Session.begin_or_resume(io, CACHE_JOURNAL, JOURNAL).cache_batch()
        else:
            result = collect(io.read)
        print(json.dumps(result, indent=2))
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
        print(f'Allocator session failed: {error}', file=sys.stderr)
        sys.exit(1)
