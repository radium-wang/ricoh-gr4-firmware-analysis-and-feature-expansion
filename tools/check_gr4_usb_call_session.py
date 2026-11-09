#!/usr/bin/env python3
"""Local protocol/transaction model. Never contacts a camera."""

import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

import gr4_usb_call_session as gate
from audit_gr4_native_memory_abi import ALLOCATOR_SLOT, ALLOCATOR_VTABLE, ALLOCATOR_METHODS


class CameraModel:
    def __init__(self, fault=None):
        self.memory = {}
        self.fault = fault
        self.fault_used = False
        self.disconnected = False
        self.clock = 0
        self.writes = []
        self.native_calls = []
        self.allocations = 0
        self.frees = 0
        self.owned = False
        self.pointer = 0x59A10000
        self.original_data = bytes(range(32))
        self.original_buffer = bytes(range(1, 21))
        self.names = ('result', *gate.NAMES)
        self.table = 0x59002000
        self.put(gate.INTEGER_NAMES, struct.pack('<IH', self.table, len(self.names)))
        self.put(self.table, b''.join(n.encode().ljust(32, b'\0') for n in self.names))
        defaults = {'xpb_state':1801, 'xpb_input_code':gate.INPUT_CODE, 'xpb_return':-999}
        for name in self.names:
            self.variable(name, defaults.get(name, 0))
        for address, data in ((gate.ADAPTER, gate.ADAPTER_BYTES),
                (gate.TEST_LEAF, gate.TEST_LEAF_BYTES), (gate.MALLOC, gate.MALLOC_BYTES),
                (gate.FREE, gate.FREE_BYTES), (gate.SEND_SLOT, gate.word(gate.SEND_ORIGINAL)),
                (gate.CACHE_SVC, gate.CACHE_BYTES), (gate.QUERY_SVC, gate.QUERY_BYTES),
                (gate.RESPONSE_SLOT, gate.word(gate.RESPONSE_ORIGINAL)),
                (gate.RESPONSE_BUFFER, self.original_buffer),
                (gate.PROPERTIES, bytes.fromhex('000000803f')),
                (ALLOCATOR_SLOT, gate.word(0x553A0490)),
                (ALLOCATOR_VTABLE, struct.pack('<4I', *ALLOCATOR_METHODS))):
            self.put(address, data)
        self.put(0x553A0490, gate.word(ALLOCATOR_VTABLE)+gate.word(2)+bytes(32))
        self.put(ALLOCATOR_VTABLE+24, gate.word(0x538DDF1C))
        self.put(0x553A0490+28, gate.word(0x1000000))
        self.put(0x553A0490+36, gate.word(0x59600000))

    def put(self, address, data):
        self.memory.update({address+i: b for i,b in enumerate(data)})

    def read(self, address, length):
        if self.disconnected:
            raise RuntimeError('injected USB disconnect')
        return bytes(self.memory[address+i] for i in range(length))

    def variable(self, name, value=None):
        address = gate.INTEGER_VALUES + self.names.index(name)*4
        if value is not None:
            self.put(address, gate.word(value))
        return struct.unpack('<i', bytes(self.memory[address+i] for i in range(4)))[0]

    def write_four(self, address, data):
        if self.disconnected:
            raise RuntimeError('injected USB disconnect')
        self.writes.append((address, data.hex()))
        self.put(address, data)
        if self.fault_used:
            return
        current_target = struct.unpack('<I', self.read(gate.RESPONSE_BUFFER, 4))[0]
        go_address = gate.INTEGER_VALUES + self.names.index('xpb_go')*4
        hit = ((self.fault == 'partial_record' and address == gate.RESPONSE_BUFFER+8) or
               (self.fault == 'malloc_go_after_commit' and address == go_address and current_target == gate.MALLOC) or
               (self.fault == 'free_go_after_commit' and address == go_address and current_target == gate.FREE) or
               (self.fault == 'owned_write' and address == self.pointer and data != self.original_data[:4]))
        if hit:
            self.fault_used = True
            raise RuntimeError('injected failure after write committed')

    def sleep(self, seconds):
        self.clock += seconds
        self.variable('xpb_tick', self.variable('xpb_tick')+1)
        seq, done = self.variable('xpb_go'), self.variable('xpb_done')
        if seq == done:
            return
        assert seq == done+1
        assert self.read(gate.SEND_SLOT, 4) == gate.word(gate.ADAPTER)
        assert self.read(gate.RESPONSE_SLOT, 4) == gate.word(gate.TEST_LEAF)
        target, adjustment, r2, r1, r0 = struct.unpack('<5I', self.read(gate.RESPONSE_BUFFER, 20))
        assert adjustment == 0
        self.variable('xpb_state', 1802)
        self.native_calls.append((target, r0, r1, r2))
        if target == gate.TEST_LEAF:
            value = 3
        elif target == gate.MALLOC:
            assert (r0, r1, r2) == (gate.SIZE, 0, 0)
            self.allocations += 1
            if self.fault == 'malloc_zero':
                value = 0
            else:
                self.owned = True
                value = self.pointer
                self.put(self.pointer-8, gate.word(self.pointer-48)+bytes(4))
                self.put(self.pointer, bytes(i % 256 for i in range(gate.SIZE)))
        elif target in (gate.QUERY_SVC, gate.CACHE_SVC):
            assert self.owned and r0 % 64 == 0 and r1 == 64
            assert r2 == r0+128 and self.pointer <= r0 < r2+20 <= self.pointer+gate.SIZE
            if target == gate.QUERY_SVC:
                self.put(r2,struct.pack('<5I',r0,r0 & ~4095,4096,64,64))
                value = 0
            elif self.fault == 'cache_failure':
                value = -655360
            else:
                self.put(r2,gate.word(r0))
                value = 64
        elif target == gate.FREE:
            assert (r0, r1, r2) == (self.pointer, 0, 0) and self.owned
            self.frees += 1
            value = 0 if self.fault == 'free_failure' else 1
            if value == 1:
                self.owned = False
        else:
            raise AssertionError('unknown native target')
        self.variable('xpb_return', value)
        self.variable('xpb_done', seq)
        self.variable('xpb_state', 1803)
        if ((self.fault == 'disconnect_malloc' and target == gate.MALLOC) or
                (self.fault == 'disconnect_free' and target == gate.FREE) or
                (self.fault == 'disconnect_cache' and target == gate.CACHE_SVC)) and not self.fault_used:
            self.fault_used = True
            self.disconnected = True

    def assert_restored(self):
        assert self.read(gate.SEND_SLOT, 4) == gate.word(gate.SEND_ORIGINAL)
        assert self.read(gate.RESPONSE_SLOT, 4) == gate.word(gate.RESPONSE_ORIGINAL)
        assert self.read(gate.RESPONSE_BUFFER, 20) == self.original_buffer


def check():
    results = []
    with tempfile.TemporaryDirectory() as temporary:
        for fault in (None, 'partial_record', 'malloc_go_after_commit', 'free_go_after_commit',
                      'owned_write', 'malloc_zero', 'free_failure', 'disconnect_malloc', 'disconnect_free'):
            model = CameraModel(fault)
            journal = Path(temporary)/(str(fault)+'.json')
            with patch.object(gate.time, 'monotonic', lambda: model.clock), \
                    patch.object(gate.time, 'sleep', model.sleep):
                session = gate.Session.begin(model, journal)
                error = None
                try:
                    session.batch()
                except RuntimeError as caught:
                    error = str(caught)
                assert bool(error) == bool(fault)
                if fault in ('disconnect_malloc', 'disconnect_free'):
                    record = json.loads(journal.read_text())
                    assert record['stage'] == 'recovery_needed'
                    model.disconnected = False
                    session = gate.Session(model, journal, record)
                    session.cleanup()
                model.assert_restored()
                if fault == 'free_failure':
                    assert model.frees == 1 and model.owned
                    assert session.record['allocation_uncertain']
                    try:
                        session.cleanup()
                        raise AssertionError('failed free retried')
                    except RuntimeError:
                        pass
                    assert model.frees == 1
                else:
                    assert not model.owned
                    assert session.record['cleanup_verified']
                    if model.frees:
                        assert model.read(model.pointer, 32) == model.original_data
                assert model.allocations <= 1 and model.frees <= 1
                if not fault:
                    assert session.record['batch_passed']
                    assert [c[0] for c in model.native_calls] == [gate.TEST_LEAF, gate.MALLOC, gate.FREE, gate.TEST_LEAF]
                    assert session.record['owned_pattern_readback_verified']
                    count = len(model.writes)
                    session.cleanup()
                    assert len(model.writes) == count and model.frees == 1
                results.append({'case': fault or 'complete_batch', 'expected_error': error,
                                'malloc_calls': model.allocations, 'free_calls': model.frees,
                                'allocation_owned_after': model.owned})
        model = CameraModel()
        journal = Path(temporary)/'reboot.json'
        with patch.object(gate.time, 'monotonic', lambda: model.clock), \
                patch.object(gate.time, 'sleep', model.sleep):
            session = gate.Session.begin(model, journal)
            session.invoke(gate.MALLOC, [gate.SIZE, 0, 0])
            model.variable('xpb_token', 0)
            model.variable('xpb_go', 0); model.variable('xpb_done', 0)
            count = len(model.writes)
            try:
                session.cleanup()
                raise AssertionError('old pointer reused after reboot')
            except RuntimeError:
                pass
            assert len(model.writes) == count and model.frees == 0
        results.append({'case':'cross_reboot_refused', 'additional_writes':0, 'free_calls':0})
        for fault in (None,'cache_failure','disconnect_cache'):
            model=CameraModel(fault);model.pointer=0x59A10018
            journal=Path(temporary)/('cache-'+str(fault)+'.json')
            with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
                session=gate.Session.begin(model,journal)
                error=None
                try:session.cache_batch()
                except RuntimeError as caught:error=str(caught)
                assert bool(error)==bool(fault)
                if fault=='disconnect_cache':
                    model.disconnected=False
                    session=gate.Session(model,journal,json.loads(journal.read_text()))
                    session.cleanup()
                assert not model.owned and model.allocations==model.frees==1
                model.assert_restored()
                assert session.record['owned_data_restoration_verified']
                assert session.record['cache_output_restoration_verified']
                if fault is None:assert session.record['cache_batch_passed'] and session.record['cache_service_verified']
            results.append({'case':'cache-'+str(fault),'expected_error':error,'free_calls':model.frees})
        model=CameraModel();first=Path(temporary)/'resume-first.json';second=Path(temporary)/'resume-second.json'
        with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
            gate.Session.begin(model,first).batch()
            session=gate.Session.begin_or_resume(model,second,first)
            session.cache_batch()
            assert model.variable('xpb_done')==9 and model.allocations==model.frees==2
            assert not model.owned
        results.append({'case':'same-boot-resume','completed_requests':9,'owned_allocations_after':0})
        for fault in ('hidden-before', 'hidden-after', 'hidden-permanent',
                      'different-table', 'different-count', 'hidden-then-reboot'):
            model = CameraModel()
            journal = Path(temporary)/(fault+'.json')
            with patch.object(gate.time, 'monotonic', lambda: model.clock), \
                    patch.object(gate.time, 'sleep', model.sleep):
                session = gate.Session.begin(model, journal)
                original_read = model.read
                calls = [0]
                def read(address, length):
                    data = original_read(address, length)
                    if address != gate.INTEGER_NAMES or length != 6:
                        return data
                    calls[0] += 1
                    if fault == 'hidden-permanent':
                        return bytes(4) + data[4:]
                    if fault == 'different-table':
                        return gate.word(model.table+32) + data[4:]
                    if fault == 'different-count':
                        return data[:4] + struct.pack('<H',len(model.names)+1)
                    at = 2 if fault == 'hidden-after' else 1
                    if calls[0] == at:
                        if fault == 'hidden-then-reboot':
                            model.variable('xpb_token',0)
                        return bytes(4) + data[4:]
                    return data
                model.read = read
                count = len(model.writes)
                error = None
                try:
                    session.control()
                except RuntimeError as caught:
                    error = str(caught)
                assert bool(error) == (fault not in ('hidden-before','hidden-after'))
                assert len(model.writes) == count and not model.native_calls
                assert calls[0] <= 6
            results.append({'case':fault,'expected_error':error,
                            'holder_reads':calls[0],'new_camera_writes':0})
    return {'cases_passed':len(results), 'camera_accessed':False,
            'native_malloc_free_simulated':True, 'hardware_allocation_verified':False,
            'cases':results}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
