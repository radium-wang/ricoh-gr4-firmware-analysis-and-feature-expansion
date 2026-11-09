#!/usr/bin/env python3
"""Original raster recipe helper plus candidate native ABI and local undo.

Synthetic owner/manager; alignment 2 is a test assumption, not a device gate.
No driver execution, pixel buffer, installer, USB or SD access.
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

NAMES=('gr4_xpan_preview_recipe_native','gr4_xpan_preview_recipe_bind',
       'gr4_xpan_preview_recipe_restore')


def check(raw,chunks,entries):
    assert hashlib.sha256(raw).hexdigest()==EXPECTED_SHA256
    assert hashlib.sha256(raw[file_offset(0x53647498):file_offset(0x53647498)+376]).hexdigest()==\
        '5318bdd584a2ae3f558326adb30057bea587af160f9e9af4b6dd560b1a1bf5d0'
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
        UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x53647000,0x5388A000,0x5388B000,0x5388C000,0x538ED000,0x53FD1000):
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(BASE,0x4000)
    for a,b in chunks:u.mem_write(a,b)
    u.mem_map(0x64000000,0x30000)
    recipe,manager,binding,plan,undo=0x64001000,0x64004000,0x64004500,0x64004600,0x64005000
    owner,stack,stop=0x64010000,0x6402E000,0x6402F000
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    calls=[]
    def hook(m,a,n,unused):
        if a==0x538ED930:raise AssertionError('native assertion')
        if a==0x53647498:
            calls.append({'args':[m.reg_read(r) for r in regs],
                          'factor':struct.unpack('<I',m.mem_read(m.reg_read(UC_ARM_REG_SP),4))[0]})
    u.hook_add(UC_HOOK_CODE,hook)
    pack=lambda v:struct.pack('<%dI'%len(v),*v)
    def write(a,v):u.mem_write(a,pack(v))
    def word(a):return struct.unpack('<I',u.mem_read(a,4))[0]
    def half(a):return struct.unpack('<H',u.mem_read(a,2))[0]
    def run(entry,args,extra=()):
        calls.clear()
        for r,v in zip(regs,args):u.reg_write(r,v)
        u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
        if extra:write(stack,extra)
        try:u.emu_start(entry,stop,count=200000,timeout=2000000)
        except Exception as e:raise RuntimeError('entry=%08x PC=%08x'%(entry,u.reg_read(UC_ARM_REG_PC))) from e
        assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
        return u.reg_read(UC_ARM_REG_R0)
    def seed(resolution=7,factor=8192):
        u.mem_write(recipe,b'\xA5'*0xC00);write(recipe,[0x53EB16E8]);write(recipe+0x334,[manager])
        for offset in (0xBBD,0xBBE,0xBC4):u.mem_write(recipe+offset,b'\0')
        u.mem_write(manager,struct.pack('<II4B',0x53FD19F8,0,0,0,resolution,0))
        u.mem_write(owner,bytes(0x9800));write(owner,[0x53EB11F0])
        write(owner+0x3B0,[0x64008000]);write(owner+0x398,[manager]);write(owner+0x94,[factor])
        u.mem_write(0x64008000,bytes(0x40));write(0x64008008,[recipe])
        write(owner+0x6C,[2]);u.mem_write(undo,bytes(24))
        write(binding,[recipe,manager,owner,plan,undo,1,2,0x64008000])
        run(entries[NAMES[1]],[binding,0,0,0])
    def native_reference(aspect=0,extra=0,mode=0,factor=8192):
        run(0x53647498,[recipe,aspect,extra,mode],[factor])
        return bytes(u.mem_read(recipe,0xC00))
    cases=[]
    for resolution in (7,29,30):
      for aspect in range(4):
        seed(resolution)
        native=native_reference(aspect)
        expected={7:[(720,480),(720,404),(640,480),(480,480)],
                  29:[(1080,720),(1080,608),(960,720),(720,720)],
                  30:[(720,480),(720,404),(640,480),(480,480)]}[resolution][aspect]
        active=[half(recipe+0xBD6),half(recipe+0xBD8)]
        assert active==list(expected),(resolution,aspect,active)
        assert half(recipe+0xBE4)==expected[0] or aspect!=0
        # Height/top reference is original even for square/16:9; no XPAN active.
        cases.append({'case':'original-recipe-%d-aspect-%d'%(resolution,aspect),
                      'active_raster':active,'center':[half(recipe+0xBE0),half(recipe+0xBE2)]})
    dimensions=[(6192,4128,2288,0x3F800000,8192),(4944,3296,1824,0x3FA04F89,10260),
                (3504,2336,1292,0x3FE23119,14476)]
    for resolution in (7,29,30):
      for sw,sh,ph,bits,factor in dimensions:
        seed(resolution,factor)
        p=[1,sw,sh,6300,4300,54,58,bits,0,(sh-ph)//2,sw,ph];write(plan,p)
        original=native_reference(factor=factor)
        run(entries[NAMES[0]],[recipe,0,0,0],[factor])
        assert calls==[{'args':[recipe,0,0,0],'factor':factor}]
        actual=bytes(u.mem_read(recipe,0xC00));w=struct.unpack_from('<H',original,0xBD6)[0]
        h=struct.unpack_from('<H',original,0xBD8)[0]
        pixel_h=((p[9]+ph)*h//sh-p[9]*h//sh)&~1
        expected=bytearray(original);struct.pack_into('<H',expected,0xBD8,pixel_h)
        struct.pack_into('<H',expected,0xBE2,(h-pixel_h)//2)
        assert actual==expected and word(undo+4)==1
        # Native regeneration, repeat apply and local undo on the SAME record.
        run(entries[NAMES[0]],[recipe,0,0,0],[factor])
        assert bytes(u.mem_read(recipe,0xC00))==expected
        assert run(entries[NAMES[2]],[recipe,0xC00,undo,0])==1
        assert bytes(u.mem_read(recipe,0xC00))==original and word(undo+4)==0
        assert run(entries[NAMES[2]],[recipe,0xC00,undo,0])==1
        cases.append({'case':'native-XPAN-%d-source-%d-and-undo'%(resolution,sw),
                      'active_raster':[w,pixel_h],'center_y':(h-pixel_h)//2,
                      'full_buffers_unchanged':True,'local_undo_verified':True})
    for fault in ('unbound','not-ready','disabled-plan','wrong-factor','regular-aspect',
                  'wrong-manager-binding','wrong-owner-class','wrong-owner-collection','wrong-recipe-class',
                  'wrong-collection-member',
                  'special-flag','special-window','movie-mode','extra','wrong-alignment',
                  'input-movie-flag','short-record-state','manager-special-mode',
                  'manager-external-display','unsupported-resolution'):
        seed();write(plan,[1,6192,4128,6300,4300,54,58,0x3F800000,0,920,6192,2288])
        aspect=extra=mode=0;factor=8192
        if fault=='unbound':run(entries[NAMES[1]],[0,0,0,0])
        if fault=='not-ready':write(binding+20,[0])
        if fault=='disabled-plan':write(plan,[0])
        if fault=='wrong-factor':write(owner+0x94,[10260])
        if fault=='regular-aspect':aspect=1
        if fault=='wrong-manager-binding':write(binding+4,[manager+4])
        if fault=='wrong-owner-class':write(owner,[0])
        if fault=='wrong-owner-collection':write(owner+0x3B0,[0])
        if fault=='wrong-recipe-class':write(recipe,[0])
        if fault=='wrong-collection-member':write(0x64008008,[recipe+4])
        if fault=='special-flag':write(owner+0x6C,[1])
        if fault=='special-window':u.mem_write(owner+0x97A4,b'\1')
        if fault=='movie-mode':mode=1
        if fault=='extra':extra=2
        if fault=='wrong-alignment':write(binding+24,[3])
        if fault=='input-movie-flag':u.mem_write(recipe+0xBC4,b'\1')
        if fault=='short-record-state':write(undo+4,[2])
        if fault=='manager-special-mode':u.mem_write(manager+9,b'\3')
        if fault=='manager-external-display':u.mem_write(manager+11,b'\1')
        if fault=='unsupported-resolution':u.mem_write(manager+10,b'\x08')
        original=native_reference(aspect,extra,mode,factor);before=bytes(u.mem_read(undo,24))
        run(entries[NAMES[0]],[recipe,aspect,extra,mode],[factor])
        assert bytes(u.mem_read(recipe,0xC00))==original and bytes(u.mem_read(undo,24))==before
        assert calls==[{'args':[recipe,aspect,extra,mode],'factor':factor}]
        cases.append({'case':fault,'native_arguments_and_recipe_preserved':True})
    for fault,offset,value in [('unknown-center',0xBE2,b'\x33\0'),
                               ('new-reference-height',0xBE6,b'\x10\1'),
                               ('new-buffer-width',0xBEA,b'\x10\3'),
                               ('new-crop-factor',0xBF0,struct.pack('<I',10260))]:
        seed();write(plan,[1,6192,4128,6300,4300,54,58,0x3F800000,0,920,6192,2288])
        run(entries[NAMES[0]],[recipe,0,0,0],[8192]);u.mem_write(recipe+offset,value)
        before=bytes(u.mem_read(recipe,0xC00));record=bytes(u.mem_read(undo,24))
        assert run(entries[NAMES[2]],[recipe,0xC00,undo,0])==0
        assert bytes(u.mem_read(recipe,0xC00))==before and bytes(u.mem_read(undo,24))==record
        cases.append({'case':'undo-rejects-'+fault,'no_overwrite':True})
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    try:
        raw=Path('samples/gr4_decoded.bin').read_bytes()
        chunks,entry=build(a.out,('xpan_preview_recipe.c','xpan_preview_recipe_native.c'),NAMES[0],NAMES[1:])
        with (a.out/'coordinates.elf').open('rb') as f:
            symbols=ELFFile(f).get_section_by_name('.symtab')
            entries={n:symbols.get_symbol_by_name(n)[0]['st_value'] for n in NAMES}
        cases=check(raw,chunks,entries)
        report={'passed':True,'sample_sha256':EXPECTED_SHA256,'cases':cases,
                'original_recipe_and_raster_ARM_executed':True,'unresolved_ARM_symbols':0,
                'camera_access':False,'alignment_2_is_model_only':True,
                'real_LCD_AF_pixels_or_undo_verified':False,'xpan_installed':False,'PREVIEW_READY':False}
        (a.out/'checks.json').write_text(json.dumps(report,indent=2)+'\n')
        print('%d original-recipe/native-adapter/undo ARM cases passed'%len(cases))
    except Exception as e:
        (a.out/'failure.json').write_text(json.dumps({'passed':False,'error':repr(e),'camera_access':False},indent=2)+'\n')
        raise


if __name__=='__main__':main()
