#!/usr/bin/env python3
"""Audit native recovery primitives offline; does not load code or contact a camera."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch

COMMANDS = {'SYS_md': (527, 0x53053A84), 'SYS_reg': (528, 0x53053CF0),
            'SYS_buildinfo': (533, 0x53054854)}
TEST_RETURN = 0x538C9760  # Exactly MOV r0,#3; BX lr. No new code or memory access.
REFERENCE_RANGES = [('XRMD',0x53053A84,0x26C), ('XRREG',0x53053CF0,0x270),
                    ('XRBUILD',0x53054854,0x88), ('XRCOPY',0x53156140,0x74),
                    ('XRRET',TEST_RETURN,8), ('XRSTAT',0x53B18B24,0x214),
                    ('XRSTIO',0x53B14E1C,0xC8)]


def audit(raw, command_table):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported firmware sample')
    if len(command_table) != 651*52:
        raise ValueError('expected the saved 651-entry command table')
    for name,(index,handler) in COMMANDS.items():
        row=command_table[index*52:(index+1)*52]
        if struct.unpack_from('<I',row)[0]!=handler or row[4:].split(b'\0')[0]!=name.encode():
            raise ValueError('unexpected saved command row: '+name)
    require(raw,file_offset(TEST_RETURN),bytes.fromhex('03 00 a0 e3 1e ff 2f e1'),
            'existing side-effect-free return-3 leaf')
    require(raw,file_offset(0x53FE3B9C),b'measure mark control\0','SYS_mm identity')
    require(raw,file_offset(0x54309AF4),b'set\0','SYS_reg write keyword')
    require_branch(raw,0x53053ED4,0x53156140)
    require_branch(raw,0x53053F54,0x53053ED4,link=False)
    require(raw,file_offset(0x53053F4C),bytes.fromhex('10 00 21 e5'),
            '32-bit register value saved to local buffer')
    require(raw,file_offset(0x53156198),bytes.fromhex('04 30 8c 14'),
            '4-byte memcpy path uses a single word store')
    require(raw,file_offset(0x54373858),b'filestat\0','native filestat keyword')
    require(raw,file_offset(0x53B1D16C),bytes.fromhex('b2 30 a0 e3'),
            'filestat token 0xb2')
    require(raw,file_offset(0x53B1A960),struct.pack('<I',0x53B1AA10),
            'filestat dispatch table row')
    require_branch(raw,0x53B1AA10,0x53B18B24)
    require_branch(raw,0x53B18BCC,0x53B14E1C)
    require(raw,file_offset(0x53B14EC8),bytes.fromhex('04 c2 85 e5'),
            'native stat adapter stores reported file size at offset 0x204')
    require(raw,file_offset(0x53B18D28),bytes.fromhex('2c 16 1b e5'),
            'filestat reads reported size for integer output')
    require_branch(raw,0x53B18D2C,0x53B1E958)
    require_branch(raw,0x530552D8,0x538F0454)
    require_branch(raw,0x53055364,0x538F04C4)
    require_branch(raw,0x538F04CC,0x53A95790,link=False)
    require_branch(raw,0x538F0488,0x53A95804,link=False)
    for address,word in [(0x53087AC8,0xEE070F35),(0x53087BD4,0xEE070F11),
                         (0x53087BEC,0xEE070F15),(0x53087C90,0xEE070F35)]:
        require(raw,file_offset(address),struct.pack('<I',word),'native instruction-cache operation')
    for clean, invalidate in [(0x530882D8,0x530882E4),
                              (0x5308858C,0x53088598),
                              (0x5308867C,0x5308868C)]:
        require_branch(raw,clean,0x53087CFC)
        require_branch(raw,invalidate,0x53087C78)
    return {'sample_sha256':EXPECTED_SHA256,'command_rows':COMMANDS,
            'test_return_function':hex(TEST_RETURN),'test_return_value':3,
            'SYS_mm':'performance measure-mark control, not a memory writer',
            'SYS_reg':'arbitrary address copy; not a loader or protected transaction',
            'SYS_cache':'engineering flush/clean goes through data-cache helpers; not a complete code-publication protocol',
            'native_instruction_cache_operations_exist':True,
            'native_cache_clean_then_instruction_invalidate_call_pairs':[
                ['0x530882d8','0x530882e4'],
                ['0x5308858c','0x53088598'],
                ['0x5308867c','0x5308868c']],
            'cache_call_pair_contexts':[
                'block release', 'cache-only service', 'VA-to-PA service branch'],
            'instruction_cache_calling_and_cross_core_protocol_verified':False,
            'owned_executable_allocation_and_module_loader_verified':False,
            'minimal_probe':'temporarily change one aligned SYS_buildinfo handler word, call immutable native leaf, restore immediately',
            'module_recovery_verified':False,'camera_installable':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sample',type=Path);p.add_argument('command_table',type=Path)
    args=p.parse_args()
    print(json.dumps(audit(args.sample.read_bytes(),args.command_table.read_bytes()),indent=2))


if __name__=='__main__':main()
