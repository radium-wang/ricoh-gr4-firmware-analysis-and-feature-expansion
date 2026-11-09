#!/usr/bin/env python3
"""Offline fixed-file lifecycle faults and execution of original ARM wrappers."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch
import gr4_usb_call_session as gate
from check_gr4_usb_call_session import CameraModel
from mtp_factory_sd_file_trial import FileSession,FILES,DATA_LENGTH,STATUS_OFFSET,BUFFER_OFFSET
from audit_gr4_sd_file_abi import STAT,OPEN,READ,CLOSE,pinned
from audit_xpan_paths import file_offset


class FileModel(CameraModel):
    def __init__(self,fault=None):
        super().__init__();self.file_fault=fault;self.fd=0x59B10000
        self.open_handles=0;self.close_calls=0
        self.contents={name:bytes((i+index)%256 for i in range(n)) for index,(name,n) in enumerate(FILES)}

    def sleep(self,seconds):
        go,done=self.variable('xpb_go'),self.variable('xpb_done')
        target=struct.unpack('<I',self.read(gate.RESPONSE_BUFFER,4))[0]
        if go==done or target not in (STAT,OPEN,READ,CLOSE):return super().sleep(seconds)
        self.clock+=seconds;self.variable('xpb_tick',self.variable('xpb_tick')+1)
        assert go==done+1
        assert self.read(gate.SEND_SLOT,4)==gate.word(gate.ADAPTER)
        assert self.read(gate.RESPONSE_SLOT,4)==gate.word(gate.TEST_LEAF)
        _,adjust,r2,r1,r0=struct.unpack('<5I',self.read(gate.RESPONSE_BUFFER,20));assert adjust==0
        self.native_calls.append((target,r0,r1,r2));self.variable('xpb_state',1802)
        if target in (STAT,OPEN):
            path=self.read(r0,32).split(b'\0')[0].decode()
            name=path.split('\\')[-1];assert path=='C:\\XPV12\\'+name and name in self.contents
        if target==STAT:
            assert r1==self.pointer+STATUS_OFFSET and r2==0
            self.put(r1,bytes(524));self.put(r1+516,gate.word(len(self.contents[name])+(self.file_fault=='wrong_length')))
            value=-1 if self.file_fault=='missing' else 0
        elif target==OPEN:
            assert (r1,r2)==(0,0) and not self.open_handles
            value=0 if self.file_fault=='open_failure' else self.fd
            if value:self.open_handles=1;self.current_name=name
        elif target==READ:
            assert r0==self.fd and self.open_handles==1 and r1==self.pointer+BUFFER_OFFSET
            assert r2==len(self.contents[self.current_name])
            self.put(r1,self.contents[self.current_name]);value=-1 if self.file_fault=='read_failure' else r2
        else:
            assert (r0,r1,r2)==(self.fd,0,0) and self.open_handles==1
            self.close_calls+=1;value=0 if self.file_fault=='close_failure' else 1
            if value:self.open_handles=0
        self.variable('xpb_return',value);self.variable('xpb_done',go);self.variable('xpb_state',1803)
        label={OPEN:'disconnect_open',READ:'disconnect_read',CLOSE:'disconnect_close'}.get(target)
        if label and self.file_fault==label and not self.fault_used:
            self.fault_used=True;self.disconnected=True


def lifecycle():
    cases=[]
    with tempfile.TemporaryDirectory() as tmp:
        for fault in (None,'missing','wrong_length','open_failure','read_failure','close_failure',
                      'disconnect_open','disconnect_read','disconnect_close'):
            io=FileModel(fault);journal=Path(tmp)/(str(fault)+'.json')
            with patch.object(gate.time,'monotonic',lambda:io.clock),patch.object(gate.time,'sleep',io.sleep):
                session=FileSession.begin(io,journal);error=None
                try:session.batch()
                except RuntimeError as e:error=str(e)
                if fault and fault.startswith('disconnect_'):
                    io.disconnected=False;session=FileSession(io,journal,json.loads(journal.read_text()));session.cleanup()
                io.assert_restored()
                if fault=='close_failure':
                    assert io.close_calls==1 and io.open_handles==1 and io.owned
                    try:session.cleanup();raise AssertionError('failed close retried')
                    except RuntimeError:pass
                    assert io.close_calls==1
                else:
                    assert not io.open_handles and not io.owned and session.record['cleanup_verified']
                    original=bytes(i%256 for i in range(DATA_LENGTH))
                    assert io.read(io.pointer,DATA_LENGTH)==original
                assert len(io.native_calls)<=16
                if fault is None:
                    assert len(io.native_calls)==16 and session.record['all_files_captured']
                    for entry in session.record['files']:
                        assert bytes.fromhex(entry['data_hex'])==io.contents[entry['name']]
                    before=list(io.native_calls);session.cleanup();assert before==io.native_calls
                if fault in ('missing','wrong_length','open_failure'):
                    assert not any(c[0]==READ for c in io.native_calls)
                if fault=='wrong_length':assert not any(c[0]==OPEN for c in io.native_calls)
                if fault and fault.startswith('disconnect_'):
                    assert io.close_calls==1
                cases.append({'case':fault or 'complete_16_requests','error':error,
                              'requests':len(io.native_calls),'close_calls':io.close_calls,
                              'cleanup_verified':session.record.get('cleanup_verified',False)})
    return cases


def arm(raw):
    pinned(raw)
    from check_gr4_native_memory_abi import check_host_cache_access
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x538F1000,0x53B14000,0x537A3000,0x53F9B000):
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    for page in (0x54354000,0x553A0000,0x553B1000,0x5501A000,0x53157000,0x53AE0000,0x537A2000):u.mem_map(page,4096)
    u.mem_map(0x63000000,0x10000)
    obj,vt,path,status,buffer,stack,stop=0x63000100,0x63000200,0x63000300,0x63000400,0x63000800,0x6300E000,0x6300F000
    openstub,readstub,closestub=0x6300F100,0x6300F104,0x6300F108
    filename=b'C:\\XPV12\\PROCESSA.BIN\0';data=bytes(i%256 for i in range(960));fd=0x63000D00
    u.mem_write(path,filename);u.mem_write(0x553A09D0,gate.word(obj));u.mem_write(obj,gate.word(vt))
    u.mem_write(vt+32,gate.word(openstub));u.mem_write(vt+36,gate.word(closestub));u.mem_write(vt+40,gate.word(readstub))
    u.mem_write(0x553B1934,gate.word(0x5501A2F4));u.mem_write(0x5501A324,gate.word(0x538F1B20))
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3);observed=[];failure=[False]
    def ret(value):u.reg_write(UC_ARM_REG_R0,value&0xFFFFFFFF);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
    def hook(m,a,n,unused):
        r=[m.reg_read(reg) for reg in regs]
        if a==openstub:
            assert r[:3]==[obj,path,1];m.mem_write(r[3],gate.word(fd));observed.append('open_native_mode_1');ret(0 if failure[0] else 1)
        elif a==readstub:
            assert r==[obj,fd,buffer,960];m.mem_write(buffer,data);ret(0 if failure[0] else 1)
        elif a==closestub:
            assert r[:3]==[obj,fd,0];ret(1)
        elif a==0x538F1B20:
            assert r[0]==path
            m.mem_write(r[1],b'\x20');m.mem_write(r[2],gate.word(960));m.mem_write(r[3],struct.pack('<H',123))
            fifth=struct.unpack('<I',m.mem_read(m.reg_read(UC_ARM_REG_SP),4))[0]
            m.mem_write(fifth,struct.pack('<H',456));ret(-1 if failure[0] else 0)
        elif a==0x53157D80:
            assert r[:2]==[status,path];m.mem_write(status,filename);ret(status)
        elif a==0x537A3100:ret(1)
        elif a==0x53AE0358:
            assert r[:3]==[path,0,128];observed.append('FAT_backend_flag_0');ret(7)
        elif a in (0x537A24E4,0x537A2270):ret(0)
    u.hook_add(UC_HOOK_CODE,hook)
    cases=[]
    for target,args,expected in ((STAT,[path,status,0],0),(OPEN,[path,0,0],fd),
                                 (READ,[fd,buffer,960],960),(CLOSE,[fd,0,0],1),
                                 (0x537A3130,[obj,path,1,buffer],1)):
        for reg,val in zip(regs,args+[0]*(4-len(args))):u.reg_write(reg,val)
        u.mem_write(stack,gate.word(0));u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
        u.emu_start(target,stop,count=10000,timeout=1000000)
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
        assert u.reg_read(UC_ARM_REG_R0)==expected
        if target==STAT:
            assert struct.unpack('<I',u.mem_read(status+516,4))[0]==960
            assert bytes(u.mem_read(status,len(filename)))==filename
        if target==READ:assert bytes(u.mem_read(buffer,960))==data
        cases.append({'entry':hex(target),'case':'success','actual_original_ARM_executed':True})
    failure[0]=True
    for target,args,expected in ((STAT,[path,status,0],0xFFFFFFFF),(OPEN,[path,0,0],0),
                                 (READ,[fd,buffer,960],0xFFFFFFFF)):
        for reg,val in zip(regs,args+[0]):u.reg_write(reg,val)
        u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
        u.emu_start(target,stop,count=10000,timeout=1000000)
        assert u.reg_read(UC_ARM_REG_R0)==expected and u.reg_read(UC_ARM_REG_SP)==stack
        cases.append({'entry':hex(target),'case':'service_failure','actual_original_ARM_executed':True})
    assert 'FAT_backend_flag_0' in observed
    return {'cases':cases,'service_callbacks_modelled':True,'SD_or_USB_access':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    result={'schema':'gr4-sd-file-checks-v1','lifecycle':lifecycle(),
            'ARM':arm(Path('samples/gr4_decoded.bin').read_bytes()),'passed':True,
            'camera_access':False,'hardware_file_read_verified':False}
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('%d lifecycle cases and %d original ARM cases passed'%(len(result['lifecycle']),len(result['ARM']['cases'])))


if __name__=='__main__':main()
