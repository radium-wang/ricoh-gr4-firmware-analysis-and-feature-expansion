#!/usr/bin/env python3
"""Read only three fixed XPV12 SD diagnostics using original ROM file calls.

Default: read-only identity checks. --trial: one fresh 1801 session, at most
16 requests, owned data RAM only. --recover never reissues completed I/O.
No photo, system file, executable RAM payload or persistent setting is written.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import gr4_usb_call_session as gate
from audit_gr4_sd_file_abi import STAT,OPEN,READ,CLOSE,audit,live_check

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'devkit-output/usb-factory-20261001/sd-usb-readback-v1'
JOURNAL=OUTPUT/'session.json'
FILES=(('PROCESSA.BIN',960),('COLLA.BIN',48),('PROCESSC.BIN',960))
PATH_BYTES=32
STATUS_OFFSET=64
BUFFER_OFFSET=640
DATA_LENGTH=2048


class FileSession(gate.Session):
    def owned_data_length(self):return DATA_LENGTH

    def validate(self):
        super().validate()
        r=self.record
        if r.get('sd_file_trial'):
            if r.get('fixed_files') != [list(x) for x in FILES]:
                raise ValueError('file allowlist changed')
            for entry in r.get('files',[]):
                index=entry['index']
                if not 0<=index<len(FILES) or entry['name']!=FILES[index][0]:
                    raise ValueError('unexpected diagnostic file identity')

    def file_entry(self,index):
        matches=[e for e in self.record.get('files',[]) if e['index']==index]
        if len(matches)!=1:raise RuntimeError('file ledger is incomplete')
        return matches[0]

    def validate_call(self,call):
        target=call['target']
        if target not in (STAT,OPEN,READ,CLOSE):return super().validate_call(call)
        self.check_owned()
        index=call.setdefault('file_index',self.record['current_file_index'])
        entry=self.file_entry(index)
        name,length=FILES[index]
        base=self.data_address()
        if target in (STAT,OPEN):
            path=('C:\\XPV12\\'+name).encode()+b'\0'
            if self.io.read(base,PATH_BYTES) != path.ljust(PATH_BYTES,b'\0'):
                raise RuntimeError('owned file path does not match allowlist')
        if target==STAT:expected=[base,base+STATUS_OFFSET,0]
        elif target==OPEN:
            if not entry.get('stat_length_verified'):raise RuntimeError('open before exact stat length')
            expected=[base,0,0]
        else:
            handle=entry.get('handle',0)
            if not handle or entry.get('close_completed'):
                raise RuntimeError('no checked live file handle')
            expected=[handle,base+BUFFER_OFFSET,length] if target==READ else [handle,0,0]
        if call['arguments'] != expected or not 1<=call['sequence']<=16:
            raise ValueError('file call outside the fixed arguments/budget')
        packed=struct.pack('<5I',target,0,*reversed(expected))
        if call['record_hex']!=packed.hex():raise ValueError('file call record changed')
        return packed

    def account(self,call):
        super().account(call)
        if not call.get('completed') or call['target'] not in (STAT,OPEN,READ,CLOSE):return
        accounted=self.record.setdefault('file_accounted_sequences',[])
        if call['sequence'] in accounted:return
        entry=self.file_entry(call['file_index'])
        value=call['return_value'];target=call['target']
        if target==OPEN:
            entry['open_return']=value
            handle=value&0xFFFFFFFF
            if handle and (handle%4 or not 0x59000000<=handle<=0x5C000000-8):
                self.record['file_handle_uncertain']=True
                self.save()
                raise RuntimeError('unexpected open handle; require reboot, never dereference')
            entry['handle']=handle
        elif target==CLOSE:
            entry.update(close_completed=True,close_return=value,close_verified=value==1)
            if value!=1:self.record['file_handle_uncertain']=True
        else:entry['stat_return' if target==STAT else 'read_return']=value
        accounted.append(call['sequence']);self.save()

    def reconcile(self):
        super().reconcile()
        for call in self.record['calls']:
            if call.get('completed') and call['target'] in (STAT,OPEN,READ,CLOSE):self.account(call)

    def cleanup(self):
        self.settle();self.reconcile()
        if self.record.get('file_handle_uncertain'):
            raise RuntimeError('file handle status uncertain; preserve ledger and reboot, never repeat close')
        for entry in self.record.get('files',[]):
            if entry.get('handle') and not entry.get('close_completed'):
                self.record['current_file_index']=entry['index'];self.save()
                self.invoke(CLOSE,[entry['handle'],0,0])
                if not entry.get('close_verified'):
                    raise RuntimeError('completed close failed; preserve ledger, never repeat close')
        super().cleanup()

    def path_write(self,name):
        path=('C:\\XPV12\\'+name).encode()+b'\0'
        if len(path)>PATH_BYTES:raise ValueError('fixed path too long')
        data=path.ljust(PATH_BYTES,b'\0');base=self.data_address()
        for offset in range(0,len(data),4):
            self.write_word(base+offset,struct.unpack_from('<I',data,offset)[0],owned=True)

    def batch(self):
        self.record.update(sd_file_trial=True,fixed_files=[list(x) for x in FILES],files=[],
                           file_accounted_sequences=[],file_handle_uncertain=False)
        self.save()
        try:
            if self.invoke(gate.TEST_LEAF,[11,13,17])!=3:raise RuntimeError('initial diagnostic failed')
            pointer=self.invoke(gate.MALLOC,[gate.SIZE,0,0])
            if not pointer:raise RuntimeError('allocation failed')
            self.check_owned()
            self.record['owned_before_hex']=self.io.read(pointer,DATA_LENGTH).hex();self.save()
            for index,(name,length) in enumerate(FILES):
                entry={'index':index,'name':name,'expected_bytes':length}
                self.record['files'].append(entry);self.record['current_file_index']=index;self.save()
                self.path_write(name)
                returned=self.invoke(STAT,[pointer,pointer+STATUS_OFFSET,0])
                if returned!=0:
                    entry['status']='stat_failed';self.save();continue
                status=self.io.read(pointer+STATUS_OFFSET,524)
                size=struct.unpack_from('<I',status,516)[0]
                entry.update(stat_bytes=size,stat_length_verified=size==length)
                if size!=length:entry['status']='length_rejected';self.save();continue
                self.save()
                if not self.invoke(OPEN,[pointer,0,0]):
                    entry['status']='open_failed';self.save();continue
                try:
                    returned=self.invoke(READ,[entry['handle'],pointer+BUFFER_OFFSET,length])
                    if returned!=length:raise RuntimeError('original read wrapper returned failure')
                    data=self.io.read(pointer+BUFFER_OFFSET,length)
                    entry.update(status='captured',data_hex=data.hex(),sha256=hashlib.sha256(data).hexdigest())
                    # Persist bytes before reusing RAM or closing the handle.
                    self.save()
                finally:
                    if not self.record.get('active_call'):
                        self.reconcile()
                        if not entry.get('close_completed'):
                            self.invoke(CLOSE,[entry['handle'],0,0])
                        if not entry.get('close_verified'):raise RuntimeError('file close failed')
            self.cleanup()
            if self.invoke(gate.TEST_LEAF,[11,13,17])!=3:raise RuntimeError('final diagnostic failed')
            self.record.update(batch_passed=True,all_files_captured=all(e.get('status')=='captured' for e in self.record['files']))
            self.save()
        except Exception as error:
            self.record['batch_error']=str(error);self.save();raise
        finally:
            try:self.cleanup()
            except Exception as error:
                self.record.update(stage='recovery_needed',recovery_error=str(error));self.save();raise
        return self.record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    m=p.add_mutually_exclusive_group()
    m.add_argument('--trial',action='store_true');m.add_argument('--recover',action='store_true')
    m.add_argument('--offline',action='store_true');args=p.parse_args()
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();evidence=audit(raw)
    if args.offline:print(json.dumps(evidence,indent=2));return
    import usb.core,usb.util
    from mtp_probe_readonly import VID,PID,command
    from mtp_factory_pointer_trial import Transport
    from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS,operations_from_device_info
    device=usb.core.find(idVendor=VID,idProduct=PID)
    if device is None or device.bcdDevice!=0x111:raise RuntimeError('expected GR IV 01.11.10.07')
    usb.util.claim_interface(device,0);io=Transport(device);opened=False
    try:
        code,info,_=command(device,0x1001,0)
        if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS:
            raise RuntimeError('unexpected camera device information')
        code,_,_=command(device,0x1002,1,1);opened=code==0x2001
        if code not in (0x2001,0x201E):raise RuntimeError('OpenSession failed')
        identity=live_check(io.read,raw)
        if args.recover:
            session=FileSession(io,JOURNAL,json.loads(JOURNAL.read_text()));session.cleanup();result=session.record
        elif args.trial:
            session=FileSession.begin(io,JOURNAL)
            session.record.update(file_abi=evidence,filesystem_before=identity);session.save()
            result=session.batch()
        else:
            result={'filesystem':identity,'script_context':gate.collect(io.read),'camera_RAM_written':False}
        print(json.dumps({k:v for k,v in result.items() if k!='owned_before_hex'},indent=2))
    finally:
        try:
            if opened:command(device,0x1003,io.transaction)
        finally:usb.util.release_interface(device,0);usb.util.dispose_resources(device)


if __name__=='__main__':main()
