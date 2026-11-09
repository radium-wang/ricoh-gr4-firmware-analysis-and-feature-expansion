#!/usr/bin/env python3
"""Pin the original ROM file wrappers; no camera access or file operations."""
import hashlib
import struct
from audit_xpan_paths import EXPECTED_SHA256, file_offset

STAT, OPEN, READ, CLOSE = 0x53B14E1C, 0x538F14F8, 0x538F15B8, 0x538F1598
FS_ROOT, FS_VTABLE = 0x553A09D0, 0x53F9B9F8
FILE_HOLDER, FILE_TABLE = 0x553B1934, 0x5501A2F4
REGIONS = ((STAT,200),(OPEN,160),(READ,92),(CLOSE,32),
           (0x538F1B20,172),(0x537A86EC,380),(0x537A8548,324),
           (0x537A3130,196),(0x53F9B580,10),(FS_VTABLE,88))


def pinned(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported original firmware sample')
    return {a:raw[file_offset(a):file_offset(a)+n] for a,n in REGIONS}


def audit(raw):
    pins=pinned(raw)
    modes=struct.unpack('<5H',pins[0x53F9B580])
    if modes != (257,0,2,10,513):
        raise ValueError('original FAT open mode translation changed')
    return {'schema':'gr4-sd-file-abi-v1','sample_sha256':EXPECTED_SHA256,
        'pins':[{'address':hex(a),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
                for a,b in pins.items()],
        'stat':{'entry':hex(STAT),'status_bytes':524,'size_offset':516,'success':0},
        'open':{'entry':hex(OPEN),'wrapper_flag':0,'native_mode':1,
                'FAT_open_flag':modes[1],'FAT_backend':hex(0x537A3130)},
        'read':{'entry':hex(READ),'success_returns_requested_length':True,
                'actual_byte_count_available':False,'requires_exact_stat_length':True},
        'close':{'entry':hex(CLOSE),'success':1,'completed_failure_must_not_be_retried':True},
        'camera_access':False,'hardware_file_read_verified':False,'xpan_installed':False}


def live_check(read,raw):
    pins=pinned(raw)
    for a,b in pins.items():
        if read(a,len(b)) != b:raise RuntimeError('file ROM pin changed: %08x'%a)
    holder=read(FS_ROOT,4);obj=struct.unpack('<I',holder)[0]
    if obj%4 or not 0x59000000 <= obj <= 0x5C000000-48:
        raise RuntimeError('unexpected filesystem service object')
    if read(obj,4) != struct.pack('<I',FS_VTABLE):
        raise RuntimeError('unexpected filesystem service class')
    if read(FILE_HOLDER,4) != struct.pack('<I',FILE_TABLE):
        raise RuntimeError('unexpected interpreter file callbacks')
    for offset,entry in ((8,OPEN),(12,CLOSE),(16,READ),(48,0x538F1B20)):
        if read(FILE_TABLE+offset,4) != struct.pack('<I',entry):
            raise RuntimeError('interpreter file callback changed')
    if read(FS_ROOT,4) != holder:raise RuntimeError('filesystem service changed during read')
    return {'object':hex(obj),'vtable':hex(FS_VTABLE),'ROM_and_callbacks_verified':True}
