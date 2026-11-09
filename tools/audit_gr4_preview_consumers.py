#!/usr/bin/env python3
"""Trace fixed original raster consumers and regeneration stores offline."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from audit_xpan_paths import EXPECTED_SHA256,file_offset
from audit_sd_shell_path import require_branch

TARGETS=(0x5388AED0,0x5388B45C,0x53647498,0x538876B8,0x53887DD4)
EXPECTED={
 0x5388AED0:[0x53643820,0x53643870,0x53647514,0x53647560,0x53647B58],
 0x5388B45C:[0x53643848,0x53643894,0x5364753C,0x53647588,0x53647B78],
 0x53647498:[0x53639A48,0x5363A924],
 0x538876B8:[0x5362E4D4,0x53637E78],
 0x53887DD4:[0x5362E8C0,0x53637DD4]}


def audit(raw):
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256:raise ValueError('unsupported sample')
    found={target:[] for target in TARGETS}
    for address in range(0x53000000,0x53D00000,4):
        word=struct.unpack_from('<I',raw,file_offset(address))[0]
        if word&0x0F000000 != 0x0B000000:continue
        offset=(word&0xFFFFFF)<<2
        if offset&0x2000000:offset-=0x4000000
        target=(address+8+offset)&0xFFFFFFFF
        if target in found:found[target].append(address)
    if found!=EXPECTED:raise ValueError('fixed ARM BL cross-reference set changed')
    for target,origins in EXPECTED.items():
        for origin in origins:require_branch(raw,origin,target)
    def word(address):return struct.unpack_from('<I',raw,file_offset(address))[0]
    stores=((0x53643840,0xE18400BE),(0x53643864,0xE18400BE),
            (0x5364388C,0xE18400BE),(0x5364389C,0xE18400B3))
    for address,value in stores:
        if word(address)!=value:raise ValueError('original raster regeneration store changed')
    contexts=[]
    for address,length in ((0x53643760,324),(0x5363A8C4,164),(0x53637DC0,116)):
        data=raw[file_offset(address):file_offset(address)+length]
        contexts.append({'address':hex(address),'bytes':length,'sha256':hashlib.sha256(data).hexdigest()})
    return {'schema':'gr4-preview-consumer-audit-v1','sample_sha256':EXPECTED_SHA256,
            'ARM_BL_search_range':['0x53000000','0x53d00000'],
            'indirect_or_Thumb_calls_exhaustive':False,
            'direct_calls':{hex(t):[hex(a) for a in refs] for t,refs in found.items()},
            'pins':contexts,
            'additional_regeneration':{'range':['0x53643760','0x536438a0'],
                'manager_link':'0x334','flags':['0xbbe','0xbc4'],
                'rewrites':['0xbd6','0xbd8','0xbe4','0xbe6'],
                'active_on_camera_proven':False,
                'single_post_helper_field_write_is_not_complete_integration':True},
            'publisher':{'process_entry':'0x53637dc0','information_link':'0x3a0',
                'publish_call':'0x53637dd4','additional_calls':['0x53887ea0','0x53887ee0'],
                'LCD_consumer_proven':False},
            'camera_access':False,'xpan_installed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=audit(Path('samples/gr4_decoded.bin').read_bytes())
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('16 fixed ARM calls and four raster regeneration stores verified offline')
