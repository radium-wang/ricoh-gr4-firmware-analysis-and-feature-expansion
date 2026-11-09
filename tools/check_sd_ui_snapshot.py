#!/usr/bin/env python3
"""Run generated TTL snapshot flow with synthetic memory/files, not a camera."""
import argparse
import json
from pathlib import Path
import struct
import tempfile

from build_sd_ui_snapshot import program,build
from validate_sd_batch_probe import FlowCheck


class UIFlow(FlowCheck):
    def __init__(self,case):
        super().__init__()
        root=bytearray(460)
        struct.pack_into('<I',root,0,0x53D94F08)
        setting=bytearray(484)
        struct.pack_into('<I',setting,0,0x53DA2C70)
        struct.pack_into('<I',setting,0x198,0x59608000)
        listing=bytearray(400)
        struct.pack_into('<I',listing,0,0x53E90000)
        struct.pack_into('<I',listing,0x168,0x59609000)
        struct.pack_into('<I',root,0xB0,0x59606000)
        self.memory[0x55080D40]=root
        self.memory[0x59606000]=setting
        self.memory[0x59608000]=listing
        self.memory[0x59609000]=struct.pack('<I',0x59606000)
        self.memory[0x5539FC64]=bytes(32)
        self.case=case
        if case=='absent':struct.pack_into('<I',root,0xB0,0)
        if case=='outside_heap':struct.pack_into('<I',root,0xB0,0x5A600000)
        if case=='unaligned':struct.pack_into('<I',root,0xB0,0x59606001)
        if case=='wrong_factory':struct.pack_into('<I',root,0,0x53D94F0C)
        if case=='wrong_controller':struct.pack_into('<I',setting,0,0x53DA2C74)
        if case=='bad_list':struct.pack_into('<I',setting,0x198,0x60000000)
        if case=='bad_callback':struct.pack_into('<I',listing,0x168,0x5A5FFFF0)
        if case=='existing':self.files['C:\\XUROOTA.BIN']=bytearray(b'KEEP')

    def send(self,command):
        super().send(command)
        if self.case=='short_dump':
            name=command.split(' -f ')[1]
            self.files[name]=self.files[name][:-1]


def check():
    code,outputs=program();cases=[]
    for case in ('normal','absent','outside_heap','unaligned','wrong_factory',
                 'wrong_controller','bad_list','bad_callback','existing','short_dump'):
        model=UIFlow(case).run(code)
        generated={name.rsplit('\\',1)[-1] for name in model.files if name.startswith('C:\\XU')}
        assert model.eof_reads==0
        assert all(cmd.startswith('SYS_md ') for cmd in model.commands)
        assert generated.issubset(set(outputs))
        if case=='normal':assert len(model.commands)==15
        if case in ('absent','outside_heap','unaligned'):assert len(model.commands)==6
        if case=='wrong_factory':assert len(model.commands)==3
        if case=='wrong_controller':assert not any('XULIST' in x for x in generated)
        if case=='bad_list':assert not any('XULIST' in x for x in generated)
        if case=='bad_callback':assert not any('XUCALL' in x for x in generated)
        if case=='existing':assert not model.commands and model.files['C:\\XUROOTA.BIN']==b'KEEP'
        if case=='short_dump':assert len(model.commands)==3
        cases.append({'case':case,'memory_read_commands':len(model.commands),
                      'stale_EOF_bytes_consumed':model.eof_reads})
    with tempfile.TemporaryDirectory() as temp:
        destination=Path(temp)/'package';build(destination)
        deployed=(destination/'script/startup.ttl').read_text()
        body=deployed[deployed.index('; UI snapshot v1.'):deployed.index('\nxpb_state = 1801\n')]
        helpers=deployed[deployed.index(':ui_snapshot\n'):]
        for case in ('normal','existing'):
            flow=UIFlow(case).run(body+'\nxpb_state = 1801\nend\n'+helpers)
            assert flow.env.get('xpb_state')==1801
            if case=='existing':assert flow.files['C:\\XUROOTA.BIN']==b'KEEP' and not flow.commands
            cases.append({'case':'deployed USB handoff '+case,'USB_protocol_published':1801,
                          'stale_EOF_bytes_consumed':flow.eof_reads})
    return {'schema':'gr4-sd-ui-flow-check-v1','cases_passed':len(cases),'cases':cases,
            'camera_accessed':False,'execution':'generated TTL control flow with synthetic files/memory',
            'camera_command_timing_or_UI_lifetime_verified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    result=check();args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('Generated TTL flow cases passed:',result['cases_passed'])
