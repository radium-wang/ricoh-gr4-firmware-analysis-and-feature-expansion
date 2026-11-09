#!/usr/bin/env python3
"""Default read-only; --trial posts one owned diagnostic to original AppMain.

Uses the exact capacity-guarded queue gate and original ROM store callback.
No menu/photo/settings/flash changes. Never repost a possibly submitted message
or free a pending handler. Existing SD protocol 1801 suffices; fresh boot needed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import usb.core
import usb.util
import gr4_usb_call_session as gate
from mtp_factory_ram_leaf_trial import LeafSession,ROM,FIXED_ARGS,CPU,TTBR,CONTROL,ISB,audit as ram_audit,ROOT
from audit_gr4_ui_queue import collect as queue_context,MEDIATOR,FUNCTIONS
from audit_xpan_paths import file_offset
from mtp_factory_task_mapping_readonly import collect as task_context
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS,operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_probe_readonly import VID,PID,command

PACKAGE=ROOT/'devkit-output/usb-factory-20261001/ui-queue-native-gate-v2'
JOURNAL=ROOT/'devkit-output/usb-factory-20261001/ui-queue-session-trial-v1.json'
PAYLOAD_SHA='ed27858244e5b73affe7de6a8ad8c8f2cd49077abc9549dc696d603855c5120e'
MAGIC=0x58505549
STORE=0x5325CA0C


def payload():
    data=(PACKAGE/'queue.bin').read_bytes().ljust(512,b'\0')
    checks=json.loads((PACKAGE.parent/'ui-queue-arm-check-v3.json').read_text())
    if len(data)!=512 or hashlib.sha256(data).hexdigest()!=PAYLOAD_SHA or data[:4]!=bytes.fromhex('6ff07ff5'):
        raise ValueError('only the exact checked ISB queue gate is accepted')
    if checks.get('cases_passed')!=15 or not checks.get('native_gate',{}).get('actual_compiled_ARM_executed'):
        raise ValueError('native queue checks missing')
    return data


class QueueSession(LeafSession):
    PAYLOAD=b''
    PAYLOAD_SHA=PAYLOAD_SHA
    PAYLOAD_SIZE=512
    CACHE_LENGTH=1024
    MESSAGE_OFFSET=512
    HANDLER_OFFSET=544
    VTABLE_OFFSET=560
    CACHE_OUTPUT_OFFSET=2048
    CALLBACK_OFFSET=None

    def validate(self):
        super().validate()
        if len(self.PAYLOAD)!=self.PAYLOAD_SIZE or hashlib.sha256(self.PAYLOAD).hexdigest()!=self.PAYLOAD_SHA:
            raise ValueError('queue session payload mismatch')
        if 'payload_hex' in self.record and self.record['payload_hex']!=self.PAYLOAD.hex():
            raise ValueError('journal code differs from checked queue gate')

    def owned_data_length(self):return self.CACHE_LENGTH

    def cache_output(self):
        output=self.data_address()+self.CACHE_OUTPUT_OFFSET
        if output+20>self.record['allocation_pointer']+gate.SIZE:raise ValueError('output outside owned allocation')
        return output

    @property
    def ENTRY_ARGS(self):return [MEDIATOR,self.data_address()+self.MESSAGE_OFFSET,MAGIC]

    def handler(self):return self.data_address()+self.HANDLER_OFFSET

    def callback(self):return STORE if self.CALLBACK_OFFSET is None else self.data_address()+self.CALLBACK_OFFSET

    def validate_call(self,call):
        candidate=super().validate_call(call)
        if self.record.get('allocation_pointer') and call['target']==self.data_address():
            if any(c['target']==call['target'] for c in self.record['calls']):
                raise ValueError('queue entry already attempted; never repost it')
            data=self.data_address()
            if self.io.read(data+self.MESSAGE_OFFSET,12)!=struct.pack('<3I',0x17D,0,self.handler()):
                raise ValueError('queue message no longer matches owned diagnostic')
            if self.io.read(data+self.VTABLE_OFFSET,4)!=gate.word(self.callback()):raise ValueError('diagnostic callback differs')
            marker=self.io.read(self.handler(),4)
            allowed=(gate.word(data+self.VTABLE_OFFSET),gate.word(0x17D)) if call.get('publication_attempted') else (gate.word(data+self.VTABLE_OFFSET),)
            if marker not in allowed:raise ValueError('handler changed before verified submission')
        return candidate

    def require_consumed(self):
        if not self.record.get('queue_submission_possible'):return
        calls=[c for c in self.record['calls'] if c['target']==self.data_address() and c.get('completed')]
        if len(calls)!=1:raise RuntimeError('queue submission completion is uncertain; retain allocation')
        result=calls[0]['return_value']
        if result in (0,2,3):
            self.record['queue_submission_possible']=False;self.save();return
        if result not in (1,4,5):raise RuntimeError('unknown queue result; retain allocation')
        deadline=time.monotonic()+5
        while True:
            self.check_owned()
            marker=self.io.read(self.handler(),4)
            if marker==gate.word(0x17D):break
            if marker!=gate.word(self.data_address()+self.VTABLE_OFFSET):raise RuntimeError('unrelated handler marker; retain allocation')
            if time.monotonic()>=deadline:raise RuntimeError('AppMain callback still pending; never free or repost it')
            time.sleep(0.05)
        # The ROM callback's last owned access is STR r1,[r0]; BX LR executes
        # in ROM. Native queue/dispatch no longer dereference the handler after
        # this store. The script gate itself has also completed and returned.
        self.record.update(appmain_callback_observed=True,handler_last_owned_access_completed=True,
                           queue_submission_possible=False)
        self.save()

    def cleanup(self):
        self.settle();self.reconcile()
        # Covers interruptions before the original RAM call was published.
        if self.record.get('queue_submission_possible'):
            ram_calls=[c for c in self.record['calls'] if c['target']==self.data_address()]
            if not self.record.get('active_call') and (not ram_calls or all(c.get('not_published') for c in ram_calls)):
                self.record['queue_submission_possible']=False;self.save()
        self.require_consumed()
        super().cleanup()

    def batch(self):
        self.record.update(ram_leaf_trial=True,cache_trial=True,ui_queue_trial=True)
        self.save()
        try:
            cpu=self.invoke(CPU,FIXED_ARGS[CPU]);ttbr=self.invoke(TTBR,FIXED_ARGS[TTBR])&0xFFFFFFFF
            control=self.invoke(CONTROL,FIXED_ARGS[CONTROL])&0xFFFFFFFF
            self.record.update(cpu_observed=cpu,active_ttbr=hex(ttbr),sctlr_unchanged_value=hex(control));self.save()
            if not 0<=cpu<=2 or ttbr&0xFFFFC000!=0x53004000 or not control&1 or control&((1<<19)|(1<<20)):
                raise RuntimeError('unsupported active CPU/MMU configuration')
            pointer=self.invoke(gate.MALLOC,[gate.SIZE,0,0])
            if not pointer:raise RuntimeError('allocation failed')
            self.check_owned();data=self.data_address();output=self.cache_output()
            mapping=struct.unpack('<I',self.io.read(0x53004000+(data>>20)*4,4))[0]
            ap=((mapping>>10)&3)|((mapping>>13)&4)
            if mapping&3!=2 or mapping&0xFFF00000!=data&0xFFF00000 or mapping&16 or ap!=3 or not mapping&(1<<16):
                raise RuntimeError('owned RAM mapping unsuitable')
            for endpoint in (data+self.CACHE_LENGTH-1,output+19):
                actual=struct.unpack('<I',self.io.read(0x53004000+(endpoint>>20)*4,4))[0]
                if actual!=((endpoint&0xFFF00000)|(mapping&0xFFFFF)):raise RuntimeError('owned memory crosses mapping')
            self.record.update(owned_before_hex=self.io.read(data,self.CACHE_LENGTH).hex(),
                cache_output_before_hex=self.io.read(output,20).hex(),payload_hex=self.PAYLOAD.hex(),
                payload_write_attempted=True,owned_section_descriptor=hex(mapping))
            self.save()
            for offset in range(0,self.PAYLOAD_SIZE,4):self.write_word(data+offset,struct.unpack_from('<I',self.PAYLOAD,offset)[0],owned=True)
            packet=self.MESSAGE_OFFSET
            for offset,value in ((packet,0x17D),(packet+4,0),(packet+8,self.handler()),
                                 (self.HANDLER_OFFSET,data+self.VTABLE_OFFSET),(self.VTABLE_OFFSET,self.callback())):
                self.write_word(data+offset,value,owned=True)
            if self.io.read(data,self.PAYLOAD_SIZE)!=self.PAYLOAD:raise RuntimeError('queue code upload differs')
            if self.io.read(data+packet,12)!=struct.pack('<3I',0x17D,0,self.handler()):raise RuntimeError('message differs')
            self.sync_code('publication_verified')
            ways=self.invoke(ISB,FIXED_ARGS[ISB])
            if not 1<=ways<=32768:raise RuntimeError('instruction synchronization failed')
            self.record['queue_submission_possible']=True;self.save()
            returned=self.invoke(data,self.ENTRY_ARGS)
            self.record.update(ram_leaf_return=returned,ram_code_execution_verified=returned in (0,1,2,3,4,5));self.save()
            self.require_consumed()
            if returned!=1 or not self.record.get('appmain_callback_observed'):
                raise RuntimeError('queue did not complete normal submission/notification')
            self.restore_owned_data();self.sync_code('restored_code_published');self.restore_cache_output()
            if self.invoke(gate.FREE,[pointer,0,0])!=1:raise RuntimeError('paired free failed')
            if self.invoke(gate.TEST_LEAF,[11,13,17])!=3:raise RuntimeError('post-free diagnostic failed')
            self.record['ui_queue_batch_passed']=True
        except Exception as error:
            self.record['batch_error']=str(error);self.save();raise
        finally:
            try:self.cleanup()
            except Exception as error:
                self.record.update(stage='recovery_needed',recovery_error=str(error));self.save();raise
        return self.record


def main():
    p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group()
    m.add_argument('--trial',action='store_true');m.add_argument('--recover',action='store_true')
    m.add_argument('--offline',action='store_true');args=p.parse_args()
    QueueSession.PAYLOAD=payload()
    run(args,QueueSession,JOURNAL)


def run(args,session_class,journal):
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();ram_audit(raw)
    if args.offline:
        print(json.dumps({'payload_bytes':session_class.PAYLOAD_SIZE,'payload_sha256':session_class.PAYLOAD_SHA,'native_requests':16,
                          'menu_photo_settings_changed':False,'xpan_installed':False},indent=2));return
    device=usb.core.find(idVendor=VID,idProduct=PID)
    if device is None or device.bcdDevice!=0x111:raise RuntimeError('expected connected GR IV')
    usb.util.claim_interface(device,0);io=Transport(device);opened=False
    try:
        code,info,_=command(device,0x1001,0)
        if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS:
            raise RuntimeError('unexpected DeviceInfo')
        code,_,_=command(device,0x1002,1,1);opened=code==0x2001
        if code not in (0x2001,0x201E):raise RuntimeError('OpenSession failed')
        for address,expected in [*ROM.items(),(gate.CACHE_SVC,gate.CACHE_BYTES)]:
            if io.read(address,len(expected))!=expected:raise RuntimeError('live ROM mismatch')
        for address,size in FUNCTIONS.values():
            if io.read(address,size)!=raw[file_offset(address):file_offset(address)+size]:raise RuntimeError('queue ROM mismatch')
        if args.recover:
            session=session_class(io,journal,json.loads(journal.read_text()));session.cleanup();result=session.record
        else:
            before=queue_context(io.read,raw)
            if args.trial:
                context=task_context(io.read,raw)
                session=session_class.begin(io,journal)
                session.record.update(script_attributes=context['script_attributes'],task_mapping_before=context,
                                      queue_context_before=before,queue_gate_sha256=session_class.PAYLOAD_SHA)
                session.save();result=session.batch()
            else:result=before
        print(json.dumps({k:v for k,v in result.items() if k not in ('payload_hex','owned_before_hex','task_mapping_before','queue_context_before')},indent=2))
    finally:
        try:
            if opened:command(device,0x1003,io.transaction)
        finally:
            usb.util.release_interface(device,0);usb.util.dispose_resources(device)


if __name__=='__main__':main()
