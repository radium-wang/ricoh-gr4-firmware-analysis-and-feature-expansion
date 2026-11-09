#!/usr/bin/env python3
"""Host-only transaction fault checks. No USB, camera, or ARM execution."""

import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

import mtp_factory_rom_adapter_trial as trial
from audit_gr4_rom_call_adapter import INTEGER_VALUES, ADAPTER_BYTES


class CameraModel:
    def __init__(self, fault=None):
        self.memory = {}
        self.clock = 0
        self.writes = []
        self.fault = fault
        self.triggered = False
        self.await_bad_read = False
        self.original_buffer = bytes(range(1, 21))
        self.put(trial.ADAPTER, ADAPTER_BYTES)
        self.put(trial.TEST_LEAF, trial.TEST_LEAF_BYTES)
        self.put(trial.SEND_SLOT, trial.word(trial.SEND_ORIGINAL))
        self.put(trial.RESPONSE_SLOT, trial.word(trial.RESPONSE_ORIGINAL))
        self.put(trial.RESPONSE_BUFFER, self.original_buffer)
        self.put(trial.PROPERTIES, bytes.fromhex('000000803f'))
        self.names = ('result', 'xpg_state', 'xpg_return', 'xpg_calls', 'xpg_input_code')
        self.table = 0x59002000
        self.put(trial.INTEGER_NAMES, struct.pack('<IH', self.table, 5))
        self.put(self.table, b''.join(n.encode().ljust(32, b'\0') for n in self.names))
        for name, value in zip(self.names, (-1, 1701, -1, 10, trial.INPUT_CODE)):
            self.variable(name, value)

    def put(self, address, value):
        self.memory.update({address+i: b for i, b in enumerate(value)})

    def read(self, address, length):
        if self.await_bad_read and address == trial.SEND_SLOT:
            self.await_bad_read = False
            raise RuntimeError('injected adapter readback failure')
        return bytes(self.memory[address+i] for i in range(length))

    def variable(self, name, value=None):
        address = INTEGER_VALUES + self.names.index(name)*4
        if value is not None:
            self.put(address, struct.pack('<i', value))
        return struct.unpack('<i', self.read(address, 4))[0]

    def write_four(self, address, value):
        self.writes.append((address, value.hex()))
        restoring = address == trial.SEND_SLOT and value == trial.word(trial.SEND_ORIGINAL)
        if self.fault == 'restore_write' and restoring and not self.triggered:
            self.triggered = True
            raise RuntimeError('injected restoration write failure')
        self.put(address, value)
        if self.triggered:
            return
        if self.fault == 'partial_record' and address == trial.RESPONSE_BUFFER + 8:
            self.triggered = True
            raise RuntimeError('injected failure after third record write committed')
        if self.fault == 'arm_readback' and address == trial.SEND_SLOT and value == trial.word(trial.ADAPTER):
            self.triggered = True
            self.await_bad_read = True

    def sleep(self, seconds):
        before = int(self.clock)
        self.clock += seconds
        if int(self.clock) == before or self.variable('xpg_state') != 1701:
            return
        self.variable('xpg_calls', self.variable('xpg_calls') + 1)
        callback = struct.unpack('<I', self.read(trial.SEND_SLOT, 4))[0]
        if callback != trial.ADAPTER:
            self.variable('xpg_return', -1)
            return
        assert self.read(trial.RESPONSE_BUFFER, 20) == trial.RECORD_BYTES
        assert self.read(trial.RESPONSE_SLOT, 4) == trial.word(trial.RESPONSE_GUARD)
        if self.fault == 'timeout':
            return
        if self.fault == 'generation_change':
            self.put(trial.INTEGER_NAMES, struct.pack('<IH', self.table, 6))
            return
        self.variable('xpg_return', 4 if self.fault == 'unexpected_return' else 3)
        self.variable('xpg_state', 1702)

    def assert_restored(self):
        assert self.read(trial.SEND_SLOT, 4) == trial.word(trial.SEND_ORIGINAL)
        assert self.read(trial.RESPONSE_SLOT, 4) == trial.word(trial.RESPONSE_ORIGINAL)
        assert self.read(trial.RESPONSE_BUFFER, 20) == self.original_buffer


def check():
    results = []
    with tempfile.TemporaryDirectory() as directory:
        for fault in (None, 'partial_record', 'arm_readback', 'timeout', 'unexpected_return',
                      'restore_write', 'generation_change'):
            model = CameraModel(fault)
            journal = Path(directory) / ((fault or 'success') + '.json')
            with patch.object(trial, 'JOURNAL', journal), \
                    patch.object(trial.time, 'monotonic', lambda: model.clock), \
                    patch.object(trial.time, 'sleep', model.sleep):
                error = None
                try:
                    trial.trial(model)
                except RuntimeError as caught:
                    error = str(caught)
                record = json.loads(journal.read_text())
                assert bool(error) == bool(fault)
                if fault in ('restore_write', 'generation_change'):
                    assert record['stage'] == 'recovery_needed'
                    assert not record['restoration_verified']
                else:
                    model.assert_restored()
                    assert record['restoration_verified']
                if fault == 'restore_write':
                    trial.restore(model, record)
                    model.assert_restored()
                    assert record['restoration_verified']
                if fault is None:
                    assert record['native_return_observed']
                    assert record['capture_properties_unchanged']
                    count = len(model.writes)
                    try:
                        trial.trial(model)
                        raise AssertionError('existing journal accepted')
                    except RuntimeError:
                        pass
                    assert len(model.writes) == count
                    model.put(trial.INTEGER_NAMES, struct.pack('<IH', 0, len(model.names)))
                    trial.restore(model, record)
                    assert len(model.writes) == count
                    assert record['restoration_verified']
                results.append({'case': fault or 'success', 'expected_error': error,
                                'restoration_verified': record['restoration_verified']})
        model = CameraModel()
        model.variable('xpg_state', 1700)
        journal = Path(directory) / 'preflight.json'
        with patch.object(trial, 'JOURNAL', journal):
            try:
                trial.trial(model)
                raise AssertionError('bad waiting state accepted')
            except RuntimeError:
                pass
        assert not model.writes and not journal.exists()
        results.append({'case': 'preflight_rejected', 'camera_writes': 0})
        model = CameraModel()
        model.variable('xpg_input_code', 0)
        with patch.object(trial, 'JOURNAL', journal):
            try:
                trial.trial(model)
                raise AssertionError('bad binary payload accepted')
            except RuntimeError:
                pass
        assert not model.writes and not journal.exists()
        results.append({'case': 'wrong_binary_payload_rejected', 'camera_writes': 0})
        record = json.loads((Path(directory) / 'success.json').read_text())
        record['control_addresses']['xpg_state'] = '0x53000000'
        count = len(model.writes)
        try:
            trial.restore(model, record)
            raise AssertionError('invalid journal accepted')
        except ValueError:
            pass
        assert len(model.writes) == count
        results.append({'case': 'invalid_journal_rejected', 'camera_writes': 0})
    return {'cases_passed': len(results), 'camera_accessed': False,
            'script_and_native_calls_simulated': True,
            'hardware_recovery_verified': False, 'cases': results}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
