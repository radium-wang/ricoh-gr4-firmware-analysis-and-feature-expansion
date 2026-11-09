#!/usr/bin/env python3
"""Build pinned UI entry detours for offline emulation only; no camera access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from audit_xpan_paths import EXPECTED_SHA256,file_offset
from check_gr4_settings_backend import build as build_backend,ROOT,BASE

SITES=(
    ('refresh',0x531DA9D4,'0dc0a0e1bc3904e3'),
    ('activate',0x531DAD8C,'0dc0a0e118d82de9'),
    ('event',0x531DACAC,'b030d1e10dc0a0e1'),
    ('list_confirm',0x531D7120,'a421d0e50dc0a0e1'),
    ('button',0x531D6B50,'0dc0a0e118d82de9'))
EXPORTS=tuple('gr4_xpan_settings_'+n+'_hook' for n,a,b in SITES)+(
    'gr4_xpan_settings_hooks_bind','gr4_xpan_settings_hooks_withdraw',
    'gr4_xpan_settings_bind_selection')+tuple(
    'gr4_xpan_settings_'+n+'_original' for n,a,b in SITES)

def build(out):
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256:raise ValueError('sample changed')
    for name,address,original in SITES:
        if raw[file_offset(address):file_offset(address)+8].hex()!=original:
            raise ValueError('original prologue changed: '+name)
    out.mkdir(parents=True,exist_ok=False)
    obj=out/'xpan_settings_trampolines.S.o'
    subprocess.run([shutil.which('clang'),'--target=armv7-none-eabi','-march=armv7-a',
        '-marm','-mfpu=none','-mfloat-abi=soft','-c',
        str(ROOT/'firmware/xpan_settings_trampolines.S'),'-o',str(obj)],check=True)
    data,offsets=build_backend(out,('xpan_settings_routes.c','xpan_settings_hooks.c'),EXPORTS,(obj,))
    sites=[];words=[]
    for name,address,original in SITES:
        destination=BASE+offsets['gr4_xpan_settings_'+name+'_hook']
        replacement=bytes.fromhex('04f01fe5')+struct.pack('<I',destination)
        sites.append(dict(name=name,address=hex(address),original_hex=original,
                          replacement_hex=replacement.hex(),resume_address=hex(address+8)))
        for offset in (0,4):
            words.append(dict(address=hex(address+offset),
                original=hex(struct.unpack_from('<I',bytes.fromhex(original),offset)[0]),
                replacement=hex(struct.unpack_from('<I',replacement,offset)[0])))
    report=dict(schema='gr4-settings-entry-detours-v1',original_sample_sha256=EXPECTED_SHA256,
        emulator_link_address=hex(BASE),payload_bytes=len(data),
        payload_sha256=hashlib.sha256(data).hexdigest(),entries=offsets,sites=sites,hook_words=words,
        undo='Restore all ten original words with xpan_hook_txn under retained UI/image guard; publish caches; drain callbacks before unbinding/freeing.',
        native_quiescence_cache_and_executable_allocation_verified=False,
        installable_camera_package=False,flashable_firmware=False,camera_accessed=False,xpan_installed=False)
    (out/'patch.json').write_text(json.dumps(report,indent=2)+'\n')
    return raw,data,offsets,report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    _,_,_,report=build(a.out);print(json.dumps(report,indent=2))
