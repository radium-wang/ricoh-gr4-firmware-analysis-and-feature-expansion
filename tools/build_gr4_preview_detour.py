#!/usr/bin/env python3
"""Build an offline-only linked preview regeneration detour and undo recipe.

The link address is an emulator fixture, not an available camera allocation.
No camera access, firmware container modification, or executable publication.
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
from audit_sd_shell_path import require_branch
from audit_gr4_preview_consumers import audit
from check_gr4_preview_coordinates import build as build_c,BASE,ROOT

SITE=0x536438A0
ORIGINAL=bytes.fromhex('2c0b09eb083090e5')
DETOUR='gr4_xpan_preview_regeneration_detour'
EXPORTS=('gr4_xpan_preview_recipe_bind','gr4_xpan_preview_recipe_native',
         'gr4_xpan_preview_recipe_apply','gr4_xpan_preview_recipe_restore',
         'gr4_xpan_preview_recipe_regenerated_native')


def build(out):
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();audit(raw)
    if raw[file_offset(SITE):file_offset(SITE)+8]!=ORIGINAL:
        raise ValueError('fixed original detour instructions changed')
    require_branch(raw,SITE,0x53886558)
    if hashlib.sha256(raw[file_offset(0x53886558):file_offset(0x53886558)+120]).hexdigest()!=\
            '95325f67aa5677f332961e60b4435b9e4001a9b542d2bbf7f59739ac6c2cc481':
        raise ValueError('original singleton query changed')
    out.mkdir(parents=True,exist_ok=False)
    build_c(out,('xpan_preview_recipe.c','xpan_preview_recipe_native.c'),EXPORTS[-1],EXPORTS[:-1])
    obj=out/'xpan_preview_regeneration_detour.S.o'
    subprocess.run([shutil.which('clang'),'--target=armv7-none-eabi','-march=armv7-a',
        '-marm','-mfpu=vfpv3','-mfloat-abi=hard','-c',
        str(ROOT/'firmware/xpan_preview_regeneration_detour.S'),'-o',str(obj)],check=True)
    elf=out/'detour.elf'
    subprocess.run([shutil.which('ld.lld'),'-static','--no-undefined','--gc-sections',
        '--entry='+DETOUR,*['--undefined='+n for n in EXPORTS],'-T',str(out/'layout.ld'),
        *[str(x) for x in sorted(out.glob('*.o'))],'-o',str(elf)],check=True)
    chunks=[]
    with elf.open('rb') as handle:
        image=ELFFile(handle);symbols=image.get_section_by_name('.symtab')
        entries={n:symbols.get_symbol_by_name(n)[0]['st_value'] for n in (DETOUR,*EXPORTS)}
        for section in image.iter_sections():
            if section['sh_type'] in ('SHT_REL','SHT_RELA') and section['sh_size']:
                raise ValueError('unresolved relocation')
            if section['sh_flags']&2 and section['sh_size']:
                address=section['sh_addr'];length=section['sh_size']
                if not BASE<=address<address+length<=BASE+0x4000:raise ValueError('unexpected linked section')
                chunks.append((address,bytes(length) if section['sh_type']=='SHT_NOBITS' else section.data()))
    payload=bytearray(max(a+len(b) for a,b in chunks)-BASE)
    for a,b in chunks:payload[a-BASE:a-BASE+len(b)]=b
    (out/'detour.bin').write_bytes(payload)
    replacement=bytes.fromhex('04f01fe5')+struct.pack('<I',entries[DETOUR])
    patch={'schema':'gr4-preview-regeneration-detour-v1','original_sample_sha256':EXPECTED_SHA256,
        'site_address':hex(SITE),'site_sample_offset':file_offset(SITE),'bytes':8,
        'original_hex':ORIGINAL.hex(),'replacement_hex':replacement.hex(),
        'hook_words':[{'address':hex(SITE+offset),
                       'original':hex(struct.unpack_from('<I',ORIGINAL,offset)[0]),
                       'replacement':hex(struct.unpack_from('<I',replacement,offset)[0])}
                      for offset in (0,4)],
        'resume_address':'0x536438a8','original_call_return_address':'0x536438a4',
        'emulator_link_address':hex(BASE),'camera_allocation_verified':False,
        'payload_sha256':hashlib.sha256(payload).hexdigest(),'payload_bytes':len(payload),
        'entries':{n:hex(a) for n,a in entries.items()},
        'undo':{'accept_only_hex':[ORIGINAL.hex(),replacement.hex()],
                'restore_hex':ORIGINAL.hex(),'pause_and_cache_publication_required':True},
        'flashable_firmware':False,'installable_camera_package':False,'xpan_installed':False}
    (out/'patch.json').write_text(json.dumps(patch,indent=2)+'\n')
    return raw,chunks,entries,patch


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    _,_,_,report=build(a.out);print(json.dumps(report,indent=2))
