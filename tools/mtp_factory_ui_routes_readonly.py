#!/usr/bin/env python3
"""Read the original factory's pinned menu slots; no writes or native calls."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import usb.core
import usb.util
from audit_gr4_ui_native_routes import (audit, FACTORY, FACTORY_GUARD,
    FACTORY_VTABLE, ADJ_VTABLE, SELECT_VTABLE, SELECT_ASPECT_ROW)
from audit_gr4_menu_widgets import audit as widgets_audit, FUNCTIONS as WIDGET_FUNCTIONS
from audit_xpan_paths import file_offset
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_factory_allocator_readonly import collect as allocator_context
from mtp_probe_readonly import VID, PID, command

ROOT=Path(__file__).resolve().parents[1]
ARENA=(0x59600000,0x5A5FFFF0)


def in_heap(pointer, size):
    return pointer%4==0 and ARENA[0]<=pointer< pointer+size<=ARENA[1]


def collect_item_slots(read, raw, listing, lst, limit=5):
    """Read constructed records, including the inactive fifth slot; never enable one."""
    begin,end,allocation_end=struct.unpack_from('<3I',lst,0xF4)
    if (not in_heap(begin,4) or not begin<=end<=allocation_end<=ARENA[1]
            or (end-begin)%4 or (allocation_end-begin)%4):
        raise ValueError('list item vector outside original heap')
    count=min(limit,(end-begin)//4)
    vector=read(begin,count*4) if count else b''
    slots=[]
    for index,record in enumerate(struct.unpack('<%dI'%count,vector)):
        if not in_heap(record,8):raise ValueError('item record outside original heap')
        capture=read(record,8)
        item=struct.unpack_from('<I',capture)[0]
        active=capture[4]  # Original 53571238/53571258 use STRB; bytes 5..7 are padding.
        if not in_heap(item,0x108):raise ValueError('GUI item prefix outside original heap')
        data=read(item,0x108)
        vt=struct.unpack_from('<I',data)[0]
        if vt!=0x53E98F18:raise ValueError('item is not the pinned SelectMenuLineView')
        if read(vt,0x20)!=raw[file_offset(vt):file_offset(vt)+0x20]:
            raise ValueError('item class differs from pinned sample')
        widgets={}
        for offset in range(0xF0,0x108,4):
            widget=struct.unpack_from('<I',data,offset)[0]
            entry={'address':hex(widget),'constructed':bool(widget)}
            if widget:
                if not in_heap(widget,4):raise ValueError('item widget outside original heap')
                wvt=struct.unpack('<I',read(widget,4))[0]
                if not 0x53D00000<=wvt<0x54400000:raise ValueError('widget class outside ROM')
                if read(wvt,0x20)!=raw[file_offset(wvt):file_offset(wvt)+0x20]:
                    raise ValueError('widget class differs from pinned sample')
                entry['vtable']=hex(wvt)
                if offset in (0x100,0x104):
                    if wvt!=0x53E97FD8:raise ValueError('dynamic text is not the pinned AsciiView')
                    text_header=read(widget,0x110)
                    text_ptr=struct.unpack_from('<I',text_header,0xF0)[0]
                    text_units=text_header[0xED]
                    entry.update({'text_pointer':hex(text_ptr),'text_units':text_units,
                                  'text_state_hex':text_header[0xEC:0x100].hex()})
                    if text_ptr:
                        if not text_units or not in_heap(text_ptr,text_units*2):
                            raise ValueError('ASCII owned text outside original heap')
                        entry['utf16_hex']=read(text_ptr,text_units*2).hex()
                    if read(widget,4)!=text_header[:4] or read(widget+0xF0,4)!=text_header[0xF0:0xF4]:
                        raise ValueError('ASCII owner changed while reading')
                elif offset in (0xF8,0xFC):
                    if wvt!=0x53E984E0:raise ValueError('caption is not the pinned original class')
                    entry['caption_id']=struct.unpack('<H',read(widget+0xEA,2))[0]
            widgets[hex(offset)]=entry
        if read(record,8)!=capture or read(item,4)!=data[:4]:
            raise ValueError('GUI item identity changed while reading')
        slots.append({'index':index,'record_address':hex(record),'record_hex':capture.hex(),
                      'item_address':hex(item),'active_byte':active,'vtable':hex(vt),
                      'prefix_hex':data.hex(),'widgets':widgets})
    if read(listing+0xF4,12)!=lst[0xF4:0x100] or (count and read(begin,count*4)!=vector):
        raise ValueError('item vector changed while reading')
    return {'item_vector_begin':hex(begin),'item_vector_end':hex(end),
            'item_vector_allocation_end':hex(allocation_end),
            'item_slots_constructed':(end-begin)//4,
            'item_slots_allocated':(allocation_end-begin)//4,'first_slots':slots}


def scan_classes(read,raw):
    heap=allocator_context(read)
    if (heap['arena_base'],heap['arena_length'])!=(ARENA[0],ARENA[1]-ARENA[0]):
        raise ValueError('original allocator arena changed')
    classes={'factory':FACTORY_VTABLE,'adj':ADJ_VTABLE,
             'settings':SELECT_VTABLE,'image_calculator':0x53FD89A0}
    for vt in classes.values():
        if read(vt,16)!=raw[file_offset(vt):file_offset(vt)+16]:
            raise ValueError('scan class pin mismatch')
    matches=[];scans=[]
    for start,length in ((0x55080000,0x20000),(ARENA[0],ARENA[1]-ARENA[0])):
        digest=hashlib.sha256()
        for offset in range(0,length,65536):
            block=read(start+offset,min(65536,length-offset));digest.update(block)
            for name,vt in classes.items():
                needle=struct.pack('<I',vt);at=0
                while True:
                    at=block.find(needle,at)
                    if at<0:break
                    address=start+offset+at
                    if address%4==0:matches.append({'address':hex(address),'class':name})
                    at+=1
            if len(matches)>128:raise ValueError('too many class pointer sightings')
            if offset%(4*1024*1024)==0:
                print('Read-only scan:',hex(start),offset+len(block),'bytes',flush=True)
        scans.append({'start':hex(start),'bytes':length,'sha256':digest.hexdigest()})
    return {'scans':scans,'pointer_sightings':matches,
            'limits':['A class-pointer sighting alone is not verified object identity.',
                      'Live heap changes during the scan; the hash is a traversal record.',
                      'No full RAM dump is saved.']}


def collect(read, raw, scan=False):
    evidence=audit(raw)
    widget_evidence=widgets_audit(raw)
    before=read(0x55085D63,5)
    saved=read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)
    if saved[:8]!=struct.pack('<2I',0x538EF3C8,0x538EF9F0):
        raise ValueError('original USB script callbacks required')
    for address,length in ((FACTORY_VTABLE,8),(ADJ_VTABLE,0x44),
                           (SELECT_VTABLE,0x40),(SELECT_ASPECT_ROW,0x4C)):
        if read(address,length)!=raw[file_offset(address):file_offset(address)+length]:
            raise ValueError('live ROM class/descriptor mismatch')
    for name,(address,length) in WIDGET_FUNCTIONS.items():
        if read(address,length)!=raw[file_offset(address):file_offset(address)+length]:
            raise ValueError('live original menu/ASCII code mismatch: '+name)
    guard=read(FACTORY_GUARD,4)
    header=read(FACTORY,0x1CC)
    if struct.unpack_from('<I',guard)[0]&1==0:
        raise ValueError('factory singleton not initialized; no object followed')
    if struct.unpack_from('<I',header)[0]!=FACTORY_VTABLE:
        raise ValueError('factory class mismatch')
    objects={}
    for name,slot,size,vt,list_offset in (
            ('adj',0x84,0x294,ADJ_VTABLE,0x1F8),
            ('settings',0xB0,0x1E4,SELECT_VTABLE,0x198)):
        pointer=struct.unpack_from('<I',header,slot)[0]
        item={'factory_slot_address':hex(FACTORY+slot),
              'object_address':hex(pointer),'constructed':bool(pointer)}
        if pointer:
            if not in_heap(pointer,size):raise ValueError('controller outside original heap')
            data=read(pointer,size)
            if struct.unpack_from('<I',data)[0]!=vt:raise ValueError('controller class mismatch')
            if name=='adj' and struct.unpack_from('<I',data,0x158)[0]!=ADJ_VTABLE+0x4C:
                raise ValueError('ADJ secondary class mismatch')
            item.update({'vtable':hex(vt),'object_hex':data.hex(),
                         'controller_id':hex(struct.unpack_from('<I',data,0x124)[0]),
                         'selected_row':data[0x1FC if name=='adj' else 0x1A4]})
            listing=struct.unpack_from('<I',data,list_offset)[0]
            item['list_address']=hex(listing)
            if in_heap(listing,0x190):
                lst=read(listing,0x190)
                list_vt=struct.unpack_from('<I',lst)[0]
                if not 0x53D00000<=list_vt<0x54400000:
                    raise ValueError('list class outside original ROM')
                if read(list_vt,0x20)!=raw[file_offset(list_vt):file_offset(list_vt)+0x20]:
                    raise ValueError('list class differs from pinned sample')
                callback=struct.unpack_from('<I',lst,0x168)[0]
                manager,invoker=struct.unpack_from('<2I',lst,0x170)
                item['list']={'hex':lst.hex(),'vtable':hex(list_vt),
                              'callback_record':hex(callback),'manager':hex(manager),
                              'invoker':hex(invoker)}
                if name=='settings':
                    item['list'].update(collect_item_slots(read,raw,listing,lst))
                item['list'].update({'active_items':lst[0x108],
                                     'selected_index':struct.unpack_from('<H',lst,0x110)[0]})
                record_size=12 if name=='adj' else 4
                if in_heap(callback,record_size):
                    record=read(callback,record_size)
                    item['list']['callback_record_hex']=record.hex()
                    item['list']['original_owner_match']=(
                        record==struct.pack('<3I',0x531BF38C,0,pointer)
                        if name=='adj' else record==struct.pack('<I',pointer))
                if read(listing,4)!=lst[:4]:raise ValueError('list identity changed')
            if read(pointer,4)!=data[:4]:raise ValueError('controller identity changed')
        if read(FACTORY+slot,4)!=header[slot:slot+4]:
            raise ValueError('controller factory slot changed')
        objects[name]=item
    image_guard=read(0x5539FC84,4)
    image_owner=read(0x5539FC64,0x20)
    image={'guard_hex':image_guard.hex(),'owner_hex':image_owner.hex(),
           'calculator':None}
    if struct.unpack('<I',image_guard)[0]&1:
        if struct.unpack_from('<I',image_owner)[0]!=0x53FD8B20:
            raise ValueError('image factory class mismatch')
        vt=read(0x53FD8B20,0x20)
        if vt!=raw[file_offset(0x53FD8B20):file_offset(0x53FD8B20)+0x20]:
            raise ValueError('image factory class pin mismatch')
        calculator=struct.unpack_from('<I',image_owner,0x14)[0]
        if calculator:
            if not in_heap(calculator,4):raise ValueError('calculator outside original heap')
            if read(calculator,4)!=struct.pack('<I',0x53FD89A0):
                raise ValueError('active calculator class mismatch')
            table=read(0x53FD89A0,0x40)
            if table!=raw[file_offset(0x53FD89A0):file_offset(0x53FD89A0)+0x40]:
                raise ValueError('active calculator vtable mismatch')
            image['calculator']={'address':hex(calculator),'vtable':hex(0x53FD89A0),
                                 'vtable_hex':table.hex(),'owner_slot_verified':True}
        if read(0x5539FC84,4)!=image_guard or read(0x5539FC64,0x20)!=image_owner:
            raise ValueError('image factory changed while reading')
    class_scan=scan_classes(read,raw) if scan else None
    if read(FACTORY_GUARD,4)!=guard or read(FACTORY,4)!=header[:4]:
        raise ValueError('factory identity changed')
    if read(0x55085D63,5)!=before:
        raise ValueError('capture properties changed')
    if read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)!=saved:
        raise ValueError('script callbacks/scratch changed')
    return {'schema':'gr4-ui-routes-readonly-v2','offline_audit':evidence,
            'widget_audit':widget_evidence,'live_widget_code_pins_matched':True,
            'factory_guard_hex':guard.hex(),'factory_header_hex':header.hex(),
            'objects':objects,'capture_properties_hex':before.hex(),
            'capture_properties_unchanged':True,'callbacks_and_scratch_unchanged':True,
            'camera_memory_written':False,'native_functions_called':False,
            'image_factory':image,'class_scan':class_scan,'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--offline',action='store_true')
    p.add_argument('--scan-classes',action='store_true',
                   help='also locate pinned class pointers in the original bounded arenas')
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes()
    result=audit(raw)
    if not args.offline:
        device=usb.core.find(idVendor=VID,idProduct=PID)
        if device is None or device.bcdDevice!=0x0111:raise RuntimeError('expected connected GR IV 01.11.10.07')
        usb.util.claim_interface(device,0);io=Transport(device);opened=False
        try:
            code,info,_=command(device,0x1001,0)
            if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS:
                raise RuntimeError('unexpected device information')
            code,_,_=command(device,0x1002,1,1);opened=code==0x2001
            if code not in (0x2001,0x201E):raise RuntimeError('OpenSession failed')
            result=collect(io.read,raw,args.scan_classes)
        finally:
            try:
                if opened:command(device,0x1003,io.transaction)
            finally:
                usb.util.release_interface(device,0);usb.util.dispose_resources(device)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    if 'objects' in result:
        print(json.dumps({k:{f:v for f,v in o.items() if f not in ('object_hex','list')}
                          for k,o in result['objects'].items()},indent=2))
        if result['class_scan']:
            print(json.dumps(result['class_scan']['pointer_sightings'],indent=2))
        print('Owned image calculator:',json.dumps(result['image_factory']['calculator']))
    else:print(json.dumps(result,indent=2))
    print('Saved:',args.report)


if __name__=='__main__':main()
