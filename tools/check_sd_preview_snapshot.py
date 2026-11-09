#!/usr/bin/env python3
"""Execute generated TTL with synthetic objects; no camera or SD access."""
import argparse
import json
import struct
import tempfile
from pathlib import Path
from build_sd_preview_snapshot import program,build
from validate_sd_batch_probe import FlowCheck


class PreviewFlow(FlowCheck):
    def __init__(self,case):
        super().__init__();self.case=case
        self.memory[0x5960F000]=self.memory[self.bridge]
        self.bridge=0x5960F000
        def words(values):return bytearray(struct.pack('<%dI'%len(values),*values))
        registry,node1,node2=0x59601000,0x59602000,0x59602010
        process,jpeg,collection=0x59900000,0x59A00000,0x59603000
        self.memory[0x553A0030]=words([registry])
        self.memory[registry]=words([0x59600000,128,node1,2,0,0,0,0])
        self.memory[node1]=words([node2,0x1000005,process+4])
        self.memory[node2]=words([0,0x1000006,jpeg])
        obj=bytearray(960);struct.pack_into('<4I',obj,0,0x53EB11F0,0x53EB1228,0x1000005,0)
        struct.pack_into('<I',obj,0x3B0,collection)
        struct.pack_into('<I',obj,0x398,0x59604000);struct.pack_into('<I',obj,0x3A0,0x59605000)
        self.memory[process]=obj
        self.memory[process+0x97A0]=bytearray(8)
        raster=bytearray(68)
        for offset,values in ((0x26,[720,480]),(0x30,[0,0]),(0x34,[720,480]),(0x3A,[720,480])):
            struct.pack_into('<2H',raster,offset,*values)
        slots=[]
        for i in range(8):
            pointer=0x59700000+i*0x2000;slots.append(pointer)
            recipe=bytearray(0x19F0);struct.pack_into('<I',recipe,0,0x53EB16E8)
            struct.pack_into('<I',recipe,0x334,0x59604000);recipe[0xBB0:0xBF4]=raster
            self.memory[pointer]=recipe
        self.memory[collection]=words([0,0]+slots+[0,0])
        self.memory[0x59604000]=words([0x53FD19F8,0,7<<16,0])
        info=bytearray(120);struct.pack_into('<I',info,0,0x53FD1830);self.memory[0x59605000]=info
        self.memory[jpeg]=words([0x53ECFC58,0x1000006,0])
        self.memory[jpeg+0x8A44]=bytearray(120)
        if case=='empty-slots':self.memory[collection]=bytearray(48)
        if case=='wrong-recipe-class':struct.pack_into('<I',self.memory[slots[0]],0,0)
        if case=='bad-slot':struct.pack_into('<I',self.memory[collection],8,0x60000000)
        if case=='bad-collection':struct.pack_into('<I',obj,0x3B0,0x60000000)
        if case=='wrong-process-class':struct.pack_into('<I',obj,0,0)
        if case=='wrong-task-id':struct.pack_into('<I',obj,8,1)
        if case=='outside-node':struct.pack_into('<I',self.memory[registry],8,0x60000000)
        if case=='excess-count':struct.pack_into('<I',self.memory[registry],12,513)
        if case=='registry-cycle':
            struct.pack_into('<I',self.memory[registry],12,4)
            struct.pack_into('<I',self.memory[node1],0,node1)
            struct.pack_into('<I',obj,4,0x53FE0000)
        if case=='existing':self.files['C:\\XPV12\\ROOTA.BIN']=bytearray(b'KEEP')

    def send(self,command):
        assert command.startswith('SYS_md ')
        super().send(command)
        if self.case=='short-root':
            name=command.split(' -f ')[1];self.files[name]=self.files[name][:-1]


def check():
    code=program();cases=[]
    for case in ('normal','empty-slots','wrong-recipe-class','bad-slot','bad-collection',
                 'wrong-process-class','wrong-task-id','outside-node','excess-count','registry-cycle','existing','short-root'):
        model=PreviewFlow(case).run(code)
        assert model.eof_reads==0
        assert all(' -f C:\\XPV12\\' in cmd for cmd in model.commands)
        assert all(len(name.rsplit('\\',1)[-1].split('.')[0])<=8 for name in model.files if 'XPV12' in name)
        names=list(model.files)
        if case=='normal':assert sum('RASTER' in s for s in names)==24
        if case in ('empty-slots','bad-collection','wrong-process-class','wrong-task-id','outside-node','excess-count'):
            assert not any('RASTER' in s for s in names)
        if case in ('wrong-recipe-class','bad-slot'):
            assert not any('RASTER0' in s for s in names) and sum('RASTER' in s for s in names)==21
        if case=='existing':assert not model.commands and model.files['C:\\XPV12\\ROOTA.BIN']==b'KEEP'
        if case=='short-root':assert len(model.commands)==3
        if case=='registry-cycle':assert len(model.commands)==3*(2+4*2)
        cases.append({'case':case,'finite_SYS_md_commands':len(model.commands),
                      'out_of_model_or_EOF_read':False})
    with tempfile.TemporaryDirectory() as temp:
        dest=Path(temp)/'candidate';build(dest)
        payload=(dest/'script/startup.ttl').read_text()
        body=payload[payload.index('; Preview snapshot v12.'):payload.index('\nxpb_state = 1801\n')]
        helpers=payload[payload.index(':pv_snapshot\n'):]
        for case in ('normal','existing'):
            model=PreviewFlow(case).run(body+'\nxpb_state = 1801\nend\n'+helpers)
            assert model.env['xpb_state']==1801
            cases.append({'case':'USB-handoff-'+case,'USB_protocol_published':1801})
    return {'passed':True,'cases':cases,'camera_access':False,
            'real_SD_timing_and_atomic_frame_verified':False,'xpan_installed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=check()
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('%d generated preview TTL flow cases passed'%len(result['cases']))
