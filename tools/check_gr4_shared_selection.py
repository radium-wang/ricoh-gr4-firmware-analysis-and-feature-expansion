#!/usr/bin/env python3
"""Linked ARM menu selection -> one plan -> preview/JPEG/DNG consistency.

Original JPEG calculator and recipe helper execute. UI setter and DNG leaf
services are models. No real encoder, LCD, native locks, USB or installer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile
from audit_xpan_paths import EXPECTED_SHA256,file_offset
from check_gr4_native_memory_abi import check_host_cache_access

ROOT=Path(__file__).resolve().parents[1];BASE=0x61000000
NAMES=('gr4_xpan_settings_bind_selection','gr4_xpan_settings_select',
       'gr4_xpan_settings_deactivate',
       'gr4_xpan_selection_prepare','gr4_xpan_selection_commit',
       'gr4_xpan_preview_recipe_bind','gr4_xpan_preview_recipe_native',
       'gr4_xpan_preview_recipe_restore','gr4_xpan_jpeg_native_bind',
       'gr4_xpan_jpeg_native_virtual','gr4_xpan_dng_native_bind',
       'gr4_xpan_dng_native_virtual')


def build(out):
    out.mkdir(parents=True,exist_ok=False)
    sources=('xpan_core.c','xpan_capture.c','xpan_selection.c','xpan_memory.c',
             'xpan_settings_native.c','xpan_preview_recipe.c',
             'xpan_preview_recipe_native.c','xpan_jpeg_native.c','xpan_dng_native.c')
    flags=['--target=armv7-none-eabi','-march=armv7-a','-marm','-mfpu=vfpv3',
           '-mfloat-abi=hard','-std=c11','-Oz','-Wall','-Wextra','-Werror',
           '-ffreestanding','-fno-builtin','-fno-stack-protector','-fPIC',
           '-ffunction-sections','-fdata-sections']
    objects=[]
    for name in sources:
        obj=out/(name+'.o');objects.append(str(obj))
        subprocess.run([shutil.which('clang'),*flags,'-c',str(ROOT/'firmware'/name),'-o',str(obj)],check=True)
    layout=out/'layout.ld'
    layout.write_text('SECTIONS { . = 0x61000000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } .bss : { *(.bss*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n')
    elf=out/'shared-selection.elf'
    subprocess.run([shutil.which('ld.lld'),'-static','--no-undefined','--gc-sections',
        '--entry='+NAMES[0],*['--undefined='+n for n in NAMES],'-T',str(layout),*objects,'-o',str(elf)],check=True)
    chunks=[]
    with elf.open('rb') as f:
        e=ELFFile(f);syms=e.get_section_by_name('.symtab')
        entries={n:syms.get_symbol_by_name(n)[0]['st_value'] for n in NAMES}
        for s in e.iter_sections():
            if s['sh_type'] in ('SHT_REL','SHT_RELA') and s['sh_size']:raise ValueError('unresolved relocation')
            if s['sh_flags']&2 and s['sh_size']:
                if not BASE<=s['sh_addr']<s['sh_addr']+s['sh_size']<=BASE+0x8000:raise ValueError('oversized model payload')
                chunks.append((s['sh_addr'],bytes(s['sh_size']) if s['sh_type']=='SHT_NOBITS' else s.data()))
    data=bytearray(max(a+len(b) for a,b in chunks)-BASE)
    for a,b in chunks:data[a-BASE:a-BASE+len(b)]=b
    (out/'shared-selection.bin').write_bytes(data)
    return chunks,entries


def check(raw,chunks,entries):
    assert hashlib.sha256(raw).hexdigest()==EXPECTED_SHA256;check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_S0,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_FPEXC,UC_ARM_REG_C1_C0_2
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x531D2000,0x531D8000,0x53647000,0x53711000,0x5387E000,0x53886000,
                 0x5388A000,0x5388B000,0x5388C000,0x538CF000,0x538D0000,0x538ED000,
                 0x53FD1000,0x54354000):
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(BASE,0x8000)
    for a,b in chunks:u.mem_write(a,b)
    u.mem_map(0x60000000,0x40000)
    u.reg_write(UC_ARM_REG_C1_C0_2,0xF00000);u.reg_write(UC_ARM_REG_FPEXC,1<<30)
    controller,state,plan,geometry,selection=0x60000100,0x60000400,0x60000500,0x60000600,0x60000700
    recipe,manager,owner,collection,undo,pbinding=0x60001000,0x60004000,0x60010000,0x60008000,0x60005000,0x60004500
    calc,calcvt,jbinding,dobj,dvt,dbinding,cropobj=0x60000800,0x60000840,0x60000900,0x60000A00,0x60000A40,0x60000B00,0x60000C00
    outputs=[0x60000D00+i*4 for i in range(4)];stack,stop=0x6003E000,0x6003F000
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    pack=lambda v:struct.pack('<%dI'%len(v),*v)
    write=lambda a,v:u.mem_write(a,pack(v))
    half=lambda a:struct.unpack('<H',u.mem_read(a,2))[0]
    factors=(0x3F800000,0x3FA04F89,0x3FE23119);sizes=((6192,4128),(4944,3296),(3504,2336))
    setters=[];leaf=[];stop_at=[stop]
    def hook(m,a,n,unused):
        if a==stop_at[0]:m.emu_stop();return
        if a==0x538ED930:raise AssertionError('original assertion')
        if a in (0x531D2F70,0x531D8FFC):
            s=struct.unpack('<3I',m.mem_read(state,12));p=struct.unpack('<12I',m.mem_read(plan,48))
            assert p[0]==int(s[1]==4),'setter observer saw inconsistent state/plan'
            assert m.reg_read(UC_ARM_REG_R1)<4
            if p[0]:assert p[7]==factors[s[0]]
            setters.append({'native_index':m.reg_read(UC_ARM_REG_R1),'state':list(s),'plan_enabled':p[0]})
            m.reg_write(UC_ARM_REG_R0,0);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR));return
        if a in (0x538D05F0,0x538D0764):
            m.reg_write(UC_ARM_REG_R0,cropobj);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR));return
        if a==0x5387E108:
            args=[m.reg_read(r) for r in regs];s=struct.unpack('<3I',m.mem_read(state,12));sw,sh=sizes[s[0]]
            left=28+(6192-sw)//2;top=24+(4128-sh)//2
            for pointer,value in zip(args,(sw,sh,left,top)):m.mem_write(pointer,struct.pack('<H',value))
            leaf.append(a);m.reg_write(UC_ARM_REG_PC,m.reg_read(UC_ARM_REG_LR));return
    u.hook_add(UC_HOOK_CODE,hook)
    def run(name,args,extra=(),factor=0x3F800000,end=stop):
        stop_at[0]=end
        for reg,val in zip(regs,args):u.reg_write(reg,val)
        if extra:u.mem_write(stack,pack(extra))
        u.reg_write(UC_ARM_REG_S0,factor);u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,end)
        entry=entries[name] if isinstance(name,str) else name
        u.emu_start(entry,end,count=300000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==end and u.reg_read(UC_ARM_REG_SP)==stack
        return u.reg_read(UC_ARM_REG_R0)
    def seed(crop):
        sw,sh=sizes[crop];left=28+(6192-sw)//2;top=24+(4128-sh)//2
        write(controller,[0x53DA2C70]);write(controller+0x124,[0x0200008A]);u.mem_write(controller+0x1A4,b'\x22')
        write(state,[crop,2,2]);u.mem_write(plan,b'\xA5'*48)
        write(geometry,[crop,sw,sh,6304,4224,left,top,1,4,2]);write(selection,[state,plan,geometry])
        run('gr4_xpan_settings_bind_selection',[selection])
        write(calc,[calcvt]);write(calcvt+8,[entries['gr4_xpan_jpeg_native_virtual']])
        write(jbinding,[calc,plan,calcvt,1,0,0,1,4,2]);run('gr4_xpan_jpeg_native_bind',[jbinding])
        write(dobj,[dvt]);write(dbinding,[dobj,plan,dvt,1]);run('gr4_xpan_dng_native_bind',[dbinding])
        u.mem_write(recipe,b'\xA5'*0xC00);write(recipe,[0x53EB16E8]);write(recipe+0x334,[manager])
        for off in (0xBBD,0xBBE,0xBC4):u.mem_write(recipe+off,b'\0')
        u.mem_write(manager,struct.pack('<II4B',0x53FD19F8,0,0,0,7,0))
        u.mem_write(owner,bytes(0x9800));write(owner,[0x53EB11F0]);write(owner+0x6C,[2])
        write(owner+0x398,[manager]);write(owner+0x3B0,[collection]);write(owner+0x94,[(8192,10260,14476)[crop]])
        u.mem_write(collection,bytes(48));write(collection+8,[recipe]);u.mem_write(undo,bytes(24))
        write(pbinding,[recipe,manager,owner,plan,undo,1,2,collection]);run('gr4_xpan_preview_recipe_bind',[pbinding])
        # All three linked native adapters point at this exact stable plan.
        assert struct.unpack('<I',u.mem_read(pbinding+12,4))[0]==plan
        assert struct.unpack('<I',u.mem_read(jbinding+4,4))[0]==plan
        assert struct.unpack('<I',u.mem_read(dbinding+4,4))[0]==plan
    cases=[]
    for crop in range(3):
        for confirm in (0,1):
            seed(crop);setters.clear();factor=factors[crop]
            assert run('gr4_xpan_settings_select',[controller,state,4,confirm])==1
            assert setters==[{'native_index':0,'state':[crop,4,2],'plan_enabled':1}]
            p=struct.unpack('<12I',u.mem_read(plan,48));sw,sh=sizes[crop]
            assert p[10:12]==(sw,(2288,1824,1292)[crop])
            run('gr4_xpan_preview_recipe_native',[recipe,0,0,0],[(8192,10260,14476)[crop]])
            preview=[half(recipe+0xBD6),half(recipe+0xBD8),half(recipe+0xBE2)]
            assert preview[0]==720 and 0<preview[1]<480
            for pointer in outputs:u.mem_write(pointer,b'\xAA\xAA\x77\x88')
            run('gr4_xpan_jpeg_native_virtual',[calc,0,0,outputs[0]],[outputs[1]],factor,0x53711460)
            jpeg=[half(outputs[0]),half(outputs[1])];assert jpeg==[p[10],p[11]]
            leaf.clear();run('gr4_xpan_dng_native_virtual',[dobj,*outputs[:3]],[outputs[3],0,0],factor)
            dng=[half(x) for x in outputs];assert dng==[p[10],p[11],p[5],p[6]+p[9]] and len(leaf)==1
            assert all(bytes(u.mem_read(x+2,2))==b'\x77\x88' for x in outputs)
            assert run('gr4_xpan_preview_recipe_restore',[recipe,0xC00,undo])==1
            cases.append({'case':'fifth-selection-publishes-one-plan-before-native-setter',
                'crop':crop,'confirm':confirm,'JPEG':jpeg,'DNG':dng,'preview_raster_HY':preview[1:],
                'plan_address_shared_by_all_three_adapters':True,'preview_local_undo_verified':True})
            setters.clear();assert run('gr4_xpan_settings_deactivate',[controller,state,confirm])==1
            assert setters==[{'native_index':3,'state':[crop,2,2],'plan_enabled':0}]
            assert bytes(u.mem_read(plan,48))==bytes(48)
            cases.append({'case':'deactivate-restores-prior-regular-property-and-clears-plan-before-observers',
                          'crop':crop,'confirm':confirm,'prior_menu_index':3})
            for index,aspect in enumerate((0,1,3,2)):
                setters.clear();assert run('gr4_xpan_settings_select',[controller,state,index,confirm])==1
                assert setters[-1]['native_index']==index and setters[-1]['state']==[crop,aspect,aspect]
                assert bytes(u.mem_read(plan,48))==bytes(48)
                run('gr4_xpan_jpeg_native_virtual',[calc,0,0,outputs[0]],[outputs[1]],factor,0x53711460)
                assert [half(outputs[0]),half(outputs[1])]==[sw,sh]
                run('gr4_xpan_dng_native_virtual',[dobj,*outputs[:3]],[outputs[3],0,0],factor)
                assert [half(outputs[0]),half(outputs[1])]==[sw,sh]
                cases.append({'case':'regular-menu-entry-disables-shared-plan-and-delegates',
                              'crop':crop,'confirm':confirm,'index':index})
    for crop in range(3):
        for prior_aspect in range(4):
            seed(crop);write(state,[crop,prior_aspect,prior_aspect]);setters.clear()
            assert run('gr4_xpan_settings_select',[controller,state,4,0])==1
            run('gr4_xpan_preview_recipe_native',[recipe,0,0,0],[(8192,10260,14476)[crop]])
            assert run('gr4_xpan_preview_recipe_restore',[recipe,0xC00,undo])==1
            # A stale geometry should not prevent returning to a regular
            # native option; restoring a disabled plan needs no new crop math.
            write(geometry,[3]);setters.clear()
            assert run('gr4_xpan_settings_deactivate',[controller,state,0])==1
            index=(0,1,3,2)[prior_aspect]
            assert setters==[{'native_index':index,'state':[crop,prior_aspect,prior_aspect],'plan_enabled':0}]
            assert bytes(u.mem_read(plan,48))==bytes(48)
            cases.append({'case':'all-prior-regular-aspects-restored-even-with-stale-geometry',
                          'crop':crop,'prior_aspect':prior_aspect,'native_menu_index':index})
    for fault in ('crop_geometry_mismatch','bad_alignment','invalid_source','wrong_state_binding','invalid_index'):
        seed(0);setters.clear();before=bytes(u.mem_read(state,12));oldplan=bytes(u.mem_read(plan,48));index=4
        if fault=='crop_geometry_mismatch':write(geometry,[1])
        if fault=='bad_alignment':write(geometry+32,[3])
        if fault=='invalid_source':write(geometry+4,[0])
        if fault=='wrong_state_binding':write(selection,[state+16])
        if fault=='invalid_index':index=5
        assert run('gr4_xpan_settings_select',[controller,state,index,0])==0
        assert not setters and bytes(u.mem_read(state,12))==before and bytes(u.mem_read(plan,48))==oldplan
        cases.append({'case':'invalid-selection-preserves-state-plan-and-native-property','fault':fault})
    run('gr4_xpan_settings_bind_selection',[0]);run('gr4_xpan_preview_recipe_bind',[0])
    run('gr4_xpan_jpeg_native_bind',[0]);run('gr4_xpan_dng_native_bind',[0])
    return cases


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    chunks,entries=build(a.out);cases=check((ROOT/'samples/gr4_decoded.bin').read_bytes(),chunks,entries)
    result={'schema':'gr4-shared-selection-ARM-v1','passed':True,'cases':cases,'cases_passed':len(cases),
        'unresolved_ARM_symbols':0,'original_JPEG_calculator_and_recipe_ARM_executed':True,
        'UI_setter_and_DNG_leaf_modelled':True,'native_state_lock_and_reader_drain_modelled':True,
        'alignment_is_model_assumption':True,'camera_access':False,'encoded_images_verified':False,
        'LCD_AF_pixels_verified':False,'xpan_installed':False}
    (a.out/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print('%d linked menu/shared-plan/preview/JPEG/DNG cases passed'%len(cases))
