#!/usr/bin/env python3
"""One RAM callback on AppMain: read menu/widgets/calculator, then fully remove.

Default only reads existing queue state. No menu, photo, file or flash changes.
The callback exits RAM into the fixed ROM store leaf before marking completion.
"""
import argparse
import hashlib
import json
import struct
import mtp_factory_ui_queue_trial as queue

PACKAGE=queue.ROOT/'devkit-output/usb-factory-20261001/ui-inspect-native-v2'
JOURNAL=queue.ROOT/'devkit-output/usb-factory-20261001/ui-inspect-session-trial-v1.json'
SHA='ba2eefef4b083b19793f3c65024a8a5d221087a7f41628b54b456a7a3f7ba38e'


class InspectSession(queue.QueueSession):
    PAYLOAD_SHA=SHA
    PAYLOAD_SIZE=2048
    CACHE_LENGTH=4096
    MESSAGE_OFFSET=2048
    HANDLER_OFFSET=2080
    VTABLE_OFFSET=2096
    CACHE_OUTPUT_OFFSET=6144
    CALLBACK_OFFSET=8

    def require_consumed(self):
        super().require_consumed()
        if (self.record.get('appmain_callback_observed') and self.record.get('allocation_owned')
                and 'ui_inspection_hex' not in self.record):
            self.check_owned()
            data=self.io.read(self.handler()+64,256)
            words=struct.unpack('<64I',data)
            # Invalid reports are kept as evidence; proven consumption still
            # allows normal restoration/free. They never authorize UI changes.
            report={'magic':hex(words[0]),'status':words[1],'appmain_task_id':hex(words[2]),
                    'controller':hex(words[3]),'controller_id':hex(words[4]),'row':words[5],
                    'list':hex(words[6]),'constructed_slots':words[7],'vector_capacity':words[8],
                    'active_count':words[9],'manager':hex(words[10]),'invoker':hex(words[11]),
                    'callback_owner':hex(words[12]),'calculator':hex(words[13]),
                    'calculator_vtable':hex(words[14]),'items':[]}
            for i in range(5):
                start=16+i*8;v=words[start:start+8]
                report['items'].append({'index':i,'record':hex(v[0]),'item':hex(v[1]),'enabled_byte':v[2],
                    'ascii_widget':hex(v[3]),'owned_text':hex(v[4]),'text_units':v[5]})
            expected=self.record.get('queue_context_before',{}).get('appmain_task_id')
            self.record.update(ui_inspection_hex=data.hex(),ui_inspection=report,
                ui_inspection_header_verified=words[0]==0x58504931 and (expected is None or hex(words[2])==expected))
            self.save()


def configure():
    manifest=json.loads((PACKAGE/'manifest.json').read_text())
    data=(PACKAGE/'inspect.bin').read_bytes()
    if (len(data)!=2048 or hashlib.sha256(data).hexdigest()!=SHA or
        manifest['payload_sha256']!=SHA or manifest['callback_offset']!=8 or
        manifest['queue_checks']['cases_passed']!=15 or manifest['callback_checks']['cases_passed']!=4):
        raise ValueError('only the exact checked read-only AppMain callback is accepted')
    InspectSession.PAYLOAD=data


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--trial',action='store_true');mode.add_argument('--recover',action='store_true')
    mode.add_argument('--offline',action='store_true');args=parser.parse_args()
    configure();queue.run(args,InspectSession,JOURNAL)


if __name__=='__main__':main()
