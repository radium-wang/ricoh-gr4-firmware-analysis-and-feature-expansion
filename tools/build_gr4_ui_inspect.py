#!/usr/bin/env python3
"""Build/check an owned RAM AppMain callback that only reads camera objects."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile
from audit_xpan_paths import file_offset
from check_gr4_ui_queue import check as queue_check
from check_gr4_native_memory_abi import check_host_cache_access

ROOT=Path(__file__).resolve().parents[1]


def build(out):
    out.mkdir(parents=True)
    flags=['--target=armv7-none-eabi','-march=armv7-a','-marm','-mfpu=none',
           '-mfloat-abi=soft','-Oz','-Wall','-Wextra','-Werror','-ffreestanding',
           '-fno-builtin','-fno-stack-protector','-fPIC','-fvisibility=hidden',
           '-ffunction-sections','-fdata-sections']
    entry=out/'entry.S'
    entry.write_text('''.syntax unified
.arm
.section .entry,"ax",%progbits
.global gr4_xpan_inspect_entry
gr4_xpan_inspect_entry:
 isb sy
 b gr4_xpan_ui_enqueue
.section .callback,"ax",%progbits
.global gr4_xpan_inspect_callback
gr4_xpan_inspect_callback:
 push {r4,lr}
 mov r4,r0
 bl gr4_xpan_ui_inspect
 mov r0,r4
 movw r1,#0x17d
 pop {r4,lr}
 movw ip,#0xca0c
 movt ip,#0x5325
 bx ip
''')
    objects=[]
    for source in (entry,ROOT/'firmware/xpan_ui_queue_native.c',ROOT/'firmware/xpan_ui_inspect.c'):
        obj=out/(source.name+'.o');objects.append(str(obj))
        subprocess.run([shutil.which('clang'),*flags,'-c',str(source),'-o',str(obj)],check=True)
    layout=out/'layout.ld'
    layout.write_text('SECTIONS { . = 0; .text : { *(.entry) *(.callback) *(.text*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n')
    elf=out/'inspect.elf'
    subprocess.run([shutil.which('ld.lld'),'-static','--no-undefined','--gc-sections',
                    '--entry=gr4_xpan_inspect_entry','--undefined=gr4_xpan_inspect_callback',
                    '-T',str(layout),*objects,'-o',str(elf)],check=True)
    with elf.open('rb') as handle:
        e=ELFFile(handle)
        for s in e.iter_sections():
            if s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size']:raise ValueError('relocation remains')
            if s['sh_flags']&2 and s['sh_size'] and s.name!='.text':raise ValueError('unexpected load section')
        assert e['e_entry']==0
        data=e.get_section_by_name('.text').data()
        symbols=e.get_section_by_name('.symtab')
        callback=symbols.get_symbol_by_name('gr4_xpan_inspect_callback')[0]['st_value']
    assert len(data)<=2048 and data[:4]==bytes.fromhex('6ff07ff5')
    # Fixed completion suffix branches into ROM. There is no RAM instruction
    # after the ROM store; marker observation permits reclamation of this code.
    suffix=bytes.fromhex('0400a0e17d1100e31040bde80cca0ce325c345e31cff2fe1')
    assert data[callback+12:callback+36]==suffix
    padded=data.ljust(2048,b'\0');(out/'inspect.bin').write_bytes(padded)
    return padded,callback


def inspect_check(raw,data,callback):
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
    from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    u.mem_map(0x5325C000,4096);u.mem_write(0x5325C000,raw[file_offset(0x5325C000):file_offset(0x5325C000)+4096])
    u.mem_map(0x55080000,0x10000);u.mem_map(0x5539F000,4096)
    u.mem_map(0x5A010000,0x10000);u.mem_map(0x60000000,0x10000)
    u.mem_map(0x61000000,4096);u.mem_write(0x61000000,data)
    c=0x5A010000;l=c+0x1000;vector=c+0x2000;image=c+0x3000
    handler=0x60003000;report=handler+64;stack=0x6000E000;stop=0x6000F000
    writes=[]
    def written(machine,access,address,size,value,unused):writes.append((address,size))
    u.hook_add(UC_HOOK_MEM_WRITE,written)
    cases=[]
    for fault in ('present','absent','wrong row','four constructed'):
        u.mem_write(0x55080D40,struct.pack('<I',0x53D94F08));u.mem_write(0x55080DF0,struct.pack('<I',c))
        u.mem_write(0x55082004,struct.pack('<I',0x100007C))
        u.mem_write(0x5539FC78,struct.pack('<I',image));u.mem_write(image,struct.pack('<I',0x53FD89A0))
        u.mem_write(c,struct.pack('<I',0x53DA2C70));u.mem_write(c+0x124,struct.pack('<I',0x0200008A))
        u.mem_write(c+0x1A4,b'\x22');u.mem_write(c+0x198,struct.pack('<I',l))
        u.mem_write(l,struct.pack('<I',0x53E98468))
        u.mem_write(l+0xF4,struct.pack('<3I',vector,vector+37*4,vector+64*4))
        u.mem_write(l+0x108,b'\x04');u.mem_write(l+0x168,struct.pack('<I',c+0x3300))
        u.mem_write(c+0x3300,struct.pack('<I',c));u.mem_write(l+0x170,struct.pack('<2I',0x531D5D0C,0x531D71AC))
        for i in range(5):
            record=c+0x4000+i*8;item=c+0x5000+i*0x200;ascii=c+0x6000+i*0x100
            u.mem_write(vector+i*4,struct.pack('<I',record));u.mem_write(record,struct.pack('<I',item)+bytes([i<4,77,88,99]))
            u.mem_write(item,struct.pack('<I',0x53E98F18));u.mem_write(item+0x100,struct.pack('<I',ascii))
            u.mem_write(ascii,struct.pack('<I',0x53E97FD8))
        if fault=='absent':u.mem_write(0x55080DF0,bytes(4))
        elif fault=='wrong row':u.mem_write(c+0x1A4,b'\x21')
        elif fault=='four constructed':u.mem_write(l+0xF8,struct.pack('<I',vector+16))
        u.mem_write(handler,b'\xAA'*320);writes.clear()
        u.reg_write(UC_ARM_REG_R0,handler);u.reg_write(UC_ARM_REG_R1,0x17D)
        u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
        u.emu_start(0x61000000+callback,stop,count=30000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
        result=struct.unpack('<64I',u.mem_read(report,256))
        assert result[0]==0x58504931 and result[1]=={'present':0,'absent':2,'wrong row':8,'four constructed':32}[fault]
        assert u.mem_read(handler,4)==struct.pack('<I',0x17D)
        assert all(report<=a and a+s<=report+256 or stack-0x100<=a and a+s<=stack or a==handler and s==4 for a,s in writes)
        assert writes[-1]==(handler,4) # final owned access is the original ROM store
        if fault=='present':assert result[7:10]==(37,64,4) and result[12]==c and result[13]==image
        cases.append({'case':fault,'status':result[1],'writes_only_owned_report_stack_marker':True,
                      'ROM_completion_is_last_owned_access':True})
    return {'cases_passed':len(cases),'cases':cases,'actual_RAM_callback_and_ROM_completion_ARM_executed':True,
            'camera_objects_synthetic':True,'camera_accessed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError('immutable package already exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();data,callback=build(args.output)
    result={'schema':'gr4-ui-inspect-candidate-v1','deployed':False,'xpan_installed':False,
            'payload_bytes':len(data),'payload_sha256':hashlib.sha256(data).hexdigest(),
            'callback_offset':callback,'native_requests':16,
            'queue_checks':queue_check(raw,data),'callback_checks':inspect_check(raw,data,callback)}
    (args.output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Prepared:',len(data),'bytes; callback offset',callback)
    print('ARM checks:',result['queue_checks']['cases_passed'],'queue +',result['callback_checks']['cases_passed'],'callback')


if __name__=='__main__':main()
