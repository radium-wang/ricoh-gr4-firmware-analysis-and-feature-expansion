#!/usr/bin/env python3
"""Build/check a fixed position-independent XPAN core check. No camera access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from elftools.elf.elffile import ELFFile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'devkit-output/usb-factory-20261001/xpan-core-ram'
ENTRY=''' .syntax unified
.arm
.section .entry,"ax",%progbits
.global gr4_xpan_ram_entry
.type gr4_xpan_ram_entry,%function
gr4_xpan_ram_entry:
 isb sy
 b gr4_xpan_ram_check
.size gr4_xpan_ram_entry, .-gr4_xpan_ram_entry
'''
LAYOUT='''SECTIONS {
 . = 0;
 .text : { *(.entry) *(.text*) }
 .rodata : { *(.rodata*) }
 .data : { *(.data*) *(.got*) }
 .bss : { *(.bss*) *(COMMON) }
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
'''


def extract(path):
    with path.open('rb') as f:
        e=ELFFile(f)
        if e.elfclass!=32 or not e.little_endian or e['e_machine']!='EM_ARM' or e['e_entry']!=0:
            raise ValueError('unexpected linked ARM image')
        chunks=[]
        for s in e.iter_sections():
            if s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size']:
                raise ValueError('unresolved relocation')
            if s['sh_flags'] & 2 and s['sh_size']:
                if s.name not in ('.text','.rodata'):
                    raise ValueError('writable data/GOT or an unexpected load section')
                chunks.append((s['sh_addr'],s.data()))
            if s['sh_type']=='SHT_SYMTAB':
                if any(x.name and x['st_shndx']=='SHN_UNDEF' for x in s.iter_symbols()):
                    raise ValueError('unresolved symbol')
        end=max(a+len(b) for a,b in chunks)
        if not 8<=end<=3072:raise ValueError('fixed core image exceeds owned code window')
        data=bytearray(3072)
        for a,b in chunks:data[a:a+len(b)]=b
        if data[:4]!=bytes.fromhex('6ff07ff5'):raise ValueError('entry must begin with ISB')
        return bytes(data),end


def emulate(data):
    from check_gr4_native_memory_abi import check_host_cache_access
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_MEM_WRITE
    from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11
    registers=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
    cases=[]
    for base in (0x5A0C2000,0x59A12000):
        for args,expected in (([0x5850414E,65,24],0),([0,65,24],0x80000000),([0x5850414E,65,25],0x80000000)):
            machine=Uc(UC_ARCH_ARM,UC_MODE_ARM)
            machine.mem_map(base,0x2000);machine.mem_write(base+64,data)
            machine.mem_map(0x60000000,0x10000)
            sp=0x6000E000;end=0x6000F000
            machine.reg_write(UC_ARM_REG_SP,sp);machine.reg_write(UC_ARM_REG_LR,end)
            for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),args):machine.reg_write(reg,value)
            for index,reg in enumerate(registers):machine.reg_write(reg,0x12340000+index)
            writes=[]
            def write(uc,access,address,size,value,context):
                if not 0x60000000<=address<address+size<=sp:
                    raise AssertionError('core wrote outside its local stack')
                writes.append(address)
            machine.hook_add(UC_HOOK_MEM_WRITE,write)
            machine.emu_start(base+64,end,count=500000,timeout=3000000)
            result=machine.reg_read(UC_ARM_REG_R0)
            if result!=expected or machine.reg_read(UC_ARM_REG_SP)!=sp:raise AssertionError('core result/stack mismatch')
            if any(machine.reg_read(reg)!=0x12340000+i for i,reg in enumerate(registers)):
                raise AssertionError('callee-saved ARM register changed')
            cases.append({'load_address':hex(base+64),'arguments':args,'return':hex(result),
                          'lowest_stack_write':hex(min(writes)) if writes else None,'external_writes':0})
    return {'cases_passed':len(cases),'cases':cases,'camera_accessed':False,
            'actual_linked_ARM_core_executed_in_emulator':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--emulate',action='store_true');args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if not args.emulate:
        clang=shutil.which('clang');linker=shutil.which('ld.lld')
        if not clang or not linker:raise RuntimeError('clang and ld.lld required')
        (OUT/'entry.S').write_text(ENTRY);(OUT/'layout.ld').write_text(LAYOUT)
        flags=['--target=armv7-none-eabi','-march=armv7-a','-marm','-mfpu=none','-mfloat-abi=soft']
        subprocess.run([clang,*flags,'-std=c11','-Oz','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin',
                        '-fno-stack-protector','-fPIC','-fvisibility=hidden','-ffunction-sections','-fdata-sections',
                        '-c',str(ROOT/'firmware/xpan_ram_check.c'),'-o',str(OUT/'core.o')],check=True)
        subprocess.run([clang,*flags,'-c',str(OUT/'entry.S'),'-o',str(OUT/'entry.o')],check=True)
        subprocess.run([linker,'-static','--no-undefined','--gc-sections','--entry=gr4_xpan_ram_entry',
                        '-T',str(OUT/'layout.ld'),str(OUT/'entry.o'),str(OUT/'core.o'),'-o',str(OUT/'core.elf')],check=True)
        data,used=extract(OUT/'core.elf');(OUT/'core.bin').write_bytes(data)
        sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                 (ROOT/'firmware'/name for name in ('xpan_ram_check.c','xpan_core.c','xpan_core.h','xpan_capture.c','xpan_capture.h','xpan_undo.c','xpan_undo.h'))}
        report={'bytes':len(data),'used_bytes':used,'sha256':hashlib.sha256(data).hexdigest(),
                'source_sha256':sources,'entry_offset':0,'entry_arguments':[0x5850414E,65,24],
                'expected_return':0,'unresolved_symbols':0,'relocations':0,'writable_static_data':False,
                'checks':['12 crop/aspect combinations and restoration','five menu indices and invalid index',
                          'XPAN 65:24 photo rectangle','matching preview rectangle',
                          'DNG parameter fields and exact undo in a local buffer'],
                'geometry_alignments_are_examples_not_live_adapter_evidence':True,
                'camera_accessed':False,'xpan_installed':False}
        (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    else:
        data,used=extract(OUT/'core.elf')
        if data!=(OUT/'core.bin').read_bytes():raise ValueError('ELF and payload differ')
        report=emulate(data);(OUT/'arm-checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
