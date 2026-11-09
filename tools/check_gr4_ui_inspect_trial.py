#!/usr/bin/env python3
"""Model the enlarged RAM callback/report ownership and recovery; no camera."""
import argparse
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch
import gr4_usb_call_session as gate
import mtp_factory_ram_leaf_trial as leaf
import mtp_factory_ui_inspect_trial as trial
from check_gr4_ui_queue_trial import QueueModel


class InspectModel(QueueModel):
    def complete_callback(self):
        words=[0]*64;words[0]=0x58504931;words[1]=2;words[2]=0x100007C
        self.put(self.pointer+trial.InspectSession.HANDLER_OFFSET+64,struct.pack('<64I',*words))
        self.put(self.pointer+trial.InspectSession.HANDLER_OFFSET,gate.word(0x17D))

    def sleep(self,seconds):
        seq,done=self.variable('xpb_go'),self.variable('xpb_done')
        if seq==done:self.clock+=seconds;return
        target,zero,r2,r1,r0=struct.unpack('<5I',self.read(gate.RESPONSE_BUFFER,20))
        if target not in (self.pointer,gate.CACHE_SVC):super().sleep(seconds);return
        cls=trial.InspectSession
        assert self.owned and seq==done+1 and zero==0
        self.clock+=seconds;self.native_calls.append((target,r0,r1,r2))
        if target==gate.CACHE_SVC:
            assert [r0,r1,r2]==[self.pointer,cls.CACHE_LENGTH,self.pointer+cls.CACHE_OUTPUT_OFFSET]
            self.put(r2,gate.word(r0));value=cls.CACHE_LENGTH
        else:
            assert [r0,r1,r2]==[trial.queue.MEDIATOR,self.pointer+cls.MESSAGE_OFFSET,trial.queue.MAGIC]
            assert self.read(target,cls.PAYLOAD_SIZE)==cls.PAYLOAD
            assert self.read(self.pointer+cls.MESSAGE_OFFSET,12)==struct.pack('<3I',0x17D,0,self.pointer+cls.HANDLER_OFFSET)
            assert self.read(self.pointer+cls.VTABLE_OFFSET,4)==gate.word(self.pointer+cls.CALLBACK_OFFSET)
            assert [x[0] for x in self.native_calls[-6:-1]]==[gate.CACHE_SVC,leaf.DSB,leaf.IALL,leaf.DSB,leaf.ISB]
            value=1
            if self.leaf_fault!='pending_callback':self.complete_callback()
        self.variable('xpb_return',value);self.variable('xpb_done',seq);self.variable('xpb_state',1803)
        if self.leaf_fault=='disconnect_ram' and target==self.pointer and not self.fault_used:
            self.disconnected=True;self.fault_used=True


def check():
    trial.configure();results=[]
    with tempfile.TemporaryDirectory() as directory:
        for fault in (None,'partial_payload','pending_callback','disconnect_ram','disconnect_restore','queue_go_after_commit'):
            model=InspectModel(fault);journal=Path(directory)/(str(fault)+'.json')
            with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
                session=trial.InspectSession.begin(model,journal);session.record['script_attributes']='0x21003';session.save()
                error=None
                try:session.batch()
                except RuntimeError as caught:error=str(caught)
                assert bool(error)==bool(fault),(fault,error)
                if fault=='pending_callback':
                    assert model.owned and not model.frees;model.assert_restored();model.complete_callback()
                    session=trial.InspectSession(model,journal,json.loads(journal.read_text()));session.cleanup()
                if model.disconnected:
                    model.disconnected=False;session=trial.InspectSession(model,journal,json.loads(journal.read_text()));session.cleanup()
                model.assert_restored();assert not model.owned and model.allocations==model.frees==1
                assert model.read(model.pointer,4096)==bytes(i%256 for i in range(4096))
                assert model.read(model.pointer+6144,20)==bytes(range(20))
                assert model.variable('xpb_done')<=16 and session.record['cleanup_verified']
                if fault!='partial_payload':assert session.record['ui_inspection_header_verified']
                results.append({'case':fault or 'full_16_request_batch','expected_error':error,
                    'report_captured_before_restore':fault!='partial_payload','owned_4096_bytes_restored':True,
                    'free_calls':model.frees,'completed_requests':model.variable('xpb_done')})
    return {'schema':'gr4-ui-inspect-lifecycle-model-v1','cases_passed':len(results),'cases':results,
            'camera_accessed':False,'RAM_callback_and_UI_consumption_simulated':True}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    if a.report.exists():raise ValueError('immutable report already exists')
    result=check();a.report.write_text(json.dumps(result,indent=2)+'\n');print('Inspection lifecycle cases passed:',result['cases_passed'])
