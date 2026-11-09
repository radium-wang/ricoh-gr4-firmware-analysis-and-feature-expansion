#!/usr/bin/env python3
"""Build the native row backend and execute it with original ASCII ARM code.

All camera objects are synthetic. Allocation, visibility/invalidation and native
property setters are simulated. No USB access or installer is implemented.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from elftools.elf.elffile import ELFFile
from audit_gr4_menu_widgets import audit
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access

ROOT=Path(__file__).resolve().parents[1]
BASE=0x61000000
CONTROLLER=0x60000100
ITEM=0x60000400
STATE=0x60002000
LIST=0x60003000
STOP=0x6000F000


def build(out, extra_sources=(), extra_names=(), extra_objects=()):
    out.mkdir(parents=True,exist_ok=True)
    flags=['--target=armv7-none-eabi','-march=armv7-a','-marm','-mfpu=none',
           '-mfloat-abi=soft','-std=c11','-Oz','-Wall','-Wextra','-Werror',
           '-ffreestanding','-fno-builtin','-fno-stack-protector','-fPIC',
           '-fvisibility=hidden','-ffunction-sections','-fdata-sections']
    objects=[str(obj) for obj in extra_objects]
    for source in ('xpan_settings_native.c','xpan_core.c','xpan_capture.c','xpan_selection.c','xpan_memory.c',*extra_sources):
        obj=out/(source+'.o');objects.append(str(obj))
        subprocess.run([shutil.which('clang'),*flags,'-c',str(ROOT/'firmware'/source),'-o',str(obj)],check=True)
    layout=out/'layout.ld'
    layout.write_text('SECTIONS { . = 0; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } .bss : { *(.bss*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n')
    names=['gr4_xpan_settings_label','gr4_xpan_settings_selected','gr4_xpan_settings_select',*extra_names]
    elf=out/'backend.elf'
    subprocess.run([shutil.which('ld.lld'),'-static','--no-undefined','--gc-sections',
                    '--entry='+names[0],*['--undefined='+n for n in names],
                    '-T',str(layout),*objects,'-o',str(elf)],check=True)
    with elf.open('rb') as f:
        e=ELFFile(f);chunks=[]
        for s in e.iter_sections():
            if s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size']:
                raise ValueError('unresolved relocation')
            if s['sh_flags']&2 and s['sh_size']:
                if s.name not in ('.text','.rodata','.data','.bss'):raise ValueError('unexpected allocated section')
                chunks.append((s['sh_addr'],bytes(s['sh_size']) if s['sh_type']=='SHT_NOBITS' else s.data()))
        syms=e.get_section_by_name('.symtab')
        offsets={n:syms.get_symbol_by_name(n)[0]['st_value'] for n in names}
        if any(s.name and s['st_shndx']=='SHN_UNDEF' for s in syms.iter_symbols()):
            raise ValueError('unresolved symbol')
    end=max(a+len(b) for a,b in chunks)
    if end>8192:raise ValueError('backend exceeds local check window')
    data=bytearray(end)
    for a,b in chunks:data[a:a+len(b)]=b
    (out/'backend.bin').write_bytes(data)
    return bytes(data),offsets


def check(raw,data,offsets):
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
        UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC)
    uc=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x53156000,0x531D6000,0x531D7000,0x531DA000,0x5356D000,
                 0x5357A000,0x53571000,0x53570000,0x538EA000,0x53DA3000,
                 0x53DA2000):
        uc.mem_map(page,4096)
        uc.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    services=(0x531D0CCC,0x531D2F70,0x531D8FFC,0x535899FC,0x53589AB4,
              0x53571100,0x53183E14,0x53182E9C,0x531D7004,0x538E0A24,
              0x538E0A60,0x538ED930)
    loaded={a&~0xFFF for a in (0x531D6000,0x531D7000,0x53571000)}
    for page in sorted({a&~0xFFF for a in services}-loaded):uc.mem_map(page,4096)
    uc.mem_map(0x54354000,4096)
    uc.mem_map(0x60000000,0x10000)
    uc.mem_map(BASE,8192);uc.mem_write(BASE,data)
    uc.mem_write(CONTROLLER,struct.pack('<I',0x53DA2C70))
    uc.mem_write(CONTROLLER+0x124,struct.pack('<I',0x0200008A))
    uc.mem_write(CONTROLLER+0x1A4,b'\x22')
    uc.mem_write(CONTROLLER+0x198,struct.pack('<I',LIST))
    uc.mem_write(ITEM,struct.pack('<I',0x53E98F18))
    widgets=[0x60000600+i*0x200 for i in range(6)]
    uc.mem_write(ITEM+0xF0,struct.pack('<6I',*widgets))
    events=[];allocations={};cursor=[0x60008000]
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    def intercept(machine,address,size,context):
        if address not in services:return
        args=[machine.reg_read(r) for r in regs];ret=0
        events.append({'address':hex(address),'arguments':args})
        if address==0x538E0A24:
            ret=cursor[0];cursor[0]+=0x40
            if not 0<args[0]<=0x40 or cursor[0]>=0x6000C000:raise AssertionError('unexpected allocation')
            allocations[ret]=args[0]
            machine.mem_write(ret,b'\xCC'*0x40)
        elif address==0x538E0A60:
            if args[0] not in allocations:raise AssertionError('free without matching owned allocation')
            del allocations[args[0]]
        elif address==0x53571100:
            machine.mem_write(args[0]+0x110,struct.pack('<H',args[1]))
        elif address==0x53183E14:ret=0x0200008A
        elif address==0x538ED930:raise AssertionError('original assertion path reached')
        machine.reg_write(UC_ARM_REG_R0,ret)
        machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
    uc.hook_add(UC_HOOK_CODE,intercept)
    def run(address,args):
        events.clear()
        for reg,value in zip(regs,args):uc.reg_write(reg,value)
        uc.reg_write(UC_ARM_REG_SP,0x6000E000);uc.reg_write(UC_ARM_REG_LR,STOP)
        uc.emu_start(address,STOP,count=30000,timeout=2000000)
        assert uc.reg_read(UC_ARM_REG_PC)==STOP and uc.reg_read(UC_ARM_REG_SP)==0x6000E000
        return uc.reg_read(UC_ARM_REG_R0),list(events)
    cases=[]
    for index in range(4):
        ret,ev=run(BASE+offsets['gr4_xpan_settings_label'],[CONTROLLER,ITEM,index])
        assert ret==1 and len(ev)==1 and ev[0]['address']=='0x531d0ccc'
        assert ev[0]['arguments'][:3]==[CONTROLLER,ITEM,index]
        cases.append({'case':'original label delegated','index':index})
    # R3 is not an argument of label_fn; avoid interpreting its stale value.
    ascii_widget=widgets[4]
    prior=0
    for attempt in range(3):
        if attempt==2:uc.mem_write(prior,'AAAA\0'.encode('utf-16le'))
        ret,ev=run(BASE+offsets['gr4_xpan_settings_label'],[CONTROLLER,ITEM,4,0])
        ptr=struct.unpack('<I',uc.mem_read(ascii_widget+0xF0,4))[0]
        assert ret==1 and bytes(uc.mem_read(ptr,10))=='XPAN\0'.encode('utf-16le')
        assert allocations=={ptr:10} and bytes(uc.mem_read(ptr+10,2))==b'\xCC\xCC'
        assert bytes(uc.mem_read(ascii_widget+0xED,1))==b'\x05'
        if attempt==1:assert ptr==prior  # Duplicate temporary buffer was freed.
        if attempt==2:assert ptr!=prior  # Changed old buffer was freed.
        visibility=[e['arguments'][:2] for e in ev if e['address']=='0x53589ab4']
        assert visibility==[[w,0] for w in widgets]+[[ascii_widget,1]]
        prior=ptr
        cases.append({'case':'original ASCII code owns UTF-16 text','attempt':attempt,
                      'live_allocations':1,'allocation_bytes':10})
    for confirm in (0,1):
        for index in range(5):
            uc.mem_write(STATE,struct.pack('<3I',2,1,1))
            ret,ev=run(BASE+offsets['gr4_xpan_settings_select'],[CONTROLLER,STATE,index,confirm])
            assert ret==1 and len(ev)==1
            assert ev[0]['address']==hex(0x531D8FFC if confirm else 0x531D2F70)
            assert ev[0]['arguments'][:2]==[CONTROLLER,0 if index==4 else index]
            state=struct.unpack('<3I',uc.mem_read(STATE,12))
            assert state[0]==2 and state[1]==(0,1,3,2,4)[index]
            cases.append({'case':'selection never sends index 4 to original handler',
                          'index':index,'confirm':bool(confirm),'crop_preserved':True})
    for index in range(6):
        ret,ev=run(BASE+offsets['gr4_xpan_settings_selected'],[STATE,index,0,0])
        assert ret==int(index==4) and not ev
        cases.append({'case':'XPAN selected predicate','index':index})
    for invalid in ('index','row','class','item'):
        if invalid=='row':uc.mem_write(CONTROLLER+0x1A4,b'\x21')
        if invalid=='class':uc.mem_write(CONTROLLER,struct.pack('<I',0x53D9F6A0))
        if invalid=='item':uc.mem_write(ITEM,bytes(4))
        ret,ev=run(BASE+offsets['gr4_xpan_settings_label'],[CONTROLLER,ITEM,5 if invalid=='index' else 4,0])
        assert ret==0 and not ev
        uc.mem_write(CONTROLLER+0x1A4,b'\x22');uc.mem_write(CONTROLLER,struct.pack('<I',0x53DA2C70))
        uc.mem_write(ITEM,struct.pack('<I',0x53E98F18))
        cases.append({'case':'wrong label context rejected','fault':invalid})
    # Actual count routine must change only the flag byte, not record padding.
    vector=0x60004000;records=[0x60004100+i*8 for i in range(6)]
    uc.mem_write(LIST+0xF4,struct.pack('<3I',vector,vector+24,vector+24))
    uc.mem_write(vector,struct.pack('<6I',*records))
    for rec in records:uc.mem_write(rec,struct.pack('<I',ITEM)+b'\x00\x77\xD7\x79')
    for count in (4,5,4):
        ret,ev=run(0x535711E4,[LIST,count,0,0])
        for index,rec in enumerate(records):
            assert bytes(uc.mem_read(rec+4,4))==bytes([int(index<count)])+b'\x77\xD7\x79'
        assert bytes(uc.mem_read(LIST+0x108,1))==bytes([count])
        cases.append({'case':'original enable-count changes byte flags only','count':count})
    # Demonstrate every original confirm route forwards fifth index unguarded.
    storage=0x60005000;record=0x60005020
    uc.mem_write(storage,struct.pack('<I',record));uc.mem_write(record,struct.pack('<I',CONTROLLER))
    uc.mem_write(LIST+0x110,struct.pack('<H',4));uc.mem_write(0x60005100,b'\xE0\x00')
    for name,address,args in (
            ('list',0x531D71AC,[storage,4,0,0]),
            ('button',0x531D6B50,[storage,0,0,0]),
            ('event E0',0x531DACAC,[CONTROLLER,0x60005100,0,0])):
        ret,ev=run(address,args)
        calls=[e for e in ev if e['address'] in ('0x531d2f70','0x531d8ffc')]
        assert len(calls)==1 and calls[0]['arguments'][:2]==[CONTROLLER,4]
        cases.append({'case':'original fifth index requires guard','route':name})
    return {'cases_passed':len(cases),'cases':cases,'actual_linked_backend_ARM_executed':True,
            'original_ASCII_length_conversion_compare_and_count_ARM_executed':True,
            'allocation_visibility_invalidation_and_property_services_simulated':True,
            'UI_thread_synchronization_verified':False,'actual_render_or_capture_verified':False,
            'camera_accessed':False,'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('output already exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();evidence=audit(raw)
    data,offsets=build(args.output)
    result=check(raw,data,offsets)
    result.update({'schema':'gr4-settings-native-backend-check-v1','audit':evidence,
                   'backend_bytes':len(data),'backend_sha256':hashlib.sha256(data).hexdigest(),
                   'entry_offsets':offsets})
    (args.output/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Offline ARM cases passed:',result['cases_passed'])
    print('Camera not accessed. Installer and thread synchronization remain pending.')


if __name__=='__main__':main()
