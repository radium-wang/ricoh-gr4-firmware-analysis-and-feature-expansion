#!/usr/bin/env python3
"""Locate pinned menu objects in the original bounded RAM arenas using GetData.

No SetData, function calls, settings changes, uploads or arbitrary addresses.
Only class matches are followed. Bulk data is hashed, not saved as a RAM dump.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import usb.core
import usb.util
from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from mtp_factory_allocator_readonly import collect as allocator_context
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_probe_readonly import VID, PID, command

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = 0x53D9F6A0
SECONDARY = PRIMARY + 0x4C
CHUNK = 65536
HIDE = 0x53B1C55C
PUBLISH = 0x53B1C518


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported firmware sample')
    pins = {
        PRIMARY: '502c1853c0a11b5318a21b53a82b185300a11b5358451853b42b1853c4fc1b53',
        SECONDARY: '10a21b533ca21b53bcdd1b53',
        0x531BA1D0: '34309fe504b04ce22720a0e3003080e54c3083e2583180e5',
        0x531BA20C: 'a0f6d953',
        0x531BE980: 'f80195e5',  # controller owns list at +0x1f8
        0x531BE9D0: '8c230fe31b2345e3',  # original list callback target
        0x53570EE0: '5a3f84e2',  # list callback record stored at +0x168
        PUBLISH: 'b83a02e33b3545e3002093e5000052e3b42a02033b2545030020920500208305',
        HIDE: 'b82a02e3bc3c03e33b2545e33b3545e30010a0e3001082e5001083e51eff2fe1',
    }
    for address, expected in pins.items():
        require(raw,file_offset(address),bytes.fromhex(expected),hex(address))
    return {'sample_sha256':EXPECTED_SHA256,'pins':len(pins),
            'primary_vtable':hex(PRIMARY),'secondary_vtable':hex(SECONDARY),
            'interpreter_names_hide':hex(HIDE),'interpreter_names_publish':hex(PUBLISH),
            'name_pointer_clear_is_not_alone_proof_of_script_exit':True}


def collect(read, raw, progress=None):
    evidence = audit(raw)
    heap = allocator_context(read)
    base, size = heap['arena_base'], heap['arena_length']
    if (base,size) != (0x59600000,0xFFFFF0):
        raise ValueError('heap arena differs from the observed/pinned original allocator')
    before = read(0x55085D63,5)
    callbacks = read(0x553B1948,4) + read(0x553B1A30,4) + read(0x553B1990,20)
    if callbacks[:8] != struct.pack('<2I',0x538EF3C8,0x538EF9F0):
        raise ValueError('original script callbacks required')
    for address,length in ((PRIMARY,0x44),(SECONDARY,12)):
        if read(address,length) != raw[file_offset(address):file_offset(address)+length]:
            raise ValueError('live menu class table mismatch')
    ranges = ((0x55080000,0x20000),(base,size))
    matches = []
    scans = []
    needles = {PRIMARY:struct.pack('<I',PRIMARY),SECONDARY:struct.pack('<I',SECONDARY)}
    for start,length in ranges:
        digest = hashlib.sha256()
        for offset in range(0,length,CHUNK):
            block = read(start+offset,min(CHUNK,length-offset))
            digest.update(block)
            for vtable,needle in needles.items():
                at = 0
                while True:
                    index = block.find(needle,at)
                    if index < 0:
                        break
                    address = start+offset+index
                    if address % 4 == 0:
                        matches.append((address,vtable))
                    at = index+1
            if len(matches)>128:
                raise ValueError('unexpected number of class candidates')
            if progress and offset % (4*1024*1024) == 0:
                progress({'scanned_start':hex(start),'bytes_read':offset+len(block)})
        scans.append({'start':hex(start),'bytes':length,'sha256':digest.hexdigest()})
    objects = []
    candidates = sorted(set(address if vtable==PRIMARY else address-0x158
                            for address,vtable in matches))
    for address in candidates:
        if not any(lo <= address < address+0x290 <= lo+n for lo,n in ranges):
            continue
        data = read(address,0x290)
        if struct.unpack_from('<I',data)[0] != PRIMARY or struct.unpack_from('<I',data,0x158)[0] != SECONDARY:
            continue
        item = {'address':hex(address),'hex':data.hex(),'two_original_vtables_match':True,
                'list_address':hex(struct.unpack_from('<I',data,0x1F8)[0]),
                'selected_category_byte':data[0x1FC],'list_callback':None}
        pointer = struct.unpack_from('<I',data,0x1F8)[0]
        if pointer % 4 == 0 and base <= pointer < pointer+0x190 <= base+size:
            obj = read(pointer,0x190)
            vt = struct.unpack_from('<I',obj)[0]
            if 0x53D00000 <= vt < 0x54400000:
                item['list_hex']=obj.hex()
                item['list_vtable']=hex(vt)
                callback = struct.unpack_from('<I',obj,0x168)[0]
                if callback % 4 == 0 and base <= callback < callback+12 <= base+size:
                    record=read(callback,12)
                    item['list_callback']={'address':hex(callback),'hex':record.hex(),
                        'matches_original_target_and_owner':record==struct.pack('<3I',0x531BF38C,0,address)}
        if read(address,4)+read(address+0x158,4) != struct.pack('<2I',PRIMARY,SECONDARY):
            raise ValueError('menu object class changed while reading')
        objects.append(item)
    after = read(0x55085D63,5)
    restored=read(0x553B1948,4)+read(0x553B1A30,4)+read(0x553B1990,20)
    if before!=after or restored!=callbacks:
        raise ValueError('capture state or restored callbacks changed')
    return {'schema':'gr4-menu-object-readonly-v1','offline_audit':evidence,
            'scans':scans,'raw_vtable_matches':[{'address':hex(a),'vtable':hex(v)} for a,v in matches],
            'menu_objects':objects,'capture_properties_unchanged':True,
            'callbacks_and_scratch_restored':True,'camera_memory_written':False,
            'native_functions_called':False,'xpan_installed':False,
            'limits':['Class candidates are read-only snapshots; no live UI hook is established.',
                      'A missing object may not exist in the current USB UI state.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes()
    result=audit(raw)
    if not args.offline:
        device=usb.core.find(idVendor=VID,idProduct=PID)
        if device is None or device.bcdDevice!=0x0111:raise RuntimeError('expected GR IV 01.11.10.07')
        usb.util.claim_interface(device,0);io=Transport(device);opened=False
        try:
            code,info,_=command(device,0x1001,0)
            if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS:
                raise RuntimeError('unexpected device information')
            code,_,_=command(device,0x1002,1,1);opened=code==0x2001
            if code not in (0x2001,0x201E):raise RuntimeError('OpenSession failed')
            result=collect(io.read,raw,lambda p:print(json.dumps(p),flush=True))
        finally:
            try:
                if opened:command(device,0x1003,io.transaction)
            finally:
                usb.util.release_interface(device,0);usb.util.dispose_resources(device)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('scans','menu_objects')},indent=2))
    if 'menu_objects' in result:print('Verified menu objects:',len(result['menu_objects']))


if __name__=='__main__':main()
