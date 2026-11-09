#!/usr/bin/env python3
"""Execute original live-view raster-size functions offline; no camera access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from audit_xpan_paths import EXPECTED_SHA256, file_offset
from check_gr4_native_memory_abi import check_host_cache_access


def check(raw, resolutions=(7,0x1D,0x1E), source_modes=(0,3), external=0):
    assert hashlib.sha256(raw).hexdigest()==EXPECTED_SHA256
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
        UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for page in (0x5388A000,0x5388B000,0x5388C000,0x538ED000,0x53FD1000):
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(0x63000000,0x10000)
    obj,stack,stop=0x63000100,0x6300E000,0x6300F000
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    def hook(m,a,n,data):
        if a==0x538ED930: raise ValueError('original native resolution assertion')
    u.hook_add(UC_HOOK_CODE,hook)
    cases=[]
    for resolution in resolutions:
      for source_mode in source_modes:
       for aspect in range(4):
        for flags in ((0,0),(1,0),(0,1)):
            u.mem_write(obj,struct.pack('<II4B',0x53FD19F8,0,aspect,source_mode,resolution,external))
            sizes=[]
            for entry in (0x5388AED0,0x5388B45C):
                for reg,val in zip(regs,(obj,*flags,source_mode)):u.reg_write(reg,val)
                u.mem_write(stack,struct.pack('<2I',aspect,1))
                u.reg_write(UC_ARM_REG_SP,stack);u.reg_write(UC_ARM_REG_LR,stop)
                try:u.emu_start(entry,stop,count=20000,timeout=1000000)
                except Exception as e:raise RuntimeError('entry %08x PC %08x'%(entry,u.reg_read(UC_ARM_REG_PC))) from e
                assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==stack
                sizes.append(u.reg_read(UC_ARM_REG_R0))
            assert all(0<v<=65535 for v in sizes)
            cases.append({'resolution':resolution,'source_mode':source_mode,'aspect':aspect,
                          'external':external,'flags':flags,'raster':sizes})
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    try:
        raw=Path('samples/gr4_decoded.bin').read_bytes();cases=check(raw)
        report={'passed':True,'sample_sha256':EXPECTED_SHA256,'cases':cases,
                'camera_access':False,'LCD_pixels_verified':False,'xpan_installed':False}
        (a.out/'checks.json').write_text(json.dumps(report,indent=2)+'\n')
        print('%d original ARM raster-size cases passed'%len(cases))
        print('Resolution 7, source-mode 0, flags 0/0:',
              [(c['aspect'],c['raster']) for c in cases if c['resolution']==7 and c['source_mode']==0 and c['flags']==(0,0)])
    except Exception as e:
        (a.out/'failure.json').write_text(json.dumps({'passed':False,'error':repr(e),'camera_access':False},indent=2)+'\n')
        raise


if __name__=='__main__':main()
