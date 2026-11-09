#!/usr/bin/env python3
"""Finite eight-recipe collector failure checks; no camera access."""
import argparse
import json
from pathlib import Path
import struct
from audit_xpan_paths import file_offset
from mtp_factory_capture_state_readonly import preview_recipes,preview_collection_status,ROOT


def check(raw):
    owner,collection=0x59CD0000,0x59CD9900
    objects=[0x59A80000+i*0x2000 for i in range(8)]
    pack=lambda v:struct.pack('<%dI'%len(v),*v)
    base={(0x53648034,128):raw[file_offset(0x53648034):file_offset(0x53648034)+128],
          (0x5363F98C,8):raw[file_offset(0x5363F98C):file_offset(0x5363F98C)+8],
          (owner+0x3B0,4):pack([collection]),(collection+8,32):pack(objects),
          (0x53EB16E8,8):raw[file_offset(0x53EB16E8):file_offset(0x53EB16E8)+8]}
    for p in objects:
        base[p,8]=pack([0x53EB16E8,0]);base[p+0x32C,12]=pack([0,0,0x59A58900])
        base[p+0xBB0,0x44]=bytes(0x44)
    cases=[]
    for fault in ('normal','wrong-constructor','wrong-owner-ROM','null-collection','duplicate-slot',
                  'wrong-class','outside-object','short-field','changed-links','changed-slots'):
        data=dict(base);requests=[]
        if fault=='wrong-constructor':data[0x53648034,128]=bytes(128)
        if fault=='wrong-owner-ROM':data[0x5363F98C,8]=bytes(8)
        if fault=='null-collection':data[owner+0x3B0,4]=bytes(4)
        if fault=='duplicate-slot':data[collection+8,32]=pack([objects[0]]*8)
        if fault=='wrong-class':data[objects[0],8]=bytes(8)
        if fault=='outside-object':data[collection+8,32]=pack([0x60000000]+objects[1:])
        if fault=='short-field':data[objects[0]+0xBB0,0x44]=bytes(0x43)
        def read(a,n):
            key=a,n;assert key in data,'unexpected read'
            requests.append(key)
            if fault=='changed-links' and key==(objects[0]+0x32C,12) and requests.count(key)>1:
                return bytes(12)
            if fault=='changed-slots' and key==(collection+8,32) and requests.count(key)>1:
                return bytes(32)
            return data[key]
        rejected=False
        try:r=preview_recipes(read,raw,owner)
        except ValueError:rejected=True
        assert rejected==(fault!='normal')
        if fault=='normal':assert len(r['recipes'])==8 and not r['atomic_frame_or_quiescence_verified']
        if fault in ('wrong-constructor','wrong-owner-ROM','null-collection','duplicate-slot','outside-object'):
            assert not any(a==objects[0] for a,n in requests)
        cases.append({'case':fault,'rejected':rejected,'finite_requests':len(requests)})
    return cases


def check_status(raw):
    owner,collection=0x59CD0000,0x59CD9900
    cases=[]
    for fault in ('normal','empty-slots','null-collection','short-header','changed-header','changed-owner'):
        prefix=bytearray(48)
        if fault=='normal':struct.pack_into('<8I',prefix,8,*[0x59A80000+i*0x2000 for i in range(8)])
        requests=[]
        def read(a,n):
            requests.append((a,n))
            if a in (0x53648034,0x5363F98C):return raw[file_offset(a):file_offset(a)+n]
            if a==owner+0x3B0:
                p=0 if fault=='null-collection' else collection
                if fault=='changed-owner' and requests.count((a,n))>1:p+=4
                return struct.pack('<I',p)
            assert (a,n)==(collection,48),'slot pointer must never be followed'
            if fault=='short-header':return bytes(47)
            if fault=='changed-header' and requests.count((a,n))>1:return b'\1'+bytes(47)
            return bytes(prefix)
        rejected=False
        try:r=preview_collection_status(read,raw,owner)
        except ValueError:rejected=True
        assert rejected==(fault in ('short-header','changed-header','changed-owner'))
        if not rejected:
            assert not r['recipes_followed']
            if fault=='normal':assert r['eight_unique_nonnull_slots']
            if fault=='empty-slots':assert r['nonnull_slots']==0
        cases.append({'case':fault,'rejected':rejected,'slot_pointers_followed':False})
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();raw=(ROOT/'samples/gr4_decoded.bin').read_bytes()
    cases=check(raw);statuses=check_status(raw)
    with a.out.open('x') as f:json.dump({'passed':True,'cases':cases,'collection_status_cases':statuses,'camera_access':False},f,indent=2);f.write('\n')
    print('%d recipe-read + %d collection-status models passed'%(len(cases),len(statuses)))


if __name__=='__main__':main()
