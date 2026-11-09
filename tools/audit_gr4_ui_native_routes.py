#!/usr/bin/env python3
"""Pin the separate ADJ and settings aspect controllers, without camera I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch

FACTORY = 0x55080D40
FACTORY_GUARD = FACTORY - 4
FACTORY_VTABLE = 0x53D94F08
ADJ_VTABLE = 0x53D9F6A0
SELECT_VTABLE = 0x53DA2C70
SELECT_BASE = 0x53DA2D20
SELECT_STRIDE = 0x4C
SELECT_ASPECT_INDEX = 34
SELECT_ASPECT_ROW = SELECT_BASE + SELECT_STRIDE * SELECT_ASPECT_INDEX


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported firmware sample')
    pins = {
        0x53184828: struct.pack('<I', FACTORY_VTABLE),
        0x531DB368: struct.pack('<I', SELECT_VTABLE),
        0x5318735C: bytes.fromhex('b00094e5000050e3'),
        0x53187368: bytes.fromhex('790fa0e3'),  # mov r0,#0x1e4
        0x53187378: bytes.fromhex('b05084e5'),
        0x53186A3C: bytes.fromhex('840094e5000050e3'),
        0x53186A48: bytes.fromhex('a50fa0e3'),  # mov r0,#0x294
        0x53186A58: bytes.fromhex('845084e5'),
        0x531D66EC: bytes.fromhex('2230a0e3a431c0e5'),
        SELECT_ASPECT_ROW: struct.pack('<3I', 0x10100, 0x108, 0),
        SELECT_ASPECT_ROW+0x0C: struct.pack('<2I', 0x531CF298, 0),
        SELECT_ASPECT_ROW+0x14: struct.pack('<2I', 0x531D0CCC, 0),
        SELECT_ASPECT_ROW+0x24: struct.pack('<2I', 0x531D2F70, 0),
        SELECT_ASPECT_ROW+0x2C: struct.pack('<2I', 0x531D4898, 0),
        SELECT_ASPECT_ROW+0x34: struct.pack('<2I', 0x531D8FFC, 0),
        SELECT_VTABLE-4: struct.pack('<I', 0x53DA5468),
        0x53DA5468: struct.pack('<3I', 0x54373BF0, 0x53DA2C28, 0x53D79504),
        0x53DA2C28: b'20SelectMenuController\0',
        0x531D5EB0+(0x8A-0x73)*4: struct.pack('<I', 0x531D66EC),
        0x531D6C28: bytes.fromhex('ac2107e31d2345e3'),
        0x531D71AC: bytes.fromhex('003090e5000093e5'),
        0x538D0670: struct.pack('<I',0x53FD8B20),
        0x538D05EC: struct.pack('<I',0x53FD89A0),
        0x538D05C8: bytes.fromhex('0400a0e3'),
        0x538D05D8: bytes.fromhex('140084e5'),
        0x538D0610: bytes.fromhex('640c0fe3390545e3'),
    }
    for address, data in pins.items():
        require(raw, file_offset(address), data, hex(address))
    for address, target in ((0x53187374,0x531DB284),
                            (0x53186A54,0x531C048C),
                            (0x531DB294,0x53182D40),
                            (0x531D6C50,0x53570E84)):
        require_branch(raw,address,target)
    return {
        'schema':'gr4-native-ui-routes-v1', 'sample_sha256':EXPECTED_SHA256,
        'pins_checked':len(pins)+4,
        'factory':{'object':hex(FACTORY),'guard':hex(FACTORY_GUARD),
                   'vtable':hex(FACTORY_VTABLE),'lookup':hex(0x53185F7C),
                   'lookup_is_direct_method_not_factory_virtual_slot':True},
        'adj':{'class':'AdjModeController','vtable':hex(ADJ_VTABLE),
               'constructor':hex(0x531C048C),'factory_slot':0x84,
               'object_size':0x294,'descriptor_base':hex(0x53D9F714),
               'descriptor_stride':0x5C,'aspect_row_index':5},
        'settings':{'class':'SelectMenuController','vtable':hex(SELECT_VTABLE),
                    'constructor':hex(0x531DB284),'factory_slot':0xB0,
                    'object_size':0x1E4,'descriptor_base':hex(SELECT_BASE),
                    'descriptor_stride':SELECT_STRIDE,'aspect_row_index':SELECT_ASPECT_INDEX,
                    'aspect_row':hex(SELECT_ASPECT_ROW),'aspect_ui_id':hex(0x0200008A),
                    'selected_row_offset':0x1A4,'controller_id_offset':0x124,
                    'list_offset':0x198,'list_callback_storage_offset':0x168,
                    'list_invoker':hex(0x531D71AC),'list_owner_record_size':4,
                    'count_callback_offset':0x0C,'label_callback_offset':0x14,
                    'set_callback_offset':0x24,'selected_callback_offset':0x2C,
                    'confirm_callback_offset':0x34},
        'image_factory':{'object':hex(0x5539FC64),'guard':hex(0x5539FC84),
                         'vtable':hex(0x53FD8B20),'calculator_slot':0x14,
                         'calculator_vtable':hex(0x53FD89A0),'calculator_object_size':4,
                         'dimensions_outputs':{'width':'r3','height':'stack argument'},
                         'global_dimensions_hook_must_preserve_full_source_calls':True},
        'limits':['RAM factory slots may be null until their controller is constructed.',
                  'Constructor pins and RTTI establish class identity, not safe hook synchronization.',
                  'Original factory vtable contains destructor entries, not its direct lookup method.',
                  'No XPAN menu or image pipeline hook is installed.'],
        'camera_io':False,'patched_or_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path)
    args=p.parse_args()
    raw=(Path(__file__).resolve().parents[1]/'samples/gr4_decoded.bin').read_bytes()
    result=audit(raw)
    if args.report:
        if args.report.exists():raise ValueError('report already exists')
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
