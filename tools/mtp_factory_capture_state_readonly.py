#!/usr/bin/env python3
"""Read finite JPEG/preview state from freshly registered image workers.

Fields are observations, not allocation/locking or per-capture ownership proof.
No pixels, writes, function calls, SD updates or hook installation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import usb.core
import usb.util
from audit_xpan_paths import file_offset, EXPECTED_SHA256
from mtp_factory_capture_pipeline_readonly import workers, ROOT
from mtp_factory_task_mapping_readonly import ram
from mtp_factory_pointer_trial import Transport
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_probe_readonly import VID, PID, command


def preview_information(read, raw, preview, links):
    """Finite observations only; equal identities do not prove atomic state."""
    pointer = struct.unpack_from('<I', links, 8)[0]  # process +3A0, not +378
    ram(pointer, 0x2570)
    vtable = struct.pack('<I', 0x53FD1830)
    if read(pointer, 4) != vtable:
        raise ValueError('LiveViewInformation class mismatch')
    if read(0x53FD1830, 0x18) != raw[file_offset(0x53FD1830):file_offset(0x53FD1830)+0x18]:
        raise ValueError('LiveViewInformation ROM pin differs')
    fields = []
    for offset, size, role in ((4, 0x40, 'bases_and_two_virtual_windows'),
                               (0x78, 0x18, 'published_window_fields'),
                               (0x1CD4, 4, 'coordinate_divisor'),
                               (0x24E8, 0x14, 'mutex_bytes_not_idle_proof'),
                               (0x2540, 0x30, 'publication_state')):
        data = read(ram(pointer+offset, size), size)
        if len(data) != size:
            raise ValueError('short LiveViewInformation field read')
        fields.append({'role': role, 'offset': hex(offset), 'hex': data.hex()})
    if read(pointer, 4) != vtable or read(ram(preview+0x398, 0x10), 0x10) != links:
        raise ValueError('LiveViewInformation owner or identity changed')
    return {'address': hex(pointer), 'vtable': hex(0x53FD1830), 'fields': fields,
            'units_and_LCD_pixel_mapping_verified': False, 'atomic_snapshot_verified': False,
            'mutex_acquired': False}


def property_image_ram(read, raw, address, length):
    """Finite read-only span reached from CommonPropertyManager, not heap ownership.

    Some property copies live beyond the existing application-pointer guard.
    Require both pinned sample and live initial section descriptors there;
    this does not prove a task's current TTBR or permit writes/allocations.
    """
    if 0x59000000 <= address and address+length <= 0x5C000000:
        return ram(address,length)
    if (address%4 or not 1<=length<=0x1090 or
        not 0x5C000000<=address<address+length<=0x60000000):
        raise ValueError('invalid finite property-image span')
    for section in range(address>>20, ((address+length-1)>>20)+1):
        slot=0x53004000+section*4
        expected=raw[file_offset(slot):file_offset(slot)+4]
        descriptor,=struct.unpack('<I',expected)
        if (descriptor&3!=2 or descriptor&0xFFF00000!=section<<20 or
            (((descriptor>>15)&1)<<2 | (descriptor>>10)&3)!=3 or
            read(slot,4)!=expected):
            raise ValueError('property image initial mapping pin differs')
    return address


def preview_selection(read, raw, preview, links):
    """Read only selected windows and the two fixed message-84 dispatch slots.

    The dispatch table is runtime RAM, not bytes at an equivalent ROM offset.
    No message is sent and no table function is called.
    """
    from audit_gr4_preview_selection import audit
    audit(raw)
    pointer = struct.unpack_from('<I', links, 8)[0]
    ram(pointer, 0x2570)
    identity = struct.pack('<I', 0x53FD1830)
    if read(pointer, 4) != identity: raise ValueError('information identity mismatch')
    windows = read(ram(pointer+0x54, 32), 32)
    service_slot = read(ram(pointer+0x253C, 4), 4)
    service, = struct.unpack('<I', service_slot)
    ram(service, 0x51C)
    holder = read(0x5537960C, 8)
    if holder != struct.pack('<2I', 0x53F85DD0, service):
        raise ValueError('information service differs from fresh factory holder')
    service_vt = struct.pack('<I', 0x53F8EDE8)
    if read(service, 4) != service_vt: raise ValueError('CommonPropertyIf class mismatch')
    if read(0x53F8EDE8, 16) != raw[file_offset(0x53F8EDE8):file_offset(0x53F8EDE8)+16]:
        raise ValueError('CommonPropertyIf ROM class pin differs')
    dispatch = []
    for table, role in ((0x55018EF8, 'set'), (0x55018630, 'get')):
        address = table+0x84*8
        data = read(address, 8)
        if len(data) != 8: raise ValueError('short command-84 table read')
        dispatch.append({'role': role, 'address': hex(address), 'hex': data.hex(),
                         'words': list(struct.unpack('<2I', data))})
    published = read(0x55397548, 20)
    property_link = read(ram(service+0x518, 4), 4)
    manager, = struct.unpack('<I', property_link)
    header = read(ram(manager, 12), 12)
    current, pending, dirty = struct.unpack('<3I', header)
    images = []
    for role, base in (('current', current), ('pending', pending)):
        property_image_ram(read,raw,base,0x1090)
        fields = []
        for offset in (0x6C0, 0xF08):
            data = read(base+offset, 16)
            fields.append({'offset': hex(offset), 'words': list(struct.unpack('<4I', data))})
        images.append({'role': role, 'address': hex(base), 'windows': fields})
    if (read(service+0x518, 4) != property_link or read(manager, 12) != header):
        raise ValueError('CommonPropertyManager image ownership changed')
    if (read(pointer, 4) != identity or read(pointer+0x253C, 4) != service_slot or
        read(service, 4) != service_vt or read(0x5537960C, 8) != holder or
        read(ram(preview+0x398, 16), 16) != links):
        raise ValueError('selection/service ownership changed during read')
    for slot in dispatch:
        if read(int(slot['address'],16),8).hex() != slot['hex']:
            raise ValueError('command-84 table changed during read')
    return {'information': hex(pointer), 'service': hex(service),
            'special_and_selected_windows_hex': windows.hex(),
            'special_window': list(struct.unpack_from('<4I', windows)),
            'selected_window': list(struct.unpack_from('<4I', windows, 16)),
            'dispatch_slots': dispatch, 'published_buffer_and_guard_hex': published.hex(),
            'property_link_hex': property_link.hex(), 'property_manager': hex(manager),
            'property_images': images, 'dirty_list_pointer': hex(dirty),
            'dispatch_functions_called': False,
            'atomic_snapshot_or_LCD_consumer_verified': False}


def preview_collection_status(read, raw, preview):
    """Observe fixed collection slots even when USB mode has released recipes.

    Never follow a slot here. Null/repeated slots are observations, not recipe
    ownership validation and not permission to install a hook.
    """
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256: raise ValueError('unsupported sample')
    for address, size in ((0x53648034,128),(0x5363F98C,8)):
        if read(address,size)!=raw[file_offset(address):file_offset(address)+size]:
            raise ValueError('collection constructor/owner ROM differs')
    link=read(ram(preview+0x3B0,4),4)
    collection,=struct.unpack('<I',link)
    result={'collection':hex(collection),'slots':[], 'recipes_followed':False,
            'atomic_frame_or_quiescence_verified':False}
    if collection:
        ram(collection,0x30)
        prefix=read(collection,0x30)
        if len(prefix)!=0x30: raise ValueError('short recipe collection header')
        slots=struct.unpack_from('<8I',prefix,8)
        result.update({'prefix_hex':prefix.hex(), 'slots':[hex(v) for v in slots],
                       'nonnull_slots':sum(bool(v) for v in slots),
                       'eight_unique_nonnull_slots':bool(all(slots) and len(set(slots))==8)})
        if read(collection,0x30)!=prefix: raise ValueError('collection header changed')
    if read(preview+0x3B0,4)!=link: raise ValueError('collection owner changed')
    return result


def preview_recipes(read,raw,preview):
    """Eight fixed collection slots from original constructor, bounded fields only."""
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256: raise ValueError('unsupported sample')
    pin=raw[file_offset(0x53648034):file_offset(0x53648034)+128]
    if read(0x53648034,128)!=pin: raise ValueError('recipe browser constructor ROM differs')
    if read(0x5363F98C,8)!=raw[file_offset(0x5363F98C):file_offset(0x5363F98C)+8]:
        raise ValueError('recipe collection owner/constructor call ROM differs')
    link=read(ram(preview+0x3B0,4),4);collection,=struct.unpack('<I',link)
    ram(collection,0x28)
    slots=read(collection+8,32);pointers=struct.unpack('<8I',slots)
    if len(set(pointers))!=8: raise ValueError('recipe slots are not eight unique objects')
    vt=struct.pack('<I',0x53EB16E8)
    if read(0x53EB16E8,8)!=raw[file_offset(0x53EB16E8):file_offset(0x53EB16E8)+8]:
        raise ValueError('recipe ROM class differs')
    recipes=[]
    for index,pointer in enumerate(pointers):
        ram(pointer,0x19F0)
        identity=read(pointer,8)
        if identity[:4]!=vt: raise ValueError('native recipe class mismatch')
        links=read(pointer+0x32C,12)
        manager=struct.unpack_from('<I',links,8)[0]
        fields=read(pointer+0xBB0,0x44)
        if len(fields)!=0x44: raise ValueError('short native recipe raster fields')
        recipes.append({'index':index,'address':hex(pointer),'identity_hex':identity.hex(),
                        'links_32c_hex':links.hex(),'resolution_manager':hex(manager),
                        'raster_fields_bb0_hex':fields.hex(),
                        'active_WH':list(struct.unpack_from('<2H',fields,0x26)),
                        'center_XY':list(struct.unpack_from('<2H',fields,0x30)),
                        'reference_WH':list(struct.unpack_from('<2H',fields,0x34)),
                        'native_base_WH':list(struct.unpack_from('<2H',fields,0x3A))})
        if read(pointer,8)!=identity or read(pointer+0x32C,12)!=links:
            raise ValueError('recipe identity or linked fields changed')
    if read(preview+0x3B0,4)!=link or read(collection+8,32)!=slots:
        raise ValueError('recipe collection ownership changed')
    return {'collection':hex(collection),'slots_hex':slots.hex(),'recipes':recipes,
            'atomic_frame_or_quiescence_verified':False,'native_functions_called':False}


def collect(read,raw,include_preview_information=False,include_preview_selection=False,
            include_preview_recipes=False,include_preview_collection=False,
            include_jpeg_config=True):
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA256: raise ValueError('unsupported sample')
    saved=read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)
    if saved!=struct.pack('<2I',0x538EF3C8,0x538EF9F0)+bytes(20): raise ValueError('original callbacks/scratch required')
    props=read(0x55085D63,5)
    tasks,registry,header,slot=workers(read)
    def pick(vtable,base_offset):
        matching=[t for t in tasks if int(t['vtable'],16)==vtable]
        if len(matching)!=1: raise ValueError('expected unique native image worker')
        task=matching[0]; base=int(task['object'],16)
        if read(base,12).hex()!=task['identity_hex']: raise ValueError('worker identity changed')
        return base-base_offset,task
    jpeg,jpeg_task=pick(0x53ECFC58,0)
    preview,preview_task=pick(0x53EB1228,4)
    control,control_task=pick(0x53EB0D70,4)
    for vt,length in ((0x53ECFC58,0x30),(0x53EB11F0,0x34),(0x53EB0D40,0x28)):
        if read(vt,length)!=raw[file_offset(vt):file_offset(vt)+length]: raise ValueError('native image class pin differs')
    def fixed(obj,offset,size): return read(ram(obj+offset,size),size)
    jpeg_state=fixed(jpeg,0x8A44,0x78)
    capture_config=struct.unpack_from('<I',jpeg_state,4)[0]
    config=None
    if capture_config:
        config={'address':hex(capture_config),'fields_read':False,
                'capture_is_not_proven_current':True}
        if include_jpeg_config:
            ram(capture_config,0xB78)
            aspect=fixed(capture_config,0x7D8,12)
            dims=fixed(capture_config,0xB70,8)
            config.update(fields_read=True,aspect_crop_size_bytes_hex=aspect.hex(),
                          window_and_full_dimensions=list(struct.unpack('<4H',dims)))
        else:
            config['not_read_reason']='deep JPEG configuration explicitly omitted'
        if fixed(jpeg,0x8A48,4)!=struct.pack('<I',capture_config): raise ValueError('JPEG config changed')
    source=jpeg_state[8:40]
    preview_state=fixed(preview,0x64,0x3C)
    preview_links=fixed(preview,0x398,0x10)
    manager,debug,information,image_map=struct.unpack('<4I',preview_links)
    information_state = (preview_information(read, raw, preview, preview_links)
                         if include_preview_information or include_preview_selection else None)
    selection_state = (preview_selection(read, raw, preview, preview_links)
                       if include_preview_selection else None)
    recipe_state=(preview_recipes(read,raw,preview) if include_preview_recipes else None)
    collection_state=(preview_collection_status(read,raw,preview)
                      if include_preview_collection else None)
    linked=[]
    for pointer,vt,name,size in ((manager,0x53FD19F8,'resolution_manager',0x10),
                              (image_map,0x53FCF708,'preview_image_map',0x20)):
        data=read(ram(pointer,size),size)
        if struct.unpack_from('<I',data)[0]!=vt: raise ValueError('linked preview class mismatch')
        if read(vt,0x40)!=raw[file_offset(vt):file_offset(vt)+0x40]: raise ValueError('linked class ROM pin differs')
        if read(pointer,4)!=data[:4]: raise ValueError('linked preview object changed')
        linked.append({'role':name,'address':hex(pointer),'prefix_hex':data.hex()})
    control_links=fixed(control,0x34,8)
    # Three native mutexes begin at +70/+B4/+CC (constructors pinned offline).
    # This only records bytes; it neither takes these locks nor claims idle.
    mutexes=[{'offset':hex(offset),'hex':fixed(control,offset,0x14).hex()} for offset in (0x70,0xB4,0xCC)]
    for task in (jpeg_task,preview_task,control_task):
        if read(int(task['object'],16),12).hex()!=task['identity_hex']: raise ValueError('image worker identity changed')
    if (read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)!=saved or
        read(0x55085D63,5)!=props or read(registry,16)!=header): raise ValueError('restore state/registry changed')
    return {'schema':'gr4-capture-state-readonly-v1','sample_sha256':EXPECTED_SHA256,
            'JPEG':{'object':hex(jpeg),'worker':jpeg_task,'state_8a44_hex':jpeg_state.hex(),
                    'deep_config_read_requested':include_jpeg_config,
                    'config':config,'source_descriptor_hex':source.hex(),
                    'source_format':source[0],'source_planes':list(struct.unpack_from('<2I',source,4)),
                    'source_width_height_pitch':list(struct.unpack_from('<3H',source,0x10))},
            'preview':{'object':hex(preview),'worker':preview_task,'state_64_hex':preview_state.hex(),
                       'native_aspect_byte_8d':preview_state[0x8D-0x64],
                       'links_398_hex':preview_links.hex(),'linked_objects':linked,
                       'information_snapshot':information_state,
                       'selection_snapshot':selection_state,'recipe_snapshot':recipe_state,
                       'recipe_collection_snapshot':collection_state},
            'control':{'object':hex(control),'worker':control_task,'links_34_hex':control_links.hex(),
                       'mutex_snapshots_not_idle_proof':mutexes},
            'callbacks_scratch_properties_unchanged':True,'camera_memory_written':False,
            'native_functions_called':False,'worker_quiescence_and_pixel_bounds_verified':False,
            'xpan_installed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--preview-information', action='store_true',
                   help='Also read finite LiveViewInformation coordinates/publication state')
    p.add_argument('--preview-selection', action='store_true',
                   help='Include windows, CommonPropertyIf link and two fixed command-84 dispatch slots')
    p.add_argument('--preview-recipes', action='store_true',
                   help='Include eight fixed collection recipe slots and bounded raster fields')
    p.add_argument('--preview-collection', action='store_true',
                   help='Observe collection header/slots without following recipe pointers')
    p.add_argument('--skip-jpeg-config', action='store_true',
                   help='Record JPEG worker state without following its separate config pointer')
    a=p.parse_args()
    if a.report.exists(): raise ValueError('immutable report exists')
    dev=usb.core.find(idVendor=VID,idProduct=PID)
    if dev is None or dev.bcdDevice!=0x111: raise RuntimeError('expected connected GR IV')
    usb.util.claim_interface(dev,0);io=Transport(dev);opened=False;close_code=None
    try:
        code,info,_=command(dev,0x1001,0)
        if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS: raise RuntimeError('unexpected DeviceInfo')
        code,_,_=command(dev,0x1002,1,1);opened=code==0x2001
        if code not in (0x2001,0x201E): raise RuntimeError('OpenSession failed')
        result=collect(io.read,(ROOT/'samples/gr4_decoded.bin').read_bytes(),
                       a.preview_information,a.preview_selection,a.preview_recipes,a.preview_collection,
                       not a.skip_jpeg_config)
    finally:
        try:
            if opened: close_code,_,_=command(dev,0x1003,io.transaction)
        finally:
            usb.util.release_interface(dev,0);usb.util.dispose_resources(dev)
    result['USB_session']={'opened_by_probe':opened,
                           'close_response':hex(close_code) if close_code is not None else None,
                           'interface_released':True}
    a.report.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved:',a.report)
    print('JPEG dimensions:',result['JPEG']['source_width_height_pitch'])
    print('Preview native aspect:',result['preview']['native_aspect_byte_8d'])
