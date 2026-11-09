#!/usr/bin/env python3
"""Pin the original menu item, ASCII label and fifth-item event routes."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_gr4_ui_native_routes import audit as routes_audit, SELECT_VTABLE
from audit_sd_shell_path import require_branch
from audit_xpan_paths import file_offset, require

ROOT=Path(__file__).resolve().parents[1]
FUNCTIONS={
    'list_item':(0x53570A9C,0x10),
    'list_selection':(0x53570B6C,12),
    'list_count':(0x535711E4,0xCC),
    'item_selected':(0x5357AD40,8),
    'item_hide_widgets':(0x5357AD48,0x60),
    'item_ascii':(0x5357AE1C,0x48),
    'ascii_text':(0x5356D1C8,0xEC),
    'ascii_substitution':(0x5356D2F0,0x13C),
    'ascii_convert':(0x538EA24C,0xB8),
    'ascii_length':(0x538EA304,0x34),
    'ascii_destructor':(0x5356D010,0x4C),
    'confirm_from_selection':(0x531D6AE0,0x70),
    'confirm_button_invoker':(0x531D6B50,0x28),
    'list_invoker':(0x531D71AC,0xC),
    'menu_event':(0x531DACAC,0xE0),
    'menu_activation':(0x531DAD8C,0x90),
}


def audit(raw):
    base=routes_audit(raw)
    classes={}
    for name,vt,typeinfo,label_addr,label in (
            ('line',0x53E98F18,0x53E98F00,0x53E98EE8,b'18SelectMenuLineView\0'),
            ('ascii',0x53E97FD8,0x53E97FA0,0x53E97FC4,b'9AsciiView\0')):
        require(raw,file_offset(vt-4),struct.pack('<I',typeinfo),name+' RTTI')
        require(raw,file_offset(typeinfo+4),struct.pack('<I',label_addr),name+' type name')
        require(raw,file_offset(label_addr),label,name+' class name')
        classes[name]={'vtable':hex(vt),'name':label[:-1].decode()}
    # Byte flags, not the adjacent three bytes of uninitialized padding.
    for address,data in (
            (0x53571238,bytes.fromhex('0440c0e5')),
            (0x53571258,bytes.fromhex('0400c2e5')),
            (0x53570A9C,bytes.fromhex('f43090e5013193e7000093e51eff2fe1')),
            (0x53570B6C,bytes.fromhex('110e80e2b000d0e11eff2fe1')),
            (SELECT_VTABLE+0x1C,struct.pack('<I',0x531DAD8C)),
            (SELECT_VTABLE+0x28,struct.pack('<I',0x531DACAC))):
        require(raw,file_offset(address),data,hex(address))
    for address,target in ((0x5357AE30,0x5357AD48),(0x5357AE40,0x5356D2F0),
                           (0x5357AE4C,0x53589AB4),(0x5356D1E4,0x538EA304),
                           (0x5356D1F8,0x538E0A24),(0x5356D20C,0x538EA24C),
                           (0x5356D034,0x538E0A60),(0x531D6B64,0x531D6AE0),
                           (0x531DAD84,0x531D6AE0),(0x531DAD14,0x531D6A3C)):
        require_branch(raw,address,target)
    require_branch(raw,0x5357AE60,0x5356D1C8,link=False)
    require_branch(raw,0x531D71B4,0x531D7120,link=False)
    return {'schema':'gr4-menu-widgets-audit-v1','sample_sha256':base['sample_sha256'],
            'classes':classes,
            'functions':{name:{'address':hex(a),'bytes':n,
                         'sha256':hashlib.sha256(raw[file_offset(a):file_offset(a)+n]).hexdigest()}
                         for name,(a,n) in FUNCTIONS.items()},
            'item_widget_offsets':{'icon':0xF0,'caption':0xF8,'ascii':0x100,
                                   'icon_with_ascii':0x104},
            'item_record':{'pointer_offset':0,'enabled_byte_offset':4,
                           'bytes_5_to_7_are_padding':True},
            'ascii_abi':{'r0':'SelectMenuLineView*','r1':'const char* (ASCII, nul terminated)',
                         'converter_outputs':'allocated UTF-16 including nul',
                         'XPAN_allocation_bytes':10,'owner':'AsciiView +0xF0',
                         'owner_destructor_frees_text':True},
            'routes_requiring_fifth_index_guard':[
                {'source':'list callback','invoker':'0x531D71AC','dispatch':'0x531D7120'},
                {'source':'confirm button','invoker':'0x531D6B50','dispatch':'0x531D6AE0'},
                {'source':'event 0xE0','virtual_offset':0x28,'dispatch':'0x531D6AE0'}],
            'other_routes':{'event_0xDB':'0x531D6A3C reads immutable native count 4',
                            'activation':'0x531DAD8C calls immutable descriptor refresh',
                            'refresh':'0x531DA9D4 restores count 4 and native labels'},
            'limits':['These pins do not establish UI thread quiescence.',
                      'Updating only list count/invoker does not cover confirmation or refresh.',
                      'ASCII label is not the requested XPAN icon or image pipeline.'],
            'camera_accessed':False,'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True);args=p.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    result=audit((ROOT/'samples/gr4_decoded.bin').read_bytes())
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('Pinned item classes, ASCII text ownership, count and confirmation routes.')
    print('Saved:',args.report)


if __name__=='__main__':main()
