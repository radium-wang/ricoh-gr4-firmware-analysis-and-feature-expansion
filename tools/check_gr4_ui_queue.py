#!/usr/bin/env python3
"""Execute original queue copy/dispatch instructions with synthetic objects."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile

from audit_gr4_ui_queue import audit
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access


def build_gate(root,out):
    if out.exists():raise ValueError('native output already exists')
    out.mkdir(parents=True)
    source=root/'firmware/xpan_ui_queue_native.c';obj=out/'queue.o';elf=out/'queue.elf'
    flags=['--target=armv7-none-eabi','-march=armv7-a','-marm','-mfpu=none',
           '-mfloat-abi=soft','-std=c11','-Oz','-Wall','-Wextra','-Werror',
           '-ffreestanding','-fno-builtin','-fno-stack-protector','-fPIC',
           '-fvisibility=hidden','-ffunction-sections','-fdata-sections']
    subprocess.run([shutil.which('clang'),*flags,'-c',str(source),'-o',str(obj)],check=True)
    layout=out/'layout.ld'
    entry=out/'entry.S';entry_obj=out/'entry.o'
    entry.write_text('.syntax unified\n.arm\n.section .entry,"ax",%progbits\n.global gr4_xpan_queue_entry\ngr4_xpan_queue_entry:\n isb sy\n b gr4_xpan_ui_enqueue\n')
    subprocess.run([shutil.which('clang'),*flags,'-c',str(entry),'-o',str(entry_obj)],check=True)
    layout.write_text('SECTIONS { . = 0; .text : { *(.entry) *(.text*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n')
    subprocess.run([shutil.which('ld.lld'),'-static','--no-undefined','--gc-sections',
                    '--entry=gr4_xpan_queue_entry','-T',str(layout),str(entry_obj),str(obj),'-o',str(elf)],check=True)
    with elf.open('rb') as f:
        e=ELFFile(f)
        if e['e_entry']!=0:raise ValueError('unexpected queue gate entry')
        for s in e.iter_sections():
            if s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size']:raise ValueError('unresolved relocation')
            if s['sh_flags']&2 and s['sh_size'] and s.name!='.text':raise ValueError('unexpected load section')
        data=e.get_section_by_name('.text').data()
    if len(data)>1024:raise ValueError('gate exceeds check window')
    if data[:4]!=bytes.fromhex('6ff07ff5'):raise ValueError('entry must begin with ISB')
    (out/'queue.bin').write_bytes(data)
    return data


def check(raw,gate=None):
    evidence=audit(raw);check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
        UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_LR)
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x5323B000,0x5325C000,0x53FE1000):
        uc.mem_map(page,4096);uc.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    for page in (0x538DF000,0x538DB000,0x538ED000,0x53183000,0x54354000):uc.mem_map(page,4096)
    uc.mem_map(0x60000000,0x10000)
    mediator=0x60000100;ring=0x60001000;packet=0x60002000
    handler=0x60003000;vtable=handler+8;stop=0x6000F000
    events=[];service_results={}
    class AssertionPath(Exception):pass
    services=(0x538DFE24,0x538DFF78,0x538DB424,0x538ED930,0x5325C858,0x53183B40)
    def intercept(machine,address,size,context):
        if address not in services:return
        args=[machine.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
        events.append({'address':hex(address),'args':args})
        if address==0x538ED930:raise AssertionPath('original full queue assertion')
        machine.reg_write(UC_ARM_REG_R0,service_results.get(address,0x60004000 if address==0x5325C858 else 1))
        machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
    uc.hook_add(UC_HOOK_CODE,intercept)
    def run(entry,args):
        events.clear()
        for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):uc.reg_write(reg,value)
        uc.reg_write(UC_ARM_REG_SP,0x6000E000);uc.reg_write(UC_ARM_REG_LR,stop)
        uc.emu_start(entry,stop,count=5000,timeout=1000000)
        assert uc.reg_read(UC_ARM_REG_PC)==stop and uc.reg_read(UC_ARM_REG_SP)==0x6000E000
        return uc.reg_read(UC_ARM_REG_R0),list(events)
    cases=[]
    # The original two-instruction store leaf touches only its r0 argument.
    # It is a one-shot diagnostic callback, not a GUI hook or installation.
    uc.mem_write(handler,struct.pack('<I',vtable))
    uc.mem_write(vtable,struct.pack('<I',0x5325CA0C))
    data=struct.pack('<3I',0x17D,0,handler);uc.mem_write(packet,data)
    for count,tail in ((0,0),(0,63),(62,62)):
        uc.mem_write(mediator,bytes(0x40));uc.mem_write(mediator+0x14,struct.pack('<I',ring))
        uc.mem_write(mediator+0x18,struct.pack('<5H',count,64,0,tail,63))
        ret,ev=run(0x5325C768,[mediator,packet,0,0])
        assert bytes(uc.mem_read(ring+tail*12,12))==data
        assert struct.unpack('<H',uc.mem_read(mediator+0x18,2))[0]==count+1
        assert struct.unpack('<H',uc.mem_read(mediator+0x1E,2))[0]==(tail+1)&63
        assert [x['address'] for x in ev]==['0x538dfe24','0x538dff78','0x538db424']
        assert ev[0]['args'][0]==mediator+0x24 and ev[1]['args'][0]==mediator+0x24
        assert ev[2]['args'][:2]==[mediator+8,1]
        cases.append({'case':'original locked copy and notification','count_before':count,'tail_before':tail})
    uc.mem_write(mediator+0x18,struct.pack('<H',63))
    before=bytes(uc.mem_read(ring,64*12))
    try:run(0x5325C768,[mediator,packet,0,0])
    except AssertionPath:pass
    else:raise AssertionError('full queue assertion was not intercepted')
    assert bytes(uc.mem_read(ring,64*12))==before
    cases.append({'case':'full queue reaches original assertion before copying','not_a_safe_enqueue_failure_return':True})
    ret,ev=run(0x5325C87C,[mediator,packet,0,0])
    assert ret==1 and not ev and bytes(uc.mem_read(handler,4))==struct.pack('<I',0x17D)
    cases.append({'case':'0x17d invokes original ROM store callback without controller routing',
                  'marker':0x17D,'ROM_leaf_last_owned_memory_access_is_store':True})
    # Original record destructor cannot establish ownership/drain on its own.
    ret,ev=run(0x5323B804,[packet,0,0,0])
    assert not ev and bytes(uc.mem_read(packet,12))==data
    cases.append({'case':'record destructor does not free handler'})
    uc.mem_write(packet+8,bytes(4))
    ret,ev=run(0x5325C87C,[mediator,packet,0,0])
    assert ret==1 and not ev
    cases.append({'case':'null handler skipped'})
    if gate is not None:
        owner=0x55087470;owned_ring=0x59B93118
        uc.mem_map(0x55087000,4096);uc.mem_map(0x59B93000,4096)
        uc.mem_map(0x61000000,4096);uc.mem_write(0x61000000,gate)
        uc.mem_write(packet,data)
        for fault,count,tail,expected in (
                ('normal',0,0,1),('wrap',0,63,1),('full',63,63,3),
                ('busy',0,0,2),('bad layout',0,0,0),
                ('notify failure',0,0,4),('unlock failure',0,0,5),('bad magic',0,0,0)):
            service_results.clear()
            if fault=='busy':service_results[0x538DFE24]=0
            if fault=='notify failure':service_results[0x538DB424]=0
            if fault=='unlock failure':service_results[0x538DFF78]=0
            uc.mem_write(owner,bytes(0x40));uc.mem_write(owner+0x14,struct.pack('<I',owned_ring))
            uc.mem_write(owner+0x18,struct.pack('<5H',count,64,tail if count==0 else 0,tail,63))
            if fault=='bad layout':uc.mem_write(owner+0x20,struct.pack('<H',31))
            uc.mem_write(owned_ring,b'\xCC'*(64*12))
            ret,ev=run(0x61000000,[owner,packet,0 if fault=='bad magic' else 0x58505549,0])
            assert ret==expected
            if expected in (1,4,5):
                assert bytes(uc.mem_read(owned_ring+tail*12,12))==data
                assert struct.unpack('<H',uc.mem_read(owner+0x18,2))[0]==count+1
            else:assert bytes(uc.mem_read(owned_ring,64*12))==b'\xCC'*(64*12)
            assert all(e['address']!='0x538ed930' for e in ev)
            if fault=='full':assert [e['address'] for e in ev]==['0x538dfe24','0x538dff78']
            if fault=='busy':assert len(ev)==1
            if fault=='bad magic':assert not ev
            cases.append({'case':'compiled native queue gate','fault':fault,'result':ret,
                          'message_live':expected in (1,4,5),'original_assertion_avoided':True})
    return {'schema':'gr4-ui-queue-ARM-check-v1','audit':evidence,'cases_passed':len(cases),
            'cases':cases,'original_ARM_executed':True,
            'locks_notifications_and_controller_lookup_simulated':True,
            'live_AppMain_callback_or_cross_core_visibility_verified':False,
            'camera_accessed':False,'message_enqueued_on_camera':False,'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--native-output',type=Path)
    p.add_argument('--existing-native',type=Path,help='check a previously built, exact ELF/bin pair')
    args=p.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    root=Path(__file__).resolve().parents[1]
    if args.native_output and args.existing_native:raise ValueError('choose one native input')
    gate=build_gate(root,args.native_output) if args.native_output else None
    if args.existing_native:
        gate=(args.existing_native/'queue.bin').read_bytes()
        with (args.existing_native/'queue.elf').open('rb') as f:
            e=ELFFile(f)
            if e['e_entry']!=0 or gate!=e.get_section_by_name('.text').data():raise ValueError('ELF/bin differ')
    result=check((root/'samples/gr4_decoded.bin').read_bytes(),gate)
    if gate is not None:
        result['native_gate']={'bytes':len(gate),'sha256':hashlib.sha256(gate).hexdigest(),
                               'source_sha256':hashlib.sha256((root/'firmware/xpan_ui_queue_native.c').read_bytes()).hexdigest(),
                               'actual_compiled_ARM_executed':True,'camera_deployed':False}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('Original queue ARM cases passed:',result['cases_passed'])


if __name__=='__main__':main()
