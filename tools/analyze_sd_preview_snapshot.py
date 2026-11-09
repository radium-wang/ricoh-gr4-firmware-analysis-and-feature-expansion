#!/usr/bin/env python3
"""Analyze bounded shooting snapshots, retaining absent and changing objects.

Reads diagnostic files only; relationships never establish frame ownership,
task quiescence, pixel-buffer bounds or installation readiness.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

NAMES=re.compile(r'(ROOT|REG|NODE\d{1,3}|TASK\d{1,3}|PROCESS|PROCEND|SPECIAL|MANAGER|INFO|COLL|COLLEND|ID[0-7]|LINK[0-7]|RASTER[0-7]|JPEG)[ABC]\.BIN\Z')


def analyze(directory):
    files={}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name.upper() in ('RESTORE.TTL','README.TXT'):continue
        if not path.is_file() or not NAMES.fullmatch(path.name.upper()):
            raise ValueError('unexpected diagnostic entry: '+path.name)
        data=path.read_bytes()
        if len(data)>960:raise ValueError('diagnostic file too large')
        name=path.name.upper()
        if name in files:raise ValueError('duplicate diagnostic filename')
        files[name]=data
    stages=[]
    def read(kind,suffix,size):
        data=files.get(kind+suffix+'.BIN')
        if data is not None and len(data)!=size:raise ValueError('wrong diagnostic length: '+kind+suffix)
        return data
    for suffix in 'ABC':
        stage={'stage':suffix,'recipes':[],'problems':[]}
        process=read('PROCESS',suffix,960);end=read('PROCEND',suffix,960)
        collection=read('COLL',suffix,48);collend=read('COLLEND',suffix,48)
        manager=read('MANAGER',suffix,16);info=read('INFO',suffix,120)
        special=read('SPECIAL',suffix,8);jpeg=read('JPEG',suffix,120)
        if process is None:stage['problems'].append('preview_process_absent')
        else:
            if struct.unpack_from('<2I',process)!=(0x53EB11F0,0x53EB1228):
                raise ValueError('unexpected original preview classes')
            manager_pointer=struct.unpack_from('<I',process,0x398)[0]
            stage.update(native_aspect=process[0x8D],native_mode=process[0x91],
                         crop_Q13=struct.unpack_from('<I',process,0x94)[0],
                         manager_pointer=hex(manager_pointer),
                         collection_pointer=hex(struct.unpack_from('<I',process,0x3B0)[0]),
                         process_owner_links_unchanged=bool(end and process[:8]==end[:8] and
                             process[0x398:0x3B4]==end[0x398:0x3B4]),
                         special_window_byte=special[4] if special is not None else None)
            if end is None:stage['problems'].append('process_end_read_absent')
        if manager is not None:
            if struct.unpack_from('<I',manager)[0]!=0x53FD19F8:raise ValueError('unexpected resolution class')
            stage.update(resolution=manager[10],manager_source_mode=manager[9],manager_external_flag=manager[11])
        if info is not None:
            if struct.unpack_from('<I',info)[0]!=0x53FD1830:raise ValueError('unexpected information class')
            stage['selected_window_unverified_units']=list(struct.unpack_from('<4I',info,0x64))
        if collection is not None:
            slots=struct.unpack_from('<8I',collection,8)
            stage['slots']=[hex(p) for p in slots]
            stage['collection_slots_unchanged']=bool(collend and collection[8:40]==collend[8:40])
            stage['eight_unique_nonnull_slots']=bool(all(slots) and len(set(slots))==8)
            for i,pointer in enumerate(slots):
                identity=read('ID'+str(i),suffix,8);link=read('LINK'+str(i),suffix,12)
                fields=read('RASTER'+str(i),suffix,68)
                if not pointer:continue
                row={'index':i,'address':hex(pointer),'class_verified':False,'fields_available':False}
                if identity is not None:row['class_verified']=struct.unpack_from('<I',identity)[0]==0x53EB16E8
                if fields is not None:
                    if not row['class_verified'] or link is None:raise ValueError('raster without pinned recipe identity/link')
                    row.update(fields_available=True,
                               manager_matches_process=process is not None and struct.unpack_from('<I',link,8)[0]==manager_pointer,
                               active_WH=list(struct.unpack_from('<2H',fields,0x26)),
                               center_XY=list(struct.unpack_from('<2H',fields,0x30)),
                               reference_WH=list(struct.unpack_from('<2H',fields,0x34)),
                               native_base_WH=list(struct.unpack_from('<2H',fields,0x3A)),
                               crop_Q13=struct.unpack_from('<I',fields,0x40)[0],
                               flag_BBE=fields[14],flag_BC4=fields[20])
                stage['recipes'].append(row)
        else:stage['problems'].append('recipe_collection_absent')
        if jpeg is not None:
            stage['JPEG']={'config_pointer':hex(struct.unpack_from('<I',jpeg,4)[0]),
                           'source_WH_pitch':list(struct.unpack_from('<3H',jpeg,24)),
                           'capture_frame_or_encoded_output_verified':False}
        stages.append(stage)
    return {'schema':'gr4-sd-preview-analysis-v12','stages':stages,
            'files':[{'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in files.items()],
            'file_count':len(files),'diagnostic_bytes':sum(map(len,files.values())),
            'atomic_snapshot_worker_quiescence_and_pixel_bounds_verified':False,
            'xpan_installed':False,'PREVIEW_READY':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();result=analyze(a.directory)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('Analyzed',result['file_count'],'finite diagnostic files; XPAN not installed')
