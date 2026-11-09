#!/usr/bin/env python3
"""Model asynchronous queue ownership/USB recovery; no camera is contacted."""
import argparse
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch

import gr4_usb_call_session as gate
import mtp_factory_ram_leaf_trial as leaf
import mtp_factory_ui_queue_trial as trial
from check_gr4_ram_leaf_trial import LeafModel
from check_gr4_usb_call_session import CameraModel


class QueueModel(LeafModel):
    def sleep(self,seconds):
        seq,done=self.variable('xpb_go'),self.variable('xpb_done')
        if seq==done:self.clock+=seconds;return
        target,zero,r2,r1,r0=struct.unpack('<5I',self.read(gate.RESPONSE_BUFFER,20))
        if target not in (self.pointer,gate.CACHE_SVC):super().sleep(seconds);return
        assert self.owned and seq==done+1 and zero==0
        self.clock+=seconds;self.native_calls.append((target,r0,r1,r2))
        if target==gate.CACHE_SVC:
            assert [r0,r1,r2]==[self.pointer,1024,self.pointer+2048]
            self.put(r2,gate.word(r0));value=1024
        else:
            assert [r0,r1,r2]==[trial.MEDIATOR,self.pointer+512,trial.MAGIC]
            assert self.read(target,512)==trial.QueueSession.PAYLOAD
            assert self.read(self.pointer+512,12)==struct.pack('<3I',0x17D,0,self.pointer+544)
            assert self.read(self.pointer+544,4)==gate.word(self.pointer+560)
            assert self.read(self.pointer+560,4)==gate.word(trial.STORE)
            assert [x[0] for x in self.native_calls[-6:-1]]==[gate.CACHE_SVC,leaf.DSB,leaf.IALL,leaf.DSB,leaf.ISB]
            value={'queue_busy':2,'queue_full':3,'notify_failure':4}.get(self.leaf_fault,1)
            if value in (1,4,5) and self.leaf_fault!='pending_callback':self.put(self.pointer+544,gate.word(0x17D))
        self.variable('xpb_return',value);self.variable('xpb_done',seq);self.variable('xpb_state',1803)
        if self.leaf_fault=='disconnect_ram' and target==self.pointer and not self.fault_used:
            self.disconnected=True;self.fault_used=True

    def write_four(self,address,data):
        CameraModel.write_four(self,address,data)
        if self.leaf_fault=='partial_payload' and not self.fault_used and address==self.pointer+128:
            self.fault_used=True;raise RuntimeError('partial queue code upload')
        go=gate.INTEGER_VALUES+self.names.index('xpb_go')*4
        target=struct.unpack('<I',self.read(gate.RESPONSE_BUFFER,4))[0]
        if self.leaf_fault=='queue_go_after_commit' and not self.fault_used and address==go and target==self.pointer:
            self.fault_used=True;raise RuntimeError('queue publication write committed before USB error')


def check():
    trial.QueueSession.PAYLOAD=trial.payload();results=[]
    with tempfile.TemporaryDirectory() as directory:
        for fault in (None,'partial_payload','iall_rejected','queue_busy','queue_full',
                      'notify_failure','pending_callback','disconnect_ram','disconnect_restore','queue_go_after_commit'):
            model=QueueModel(fault);journal=Path(directory)/(str(fault)+'.json')
            with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
                session=trial.QueueSession.begin(model,journal)
                session.record.update(script_attributes='0x21003');session.save()
                error=None
                try:session.batch()
                except RuntimeError as caught:error=str(caught)
                assert bool(error)==bool(fault),(fault,error)
                if fault=='pending_callback':
                    assert model.owned and model.frees==0 and session.record['queue_submission_possible']
                    model.assert_restored()
                    writes=len(model.writes)
                    try:session.invoke(model.pointer,session.ENTRY_ARGS)
                    except ValueError:pass
                    else:raise AssertionError('pending message repost accepted')
                    assert len(model.writes)==writes
                    model.put(model.pointer+544,gate.word(0x17D))
                    session=trial.QueueSession(model,journal,json.loads(journal.read_text()));session.cleanup()
                if model.disconnected:
                    model.disconnected=False
                    session=trial.QueueSession(model,journal,json.loads(journal.read_text()));session.cleanup()
                model.assert_restored()
                assert not model.owned and model.allocations==model.frees==1
                assert model.read(model.pointer,1024)==bytes(i%256 for i in range(1024))
                assert model.read(model.pointer+2048,20)==bytes(range(20))
                assert sum(c[0]==model.pointer for c in model.native_calls)<=1
                assert model.variable('xpb_done')<=16 and session.record['cleanup_verified']
                if fault is None:assert session.record['ui_queue_batch_passed'] and model.variable('xpb_done')==16
                results.append({'case':fault or 'full_16_request_batch','expected_error':error,
                    'completed_requests':model.variable('xpb_done'),'ram_queue_entries':sum(c[0]==model.pointer for c in model.native_calls),
                    'free_calls':model.frees,'cleanup_verified':True,
                    'pending_handler_retained_until_consumption':fault=='pending_callback'})
        # A reboot must not let a pending old handler reach a recycled address.
        model=QueueModel('pending_callback');journal=Path(directory)/'reboot.json'
        with patch.object(gate.time,'monotonic',lambda:model.clock),patch.object(gate.time,'sleep',model.sleep):
            session=trial.QueueSession.begin(model,journal)
            session.record['script_attributes']='0x21003';session.save()
            try:session.batch()
            except RuntimeError:pass
            assert model.owned and model.frees==0
            model.variable('xpb_token',0);model.variable('xpb_go',0);model.variable('xpb_done',0)
            writes=len(model.writes)
            try:session.cleanup()
            except RuntimeError:pass
            else:raise AssertionError('cross-boot cleanup accepted')
            assert len(model.writes)==writes and model.frees==0
        results.append({'case':'cross_boot_pending_handler_refused','additional_writes':0,'free_calls':0})
    return {'schema':'gr4-ui-queue-lifecycle-model-v1','cases_passed':len(results),
            'cases':results,'camera_accessed':False,'native_execution_and_UI_consumption_simulated':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    result=check();args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('Asynchronous queue lifecycle cases passed:',result['cases_passed'])


if __name__=='__main__':main()
