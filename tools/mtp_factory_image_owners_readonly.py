#!/usr/bin/env python3
"""Bounded GetData-only image-class sightings and incoming pointer candidates.

Keeps scan bytes only in host memory. Saves hashes and pointer relationships,
not a full RAM dump. A vtable sighting is not ownership or a safe hook site.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import usb.core
import usb.util
from audit_xpan_paths import EXPECTED_SHA256,file_offset
from mtp_factory_allocator_readonly import collect as allocator_context
from mtp_factory_ui_routes_readonly import collect as menu_context
from mtp_factory_pointer_trial import Transport
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS,operations_from_device_info
from mtp_probe_readonly import VID,PID,command

ROOT=Path(__file__).resolve().parents[1]
CLASSES={'DNG_Kb636':0x53FCF430,'LiveViewControl':0x53EB0D40,
         'LiveViewProcess':0x53EB11F0,'LiveViewProcessFactory':0x53EB15E8}
PIPELINE_CLASSES={**CLASSES, 'BackResizeMacroProcess':0x53ECFC58,
                  'LiveViewResolutionManager':0x53FD19F8,
                  'ImageMapParameterSettingLiveViewKb636':0x53FCF708}


def collect(read,raw,classes=None):
    classes=CLASSES if classes is None else classes
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256:raise ValueError('unsupported firmware sample')
    heap=allocator_context(read)
    if (heap['arena_base'],heap['arena_length'])!=(0x59600000,0xFFFFF0):raise ValueError('heap changed')
    saved=read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)
    props=read(0x55085D63,5)
    if saved!=struct.pack('<2I',0x538EF3C8,0x538EF9F0)+bytes(20):raise ValueError('original callbacks/scratch required')
    for vt in classes.values():
        if read(vt-8,24)!=raw[file_offset(vt-8):file_offset(vt-8)+24]:raise ValueError('class ROM pin mismatch')
    regions=[];objects=[]
    for start,length in ((0x55080000,0x20000),(0x55390000,0x23000),(0x59600000,0xFFFFF0)):
        chunks=[]
        for offset in range(0,length,65536):
            chunks.append(read(start+offset,min(65536,length-offset)))
            if offset%(4*1024*1024)==0:print('Read-only image scan:',hex(start),offset+len(chunks[-1]),flush=True)
        data=b''.join(chunks);regions.append((start,data))
        for name,vt in classes.items():
            at=0;needle=struct.pack('<I',vt)
            while True:
                at=data.find(needle,at)
                if at<0:break
                address=start+at
                if address%4==0:
                    objects.append({'class':name,'address':hex(address),'prefix_hex':data[at:at+16].hex(),
                                    'prefix_is_not_proven_object_size':True})
                at+=1
        if len(objects)>256:raise ValueError('too many class sightings')
    for obj in objects:
        pointer=int(obj['address'],16);needle=struct.pack('<I',pointer);references=[]
        for start,data in regions:
            at=0
            while True:
                at=data.find(needle,at)
                if at<0:break
                if (start+at)%4==0:references.append(hex(start+at))
                at+=1
                if len(references)>256:break
        obj['incoming_pointer_candidates']=references
        obj['vtable_still_matches_after_scan']=read(pointer,4)==struct.pack('<I',classes[obj['class']])
    menu=menu_context(read,raw)
    if read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)!=saved or read(0x55085D63,5)!=props:
        raise ValueError('callbacks or capture properties changed during read-only scan')
    return {'schema':'gr4-image-owner-candidates-readonly-v1','sample_sha256':EXPECTED_SHA256,
            'classes':{k:hex(v) for k,v in classes.items()},'regions':[
                {'start':hex(a),'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()} for a,d in regions],
            'sightings':objects,'menu_and_calculator':menu,'camera_memory_written':False,
            'callbacks_scratch_properties_unchanged':True,'ownership_quiescence_and_pixel_bounds_verified':False,
            'full_RAM_dump_saved':False,'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);args=p.parse_args()
    if args.report.exists():raise ValueError('immutable report already exists')
    device=usb.core.find(idVendor=VID,idProduct=PID)
    if device is None or device.bcdDevice!=0x111:raise RuntimeError('expected connected GR IV')
    usb.util.claim_interface(device,0);io=Transport(device);opened=False
    try:
        code,info,_=command(device,0x1001,0)
        if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS:raise RuntimeError('unexpected DeviceInfo')
        code,_,_=command(device,0x1002,1,1);opened=code==0x2001
        if code not in (0x2001,0x201E):raise RuntimeError('OpenSession failed')
        result=collect(io.read,(ROOT/'samples/gr4_decoded.bin').read_bytes())
        args.report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result['sightings'],indent=2));print('Saved:',args.report)
    finally:
        try:
            if opened:command(device,0x1003,io.transaction)
        finally:
            usb.util.release_interface(device,0);usb.util.dispose_resources(device)


if __name__=='__main__':main()
