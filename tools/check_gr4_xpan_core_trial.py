#!/usr/bin/env python3
"""Model the fixed 3KB core lifecycle and disconnect recovery; no USB."""
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch

import gr4_usb_call_session as gate
import mtp_factory_ram_leaf_trial as leaf
import mtp_factory_xpan_core_trial as core
from check_gr4_ram_leaf_trial import LeafModel
from check_gr4_usb_call_session import CameraModel


class CoreModel(LeafModel):
    def sleep(self,seconds):
        seq,done=self.variable('xpb_go'),self.variable('xpb_done')
        if seq==done:
            self.clock+=seconds;return
        target,zero,r2,r1,r0=struct.unpack('<5I',self.read(gate.RESPONSE_BUFFER,20))
        if target not in (self.pointer,gate.CACHE_SVC):
            super().sleep(seconds);return
        assert self.owned and seq==done+1 and zero==0
        assert self.read(gate.SEND_SLOT,4)==gate.word(gate.ADAPTER)
        self.clock+=seconds;self.native_calls.append((target,r0,r1,r2))
        if target==gate.CACHE_SVC:
            assert [r0,r1,r2]==[self.pointer,3072,self.pointer+4096]
            self.put(r2,gate.word(r0));value=3072
        else:
            assert [r0,r1,r2]==core.CoreSession.ENTRY_ARGS
            assert self.read(target,3072)==core.CoreSession.PAYLOAD
            assert [x[0] for x in self.native_calls[-6:-1]]==[gate.CACHE_SVC,leaf.DSB,leaf.IALL,leaf.DSB,leaf.ISB]
            value=32 if self.leaf_fault=='ram_wrong_return' else 0
        self.variable('xpb_return',value);self.variable('xpb_done',seq);self.variable('xpb_state',1803)
        if self.leaf_fault=='disconnect_ram' and target==self.pointer and not self.fault_used:
            self.disconnected=True;self.fault_used=True

    def write_four(self,address,data):
        CameraModel.write_four(self,address,data)
        if self.leaf_fault=='partial_payload' and not self.fault_used and address==self.pointer+128:
            self.fault_used=True;raise RuntimeError('partial 3KB payload write')


def check():
    core.CoreSession.PAYLOAD=core.payload();results=[]
    with tempfile.TemporaryDirectory() as directory:
        for fault in (None,'partial_payload','iall_rejected','ram_wrong_return','disconnect_ram','disconnect_restore'):
            model=CoreModel(fault);path=Path(directory)/(str(fault)+'.json')
            with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
                session=core.CoreSession.begin(model,path)
                session.record.update(script_attributes='0x21003',xpan_core_trial=True);session.save()
                error=None
                try:session.batch()
                except RuntimeError as caught:error=str(caught)
                assert bool(error)==bool(fault)
                if model.disconnected:
                    model.disconnected=False
                    session=core.CoreSession(model,path,json.loads(path.read_text()));session.cleanup()
                model.assert_restored()
                assert not model.owned and model.allocations==model.frees==1
                original=bytes(i%256 for i in range(3072))
                assert model.read(model.pointer,3072)==original
                assert model.read(model.pointer+4096,20)==bytes(range(20)), (fault,model.read(model.pointer+4096,20).hex(),session.record.get('cache_output_before_hex'))
                calls=sum(c[0]==model.pointer for c in model.native_calls)
                assert calls<=1 and model.variable('xpb_done')<=16
                assert session.record['cleanup_verified']
                if not fault:assert session.record['ram_code_execution_verified'] and model.variable('xpb_done')==16
                results.append({'case':fault or 'complete_core_batch','expected_error':error,
                                'completed_requests':model.variable('xpb_done'),'ram_core_calls':calls,
                                'restored_bytes':3072,'free_calls':model.frees,'cleanup_verified':True})
        model=CoreModel();path=Path(directory)/'boundaries.json'
        with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
            session=core.CoreSession.begin(model,path)
            session.record.update(script_attributes='0x21003',ram_leaf_trial=True,cache_trial=True);session.save()
            session.invoke(gate.MALLOC,[gate.SIZE,0,0])
            count=len(model.writes)
            for address in (session.data_address()+3072,session.cache_output()+20):
                try:session.write_word(address,1,owned=True)
                except ValueError:pass
                else:raise AssertionError('write outside owned code/output accepted')
            try:session.invoke(gate.CACHE_SVC,[session.data_address(),64,session.cache_output()])
            except ValueError:pass
            else:raise AssertionError('wrong core cache length accepted')
            assert len(model.writes)==count
            session.cleanup()
        results.append({'case':'fixed_code_output_and_cache_bounds','rejected_extra_writes':True})
    return {'cases_passed':len(results),'camera_accessed':False,'native_calls_simulated':True,'cases':results}


if __name__=='__main__':
    result=check();p=core.PACKAGE/'lifecycle-checks.json'
    p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
