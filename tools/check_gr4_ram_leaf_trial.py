#!/usr/bin/env python3
"""Local lifecycle/fault model for the exact RAM leaf; no camera access."""
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch

import gr4_usb_call_session as gate
from check_gr4_usb_call_session import CameraModel
import mtp_factory_ram_leaf_trial as leaf


class LeafModel(CameraModel):
    def __init__(self, fault=None):
        super().__init__()
        self.leaf_fault = fault
        self.put(0x53004000 + (self.pointer >> 20)*4,gate.word(0x59A14C26))
        for address,data in leaf.ROM.items():
            self.put(address,data)

    def sleep(self, seconds):
        seq,done=self.variable('xpb_go'),self.variable('xpb_done')
        if seq == done:
            self.clock += seconds
            return
        target,adjustment,r2,r1,r0=struct.unpack('<5I',self.read(gate.RESPONSE_BUFFER,20))
        if target not in leaf.ROM and target != self.pointer:
            super().sleep(seconds)
        else:
            self.clock += seconds
            assert seq == done+1 and adjustment == 0
            assert self.read(gate.SEND_SLOT,4)==gate.word(gate.ADAPTER)
            self.native_calls.append((target,r0,r1,r2))
            values={leaf.CPU:0,leaf.TTBR:0x53004000,leaf.CONTROL:0x00C5187D,
                    leaf.DSB:0,leaf.ISB:4,leaf.IALL:0,self.pointer:65}
            if target == self.pointer:
                assert self.owned and self.read(target,32)==leaf.CODE
                previous=[x[0] for x in self.native_calls[-6:-1]]
                assert previous==[gate.CACHE_SVC,leaf.DSB,leaf.IALL,leaf.DSB,leaf.ISB]
            if self.leaf_fault=='ram_wrong_return' and target==self.pointer:
                values[target]=64
            if self.leaf_fault=='iall_rejected' and target==leaf.IALL:
                values[target]=0xFFEF0000
            self.variable('xpb_return',values[target]);self.variable('xpb_done',seq)
            self.variable('xpb_state',1803)
        if not self.fault_used and (
                (self.leaf_fault=='disconnect_ram' and target==self.pointer) or
                (self.leaf_fault=='disconnect_restore' and target==leaf.IALL and seq>10)):
            self.fault_used=True;self.disconnected=True

    def write_four(self,address,data):
        super().write_four(address,data)
        if (not self.fault_used and self.leaf_fault=='partial_payload' and
                address==self.pointer+4 and data==leaf.CODE[4:8]):
            self.fault_used=True
            raise RuntimeError('injected partial payload write')


def check():
    results=[]
    with tempfile.TemporaryDirectory() as directory:
        for fault in (None,'partial_payload','iall_rejected','ram_wrong_return','disconnect_ram','disconnect_restore'):
            model=LeafModel(fault)
            journal=Path(directory)/(str(fault)+'.json')
            with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
                session=leaf.LeafSession.begin(model,journal)
                session.record['script_attributes']='0x21003';session.save()
                error=None
                try:session.batch()
                except RuntimeError as caught:error=str(caught)
                assert bool(error)==bool(fault)
                if model.disconnected:
                    model.disconnected=False
                    session=leaf.LeafSession(model,journal,json.loads(journal.read_text()))
                    session.cleanup()
                model.assert_restored()
                assert not model.owned and model.allocations==model.frees==1
                assert model.read(model.pointer,32)==model.original_data
                assert (session.record.get('restored_code_published') or session.record.get('ram_entry_never_called'))
                assert session.record['cleanup_verified']
                assert model.variable('xpb_done')<=16
                ram_calls=sum(c[0]==model.pointer for c in model.native_calls)
                assert ram_calls<=1
                if fault is None:
                    assert session.record['ram_leaf_batch_passed'] and ram_calls==1
                    assert model.variable('xpb_done')==16
                results.append({'case':fault or 'complete_16_request_batch','error':error,
                    'completed_requests':model.variable('xpb_done'),'ram_calls':ram_calls,
                    'allocation_free_verified':True,
                    'restored_code_published':session.record.get('restored_code_published',False),
                    'ram_entry_never_called':session.record.get('ram_entry_never_called',False)})
        model=LeafModel();journal=Path(directory)/'fixed-only.json'
        with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
            session=leaf.LeafSession.begin(model,journal)
            session.record.update(script_attributes='0x21003',ram_leaf_trial=True)
            writes=len(model.writes)
            for target,args in [(leaf.CONTROL,[0,0,0]),(leaf.IALL,[7,1,0]),(0x53000858,[0,0,0])]:
                try:session.invoke(target,args)
                except ValueError:pass
                else:raise AssertionError('unapproved control/call accepted')
            assert len(model.writes)==writes
        results.append({'case':'fixed_targets_and_arguments_only','additional_writes':0})
    return {'cases_passed':len(results),'camera_accessed':False,
            'cp15_and_ram_execution_simulated':True,'cases':results}


if __name__=='__main__':
    print(json.dumps(check(),indent=2))
