#!/usr/bin/env python3
"""Bounded RAM loader experiment; default read-only, explicit --trial required.

Uploads only ISB; MOV r0,#65; BX lr in one owned 8KB allocation, then removes it.
Uses fixed ROM primitives, unchanged SCTLR writeback, checked task attributes,
live TTBR section checks, cache clean/barriers and shared I-cache invalidation.
Does not install XPAN, alter menus, write flash, or accept arbitrary code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import usb.core
import usb.util

import gr4_usb_call_session as gate
from audit_xpan_paths import file_offset, require
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_factory_task_mapping_readonly import collect as task_context, audit as audit_tasks
from mtp_probe_readonly import VID, PID, command

ROOT = Path(__file__).resolve().parents[1]
FIRST_JOURNAL = ROOT/'devkit-output/usb-factory-20261001/ram-leaf-session-trial.json'
SECOND_JOURNAL = ROOT/'devkit-output/usb-factory-20261001/ram-leaf-session-trial-v2.json'
JOURNAL = ROOT/'devkit-output/usb-factory-20261001/ram-leaf-session-trial-v3.json'
SERVICE_JOURNAL = ROOT/'devkit-output/usb-factory-20261001/ram-services-session-trial.json'
CPU, TTBR, CONTROL, DSB, ISB, IALL = (0x53000844, 0x53000850, 0x530008B4,
                                    0x5300086C, 0x53087B94, 0x53087BF4)
ROM = {
    CPU: bytes.fromhex('b00f10ee030000e21eff2fe1'),
    TTBR: bytes.fromhex('100f12ee1eff2fe1'),
    # MRC SCTLR -> r0; AND r0,r0,r1; MCR SCTLR <- r0; BX lr.
    # The only allowed r1 is all ones: no control bits change.
    CONTROL: bytes.fromhex('100f11ee010000e0100f01ee1eff2fe1'),
    DSB: bytes.fromhex('4ff07ff51eff2fe1'),
    ISB: bytes.fromhex('6ff07ff5100f30eed006eee7010080e21eff2fe1'),
}
IALL_LENGTH = 132
IALL_SHA256 = '58ce04f590159be10911a8645b64c80e68db560dd07dd2472e6a1591aef40eee'
ROM_TARGETS = (*ROM, IALL)
CODE = bytes.fromhex('6ff07ff54100a0e31eff2fe1').ljust(32, b'\0')
FIXED_ARGS = {CPU:[0,0,0], TTBR:[0,0,0], CONTROL:[0,0xFFFFFFFF,0],
              DSB:[0,0,0], ISB:[0,0,0], IALL:[2,1,0]}


def audit(raw):
    evidence = audit_tasks(raw)
    for address, expected in ROM.items():
        require(raw, file_offset(address), expected, hex(address))
    offset = file_offset(IALL)
    if hashlib.sha256(raw[offset:offset + IALL_LENGTH]).hexdigest() != IALL_SHA256:
        raise ValueError('IALL firmware window does not match the pinned digest')
    require(raw, file_offset(gate.CACHE_SVC), gate.CACHE_BYTES, 'owned cache SVC')
    return {'task_audit':evidence, 'rom_targets':[hex(x) for x in ROM_TARGETS],
            'payload_hex':CODE.hex(), 'payload_sha256':hashlib.sha256(CODE).hexdigest(),
            'control_register_action':'read SCTLR and write exactly the same value',
            'native_requests_per_complete_batch':16, 'xpan_installed':False}


class LeafSession(gate.Session):
    PAYLOAD = CODE
    ENTRY_ARGS = [11,13,17]
    EXPECTED_RETURN = 65
    CACHE_LENGTH = 64

    def owned_data_length(self):
        return len(self.PAYLOAD)

    def validate_call(self, call):
        target, args = call['target'], call['arguments']
        if target in ROM_TARGETS or target == gate.CACHE_SVC or (self.record.get('allocation_pointer') and target == self.data_address()):
            if not self.record.get('ram_leaf_trial') or self.record.get('script_attributes') != '0x21003':
                raise ValueError('RAM leaf experiment/task identity is not confirmed')
            if target in ROM_TARGETS:
                if args != FIXED_ARGS[target]:
                    raise ValueError('arguments differ from pinned ROM experiment')
            elif target == gate.CACHE_SVC:
                self.check_owned()
                if args != [self.data_address(),self.CACHE_LENGTH,self.cache_output()]:
                    raise ValueError('cache range differs from the fixed owned payload')
            else:
                self.check_owned()
                if (args != self.ENTRY_ARGS or not self.record.get('publication_verified') or
                        self.io.read(target,len(self.PAYLOAD)) != self.PAYLOAD):
                    raise ValueError('RAM target is not the exact published leaf')
            if not 1 <= call['sequence'] <= 16:
                raise ValueError('call budget exceeded')
            expected = struct.pack('<5I',target,0,*reversed(args))
            if call['record_hex'] != expected.hex():
                raise ValueError('native record differs from fixed call')
            return expected
        return super().validate_call(call)

    def sync_code(self, phase):
        # A single completed flag is written after all four requests. Recovery
        # never treats a partial publication as permission to call RAM code.
        data, output = self.data_address(), self.cache_output()
        self.settle()
        ledger = self.record.setdefault('publication_steps', {})
        if phase not in ledger:
            ledger[phase] = self.control()['xpb_done'] + 1
            self.save()
        start = ledger[phase]
        steps = [(gate.CACHE_SVC,[data,self.CACHE_LENGTH,output],self.CACHE_LENGTH),
                 (DSB,FIXED_ARGS[DSB],0),(IALL,FIXED_ARGS[IALL],0),(DSB,FIXED_ARGS[DSB],0)]
        for offset,(target,args,expected) in enumerate(steps):
            sequence = start + offset
            completed = [c for c in self.record['calls'] if c['sequence'] == sequence and c.get('completed')]
            if completed:
                if len(completed) != 1 or completed[0]['target'] != target or completed[0]['arguments'] != args:
                    raise RuntimeError('cache publication ledger differs from completed request')
                returned = completed[0]['return_value']
            else:
                if self.control()['xpb_done'] != sequence - 1:
                    raise RuntimeError('cache publication sequence changed')
                returned = self.invoke(target,args)
            if returned != expected:
                raise RuntimeError('cache publication return mismatch')
            if offset == 0 and self.io.read(output,4) != gate.word(data):
                raise RuntimeError('owned cache service did not confirm its range')
            if offset == 0:
                self.record['cache_output_restoration_verified'] = False
                self.save()
        self.record[phase] = True
        self.save()

    def cleanup(self):
        self.settle()
        self.reconcile()
        if self.record.get('allocation_uncertain'):
            raise RuntimeError('allocation uncertain; refuse another free')
        if self.record.get('allocation_owned') and self.record.get('payload_write_attempted'):
            ram_calls = [c for c in self.record['calls'] if c['target'] == self.data_address()
                         and c.get('completed')]
            if not ram_calls and not self.record.get('active_call'):
                # A rejected publication prevents entry to RAM code. There is
                # no installed pointer to this allocation after settle(), so
                # restore data and free without requiring the rejected service.
                self.record['ram_entry_never_called'] = True
                self.save()
                return super().cleanup()
            if not self.record.get('restored_code_published'):
                if 'restored_code_published' not in self.record.get('publication_steps', {}):
                    self.restore_owned_data()
                self.sync_code('restored_code_published')
            self.restore_cache_output()
        super().cleanup()

    def batch(self):
        self.record.update(ram_leaf_trial=True,cache_trial=True)
        self.save()
        try:
            cpu = self.invoke(CPU,FIXED_ARGS[CPU])
            ttbr = self.invoke(TTBR,FIXED_ARGS[TTBR]) & 0xFFFFFFFF
            control = self.invoke(CONTROL,FIXED_ARGS[CONTROL]) & 0xFFFFFFFF
            self.record.update(cpu_observed=cpu,active_ttbr=hex(ttbr),sctlr_unchanged_value=hex(control))
            self.save()
            if not 0 <= cpu <= 2 or (ttbr & 0xFFFFC000) != 0x53004000:
                raise RuntimeError('unexpected native CPU or active translation table')
            if not control & 1 or control & ((1<<19)|(1<<20)):
                raise RuntimeError('MMU/WXN/UWXN configuration does not permit this experiment')
            pointer = self.invoke(gate.MALLOC,[gate.SIZE,0,0])
            if not pointer:
                raise RuntimeError('native allocation failed')
            self.check_owned()
            data, output = self.data_address(), self.cache_output()
            index = data >> 20
            mapping = struct.unpack('<I',self.io.read(0x53004000+index*4,4))[0]
            ap = ((mapping>>10)&3) | ((mapping>>13)&4)
            if ((mapping & 3) != 2 or (mapping & 0xFFF00000) != (data & 0xFFF00000) or
                    mapping & 16 or ap != 3 or not mapping & (1<<16)):
                raise RuntimeError('owned RAM is not a writable/executable shareable identity section')
            for endpoint in (data+len(self.PAYLOAD)-1,output+19):
                entry = struct.unpack('<I',self.io.read(0x53004000+(endpoint>>20)*4,4))[0]
                if entry != ((endpoint & 0xFFF00000) | (mapping & 0x000FFFFF)):
                    raise RuntimeError('owned payload/output crosses an incompatible memory section')
            self.record.update(owned_section_descriptor=hex(mapping),
                owned_before_hex=self.io.read(data,len(self.PAYLOAD)).hex(),
                cache_output_before_hex=self.io.read(output,20).hex(),
                payload_hex=self.PAYLOAD.hex(),payload_write_attempted=True)
            self.save()
            for offset in range(0,len(self.PAYLOAD),4):
                self.write_word(data+offset,struct.unpack_from('<I',self.PAYLOAD,offset)[0],owned=True)
            if self.io.read(data,len(self.PAYLOAD)) != self.PAYLOAD:
                raise RuntimeError('uploaded leaf differs from fixed instructions')
            self.sync_code('publication_verified')
            ways = self.invoke(ISB,FIXED_ARGS[ISB])
            if not 1 <= ways <= 32768:
                raise RuntimeError('ISB/CCSIDR leaf returned an invalid result')
            returned = self.invoke(data,self.ENTRY_ARGS)
            self.record.update(ram_leaf_return=returned,ram_code_execution_verified=returned==self.EXPECTED_RETURN)
            self.save()
            if returned != self.EXPECTED_RETURN:
                raise RuntimeError('RAM check returned a failure value')
            self.restore_owned_data()
            self.sync_code('restored_code_published')
            self.restore_cache_output()
            if self.invoke(gate.FREE,[pointer,0,0]) != 1:
                raise RuntimeError('paired free failed')
            if self.invoke(gate.TEST_LEAF,[11,13,17]) != 3:
                raise RuntimeError('post-free original diagnostic failed')
            self.record['ram_leaf_batch_passed'] = True
        except Exception as error:
            self.record['batch_error'] = str(error)
            self.save()
            raise
        finally:
            try:
                self.cleanup()
            except Exception as error:
                self.record.update(stage='recovery_needed',recovery_error=str(error))
                self.save()
                raise
        return self.record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--trial',action='store_true')
    group.add_argument('--recover',action='store_true')
    group.add_argument('--services-only',action='store_true')
    group.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes()
    evidence=audit(raw)
    if args.offline:
        print(json.dumps(evidence,indent=2));return
    device=usb.core.find(idVendor=VID,idProduct=PID)
    if device is None or device.bcdDevice!=0x0111:
        raise RuntimeError('expected connected GR IV 01.11.10.07')
    usb.util.claim_interface(device,0)
    io=Transport(device);opened=False
    try:
        response,info,_=command(device,0x1001,0)
        if response!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS:
            raise RuntimeError('unexpected MTP device information')
        response,_,_=command(device,0x1002,1,1)
        opened=response==0x2001
        if response not in (0x2001,0x201E):raise RuntimeError('OpenSession failed')
        for address,expected in [*ROM.items(),(gate.CACHE_SVC,gate.CACHE_BYTES)]:
            if io.read(address,len(expected))!=expected:raise RuntimeError('live native code mismatch')
        if hashlib.sha256(io.read(IALL, IALL_LENGTH)).hexdigest() != IALL_SHA256:
            raise RuntimeError('live IALL code does not match the pinned digest')
        if args.recover:
            selected = next(p for p in (JOURNAL,SECOND_JOURNAL,FIRST_JOURNAL) if p.exists())
            session=LeafSession(io,selected,json.loads(selected.read_text()))
            session.cleanup();result=session.record
        elif args.services_only:
            session=LeafSession.begin_or_resume(io,SERVICE_JOURNAL,FIRST_JOURNAL)
            session.record.update(ram_leaf_trial=True,script_attributes='0x21003',
                                  no_allocation_or_payload=True,offline_audit=evidence)
            session.save()
            try:
                results={}
                for target in (IALL,DSB,ISB):
                    results[hex(target)]=session.invoke(target,FIXED_ARGS[target])
                session.record['service_results']=results
                session.record['services_passed']=(results[hex(IALL)]==0 and results[hex(DSB)]==0
                                                    and 1<=results[hex(ISB)]<=32768)
                session.save()
                if not session.record['services_passed']:raise RuntimeError('fixed publication service failed')
            finally:session.cleanup()
            result=session.record
        else:
            context=task_context(io.read,raw)
            if args.trial:
                session=LeafSession.begin(io,JOURNAL)
                session.record.update(script_attributes=context['script_attributes'],
                    task_mapping_before=context,offline_audit=evidence)
                session.save()
                result=session.batch()
            else:result=context
        print(json.dumps({k:v for k,v in result.items() if k!='task_mapping_before'},indent=2))
    finally:
        try:
            if opened:command(device,0x1003,io.transaction)
        finally:
            usb.util.release_interface(device,0);usb.util.dispose_resources(device)


if __name__=='__main__':
    main()
