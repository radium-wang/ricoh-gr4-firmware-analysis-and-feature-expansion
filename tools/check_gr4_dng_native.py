#!/usr/bin/env python3
"""Compile and execute the hard-float Kb636 virtual adapter with original ARM.

Synthetic capture objects; original leaf dimensions simulated. No camera,
installer, image worker lock, RAW encoding or actual DNG output verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile
from audit_xpan_paths import file_offset,EXPECTED_SHA256
from check_gr4_native_memory_abi import check_host_cache_access

ROOT=Path(__file__).resolve().parents[1]
BASE=0x61000000


def build(out):
    out.mkdir(parents=True)
    flags=['--target=armv7-none-eabi','-march=armv7-a','-marm','-mfpu=vfpv3',
           '-mfloat-abi=hard','-std=c11','-Oz','-Wall','-Wextra','-Werror',
           '-ffreestanding','-fno-builtin','-fno-stack-protector','-fPIC',
           '-fvisibility=hidden','-ffunction-sections','-fdata-sections']
    objects=[]
    for source in ('xpan_dng_native.c','xpan_capture.c'):
        obj=out/(source+'.o');objects.append(str(obj))
        subprocess.run([shutil.which('clang'),*flags,'-c',str(ROOT/'firmware'/source),'-o',str(obj)],check=True)
    layout=out/'layout.ld'
    layout.write_text('SECTIONS { . = 0x61000000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } .bss : { *(.bss*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n')
    names=['gr4_xpan_dng_native_bind','gr4_xpan_dng_native_virtual'];elf=out/'dng.elf'
    subprocess.run([shutil.which('ld.lld'),'-static','--no-undefined','--gc-sections','--entry='+names[0],
        *['--undefined='+name for name in names],'-T',str(layout),*objects,'-o',str(elf)],check=True)
    chunks=[]
    with elf.open('rb') as handle:
        e=ELFFile(handle)
        for s in e.iter_sections():
            if s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size']:raise ValueError('relocation remains')
            if s['sh_flags']&2 and s['sh_size']:
                assert BASE<=s['sh_addr']<BASE+4096
                chunks.append((s['sh_addr'],bytes(s['sh_size']) if s['sh_type']=='SHT_NOBITS' else s.data()))
        symbols=e.get_section_by_name('.symtab');entries={n:symbols.get_symbol_by_name(n)[0]['st_value'] for n in names}
    return chunks,entries


def check(raw,chunks,entries):
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
        UC_ARM_REG_S0,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_FPEXC,UC_ARM_REG_C1_C0_2)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x5387E000,0x538D0000,0x538ED000,0x54354000):
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(BASE,4096)
    for address,data in chunks:u.mem_write(address,data)
    u.mem_map(0x60000000,0x10000)
    u.reg_write(UC_ARM_REG_C1_C0_2,0xF00000);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    obj=0x60000100;clone=0x60000200;binding=0x60000300;plan=0x60000400
    outputs=[0x60000600+i*4 for i in range(4)];stack=0x6000E000;stop=0x6000F000;calls=[]
    def hook(machine,address,size,unused):
        if address==0x538ED930:raise AssertionError('unsupported original flag assert')
        if address in (0x538D05F0,0x538D0764,0x60004000):
            if address==0x60004000:machine.reg_write(UC_ARM_REG_S0,0x3F800000)
            else:machine.reg_write(UC_ARM_REG_R0,0x60001300)
            machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR));return
        if address!=0x5387E108:return
        args=[machine.reg_read(r) for r in regs];sp=machine.reg_read(UC_ARM_REG_SP)
        aspect=struct.unpack('<I',machine.mem_read(sp,4))[0];crop=machine.reg_read(UC_ARM_REG_S0)
        calls.append({'pointers':args,'crop_bits':crop,'aspect':aspect})
        for pointer,value in zip(args,(6192,4128,54,58)):machine.mem_write(pointer,struct.pack('<H',value))
        machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook)
    def run(entry,args,extra=(),crop=0x3F800000):
        for register,value in zip(regs,args):u.reg_write(register,value)
        u.reg_write(UC_ARM_REG_S0,crop);u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
        if extra:u.mem_write(stack,struct.pack('<%dI'%len(extra),*extra))
        u.emu_start(entry,stop,count=30000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
    u.mem_write(obj,struct.pack('<I',clone));u.mem_write(binding,struct.pack('<4I',obj,plan,clone,1))
    # 6192 x 2288 preserves even Bayer centre (offset 920); alignment remains
    # caller-supplied integration evidence, not claimed by this synthetic plan.
    original_plan=struct.pack('<12I',1,6192,4128,6300,4300,54,58,0x3F800000,0,920,6192,2288)
    cases=[]
    for fault in ('normal','disabled','unbound','other object','other vtable','other crop','other aspect','invalid plan'):
        u.mem_write(plan,original_plan);u.mem_write(binding,struct.pack('<4I',obj,plan,clone,1))
        u.mem_write(obj,struct.pack('<I',clone));self=obj;crop=0x3F800000;aspect=0
        if fault=='disabled':u.mem_write(binding+12,bytes(4))
        if fault=='other object':self=obj+16;u.mem_write(self,struct.pack('<I',clone))
        if fault=='other vtable':u.mem_write(obj,struct.pack('<I',0x53FCF430))
        if fault=='other crop':crop=0x3FA04F89
        if fault=='other aspect':aspect=1
        if fault=='invalid plan':u.mem_write(plan,bytes(4))
        run(entries['gr4_xpan_dng_native_bind'],[0 if fault=='unbound' else binding,0,0,0])
        calls.clear()
        for pointer in outputs:u.mem_write(pointer,b'\xAA\xAA\x77\x88')
        run(entries['gr4_xpan_dng_native_virtual'],[self,*outputs[:3]],[outputs[3],aspect,0],crop)
        actual=[struct.unpack('<H',u.mem_read(p,2))[0] for p in outputs]
        assert actual==([6192,2288,54,978] if fault=='normal' else [6192,4128,54,58])
        assert len(calls)==1 and calls[0]=={'pointers':outputs,'crop_bits':crop,'aspect':aspect}
        assert all(u.mem_read(p+2,2)==b'\x77\x88' for p in outputs)
        cases.append({'case':fault,'hard_float_and_stack_arguments_preserved':True,'fields':actual})
    # Execute the entire original parameter writer. Replacing +0x34 causes
    # its real equality guard/alternate branch to call the project virtual ABI.
    # The full-source fields must retain the original values while only the
    # current four crop-window fields change. Factory/crop lookup is simulated.
    params=0x60001000;metadata=0x60001100;rawdims=0x60001200;cropobj=0x60001300
    cropvt=0x60001400;full=0x60001500;block=0x60001600
    u.mem_write(plan,original_plan);u.mem_write(binding,struct.pack('<4I',obj,plan,clone,1))
    u.mem_write(obj,struct.pack('<I',clone));u.mem_write(clone+0x34,struct.pack('<I',entries['gr4_xpan_dng_native_virtual']))
    u.mem_write(params+0xE8,struct.pack('<I',block));u.mem_write(params+0xF0,struct.pack('<I',metadata))
    u.mem_write(metadata+0xC0,struct.pack('<I',rawdims));u.mem_write(rawdims,struct.pack('<2H',6192,4128))
    u.mem_write(params+0x100,struct.pack('<I',full));u.mem_write(full+0x20,struct.pack('<2H',6300,4300))
    u.mem_write(params+0x116,struct.pack('<2H',22,26))
    u.mem_write(cropobj,struct.pack('<I',cropvt));u.mem_write(cropvt+0x34,struct.pack('<I',0x60004000))
    run(entries['gr4_xpan_dng_native_bind'],[binding,0,0,0]);calls.clear()
    run(0x5387E2AC,[obj,params,0,0])
    fields=struct.unpack('<16H',u.mem_read(block,32))
    assert fields[0:2]==(6300,4300) and fields[8:12]==(54,58,6192,4128)
    assert fields[12:16]==(6192,2288,54,978) and len(calls)==1
    cases.append({'case':'original writer alternate virtual branch preserves full source',
                  'full_raw_fields':list(fields[0:2]),'source_origin_and_dimensions':list(fields[8:12]),
                  'current_window':list(fields[12:16])})
    return {'cases_passed':len(cases),'cases':cases,'linked_hard_float_adapter_ARM_executed':True,
            'original_virtual_wrapper_ARM_executed':True,'original_dimension_leaf_simulated':True,
            'original_parameter_writer_alternate_virtual_branch_ARM_executed':True,
            'installer_capture_plan_production_worker_quiescence_and_RAW_output_pending':True,
            'camera_accessed':False,'xpan_installed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('immutable output exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();assert hashlib.sha256(raw).hexdigest()==EXPECTED_SHA256
    chunks,entries=build(a.output);result=check(raw,chunks,entries)
    result.update(schema='gr4-dng-native-virtual-check-v1',sample_sha256=EXPECTED_SHA256,entries=entries,
                  build_is_fixed_emulator_address_not_installable=True)
    (a.output/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Hard-float DNG virtual checks passed:',result['cases_passed'])
