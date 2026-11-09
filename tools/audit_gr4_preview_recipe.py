#!/usr/bin/env python3
"""Pin original raster helpers, recipe ABI and collection construction offline."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from audit_xpan_paths import EXPECTED_SHA256, file_offset
from audit_sd_shell_path import require_branch

PINS = [
    (0x5388AED0,68,'8f94b98f6e429dc6a70ebed8677f91449e4525f8732d54fad61362940074bec2'),
    (0x5388B45C,68,'5d7b268b87f8fd64c4a4e02ee1d5a018240af8c2ef31b66dd96dc16a6c5fc2bb'),
    (0x5388A954,1404,'b636b3eff1b403b3650fb158eff960ed7e218fe354b08af01dbb463f70e1ba30'),
    (0x5388AF1C,1344,'edf5f7e8da06917cc9ddf18345bd28cd8825e7620f9fae025a14219581d9aa75'),
    (0x53647498,376,'5318bdd584a2ae3f558326adb30057bea587af160f9e9af4b6dd560b1a1bf5d0'),
    (0x53648034,128,'24e94955730b775e020deb01d9557267eb016d3446998d201b516b3c0a8a4cda'),
    (0x5363F98C,8,'1b4ada8ea9fd309e432cb167b6ad431409b4bb6b2ccb04142a518b8e92e74524'),
    (0x53EB16E8,16,'6105335f9f5770bd8feb7e1617676cfb733e372bc24a95c54c1cb132efaf3eaf'),
    (0x53FD19F8,64,'f0576a1c9a8673a2d1d880d90624607ed7f8ce68e5abe6a601077aeb11807900'),
]


def audit(raw):
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256:
        raise ValueError('unsupported original firmware sample')
    for address,size,digest in PINS:
        if hashlib.sha256(raw[file_offset(address):file_offset(address)+size]).hexdigest()!=digest:
            raise ValueError('recipe/raster pin differs: %08x'%address)
    for origin,target in ((0x5363F990,0x53648034),(0x5364805C,0x538E09B0),
                          (0x53648064,0x53641F90),(0x5363A924,0x53647498),
                          (0x53639A48,0x53647498),(0x53647514,0x5388AED0),
                          (0x5364753C,0x5388B45C),(0x53647560,0x5388AED0),
                          (0x53647588,0x5388B45C)):
        require_branch(raw,origin,target)
    def word(address):return struct.unpack_from('<I',raw,file_offset(address))[0]
    if word(0x5363F98C)!=0xE59403B0 or word(0x53648070)!=0xE5A45004:
        raise ValueError('collection owner/preincrement slot store changed')
    if word(0x53642C48)!=0x53EB16E8:raise ValueError('recipe constructor primary class changed')
    return {'schema':'gr4-preview-recipe-audit-v1','firmware_sha256':EXPECTED_SHA256,
            'pins':[{'address':hex(a),'bytes':n,'sha256':s} for a,n,s in PINS],
            'helper':{'address':'0x53647498','ABI':['recipe','aspect','extra','mode','stack:crop_Q13'],
                      'direct_ROM_calls':True,'virtual_install_slot':False,
                      'active_WH':['0xbd6','0xbd8'],'center_XY':['0xbe0','0xbe2'],
                      'full_reference_WH':['0xbe4','0xbe6'],'base_WH':['0xbea','0xbec']},
            'collection':{'process_link':'0x3b0','slots':[hex(8+4*i) for i in range(8)],
                          'recipe_bytes':'0x19f0','recipe_vtable':'0x53eb16e8',
                          'recipe_manager_link':'0x334'},
            'camera_access':False,'hardware_alignment_verified':False,
            'native_frame_quiescence_verified':False,'xpan_installed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample',type=Path,default=Path('samples/gr4_decoded.bin'))
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=audit(a.sample.read_bytes())
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('Original recipe and raster ABI pins verified; no camera access')
