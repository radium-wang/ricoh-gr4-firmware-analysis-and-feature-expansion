#!/usr/bin/env python3
"""Bounded native calls with an ownership ledger and checked script identity."""

import json
import os
import secrets
import struct
import time
from pathlib import Path

from audit_gr4_rom_call_adapter import (ADAPTER, ADAPTER_BYTES, SEND_SLOT,
    RESPONSE_SLOT, SEND_ORIGINAL, RESPONSE_ORIGINAL, RESPONSE_BUFFER,
    INTEGER_NAMES, INTEGER_VALUES)
from mtp_factory_runtime_readonly import TEST_LEAF, TEST_LEAF_BYTES, PROPERTIES
from mtp_factory_script_context_readonly import collect
from mtp_factory_allocator_readonly import collect as allocator_context

MALLOC = 0x538E0A24
FREE = 0x538E0A60
MALLOC_BYTES = bytes.fromhex('0dc0a0e130d82de904b04ce20050a0e10200a0e30e40a0e1f7f2ffeb003090e50510a0e10020a0e308c093e50430a0e114d04be230689de81cff2fe1')
FREE_BYTES = bytes.fromhex('0dc0a0e130d82de90050a0e104b04ce20200a0e30e40a0e1e8f2ffeb003090e50510a0e10420a0e10c3093e514d04be230689de813ff2fe1')
CACHE_SVC = 0x53065A40
QUERY_SVC = 0x53065A8C
SVC_PREFIX = bytes.fromhex('0f002de90d00a0e100402de90cc09fe5060000ef0040bde810d08de21eff2fe1')
CACHE_BYTES = SVC_PREFIX + bytes.fromhex('11030101')
QUERY_BYTES = SVC_PREFIX + bytes.fromhex('11030001')
SIZE = 8192
INPUT_CODE = -1877394603
NAMES = ('xpb_state', 'xpb_go', 'xpb_done', 'xpb_return', 'xpb_input_code',
         'xpb_token', 'xpb_tick', 'xpb_stop')
PATTERN = b'GR4_XPAN_OWNED_RAM_TEST_20261001'.ljust(32, b'\0')
SCHEMA = 'gr4-usb-call-session-1801'


class NamesTemporarilyHidden(RuntimeError):
    """The interpreter hid the name pointer; no table has been followed."""


def word(value):
    return struct.pack('<I', value & 0xFFFFFFFF)


def pointer_valid(address):
    return address % 8 == 0 and 0x59000008 <= address <= 0x5C000000 - SIZE


class Session:
    def __init__(self, io, journal, record):
        self.io, self.journal, self.record = io, Path(journal), record
        self.validate()

    def validate(self):
        r = self.record
        if r.get('schema') != SCHEMA or not 1 <= r['token'] < 0x40000000:
            raise ValueError('unexpected session identity')
        table, count = struct.unpack('<IH', bytes.fromhex(r['names_holder_hex']))
        if not 8 <= count <= 256 or table % 4 or not (
                0x55000000 <= table <= 0x56000000 - count*32 or
                0x59000000 <= table <= 0x5C000000 - count*32):
            raise ValueError('unexpected variable table')
        addresses = r['addresses']
        if set(addresses) != set(NAMES):
            raise ValueError('unexpected variable names')
        values = list(addresses.values())
        if len(set(values)) != len(NAMES) or any(
                a % 4 or not INTEGER_VALUES <= a < INTEGER_VALUES + count*4 for a in values):
            raise ValueError('unexpected variable addresses')
        if len(bytes.fromhex(r['buffer_before_hex'])) != 20:
            raise ValueError('incomplete original buffer')
        heap = r['heap_context']
        base, length = heap['arena_base'], heap['arena_length']
        if not heap['ownership_predicate_verified'] or not (length >= SIZE and
                0x59000000 <= base < base + length <= 0x5C000000):
            raise ValueError('journal has an unexpected heap arena')

    def save(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal.with_suffix('.json.tmp')
        with temporary.open('w') as handle:
            json.dump(self.record, handle, indent=2)
            handle.write('\n'); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, self.journal)

    def control(self, initial=False):
        # Original 0x53b1c55c hides the names between commands; 0x53b1c518
        # republishes them. Exit also clears the pointer. Wait only for an
        # exact null/same-count holder, then restart EVERY identity/value
        # check. Never follow a null pointer or accept values from that read.
        for attempt in range(5):
            try:
                return self._control_once(initial)
            except NamesTemporarilyHidden:
                if attempt == 4:
                    raise
                time.sleep(0.02)

    def _control_once(self, initial=False):
        self.validate()
        holder = bytes.fromhex(self.record['names_holder_hex'])
        actual_holder = self.io.read(INTEGER_NAMES, 6)
        if actual_holder != holder:
            self.record.setdefault('read_anomalies', []).append({'location':'holder_before',
                'expected':holder.hex(),'actual':actual_holder.hex()})
            self.save()
            if actual_holder == bytes(4) + holder[4:]:
                raise NamesTemporarilyHidden('script names remain hidden; no request permitted')
            raise RuntimeError('script generation ended or changed; refuse old allocation')
        table = struct.unpack_from('<I', holder)[0]
        # Pin all eight identities, then bracket the value read with go/done.
        for name, address in self.record['addresses'].items():
            index = (address - INTEGER_VALUES) // 4
            if self.io.read(table + index*32, 32).split(b'\0', 1)[0] != name.encode():
                raise RuntimeError('script variable identity changed')
        for _ in range(5):
            before = tuple(self.value(n) for n in ('xpb_go', 'xpb_done'))
            state = {n: self.value(n) for n in NAMES}
            after = tuple(self.value(n) for n in ('xpb_go', 'xpb_done'))
            if before == after == (state['xpb_go'], state['xpb_done']):
                break
        else:
            raise RuntimeError('script request changed while reading')
        actual_holder = self.io.read(INTEGER_NAMES, 6)
        if actual_holder != holder:
            self.record.setdefault('read_anomalies', []).append({'location':'holder_after',
                'expected':holder.hex(),'actual':actual_holder.hex(),'state_observed':state})
            self.save()
            if actual_holder == bytes(4) + holder[4:]:
                raise NamesTemporarilyHidden('script names remain hidden; no request permitted')
            raise RuntimeError('script generation changed while reading')
        if state['xpb_input_code'] != INPUT_CODE or state['xpb_token'] != (0 if initial else self.record['token']):
            raise RuntimeError('session token/input mismatch; refuse cross-reboot recovery')
        if not 0 <= state['xpb_done'] <= state['xpb_go'] <= 16:
            raise RuntimeError('invalid script request counters')
        return state

    def value(self, name):
        return struct.unpack('<i', self.io.read(self.record['addresses'][name], 4))[0]

    def write_word(self, address, value, owned=False):
        allowed = {SEND_SLOT, RESPONSE_SLOT, *range(RESPONSE_BUFFER, RESPONSE_BUFFER+20, 4),
                   *(self.record['addresses'][n] for n in ('xpb_go', 'xpb_token'))}
        if owned:
            self.check_owned()
            windows = [(self.data_address(), self.owned_data_length())]
            if self.record.get('cache_trial'):
                windows.append((self.cache_output(), 20))
            if address % 4 or not any(base <= address <= base+size-4 for base,size in windows):
                raise ValueError('owned write outside the fixed data/output windows')
        elif address not in allowed:
            raise ValueError('write outside pinned words')
        self.io.write_four(address, word(value))
        if self.io.read(address, 4) != word(value):
            raise RuntimeError('RAM word readback mismatch')

    def wait(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while True:
            state = self.control()
            if predicate(state):
                return state
            if time.monotonic() >= deadline:
                raise RuntimeError('native request completion timed out; keep record intact')
            time.sleep(0.1)

    def validate_call(self, call):
        target, args = call['target'], call['arguments']
        if target == TEST_LEAF and args == [11, 13, 17]:
            pass
        elif target == MALLOC and args == [SIZE, 0, 0]:
            pass
        elif target == FREE and args == [self.record.get('allocation_pointer'), 0, 0]:
            self.check_owned()
        elif target in (CACHE_SVC, QUERY_SVC) and self.record.get('cache_trial'):
            self.check_owned()
            if args != [self.data_address(), 64, self.cache_output()]:
                raise ValueError('cache/query outside the owned aligned range')
        else:
            raise ValueError('call is outside the fixed diagnostic/malloc/free set')
        if not 1 <= call['sequence'] <= 16:
            raise ValueError('unexpected call sequence')
        expected = struct.pack('<5I', target, 0, *reversed(args))
        if call['record_hex'] != expected.hex():
            raise ValueError('call record identity mismatch')
        return expected

    def settle(self):
        call = self.record.get('active_call')
        if not call:
            return
        candidate = self.validate_call(call)
        send = struct.unpack('<I', self.io.read(SEND_SLOT, 4))[0]
        response = struct.unpack('<I', self.io.read(RESPONSE_SLOT, 4))[0]
        if send not in (SEND_ORIGINAL, ADAPTER) or response not in (RESPONSE_ORIGINAL, TEST_LEAF):
            raise RuntimeError('unrelated callback; refuse overwrite')
        state = self.control()
        seq = call['sequence']
        if state['xpb_go'] == seq:
            if not call.get('publication_attempted'):
                raise RuntimeError('request advanced before host publication; refuse recovery')
            # Once published, leave the valid record/adapter untouched until
            # the one native call finishes. Never turn a queued free into an
            # ordinary shell call and never issue its sequence twice.
            state = self.wait(lambda s: s['xpb_done'] == seq and s['xpb_state'] != 1802)
            if not call.get('completed'):
                call.update(completed=True, return_value=state['xpb_return'])
                self.save()
        elif state['xpb_go'] == seq-1 and state['xpb_done'] == seq-1:
            if call.get('completed'):
                raise RuntimeError('completed request disappeared; refuse recovery')
            call['not_published'] = True
        else:
            raise RuntimeError('request sequence disagrees with journal')
        original = bytes.fromhex(self.record['buffer_before_hex'])
        for offset in range(0, 20, 4):
            current = self.io.read(RESPONSE_BUFFER+offset, 4)
            if current not in (original[offset:offset+4], candidate[offset:offset+4]):
                raise RuntimeError('unrelated scratch word; refuse overwrite')
        self.write_word(SEND_SLOT, SEND_ORIGINAL)
        for offset in range(0, 20, 4):
            self.write_word(RESPONSE_BUFFER+offset, struct.unpack_from('<I', original, offset)[0])
        self.write_word(RESPONSE_SLOT, RESPONSE_ORIGINAL)
        self.assert_restored()
        call['restoration_verified'] = True
        self.record['calls'].append(call)
        self.record['active_call'] = None
        self.save()
        self.account(call)

    def account(self, call):
        if not call.get('completed'):
            return
        if call['target'] == MALLOC:
            pointer = call['return_value']
            if pointer == 0:
                self.record['allocation_failed'] = True
            elif not self.in_arena(pointer):
                self.record['allocation_uncertain'] = True
                self.save()
                raise RuntimeError('malloc returned an unexpected address; do not read or free it')
            else:
                self.record.update(allocation_pointer=pointer, allocation_owned=True)
        elif call['target'] == FREE:
            self.record['free_completed'] = True
            self.record['free_return'] = call['return_value']
            if call['return_value'] == 1:
                self.record.update(allocation_owned=False, allocation_free_verified=True)
            else:
                self.record['allocation_uncertain'] = True
                self.save()
                raise RuntimeError('completed free returned failure; never retry it')
        self.save()

    def reconcile(self):
        # settle() journals completion before accounting it. An interruption
        # between these writes must not lose a malloc or repeat a free.
        for call in self.record['calls']:
            if call.get('completed') and call['target'] == MALLOC and 'allocation_pointer' not in self.record and not self.record.get('allocation_failed'):
                self.account(call)
            if call.get('completed') and call['target'] == FREE and not self.record.get('free_completed'):
                self.account(call)

    def check_owned(self):
        r = self.record
        pointer = r.get('allocation_pointer', 0)
        origins = [c for c in r['calls'] if c.get('completed') and c['target'] == MALLOC and
                   c['arguments'] == [SIZE, 0, 0] and c['return_value'] == pointer]
        if (not self.in_arena(pointer) or not r.get('allocation_owned') or
                r.get('free_completed') or r.get('allocation_uncertain') or len(origins) != 1):
            raise RuntimeError('no confirmed live owned allocation')
        self.control()

    def in_arena(self, pointer):
        heap = self.record['heap_context']
        return (pointer_valid(pointer) and heap['arena_base']+8 <= pointer <=
                heap['arena_base'] + heap['arena_length'] - SIZE)

    def data_address(self):
        pointer = self.record['allocation_pointer']
        return (pointer+63) & ~63 if self.record.get('cache_trial') else pointer

    def owned_data_length(self):
        return 32

    def cache_output(self):
        output = self.data_address()+128
        if output+20 > self.record['allocation_pointer']+SIZE:
            raise ValueError('cache output exceeds the owned allocation')
        return output

    def invoke(self, target, arguments):
        if self.record.get('active_call'):
            raise RuntimeError('recover the previous request first')
        if target == MALLOC and any(c.get('completed') and c['target'] == MALLOC for c in self.record['calls']):
            raise RuntimeError('only one allocation is allowed in this batch')
        state = self.control()
        if (state['xpb_go'] != state['xpb_done'] or state['xpb_state'] not in (1801, 1803) or
                state['xpb_stop'] != 0 or state['xpb_tick'] > 8000):
            raise RuntimeError('script is not in its checked idle window')
        self.assert_restored()
        call = {'target': target, 'arguments': list(arguments), 'sequence': state['xpb_done']+1,
                'record_hex': struct.pack('<5I', target, 0, *reversed(arguments)).hex(),
                'completed': False, 'restoration_verified': False}
        candidate = self.validate_call(call)
        self.record['active_call'] = call
        self.save()
        try:
            self.write_word(RESPONSE_SLOT, TEST_LEAF)
            for offset in range(0, 20, 4):
                self.write_word(RESPONSE_BUFFER+offset, struct.unpack_from('<I', candidate, offset)[0])
            self.write_word(SEND_SLOT, ADAPTER)
            call['publication_attempted'] = True
            self.save()
            self.write_word(self.record['addresses']['xpb_go'], call['sequence'])
        except Exception as error:
            call['transport_error'] = str(error)
            self.save()
            raise
        finally:
            self.settle()
        if not call.get('completed'):
            raise RuntimeError('native request was not published')
        return call['return_value']

    def assert_restored(self):
        if (self.io.read(SEND_SLOT, 4) != word(SEND_ORIGINAL) or
                self.io.read(RESPONSE_SLOT, 4) != word(RESPONSE_ORIGINAL) or
                self.io.read(RESPONSE_BUFFER, 20).hex() != self.record['buffer_before_hex']):
            raise RuntimeError('callback/buffer restoration mismatch')

    def restore_owned_data(self):
        if not self.record.get('allocation_owned') or 'owned_before_hex' not in self.record:
            return
        self.check_owned()
        data = bytes.fromhex(self.record['owned_before_hex'])
        if len(data) != self.owned_data_length():
            raise ValueError('incomplete owned-data backup')
        base = self.data_address()
        for offset in range(0, len(data), 4):
            self.write_word(base+offset, struct.unpack_from('<I', data, offset)[0], owned=True)
        self.record['owned_data_restoration_verified'] = self.io.read(base, len(data)) == data
        self.restore_cache_output()
        self.save()
        if not self.record['owned_data_restoration_verified']:
            raise RuntimeError('owned data restoration mismatch')

    def restore_cache_output(self):
        if 'cache_output_before_hex' in self.record:
            self.check_owned()
            original = bytes.fromhex(self.record['cache_output_before_hex'])
            if len(original) != 20:
                raise ValueError('incomplete cache output backup')
            output = self.cache_output()
            for offset in range(0, 20, 4):
                self.write_word(output+offset, struct.unpack_from('<I', original, offset)[0], owned=True)
            self.record['cache_output_restoration_verified'] = self.io.read(output, 20) == original
            if not self.record['cache_output_restoration_verified']:
                raise RuntimeError('cache output restoration mismatch')
        self.save()

    def cleanup(self):
        self.settle()
        self.reconcile()
        if self.record.get('allocation_uncertain'):
            raise RuntimeError('allocation status uncertain; require reboot rather than another free')
        if self.record.get('allocation_owned'):
            try:
                self.restore_owned_data()
            finally:
                # The data belongs to this allocation. A data readback failure
                # does not justify leaking it; the exact captured pointer is freed.
                if self.record.get('allocation_owned') and not self.record.get('active_call'):
                    self.invoke(FREE, [self.record['allocation_pointer'], 0, 0])
        self.assert_restored()
        after = self.io.read(PROPERTIES, 5).hex()
        self.record['properties_after_hex'] = after
        self.record['capture_properties_unchanged'] = after == self.record['properties_before_hex']
        self.record['cleanup_verified'] = not self.record.get('allocation_owned', False)
        self.record['stage'] = 'cleaned_up'
        self.save()
        if not self.record['capture_properties_unchanged']:
            raise RuntimeError('capture properties changed')

    @classmethod
    def begin(cls, io, journal):
        if Path(journal).exists():
            raise RuntimeError('journal already exists; use recovery, do not repeat the batch')
        context = collect(io.read)
        variables = context['selected_variables']
        if not context['script_callbacks_initialized'] or not all(n in variables for n in NAMES):
            raise RuntimeError('protocol 1801 companion script is not active')
        for address, expected in ((ADAPTER, ADAPTER_BYTES), (TEST_LEAF, TEST_LEAF_BYTES),
                                  (MALLOC, MALLOC_BYTES), (FREE, FREE_BYTES)):
            if io.read(address, len(expected)) != expected:
                raise RuntimeError('pinned ROM bytes mismatch')
        heap = allocator_context(io.read)
        record = {'schema': SCHEMA, 'token': secrets.randbelow(0x3FFFFFFF)+1,
                  'names_holder_hex': context['names_holder_hex'],
                  'addresses': {n: int(variables[n]['address'], 16) for n in NAMES},
                  'buffer_before_hex': context['response_buffer_first_20_hex'],
                  'properties_before_hex': io.read(PROPERTIES, 5).hex(),
                  'heap_context': heap, 'calls': [], 'active_call': None,
                  'stage': 'prepared', 'camera_installable_xpan': False}
        session = cls(io, journal, record)
        state = session.control(initial=True)
        if state['xpb_state'] != 1801 or state['xpb_go'] != 0 or state['xpb_done'] != 0 or state['xpb_tick'] > 8000 or state['xpb_stop'] != 0:
            raise RuntimeError('script is not a fresh idle session')
        session.save()
        session.write_word(record['addresses']['xpb_token'], record['token'])
        session.control()
        return session

    def batch(self):
        try:
            if self.invoke(TEST_LEAF, [11, 13, 17]) != 3:
                raise RuntimeError('first native diagnostic mismatch')
            pointer = self.invoke(MALLOC, [SIZE, 0, 0])
            if not pointer:
                raise RuntimeError('native allocation failed')
            self.check_owned()
            header = self.io.read(pointer-8, 8)
            origin = struct.unpack_from('<I', header)[0]
            if not self.record['heap_context']['arena_base'] <= origin <= pointer-8:
                raise RuntimeError('allocation origin metadata is outside the checked heap')
            self.record['allocation_header_hex'] = header.hex()
            self.record['owned_before_hex'] = self.io.read(pointer, 32).hex()
            self.save()
            for offset in range(0, 32, 4):
                self.write_word(pointer+offset, struct.unpack_from('<I', PATTERN, offset)[0], owned=True)
            self.record['owned_pattern_readback_verified'] = self.io.read(pointer, 32) == PATTERN
            self.save()
            if not self.record['owned_pattern_readback_verified']:
                raise RuntimeError('owned RAM test pattern mismatch')
            self.restore_owned_data()
            if self.invoke(FREE, [pointer, 0, 0]) != 1:
                raise RuntimeError('native free failed')
            if self.invoke(TEST_LEAF, [11, 13, 17]) != 3:
                raise RuntimeError('post-free native diagnostic mismatch')
            self.record['batch_passed'] = True
        except Exception as error:
            self.record['batch_error'] = str(error)
            self.save()
            raise
        finally:
            try:
                self.cleanup()
            except Exception as error:
                self.record.update(stage='recovery_needed', recovery_error=str(error))
                self.save()
                raise
        return self.record

    @classmethod
    def begin_or_resume(cls, io, journal, previous_journal):
        context = collect(io.read)
        variables = context['selected_variables']
        if not all(n in variables for n in NAMES):
            raise RuntimeError('continuous script is inactive; reboot with the existing card')
        if variables['xpb_token']['value'] == 0:
            return cls.begin(io, journal)
        if Path(journal).exists():
            raise RuntimeError('cache journal already exists; recover rather than repeat')
        prior = json.loads(Path(previous_journal).read_text())
        if (not prior.get('cleanup_verified') or prior.get('allocation_owned') or prior.get('active_call') or
                prior.get('token') != variables['xpb_token']['value'] or
                prior.get('names_holder_hex') != context['names_holder_hex']):
            raise RuntimeError('previous session is not confirmed clean in this boot')
        record = {'schema':SCHEMA, 'token':prior['token'],
                  'names_holder_hex':context['names_holder_hex'],
                  'addresses':{n:int(variables[n]['address'],16) for n in NAMES},
                  'buffer_before_hex':context['response_buffer_first_20_hex'],
                  'properties_before_hex':io.read(PROPERTIES,5).hex(),
                  'heap_context':allocator_context(io.read), 'calls':[], 'active_call':None,
                  'stage':'prepared', 'camera_installable_xpan':False}
        session = cls(io,journal,record)
        state = session.control()
        last = max(c['sequence'] for c in prior['calls'])
        if (state['xpb_go'] != last or state['xpb_done'] != last or state['xpb_state'] != 1803 or
                state['xpb_tick'] > 8000 or state['xpb_stop'] != 0 or last > 11):
            raise RuntimeError('previous request counters disagree')
        session.assert_restored()
        session.save()
        return session

    def cache_batch(self):
        self.record['cache_trial'] = True
        self.save()
        try:
            pointer = self.invoke(MALLOC, [SIZE,0,0])
            if not pointer:
                raise RuntimeError('cache allocation failed')
            self.check_owned()
            data, output = self.data_address(), self.cache_output()
            self.record['owned_before_hex'] = self.io.read(data,32).hex()
            self.record['cache_output_before_hex'] = self.io.read(output,20).hex()
            self.save()
            for offset in range(0,32,4):
                self.write_word(data+offset,struct.unpack_from('<I',PATTERN,offset)[0],owned=True)
            if self.io.read(data,32) != PATTERN:
                raise RuntimeError('aligned data pattern mismatch')
            query = self.invoke(QUERY_SVC,[data,64,output])
            info = list(struct.unpack('<5I',self.io.read(output,20)))
            self.record.update(cache_query_return=query, cache_query_words=info)
            self.save()
            if query != 0 or info[0] != data or info[3] != 64 or info[4] != 64:
                raise RuntimeError('cache information result mismatch')
            returned = self.invoke(CACHE_SVC,[data,64,output])
            echoed = struct.unpack('<I',self.io.read(output,4))[0]
            self.record.update(cache_service_return=returned,cache_output_address_echo=echoed,
                               cache_service_verified=returned==64 and echoed==data)
            self.save()
            if not self.record['cache_service_verified'] or self.io.read(data,32) != PATTERN:
                raise RuntimeError('cache service result or data mismatch')
            self.restore_owned_data()
            if self.invoke(FREE,[pointer,0,0]) != 1:
                raise RuntimeError('cache allocation free failed')
            if self.invoke(TEST_LEAF,[11,13,17]) != 3:
                raise RuntimeError('post-cache native diagnostic mismatch')
            self.record['cache_batch_passed'] = True
        except Exception as error:
            self.record['batch_error'] = str(error)
            self.save()
            raise
        finally:
            try:
                self.cleanup()
            except Exception as error:
                self.record.update(stage='recovery_needed',recovery_error=str(error));self.save();raise
        return self.record
