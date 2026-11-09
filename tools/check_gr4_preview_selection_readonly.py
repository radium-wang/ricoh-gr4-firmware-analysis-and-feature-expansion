#!/usr/bin/env python3
"""Bounded read models for native preview selection and runtime dispatch slots."""
import argparse
import json
from pathlib import Path
import struct
from audit_xpan_paths import file_offset
from mtp_factory_capture_state_readonly import preview_selection, ROOT


def check(raw):
    preview,pointer,service=0x59CD6290,0x59A550F0,0x59A58000
    links=struct.pack('<4I',0x59A589F8,0x59A55048,pointer,0x59A4C000)
    pack=lambda v:struct.pack('<%dI'%len(v),*v)
    fixed={(pointer,4):pack([0x53FD1830]),(pointer+0x54,32):pack([1,2,3,4,5,6,7,8]),
           (pointer+0x253C,4):pack([service]),(0x5537960C,8):pack([0x53F85DD0,service]),
           (service,4):pack([0x53F8EDE8]),
           (0x53F8EDE8,16):raw[file_offset(0x53F8EDE8):file_offset(0x53F8EDE8)+16],
           (0x55019318,8):pack([0x53740000,0]),(0x55018A50,8):pack([0x53740004,0]),
           (0x55397548,20):pack([5,6,7,8,1]),(service+0x518,4):pack([0x59A59000]),
           (0x59A59000,12):pack([0x59A60000,0x59A62000,0x59A64000]),
           (0x59A60000+0x6C0,16):pack([5,6,7,8]),(0x59A60000+0xF08,16):pack([5,6,7,8]),
           (0x59A62000+0x6C0,16):pack([5,6,7,8]),(0x59A62000+0xF08,16):pack([5,6,7,8]),
           (preview+0x398,16):links}
    cases=[]
    for fault in ('normal','null-information','wrong-information-class','null-service',
                  'wrong-holder','wrong-service-class','wrong-service-ROM','changed-table',
                  'changed-owner','short-table','changed-property-images','null-property-image',
                  'high-property-arena','wrong-high-map','outside-property-span'):
        data=dict(fixed); supplied=links; reads=[]
        if fault=='null-information': supplied=links[:8]+bytes(4)+links[12:]
        if fault=='wrong-information-class': data[pointer,4]=bytes(4)
        if fault=='null-service': data[pointer+0x253C,4]=bytes(4)
        if fault=='wrong-holder': data[0x5537960C,8]=pack([0x53F85DD0,service+4])
        if fault=='wrong-service-class': data[service,4]=bytes(4)
        if fault=='wrong-service-ROM': data[0x53F8EDE8,16]=bytes(16)
        if fault=='changed-owner': data[preview+0x398,16]=bytes(16)
        if fault=='short-table': data[0x55019318,8]=bytes(7)
        if fault=='null-property-image': data[0x59A59000,12]=pack([0,0x59A62000,0x59A64000])
        if fault in ('high-property-arena','wrong-high-map','outside-property-span'):
            high=0x5D7A10B8 if fault!='outside-property-span' else 0x60000000
            data[0x59A59000,12]=pack([high,0x59A62000,0x59A64000])
            for offset in (0x6C0,0xF08): data[high+offset,16]=pack([5,6,7,8])
            slot=0x53004000+(high>>20)*4
            data[slot,4]=(bytes(4) if fault=='wrong-high-map' else
                          raw[file_offset(slot):file_offset(slot)+4])
        def read(address,size):
            key=address,size
            assert key in data,'unexpected address or length'
            reads.append(key)
            if fault=='changed-table' and key==(0x55019318,8) and reads.count(key)>1:
                return bytes(8)
            if fault=='changed-property-images' and key==(0x59A59000,12) and reads.count(key)>1:
                return bytes(12)
            return data[key]
        rejected=False
        try: report=preview_selection(read,raw,preview,supplied)
        except ValueError: rejected=True
        assert rejected==(fault not in ('normal','high-property-arena'))
        if fault in ('normal','high-property-arena'):
            assert report['selected_window']==[5,6,7,8] and len(report['dispatch_slots'])==2
            assert not report['dispatch_functions_called']
            assert not report['atomic_snapshot_or_LCD_consumer_verified']
        if fault=='null-information': assert not reads
        if fault in ('wrong-information-class','null-service','wrong-holder',
                     'wrong-service-class','wrong-service-ROM'):
            assert (0x55019318,8) not in reads
        cases.append({'case':fault,'rejected':rejected,'bounded_reads':len(reads)})
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True); args=parser.parse_args()
    cases=check((ROOT/'samples/gr4_decoded.bin').read_bytes())
    with args.out.open('x') as handle:
        json.dump({'passed':True,'cases':cases,'camera_access':False},handle,indent=2)
        handle.write('\n')
    print('%d bounded selection read models passed; no camera access'%len(cases))


if __name__=='__main__': main()
