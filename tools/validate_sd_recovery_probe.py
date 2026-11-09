#!/usr/bin/env python3
"""Synthetic recovery-script fault checks; not firmware execution or device proof."""
import argparse
import shlex
import struct
from pathlib import Path
from audit_xpan_paths import file_offset
from audit_xpan_runtime_loader import COMMANDS,TEST_RETURN,REFERENCE_RANGES,audit
from build_sd_recovery_probe import HOLDER,ORIGINAL,PROPERTIES,build,references,controls
from validate_sd_batch_probe import FlowCheck


class RecoveryFlow(FlowCheck):
    def __init__(self,raw,command_table,fault=None,files=None,base=0x59616000,
                 handler=ORIGINAL):
        super().__init__()
        # Keep only the parent's unused flag for its final invariant; avoid
        # overlapping zero-filled snapshot ranges from the older batch model.
        self.memory={self.bridge:bytearray(117)}
        self.fault=fault
        self.table=base
        self.address=base+COMMANDS['SYS_buildinfo'][0]*52
        self.writes=[]
        self.files={} if files is None else {k:bytearray(v) for k,v in files.items()}
        for name,data in references(raw).items():self.files['C:\\'+name]=bytearray(data)
        for name,data in controls().items():self.files['C:\\'+name]=bytearray(data)
        self.files['C:\\DCIM\\KEEP.JPG']=bytearray(b'UNCHANGED PHOTO')
        for tag,address,size in REFERENCE_RANGES:
            self.memory[address]=bytearray(raw[file_offset(address):file_offset(address)+size])
        self.memory[HOLDER]=bytearray(struct.pack('<IH',base,651)+b'\0\0')
        self.memory[PROPERTIES]=bytearray(b'\0\0\0\x80\x3f')
        self.memory[base]=bytearray(command_table)
        struct.pack_into('<I',self.memory[base],self.address-base,handler)
        if fault=='bad_pointer':struct.pack_into('<I',self.memory[HOLDER],0,0xDEADBEEF)
        if fault=='unaligned':struct.pack_into('<I',self.memory[HOLDER],0,base+1)
        if fault=='bad_count':struct.pack_into('<H',self.memory[HOLDER],4,650)
        if fault=='bad_reference':self.files['C:\\XRREG.REF'][17]^=1
        if fault=='extra_reference':self.files['C:\\XRREG.REF'].append(0)
        if fault=='missing_reference':del self.files['C:\\XRREG.REF']
        if fault=='foreign_handler':struct.pack_into('<I',self.memory[base],self.address-base,0x53100000)
        if fault=='bad_control':self.files['C:\\XCEQ.BIN'][2]^=1
        if fault=='missing_control':del self.files['C:\\XCDIFF.BIN']
        if fault=='short_reference':self.files['C:\\XRREG.REF']=self.files['C:\\XRREG.REF'][:-1]

    def stat_file(self,name):
        if self.fault=='stat_failure':return (-1,-1)
        if self.fault=='stat_wrong_size':return (0,4)
        return super().stat_file(name)

    def send(self,cmd):
        self.commands.append(cmd)
        args=shlex.split(cmd,posix=False)
        self.env['result']=0
        if args[0]=='SYS_md':
            address,size,name=int(args[1],0),int(args[3],0),args[5]
            assert args[2]=='-s' and args[4]=='-f'
            if self.fault=='readback_failure' and name=='C:\\XR1POST.BIN':return
            data=bytearray(self.read_memory(address,size))
            if self.fault=='short_backup' and name=='C:\\XR1BIROW.BIN':data=data[:-1]
            self.files[name]=data
        elif args[0]=='SYS_reg':
            assert args[1]=='set' and len(args)==5
            address,size,value=int(args[2],0),int(args[3]),int(args[4],0)
            assert address==self.address and address%4==0 and size==4
            assert value in (TEST_RETURN,ORIGINAL), 'unexpected RAM write'
            self.writes.append(value)
            if self.fault=='restore_failure' and value==ORIGINAL:
                self.env['result']=-1;return
            if self.fault=='write_no_effect' and value==TEST_RETURN:return
            struct.pack_into('<I',self.memory[self.table],address-self.table,value)
        elif cmd=='SYS_buildinfo':
            value=struct.unpack_from('<I',self.memory[self.table],self.address-self.table)[0]
            assert value in (ORIGINAL,TEST_RETURN), 'unexpected diagnostic function call'
            self.env['result']=3 if value==TEST_RETURN else 0
        else:raise AssertionError('unexpected command: '+cmd)

    def checked_run(self,program):
        lines=[s.strip() for s in program.splitlines() if s.strip() and not s.lstrip().startswith(';')]
        a=lines.index('sendln patch_command');b=lines.index('sendln restore_command',a)
        assert lines[a:b+1]==['sendln patch_command','patch_result = result',
            "sendln 'SYS_buildinfo'",'test_result = result','sendln restore_command']
        self.run(program)
        assert self.files['C:\\DCIM\\KEEP.JPG']==b'UNCHANGED PHOTO'
        assert self.eof_reads==0, 'must not read beyond a verified file length'
        return self


def check(raw,commands):
    audit(raw,commands)
    read_only=RecoveryFlow(raw,commands).checked_run(build())
    assert not read_only.writes and read_only.env['good']==1
    first=RecoveryFlow(raw,commands).checked_run(build(True))
    assert first.writes==[TEST_RETURN,ORIGINAL] and first.env['good']==1
    assert first.env['test_result']==3 and first.env['original_result']==0
    assert struct.unpack_from('<I',first.memory[first.table],first.address-first.table)[0]==ORIGINAL
    # A new boot resolves a new table address. Never trust the saved heap pointer.
    second=RecoveryFlow(raw,commands,files=first.files,base=0x59626000).checked_run(build(True))
    assert second.env['phase']==2 and second.env['good']==1 and not second.writes
    assert all(address!=first.address for address in [second.address])
    repeat=RecoveryFlow(raw,commands,files=second.files).checked_run(build(True))
    assert not repeat.commands and not repeat.writes
    for fault in ('bad_pointer','unaligned','bad_count','bad_reference','extra_reference',
                  'missing_reference','foreign_handler','short_backup','short_reference',
                  'bad_control','missing_control','stat_failure','stat_wrong_size'):
        flow=RecoveryFlow(raw,commands,fault=fault).checked_run(build(True))
        assert not flow.writes and flow.env['good']==0, fault
    for fault in ('write_no_effect','readback_failure'):
        flow=RecoveryFlow(raw,commands,fault=fault).checked_run(build(True))
        assert flow.writes==[TEST_RETURN,ORIGINAL] and flow.env['good']==0, fault
        assert struct.unpack_from('<I',flow.memory[flow.table],flow.address-flow.table)[0]==ORIGINAL
    broken=RecoveryFlow(raw,commands,fault='restore_failure').checked_run(build(True))
    assert broken.env['good']==0 and broken.writes==[TEST_RETURN,ORIGINAL]
    recovery=RecoveryFlow(raw,commands,files=broken.files,handler=TEST_RETURN).checked_run(build(False,True))
    assert recovery.writes==[ORIGINAL] and recovery.env['good']==1
    unknown=RecoveryFlow(raw,commands,handler=0x53100000).checked_run(build(False,True))
    assert not unknown.writes and unknown.env['good']==0
    return {'read_only_default':'passed','temporary_pointer_and_immediate_restore':'passed',
            'second_boot_new_pointer_and_repeat_protection':'passed',
            '13_preflight_faults_block_writes':'passed','2_postwrite_faults_still_restore':'passed',
            'observed_EOF_zero_and_stale_byte_not_used':'passed',
            'restore_failure_and_independent_recovery':'passed','foreign_handler_not_overwritten':'passed',
            'camera_execution_tested':False,'cold_boot_recovery_verified':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sample',type=Path);p.add_argument('command_table',type=Path)
    args=p.parse_args()
    import json
    print(json.dumps(check(args.sample.read_bytes(),args.command_table.read_bytes()),indent=2))


if __name__=='__main__':main()
