#!/usr/bin/env python3
"""Prepare shooting-mode finite snapshots plus the existing USB call session.

Writes a local candidate, not an SD card. On camera only SYS_md is added:
no settings, callbacks, executable RAM, internal files or firmware changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
from audit_gr4_preview_recipe import audit
from audit_sd_shell_path import audit as audit_shell
from build_sd_ui_snapshot import program as ui_program

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY='XPV12'


def program():
    # Reuse the previously exercised checked binary reader and bounded dump.
    helper=ui_program()[0].split(':ui_dump_heap\n',1)[1]
    helper=(':ui_dump_heap\n'+helper).replace('ui_','pv_')
    helper=helper.replace("pv_path = 'C:\\XU'", "pv_path = 'C:\\XPV12\\'")
    entry=['; Preview snapshot v12. Original GR IV 01.11.10.07 only.']
    for suffix in 'ABC':
        entry += ["filesearch 'C:\\XPV12\\ROOT%s.BIN'"%suffix,
                  'if result = 1 then','    goto pv_skip_capture','endif']
    for suffix,delay in (('A',15000),('B',60000),('C',60000)):
        entry += ['mpause '+str(delay),"pv_suffix = '%s'"%suffix,'call pv_snapshot']
    entry += [':pv_skip_capture','end']
    body=r'''
:pv_snapshot
pv_addr = 1429864496
pv_size = 4
pv_kind = 'ROOT'
call pv_dump
if pv_ok = 0 then
    return
endif
pv_offset = 0
call pv_u32
if pv_ok = 0 then
    return
endif
pv_registry = pv_value
pv_addr = pv_registry
pv_size = 32
pv_kind = 'REG'
call pv_dump_heap
if pv_ok = 0 then
    return
endif
pv_offset = 8
call pv_u32
pv_node = pv_value
pv_offset = 12
call pv_u32
pv_count = pv_value
if pv_ok = 0 then
    return
endif
if pv_count < 1 then
    return
endif
if pv_count > 512 then
    return
endif
pv_index = 0
pv_found_preview = 0
pv_found_jpeg = 0
while pv_index < pv_count
    if pv_node = 0 then
        return
    endif
    int2str pv_text pv_index
    pv_kind = 'NODE'
    strconcat pv_kind pv_text
    pv_addr = pv_node
    pv_size = 12
    call pv_dump_heap
    if pv_ok = 0 then
        return
    endif
    pv_offset = 0
    call pv_u32
    pv_next = pv_value
    pv_offset = 4
    call pv_u32
    pv_task_id = pv_value
    pv_offset = 8
    call pv_u32
    pv_object = pv_value
    if pv_ok = 0 then
        return
    endif
    int2str pv_text pv_index
    pv_kind = 'TASK'
    strconcat pv_kind pv_text
    pv_addr = pv_object
    pv_size = 12
    call pv_dump_heap
    if pv_ok = 0 then
        return
    endif
    pv_offset = 4
    call pv_u32
    if pv_ok = 0 then
        return
    endif
    if pv_value != pv_task_id then
        return
    endif
    pv_offset = 0
    call pv_u32
    pv_class = pv_value
    if pv_ok = 0 then
        return
    endif
    if pv_class = 1407914536 then
        if pv_found_preview = 0 then
            pv_process = pv_object - 4
            call pv_preview
            pv_found_preview = 1
        endif
    endif
    if pv_class = 1408040024 then
        if pv_found_jpeg = 0 then
            call pv_jpeg
            pv_found_jpeg = 1
        endif
    endif
    if pv_found_preview = 1 then
        if pv_found_jpeg = 1 then
            return
        endif
    endif
    pv_node = pv_next
    pv_index = pv_index + 1
endwhile
return

:pv_preview
pv_addr = pv_process
pv_size = 960
pv_kind = 'PROCESS'
call pv_dump_heap
if pv_ok = 0 then
    return
endif
pv_process_path = pv_path
pv_offset = 0
call pv_u32
if pv_ok = 0 then
    return
endif
if pv_value != 1407914480 then
    return
endif
pv_offset = 944
call pv_u32
pv_collection = pv_value
pv_offset = 920
call pv_u32
pv_manager = pv_value
pv_offset = 928
call pv_u32
pv_information = pv_value
pv_addr = pv_process + 38816
pv_size = 8
pv_kind = 'SPECIAL'
call pv_dump_heap
pv_addr = pv_manager
pv_size = 16
pv_kind = 'MANAGER'
call pv_dump_heap
pv_addr = pv_information
pv_size = 120
pv_kind = 'INFO'
call pv_dump_heap
pv_addr = pv_collection
pv_size = 48
pv_kind = 'COLL'
call pv_dump_heap
if pv_ok = 0 then
    return
endif
pv_collection_path = pv_path
pv_recipe_index = 0
while pv_recipe_index < 8
    pv_path = pv_collection_path
    pv_offset = 8 + pv_recipe_index * 4
    call pv_u32
    if pv_ok = 0 then
        return
    endif
    pv_recipe = pv_value
    if pv_recipe != 0 then
        int2str pv_recipe_text pv_recipe_index
        pv_kind = 'ID'
        strconcat pv_kind pv_recipe_text
        pv_addr = pv_recipe
        pv_size = 8
        call pv_dump_heap
        if pv_ok = 1 then
            pv_offset = 0
            call pv_u32
            if pv_ok = 1 then
                if pv_value = 1407915752 then
                    pv_kind = 'LINK'
                    strconcat pv_kind pv_recipe_text
                    pv_addr = pv_recipe + 812
                    pv_size = 12
                    call pv_dump_heap
                    pv_kind = 'RASTER'
                    strconcat pv_kind pv_recipe_text
                    pv_addr = pv_recipe + 2992
                    pv_size = 68
                    call pv_dump_heap
                endif
            endif
        endif
    endif
    pv_recipe_index = pv_recipe_index + 1
endwhile
pv_addr = pv_collection
pv_size = 48
pv_kind = 'COLLEND'
call pv_dump_heap
pv_addr = pv_process
pv_size = 960
pv_kind = 'PROCEND'
call pv_dump_heap
return

:pv_jpeg
pv_addr = pv_object + 35396
pv_size = 120
pv_kind = 'JPEG'
call pv_dump_heap
return
'''
    pins={1429864496:0x553A0030,1407914536:0x53EB1228,
          1408040024:0x53ECFC58,1407914480:0x53EB11F0,1407915752:0x53EB16E8}
    if any(d!=a for d,a in pins.items()):raise AssertionError('TTL decimal pin mismatch')
    return '\n'.join(entry)+'\n'+body+helper


def build(destination):
    if destination.exists():raise ValueError('immutable package already exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();audit(raw);audit_shell(raw)
    code=program();original=(ROOT/'examples/probe-sd-usb-session.ttl.example').read_text()
    original_sha='221d79821b4f7cbd2028477001529b02dcb8f9bfcf016cecffa11c71cf071c59'
    if hashlib.sha256(original.encode()).hexdigest()!=original_sha:raise ValueError('USB script changed')
    body,helpers=code.split('\n:pv_snapshot\n',1)
    body=body.rstrip()
    if not body.endswith('\nend'):raise ValueError('snapshot entry boundary changed')
    payload=original.replace('xpb_state = 1801\n',body[:-4]+'\nxpb_state = 1801\n',1)
    payload+='\n:pv_snapshot\n'+helpers
    destination.mkdir(parents=True);(destination/'script').mkdir();(destination/DIRECTORY).mkdir()
    (destination/'script/startup.ttl').write_text(payload,encoding='ascii')
    (destination/'restore-startup.ttl').write_text(original,encoding='ascii')
    manifest={'schema':'gr4-sd-preview-snapshot-v12','startup_sha256':hashlib.sha256(payload.encode()).hexdigest(),
              'snapshot_minimum_times_seconds':[15,75,135],'timing_includes_unverified_SD_read_overhead':True,
              'diagnostics_directory':DIRECTORY,'registry_node_limit_per_snapshot':512,
              'maximum_diagnostic_bytes':3*(4+32+512*24+2*960+8+16+120+2*48+8*88+120),
              'original_restore_sha256':original_sha,'existing_ROOT_behavior':'skip snapshots and keep USB protocol',
              'camera_RAM_settings_system_or_firmware_written':False,'SD_diagnostics_written':True,
              'atomic_snapshot_or_unique_registry_class_verified':False,
              'native_recipe_functions_called':False,'xpan_installed':False,'deployed':False,
              'USB_protocol_after_snapshots':1801,'diagnostic_filenames_fit_8_3':True}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'README.txt').write_text(
        '候选取样包，尚未部署，也不是 XPAN 安装器。\n'
        '备份原启动脚本，仅替换 script/startup.ttl，并在卡根目录建立空 XPV12 文件夹。\n'
        '开机后先不接 USB，在拍摄界面保持 3:2 约一分钟，再选 16:9 并试拍，保持开机约四分钟。\n'
        '三个取样点最早在 15/75/135 秒，实际取样耗时未验证。然后接 USB 影像显示。\n'
        '新增命令仅 SYS_md，把有限 RAM 字段读入 XPV12；不改设置或内部文件。\n'
        '检测到先前 ROOT 文件会跳过取样，继续原 USB 协议。\n'
        '恢复方法：相机关机后用 restore-startup.ttl 替换卡上启动脚本；诊断文件先归档再移除。\n'
        '读数不保证同一帧，不授权安装；USB 接入后对象可能释放。\n',encoding='utf8')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.output);print('Prepared local shooting-mode snapshot candidate:',a.output)
