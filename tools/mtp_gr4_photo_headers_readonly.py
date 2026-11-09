#!/usr/bin/env python3
"""Read bounded headers of existing JPEG/DNG objects via standard PTP.

Only the last 64 returned handles per storage are candidates (not guaranteed
chronological). At most six image headers, <=256KiB each. No full photos,
uploads, deletion, property changes, shutter commands or factory writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import usb.core
import usb.util
from mtp_probe_readonly import VID, PID, command
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info

TAGS={256:'ImageWidth',257:'ImageLength',330:'SubIFDs',33421:'CFARepeatPatternDim',
      33422:'CFAPattern',50718:'DefaultScale',50719:'DefaultCropOrigin',
      50720:'DefaultCropSize',50829:'ActiveArea'}


def jpeg_dimensions(data):
    if data[:2]!=b'\xff\xd8': return None
    i=2
    while i+4<=len(data):
        if data[i]!=255: return None
        while i<len(data) and data[i]==255: i+=1
        if i>=len(data): return None
        marker=data[i]; i+=1
        if marker in (0xD9,0xDA): return None
        if marker in (0x01,*range(0xD0,0xD9)): continue
        if i+2>len(data): return None
        length=struct.unpack_from('>H',data,i)[0]
        if length<2 or i+length>len(data): return None
        if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
            if length<8: return None
            height,width=struct.unpack_from('>2H',data,i+3)
            return {'width':width,'height':height,'precision':data[i+2],'SOF':hex(marker)}
        i+=length
    return None


def tiff_fields(data):
    if data[:4] not in (b'II*\0',b'MM\0*'): return None
    order='<' if data[:2]==b'II' else '>'
    if len(data)<8: return None
    pending=[struct.unpack_from(order+'I',data,4)[0]]; seen=set(); ifds=[]
    while pending and len(ifds)<8:
        offset=pending.pop(0)
        if not offset or offset in seen: continue
        seen.add(offset)
        if offset+2>len(data):
            ifds.append({'offset':offset,'outside_read_prefix':True}); continue
        count=struct.unpack_from(order+'H',data,offset)[0]
        if count>512 or offset+2+count*12+4>len(data):
            ifds.append({'offset':offset,'incomplete_or_over_limit':True}); continue
        fields={}
        for j in range(count):
            at=offset+2+j*12; tag,kind,n,value=struct.unpack_from(order+'HHII',data,at)
            if tag not in TAGS: continue
            sizes={1:1,3:2,4:4,5:8,9:4,10:8}
            if kind not in sizes or not 1<=n<=16:
                fields[TAGS[tag]]={'type':kind,'count':n,'unsupported_or_over_limit':True}; continue
            size=n*sizes[kind]; start=at+8 if size<=4 else value
            if start+size>len(data):
                fields[TAGS[tag]]={'offset':start,'bytes':size,'outside_read_prefix':True}; continue
            buf=data[start:start+size]
            if kind in (1,3,4,9):
                values=list(struct.unpack(order+str(n)+{1:'B',3:'H',4:'I',9:'i'}[kind],buf))
            else:
                values=[list(struct.unpack_from(order+('2I' if kind==5 else '2i'),buf,k*8)) for k in range(n)]
            fields[TAGS[tag]]=values
            if tag==330: pending.extend(values)
        next_ifd=struct.unpack_from(order+'I',data,offset+2+count*12)[0]
        if next_ifd: pending.append(next_ifd)
        ifds.append({'offset':offset,'fields':fields})
    return {'byte_order':order,'IFDs':ifds,'not_a_full_TIFF_validation':True}


def collect(dev,transaction):
    def get(op,*args):
        code,data,params=command(dev,op,transaction[0],*args); transaction[0]+=1
        if code!=0x2001 or data is None: raise RuntimeError('read request %s returned %s'%(hex(op),hex(code)))
        return data,params
    def vector(data,limit):
        if len(data)<4: raise ValueError('short PTP vector')
        n=struct.unpack_from('<I',data)[0]
        if n>limit or len(data)!=4+4*n: raise ValueError('PTP vector outside bound')
        return struct.unpack_from('<%dI'%n,data,4)
    storages=vector(get(0x1004)[0],8); candidates=[]
    for storage in storages:
        handles=vector(get(0x1007,storage,0,0)[0],100000)
        for handle in handles[-64:]:
            info,_=get(0x1008,handle)
            if len(info)<53: raise ValueError('short ObjectInfo')
            units=info[52]
            if 53+units*2>len(info): raise ValueError('truncated ObjectInfo filename')
            name=info[53:53+units*2].decode('utf-16le').rstrip('\0')
            if not name.upper().endswith(('.JPG','.JPEG','.DNG')): continue
            candidates.append({'handle':handle,'storage':hex(storage),'name':name,
                'format':hex(struct.unpack_from('<H',info,4)[0]),'bytes':struct.unpack_from('<I',info,8)[0],
                'PTP_width_height':list(struct.unpack_from('<2I',info,26)),
                'parent_handle':struct.unpack_from('<I',info,38)[0]})
    images=[]
    for obj in candidates[-6:]:
        wanted=min(obj['bytes'],256*1024)
        if wanted<8: continue
        data,params=get(0x101B,obj['handle'],0,wanted)
        if len(data)>wanted or not data: raise ValueError('partial object length outside request')
        images.append({**obj,'header_bytes':len(data),'header_sha256':hashlib.sha256(data).hexdigest(),
            'JPEG_SOF':jpeg_dimensions(data),'TIFF_selected_fields':tiff_fields(data)})
    return {'schema':'gr4-existing-photo-headers-readonly-v1','storage_count':len(storages),
            'candidate_limit_per_storage':64,'image_header_limit':6,'images':images,
            'handles_order_is_not_proven_chronological':True,'full_photo_or_header_bytes_saved':False,
            'camera_memory_or_files_written':False,'shutter_or_property_commands_sent':False,
            'xpan_installed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    if a.report.exists(): raise ValueError('immutable report exists')
    dev=usb.core.find(idVendor=VID,idProduct=PID)
    if dev is None or dev.bcdDevice!=0x111: raise RuntimeError('expected connected GR IV')
    usb.util.claim_interface(dev,0);opened=False;transaction=[2]
    try:
        code,data,_=command(dev,0x1001,0)
        if code!=0x2001 or data is None or operations_from_device_info(data)!=EXPECTED_OPERATIONS: raise RuntimeError('unexpected DeviceInfo')
        code,_,_=command(dev,0x1002,1,1);opened=code==0x2001
        if code not in (0x2001,0x201E): raise RuntimeError('OpenSession failed')
        result=collect(dev,transaction)
        a.report.write_text(json.dumps(result,indent=2)+'\n')
        print('Saved:',a.report)
        for im in result['images']: print(im['name'],im['JPEG_SOF'],im['TIFF_selected_fields'])
    finally:
        try:
            if opened: command(dev,0x1003,transaction[0])
        finally:
            usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
