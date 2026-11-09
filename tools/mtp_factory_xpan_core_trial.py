#!/usr/bin/env python3
"""Run the exact XPAN calculation/undo checks in owned camera RAM, then remove.

Default read-only. --trial needs a fresh protocol 1801 boot and performs one
16-request lifecycle batch. --recover resumes its own ledger. No native menu,
preview, encoded photo, flash or internal file is changed by this core check.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import usb.core
import usb.util
import gr4_usb_call_session as gate
from mtp_factory_ram_leaf_trial import LeafSession,ROM,audit,ROOT
from mtp_factory_task_mapping_readonly import collect as task_context
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS,operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_probe_readonly import VID,PID,command

PACKAGE=ROOT/'devkit-output/usb-factory-20261001/xpan-core-ram'
JOURNAL=ROOT/'devkit-output/usb-factory-20261001/xpan-core-session-trial-v1.json'
EXPECTED_PAYLOAD_SHA='c7ae84a2683a87a43e3f240fd867fdc1b809ead85bec32bbacd520cc0d6f606b'


def payload():
    data=(PACKAGE/'core.bin').read_bytes()
    if len(data)!=3072 or hashlib.sha256(data).hexdigest()!=EXPECTED_PAYLOAD_SHA:
        raise ValueError('only the exact audited XPAN core payload is accepted')
    report=json.loads((PACKAGE/'arm-checks.json').read_text())
    # The machine-code payload is pinned independently from the emulation log.
    if report.get('cases_passed')!=6 or not report.get('actual_linked_ARM_core_executed_in_emulator'):
        raise ValueError('the core ARM checks must be completed before trial')
    return data


class CoreSession(LeafSession):
    PAYLOAD=b''  # assigned only after the fixed SHA check
    ENTRY_ARGS=[0x5850414E,65,24]
    EXPECTED_RETURN=0
    CACHE_LENGTH=3072

    def cache_output(self):
        output=self.data_address()+4096
        if output+20>self.record['allocation_pointer']+gate.SIZE:
            raise ValueError('core cache output exceeds the owned allocation')
        return output

    def validate(self):
        super().validate()
        if len(self.PAYLOAD)!=3072 or hashlib.sha256(self.PAYLOAD).hexdigest()!=EXPECTED_PAYLOAD_SHA:
            raise ValueError('core session has not loaded the fixed payload')
        if 'payload_hex' in self.record and self.record['payload_hex']!=self.PAYLOAD.hex():
            raise ValueError('recovery payload does not match the fixed core')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--trial',action='store_true');modes.add_argument('--recover',action='store_true')
    modes.add_argument('--offline',action='store_true');args=p.parse_args()
    data=payload();CoreSession.PAYLOAD=data
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();evidence=audit(raw)
    evidence.pop('payload_hex',None)
    evidence.update(payload_sha256=EXPECTED_PAYLOAD_SHA,payload_bytes=len(data),
                    entry_arguments=CoreSession.ENTRY_ARGS,expected_return=0,
                    checks=json.loads((PACKAGE/'manifest.json').read_text())['checks'],
                    xpan_installed=False)
    if args.offline:print(json.dumps(evidence,indent=2));return
    device=usb.core.find(idVendor=VID,idProduct=PID)
    if device is None or device.bcdDevice!=0x111:raise RuntimeError('expected GR IV 01.11.10.07')
    usb.util.claim_interface(device,0);io=Transport(device);opened=False
    try:
        code,info,_=command(device,0x1001,0)
        if code!=0x2001 or info is None or operations_from_device_info(info)!=EXPECTED_OPERATIONS:
            raise RuntimeError('unexpected camera information')
        code,_,_=command(device,0x1002,1,1);opened=code==0x2001
        if code not in (0x2001,0x201E):raise RuntimeError('OpenSession failed')
        for address,expected in [*ROM.items(),(gate.CACHE_SVC,gate.CACHE_BYTES)]:
            if io.read(address,len(expected))!=expected:raise RuntimeError('native ROM mismatch')
        if args.recover:
            session=CoreSession(io,JOURNAL,json.loads(JOURNAL.read_text()))
            session.cleanup();result=session.record
        else:
            context=task_context(io.read,raw)
            if args.trial:
                session=CoreSession.begin(io,JOURNAL)
                session.record.update(script_attributes=context['script_attributes'],task_mapping_before=context,
                                      xpan_core_trial=True,xpan_core_payload_sha256=EXPECTED_PAYLOAD_SHA,
                                      offline_audit=evidence)
                session.save();result=session.batch()
                result['xpan_core_checks_verified']=result.get('ram_code_execution_verified',False)
                result['xpan_menu_preview_capture_hooks_installed']=False
                session.save()
            else:result=context
        print(json.dumps({k:v for k,v in result.items() if k not in ('task_mapping_before','payload_hex','owned_before_hex')},indent=2))
    finally:
        try:
            if opened:command(device,0x1003,io.transaction)
        finally:
            usb.util.release_interface(device,0);usb.util.dispose_resources(device)


if __name__=='__main__':main()
