#!/usr/bin/env python3
"""Pin and optionally read the AppMain message queue. Never enqueue anything."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_gr4_ui_native_routes import audit as routes_audit
from audit_sd_shell_path import require_branch
from audit_xpan_paths import file_offset, require
from mtp_factory_task_mapping_readonly import (
    audit as tasks_audit, TCB_TABLE, TASK_LIMIT, STRIDE, kernel_ram)
from mtp_factory_script_context_readonly import collect as script_context

ROOT=Path(__file__).resolve().parents[1]
MAIN=0x55082000
MEDIATOR=0x55087470
FUNCTIONS={'appmain_run':(0x5323B9F4,0x28),'message_constructor':(0x5323B7F8,12),
           'message_destructor':(0x5323B804,4),'enqueue_record':(0x5325C768,0xF0),
           'dispatch_record':(0x5325C87C,0x54),'consume_queue':(0x5325C8D0,0x13C),
           'diagnostic_store_leaf':(0x5325CA0C,8),'producer_lock':(0x538DFE24,0x154),
           'producer_unlock':(0x538DFF78,0x104),'event_notify':(0x538DB424,0xB8)}


def audit(raw):
    evidence=routes_audit(raw);tasks_audit(raw)
    require(raw,file_offset(0x53DB91A0),struct.pack('<3I',0x5323B99C,0x5323B9C4,0x5323B9F4),'AppMain thread methods')
    require(raw,file_offset(0x5323EC18),bytes.fromhex('700407e3080545e3'),'mediator fixed singleton')
    require(raw,file_offset(0x5323B7F8),bytes.fromhex('b010c0e10c0080e91eff2fe1'),'message fields')
    require(raw,file_offset(0x5325C888),bytes.fromhex('7d3100e3030052e1'),'message 0x17d comparison')
    require(raw,file_offset(0x5325C8B4),bytes.fromhex('003090e5b010d4e1003093e5042094e533ff2fe1'),'handler vtable call')
    require(raw,file_offset(0x5325CA0C),bytes.fromhex('001080e51eff2fe1'),'diagnostic single owned-word store')
    for a,t in ((0x5323BA14,0x5325C8D0),(0x5325C990,0x5325C87C),
                (0x5325C7E0,0x538DFF78),(0x5325C794,0x538DFE24),
                (0x5325C6A4,0x5323B7F8)):
        require_branch(raw,a,t)
    require_branch(raw,0x5325C7F4,0x538DB424,link=False)
    return {'schema':'gr4-ui-message-queue-audit-v1','sample_sha256':evidence['sample_sha256'],
            'appmain':{'object':hex(MAIN),'vtable':'0x53db91a0','run':'0x5323b9f4'},
            'mediator':{'object':hex(MEDIATOR),'guard':'0x550821b8',
                        'has_vtable':False,'queue_offset':0x14,'count_offset':0x18,
                        'capacity_offset':0x1A,'head_offset':0x1C,'tail_offset':0x1E,
                        'mask_offset':0x20,'producer_mutex_offset':0x24},
            'enqueue_abi':{'address':'0x5325c768','r0':'mediator','r1':'12-byte message*',
                           'record_copied_under_original_mutex':True,
                           'notify':'event flag 1 via 0x538db424',
                           'queue_full_behavior':'original assertion; producer must guard fullness under the same mutex'},
            'message':{'bytes':12,'code_u16_offset':0,'data_u32_offset':4,
                       'handler_u32_offset':8,'direct_handler_code':'0x17d',
                       'handler_call':'handler->vtable[0](handler,code,data)',
                       'destructor':'0x5323b804 is BX LR; does not release handler'},
            'functions':{n:{'address':hex(a),'bytes':s,
                         'sha256':hashlib.sha256(raw[file_offset(a):file_offset(a)+s]).hexdigest()}
                         for n,(a,s) in FUNCTIONS.items()},
            'limits':['Static AppMain consumption establishes a candidate UI dispatch route, not a live callback execution.',
                      'Handler and its code/data must remain alive until consumption and return are proven.',
                      'A completion store before BX LR alone does not permit freeing executing RAM code.',
                      'No GUI thread synchronization, hook installation or image capture is verified.'],
            'camera_accessed':False,'message_enqueued':False,'xpan_installed':False}


def collect(read,raw):
    evidence=audit(raw)
    before=read(0x55085D63,5)
    callbacks=read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)
    if callbacks!=struct.pack('<2I',0x538EF3C8,0x538EF9F0)+bytes(20):
        raise ValueError('original callbacks and scratch required')
    for name,(a,s) in FUNCTIONS.items():
        if read(a,s)!=raw[file_offset(a):file_offset(a)+s]:raise ValueError('queue function differs: '+name)
    guards=read(MAIN-4,4)+read(0x550821B8,4)
    if not all(v&1 for v in struct.unpack('<2I',guards)):raise ValueError('queue owner not initialized')
    main=read(MAIN,12);vt,task_id,name=struct.unpack('<3I',main)
    if vt!=0x53DB91A0 or not 0x53D00000<=name<0x54400000:raise ValueError('AppMain class/name mismatch')
    original_name=raw[file_offset(name):file_offset(name)+64].split(b'\0')[0]+b'\0'
    if original_name!=b'AppMain\0' or read(name,len(original_name))!=original_name:
        raise ValueError('AppMain configured name mismatch')
    maximum=struct.unpack('<I',read(TASK_LIMIT,4))[0]
    table=struct.unpack('<I',read(TCB_TABLE,4))[0]
    index=task_id&0xFFFF
    if not 1<=index<=maximum<=1024:raise ValueError('UI task outside original table')
    kernel_ram(table,maximum*STRIDE)
    tcb=kernel_ram(table+(index-1)*STRIDE,0xD0);state=read(tcb,0xD0)
    if struct.unpack_from('<4I',state,8)!=(task_id,MAIN,0x21003,0x538E1F70):
        raise ValueError('AppMain TCB identity differs')
    queue=read(MEDIATOR,0x40)
    ring=struct.unpack_from('<I',queue,0x14)[0]
    count,capacity,head,tail,mask=struct.unpack_from('<5H',queue,0x18)
    if capacity!=64 or mask!=63 or not count<capacity or head>=capacity or tail>=capacity:
        raise ValueError('mediator ring dimensions differ')
    if ring%4 or not 0x59600008<=ring<ring+capacity*12<=0x5A5FFFF0:
        raise ValueError('UI ring outside original heap')
    allocation=read(ring-8,8)
    if allocation!=struct.pack('<2I',12,64):raise ValueError('UI ring allocation header differs')
    context=script_context(read)
    if read(MAIN,12)!=main or read(TCB_TABLE,4)!=struct.pack('<I',table):
        raise ValueError('UI task identity changed while reading')
    if read(MEDIATOR+0x14,4)!=struct.pack('<I',ring):raise ValueError('UI ring owner changed')
    if read(0x55085D63,5)!=before or read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)!=callbacks:
        raise ValueError('capture properties/callbacks changed')
    return {'schema':'gr4-ui-queue-readonly-v1','audit':evidence,'live_code_matches':True,
            'appmain_header_hex':main.hex(),'appmain_task_id':hex(task_id),'appmain_tcb':hex(tcb),
            'mediator_prefix_hex':queue.hex(),'ring':hex(ring),'allocation_header_hex':allocation.hex(),
            'queue_sample':{'count':count,'capacity':capacity,'head':head,'tail':tail,'mask':mask},
            'script_context':context,'capture_properties_unchanged':True,
            'callbacks_and_scratch_unchanged':True,'camera_memory_written':False,
            'message_enqueued':False,'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    result=audit((ROOT/'samples/gr4_decoded.bin').read_bytes())
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n');print('Saved:',args.report)


if __name__=='__main__':main()
