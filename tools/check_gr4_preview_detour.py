#!/usr/bin/env python3
"""Execute patched original ARM site, detour and local undo offline."""
import argparse
import json
from pathlib import Path
import struct
from build_gr4_preview_detour import build,SITE,ORIGINAL,BASE,DETOUR
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access


def check(raw,chunks,entries,patch):
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
        UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,
        UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,
        UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_CPSR)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x53643000,0x53647000,0x53886000,0x5388A000,0x5388B000,0x5388C000,0x538ED000,0x53FD1000):
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(0x55397000,4096);u.mem_write(0x55397544,struct.pack('<I',1))
    u.mem_write(0x55397538,struct.pack('<I',0x12345678))
    u.mem_map(BASE,0x4000)
    for a,b in chunks:u.mem_write(a,b)
    u.mem_map(0x64000000,0x30000)
    recipe,manager,binding,plan,undo,owner,collection=0x64001000,0x64004000,0x64004500,0x64004600,0x64005000,0x64010000,0x64008000
    stack,stop=0x6402E000,0x6402F000
    registers=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
               UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
               UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
    pack=lambda values:struct.pack('<%dI'%len(values),*values)
    write=lambda a,v:u.mem_write(a,pack(v))
    half=lambda a:struct.unpack('<H',u.mem_read(a,2))[0]
    queries=[];adapters=[]
    def hook(m,a,n,unused):
        if a==0x538ED930:raise AssertionError('original assertion')
        if a==0x53886558:queries.append(a)
        if a==entries['gr4_xpan_preview_recipe_regenerated_native']:
            assert m.reg_read(UC_ARM_REG_SP)%8==0
            assert m.reg_read(UC_ARM_REG_R0)==recipe;adapters.append(a)
    u.hook_add(UC_HOOK_CODE,hook)
    def call(name,args,extra=()):
        for reg,val in zip(registers,args):u.reg_write(reg,val)
        if extra:u.mem_write(stack,pack(extra))
        u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
        u.emu_start(entries[name],stop,count=200000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
        return u.reg_read(UC_ARM_REG_R0)
    def seed():
        u.mem_write(recipe,b'\xA5'*0xC00);write(recipe,[0x53EB16E8]);write(recipe+0x334,[manager])
        for off in (0xBBD,0xBBE,0xBC4):u.mem_write(recipe+off,b'\0')
        u.mem_write(manager,struct.pack('<II4B',0x53FD19F8,0,0,0,7,0))
        u.mem_write(owner,bytes(0x9800));write(owner,[0x53EB11F0]);write(owner+0x6C,[2])
        write(owner+0x398,[manager]);write(owner+0x3B0,[collection]);write(owner+0x94,[8192])
        u.mem_write(collection,bytes(48));write(collection+8,[recipe]);u.mem_write(undo,bytes(24))
        write(plan,[1,6192,4128,6300,4300,54,58,0x3F800000,0,920,6192,2288])
        write(binding,[recipe,manager,owner,plan,undo,1,2,collection])
        call('gr4_xpan_preview_recipe_bind',[binding])
        call('gr4_xpan_preview_recipe_native',[recipe,0,0,0],[8192])
        assert half(recipe+0xBD8)==266
    def slice(patched):
        u.mem_write(SITE,bytes.fromhex(patch['replacement_hex']) if patched else ORIGINAL)
        # Unicorn translation blocks need explicit invalidation when replacing
        # executable instructions. This is emulator maintenance, not a camera
        # cache-publication implementation.
        u.ctl_remove_cache(SITE,SITE+8)
        for reg,val in zip(registers,(0,11,13,manager,recipe,0,0xA6A6,1,0xA8A8,0xA9A9,0xAAAA,0xABAB)):
            u.reg_write(reg,val)
        u.reg_write(UC_ARM_REG_R12,0xACAC);u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,0x53643898)
        queries.clear();adapters.clear()
        u.emu_start(0x53643800,SITE+8,count=200000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==SITE+8 and u.reg_read(UC_ARM_REG_SP)==stack
        assert queries==[0x53886558] and len(adapters)==int(patched)
        assert u.reg_read(UC_ARM_REG_R0)==0x55397530 and u.reg_read(UC_ARM_REG_R3)==0x12345678
        assert u.reg_read(UC_ARM_REG_LR)==SITE+4
        return [u.reg_read(r) for r in registers]+[u.reg_read(UC_ARM_REG_CPSR)&0xF8000000]
    cases=[]
    for fault in (None,'unbound','not_ready','inactive_poisoned_process','wrong_owner','wrong_member','unknown_center','bad_alignment','manager_source_2'):
        seed()
        if fault=='unbound':call('gr4_xpan_preview_recipe_bind',[0])
        if fault=='not_ready':write(binding+20,[0])
        if fault=='inactive_poisoned_process':
            write(binding+20,[0]);write(binding+8,[1])
        if fault=='wrong_owner':write(owner,[0])
        if fault=='wrong_member':write(collection+8,[recipe+4])
        if fault=='unknown_center':u.mem_write(recipe+0xBE2,struct.pack('<H',109))
        if fault=='bad_alignment':write(binding+24,[3])
        if fault=='manager_source_2':u.mem_write(manager+9,b'\2')
        initial=bytes(u.mem_read(recipe,0xC00));savedundo=bytes(u.mem_read(undo,24))
        baseline=slice(False);native=bytes(u.mem_read(recipe,0xC00))
        u.mem_write(recipe,initial);u.mem_write(undo,savedundo)
        actual=slice(True);after=bytes(u.mem_read(recipe,0xC00))
        assert actual==baseline,'original live return/callee registers or condition flags changed'
        if fault:
            assert after==native and bytes(u.mem_read(undo,24))==savedundo
        else:
            expected=bytearray(native);struct.pack_into('<H',expected,0xBD8,266)
            assert after==expected and half(recipe+0xBE2)==107
            assert call('gr4_xpan_preview_recipe_restore',[recipe,0xC00,undo])==1
            assert half(recipe+0xBD8)==480 and half(recipe+0xBE2)==0
        # Independent offline instruction removal accepts only exact candidate.
        assert bytes(u.mem_read(SITE,8))==bytes.fromhex(patch['replacement_hex'])
        u.mem_write(SITE,ORIGINAL);u.ctl_remove_cache(SITE,SITE+8)
        assert bytes(u.mem_read(SITE,8))==ORIGINAL
        cases.append({'case':fault or 'patched_original_regeneration_and_local_undo',
                      'original_query_called_once':True,'live_return_and_callee_registers_preserved':True,
                      'condition_flags_preserved':True,'instruction_patch_removed':True})
    return cases


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    raw,chunks,entries,report=build(a.out);cases=check(raw,chunks,entries,report)
    from check_gr4_detour_transaction import check as transaction_check
    transaction=transaction_check(a.out,report)
    result={'schema':'gr4-preview-detour-ARM-v1','passed':True,'cases':cases,
            'unresolved_ARM_symbols':0,'original_singleton_already_initialized_fixture':True,
            'owner_pause_is_model_contract':True,'hardware_cache_publication_verified':False,
            'camera_access':False,'xpan_installed':False}
    result['exact_site_host_transaction_cases']=len(transaction['cases'])
    (a.out/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print('%d patched-original-site ARM and instruction-undo cases passed'%len(cases))
