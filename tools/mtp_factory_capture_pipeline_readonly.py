#!/usr/bin/env python3
"""One USB GetData batch: image class sightings, links and registered workers.

Fresh pointers only. No function calls/writes, full RAM dump, task suspension,
capture ownership proof or hook installation. SD script stays unchanged.
"""
import argparse
import json
from pathlib import Path
import struct
import usb.core
import usb.util
from audit_xpan_paths import file_offset
from mtp_factory_image_owners_readonly import collect as image_context, PIPELINE_CLASSES
from mtp_factory_task_mapping_readonly import REGISTRY, TCB_TABLE, TASK_LIMIT, STRIDE, ram, kernel_ram
from mtp_factory_pointer_trial import Transport
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_probe_readonly import VID, PID, command

ROOT=Path(__file__).resolve().parents[1]
TASK_BASE_OFFSETS={'BackResizeMacroProcess':0, 'LiveViewControl':4, 'LiveViewProcess':4}
PREFIX_LENGTHS={'BackResizeMacroProcess':0x38, 'LiveViewControl':0x3C,
                'LiveViewProcess':0x3C0, 'LiveViewResolutionManager':0x10,
                'ImageMapParameterSettingLiveViewKb636':0x10, 'DNG_Kb636':0x20}


def workers(read):
    slot=read(REGISTRY,4); registry=struct.unpack('<I',slot)[0]
    header=read(ram(registry,32),32)
    buckets,bucket_count,head,count=struct.unpack_from('<4I',header)
    ram(buckets,4)
    if not 1<=bucket_count<=1024 or not 1<=count<=512: raise ValueError('registry bound changed')
    node=head; seen=set(); entries=[]
    while node:
        if node in seen or len(seen)>=count: raise ValueError('registry cycle/count mismatch')
        seen.add(node); item=read(ram(node,12),12)
        next_node,task,obj=struct.unpack('<3I',item)
        prefix=read(ram(obj,12),12); vt,identity,name=struct.unpack('<3I',prefix)
        if task!=identity: raise ValueError('task registry identity mismatch')
        entries.append({'node':hex(node),'object':hex(obj),'id':hex(task),'vtable':hex(vt),
                        'name_pointer':hex(name),'identity_hex':prefix.hex()})
        node=next_node
    if len(seen)!=count: raise ValueError('registry count changed')
    if read(REGISTRY,4)!=slot or read(registry,16)!=header[:16]: raise ValueError('registry changed during traversal')
    return entries,registry,header[:16],slot


def collect(read,raw):
    saved=read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)
    props=read(0x55085D63,5)
    report=image_context(read,raw,PIPELINE_CLASSES)
    task_entries,registry,header,slot=workers(read)
    table_slot=read(TCB_TABLE,4); table=struct.unpack('<I',table_slot)[0]
    maximum=struct.unpack('<I',read(TASK_LIMIT,4))[0]
    if not 1<=maximum<=1024: raise ValueError('kernel task limit changed')
    kernel_ram(table,maximum*STRIDE)
    details=[]
    for sighting in report['sightings']:
        kind=sighting['class']; obj=int(sighting['address'],16)
        if kind not in PREFIX_LENGTHS: continue
        data=read(ram(obj,PREFIX_LENGTHS[kind]),PREFIX_LENGTHS[kind])
        if struct.unpack_from('<I',data)[0]!=PIPELINE_CLASSES[kind]:
            raise ValueError('class sighting expired; no old object followed')
        entry={'class':kind,'address':hex(obj),'prefix_hex':data.hex(),
               'allocation_size_and_ownership_not_proven':True,'worker':None,'linked_fields':[]}
        if kind in TASK_BASE_OFFSETS:
            base=obj+TASK_BASE_OFFSETS[kind]
            matching=[t for t in task_entries if int(t['object'],16)==base]
            if len(matching)!=1: raise ValueError('image worker is not uniquely registered')
            task=matching[0]; task_id=int(task['id'],16); index=task_id&0xFFFF
            if not 1<=index<=maximum: raise ValueError('worker outside kernel table')
            tcb_address=kernel_ram(table+(index-1)*STRIDE,0x18)
            tcb=read(tcb_address,0x18)
            identity,exinf,attributes,initial_entry=struct.unpack_from('<4I',tcb,8)
            if identity!=task_id or exinf!=base or initial_entry!=0x538E1F70:
                raise ValueError('registered image worker kernel identity differs')
            if read(base,12).hex()!=task['identity_hex']: raise ValueError('worker identity changed')
            vt=int(task['vtable'],16)
            if read(vt,16)!=raw[file_offset(vt):file_offset(vt)+16]: raise ValueError('worker class ROM pin mismatch')
            entry['worker']={**task,'TCB':hex(tcb_address),'TCB_identity_hex':tcb.hex(),
                             'attributes':hex(attributes),'entry':hex(initial_entry)}
        offsets=(0x38,) if kind=='LiveViewControl' else range(0x374,0x3C0,4) if kind=='LiveViewProcess' else ()
        for offset in offsets:
            ptr=struct.unpack_from('<I',data,offset)[0]
            link={'offset':hex(offset),'pointer':hex(ptr),'class_prefix_hex':None}
            if ptr and ptr%4==0 and 0x59600000<=ptr<=0x5A5FFFF0-16:
                prefix=read(ptr,16); vt=struct.unpack_from('<I',prefix)[0]
                if 0x53D00000<=vt<0x54400000:
                    if read(vt,16)!=raw[file_offset(vt):file_offset(vt)+16]: raise ValueError('linked class ROM differs')
                    if read(ptr,4)!=prefix[:4]: raise ValueError('linked class changed')
                    link.update(class_prefix_hex=prefix.hex(),vtable=hex(vt),
                                known_class=[n for n,v in PIPELINE_CLASSES.items() if v==vt])
            entry['linked_fields'].append(link)
        if read(obj,4)!=data[:4]: raise ValueError('image class changed while reading')
        details.append(entry)
    if (read(REGISTRY,4)!=slot or read(registry,16)!=header or read(TCB_TABLE,4)!=table_slot or
        read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)!=saved or read(0x55085D63,5)!=props):
        raise ValueError('registry/callbacks/scratch/properties changed')
    report.update(schema='gr4-capture-pipeline-readonly-v1',worker_and_link_snapshots=details,
                  task_registry_objects=task_entries,task_snapshot_is_not_worker_quiescence=True,
                  native_functions_called=False,SD_script_changed=False)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    if a.report.exists(): raise ValueError('immutable report exists')
    dev=usb.core.find(idVendor=VID,idProduct=PID)
    if dev is None or dev.bcdDevice!=0x111: raise RuntimeError('expected connected GR IV')
    usb.util.claim_interface(dev,0);io=Transport(dev);opened=False
    try:
        code,info,_=command(dev,0x1001,0)
        if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS: raise RuntimeError('unexpected DeviceInfo')
        code,_,_=command(dev,0x1002,1,1);opened=code==0x2001
        if code not in (0x2001,0x201E): raise RuntimeError('OpenSession failed')
        result=collect(io.read,(ROOT/'samples/gr4_decoded.bin').read_bytes())
        a.report.write_text(json.dumps(result,indent=2)+'\n')
        print('Saved:',a.report)
        print('Class snapshots:',len(result['worker_and_link_snapshots']))
    finally:
        try:
            if opened: command(dev,0x1003,io.transaction)
        finally:
            usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
