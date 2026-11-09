#!/usr/bin/env python3
"""Execute original raster regeneration stores, then shared XPAN apply/undo.

Runs a bounded original instruction slice with synthetic objects; neither its
complete initializer nor any driver is executed. No camera access or installer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from elftools.elf.elffile import ELFFile
from audit_xpan_paths import EXPECTED_SHA256,file_offset
from check_gr4_preview_coordinates import build,BASE
from check_gr4_native_memory_abi import check_host_cache_access

APPLY='gr4_xpan_preview_recipe_apply'
RESTORE='gr4_xpan_preview_recipe_restore'
REAPPLY='gr4_xpan_preview_recipe_reapply_after_regeneration'


def check(raw,chunks,entries):
    assert hashlib.sha256(raw).hexdigest()==EXPECTED_SHA256
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R7,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x53643000,0x5388A000,0x5388B000,0x5388C000,0x538ED000,0x53FD1000):
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(BASE,0x4000)
    for a,b in chunks:u.mem_write(a,b)
    u.mem_map(0x64000000,0x20000)
    recipe,manager,plan,undo,stack,stop=0x64001000,0x64004000,0x64005000,0x64006000,0x6401E000,0x6401F000
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    pack=lambda v:struct.pack('<%dI'%len(v),*v)
    def half(a):return struct.unpack('<H',u.mem_read(a,2))[0]
    def hook(m,a,n,unused):
        if a==0x538ED930:raise AssertionError('original assertion')
    u.hook_add(UC_HOOK_CODE,hook)
    def regenerate():
        for reg,val in ((UC_ARM_REG_R3,manager),(UC_ARM_REG_R4,recipe),(UC_ARM_REG_R5,0),(UC_ARM_REG_R7,1)):
            u.reg_write(reg,val)
        u.reg_write(UC_ARM_REG_SP,stack)
        u.emu_start(0x53643800,0x536438A0,count=200000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==0x536438A0 and u.reg_read(UC_ARM_REG_SP)==stack
    def run(entry,args,extra=()):
        for reg,val in zip(regs,args):u.reg_write(reg,val)
        u.mem_write(stack,pack(extra or [0,0]));u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
        u.emu_start(entry,stop,count=200000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
        return u.reg_read(UC_ARM_REG_R0)
    cases=[]
    for resolution,source,external in ((7,0,0),(3,2,1)):
        u.mem_write(recipe,b'\xA5'*0xC00);u.mem_write(recipe+0x334,pack([manager]))
        u.mem_write(manager,struct.pack('<II4B',0x53FD19F8,0,0,source,resolution,external))
        for offset in (0xBBE,0xBC4):u.mem_write(recipe+offset,b'\0')
        u.mem_write(recipe+0xBE0,bytes(4));u.mem_write(recipe+0xBF0,pack([8192]))
        u.mem_write(undo,bytes(24))
        u.mem_write(plan,pack([1,6192,4128,6300,4300,54,58,0x3F800000,0,920,6192,2288]))
        regenerate()
        width,height=half(recipe+0xBD6),half(recipe+0xBD8)
        # Existing portable contract requires a matching full base; seed only
        # those earlier initializer fields, not an assertion of actual owner.
        u.mem_write(recipe+0xBEA,struct.pack('<HH',width,height))
        original=bytes(u.mem_read(recipe,0xC00))
        assert run(entries[APPLY],[recipe,0xC00,plan,8192],[2,undo])==1
        cropped=half(recipe+0xBD8);assert cropped<height
        regenerate()
        assert half(recipe+0xBD8)==height and half(recipe+0xBE2)!=0
        # The native slice rewrites H but leaves a prior crop center behind.
        before=bytes(u.mem_read(recipe,0xC00));beforeundo=bytes(u.mem_read(undo,24))
        assert run(entries[APPLY],[recipe,0xC00,plan,8192],[2,undo])==0
        assert bytes(u.mem_read(recipe,0xC00))==before and bytes(u.mem_read(undo,24))==beforeundo
        # Local undo recognizes original H/applied Y only as conflict; complete
        # integration must reconcile this regeneration, not weaken the guard.
        assert run(entries[RESTORE],[recipe,0xC00,undo,0])==0
        assert bytes(u.mem_read(recipe,0xC00))==before
        # New recovery helper accepts the exact observed mixed state while
        # rejecting invalid plan/alignment and unrelated centers unchanged.
        for bad_alignment in (0,3,32):
            assert run(entries[REAPPLY],[recipe,0xC00,plan,8192],[bad_alignment,undo])==0
            assert bytes(u.mem_read(recipe,0xC00))==before and bytes(u.mem_read(undo,24))==beforeundo
        u.mem_write(recipe+0xBE2,struct.pack('<H',half(recipe+0xBE2)+1))
        unknown=bytes(u.mem_read(recipe,0xC00))
        assert run(entries[REAPPLY],[recipe,0xC00,plan,8192],[2,undo])==0
        assert bytes(u.mem_read(recipe,0xC00))==unknown
        u.mem_write(recipe,before)
        assert run(entries[REAPPLY],[recipe,0xC00,plan,8192],[2,undo])==1
        assert half(recipe+0xBD8)==cropped
        assert run(entries[RESTORE],[recipe,0xC00,undo,0])==1
        assert bytes(u.mem_read(recipe,0xC00))==original
        cases.append({'resolution':resolution,'source_mode':source,'external':external,
                      'original_WH':[width,height],'applied_height':cropped,
                      'native_regeneration_overwrites_height':True,
                      'native_regeneration_preserves_stale_XPAN_center':True,
                      'conflicting_reapply_and_undo_refused':True,
                      'exact_mixed_state_reconciliation_and_undo_verified':True,
                      'unknown_center_and_bad_alignments_unchanged':True,
                      'full_recipe_constructor_executed':False})
    return cases


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    chunks,_=build(a.out,('xpan_preview_recipe.c',),APPLY,(RESTORE,REAPPLY))
    with (a.out/'coordinates.elf').open('rb') as f:
        symbols=ELFFile(f).get_section_by_name('.symtab')
        entries={n:symbols.get_symbol_by_name(n)[0]['st_value'] for n in (APPLY,RESTORE,REAPPLY)}
    cases=check(Path('samples/gr4_decoded.bin').read_bytes(),chunks,entries)
    result={'schema':'gr4-preview-regeneration-checks-v1','passed':True,'cases':cases,
            'camera_access':False,'alignment_2_is_model_assumption':True,
            'real_hardware_consumer_verified':False,'xpan_installed':False}
    (a.out/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print('2 original ARM regeneration + candidate apply/undo conflict cases passed')
