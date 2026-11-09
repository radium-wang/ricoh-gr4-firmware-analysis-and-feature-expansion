#!/usr/bin/env python3
"""Prepare three shooting-state menu snapshots plus the unchanged USB session.

Local build only. SYS_md reads RAM into new SD diagnostic files. No SetData,
settings, callback, system-file or firmware write is emitted by the snapshot.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_gr4_ui_native_routes import audit

ROOT=Path(__file__).resolve().parents[1]


def program():
    lines=['; UI snapshot v1. GR IV 01.11.10.07 only. SD output only.']
    outputs=[]
    for suffix in 'ABC':
        outputs.extend('XU'+kind+suffix+'.BIN' for kind in ('ROOT','ADJ','SET','LIST','CALL','IM'))
    for name in outputs:
        lines.extend(["filesearch 'C:\\%s'"%name,'if result = 1 then','    goto ui_skip_capture','endif'])
    for suffix,delay in (('A',5000),('B',20000),('C',20000)):
        lines.extend(['mpause '+str(delay),"ui_suffix = '%s'"%suffix,'call ui_snapshot'])
    lines.extend([':ui_skip_capture','end'])
    helpers=r'''
:ui_snapshot
ui_addr = 1426591040
ui_size = 460
ui_kind = 'ROOT'
call ui_dump
if ui_ok = 0 then
    return
endif
ui_root_path = ui_path
ui_offset = 0
call ui_u32
if ui_ok = 0 then
    return
endif
if ui_value != 1406750472 then
    return
endif
; Capture only an exact original settings controller, never a guessed class.
ui_path = ui_root_path
ui_offset = 176
call ui_u32
ui_pointer = ui_value
if ui_ok = 1 then
    ui_addr = ui_pointer
    ui_size = 484
    ui_kind = 'SET'
    call ui_dump_heap
    if ui_ok = 1 then
        ui_offset = 0
        call ui_u32
        if ui_ok = 1 then
            if ui_value = 1406807152 then
                ui_offset = 408
                call ui_u32
                if ui_ok = 1 then
                    ui_addr = ui_value
                    ui_size = 400
                    ui_kind = 'LIST'
                    call ui_dump_heap
                    if ui_ok = 1 then
                        ui_offset = 0
                        call ui_u32
                        if ui_ok = 1 then
                            if ui_value >= 1406140416 then
                                if ui_value < 1413480448 then
                                    ui_offset = 360
                                    call ui_u32
                                    if ui_ok = 1 then
                                        ui_addr = ui_value
                                        ui_size = 4
                                        ui_kind = 'CALL'
                                        call ui_dump_heap
                                    endif
                                endif
                            endif
                        endif
                    endif
                endif
            endif
        endif
    endif
endif
ui_path = ui_root_path
ui_offset = 132
call ui_u32
if ui_ok = 1 then
    ui_addr = ui_value
    ui_size = 660
    ui_kind = 'ADJ'
    call ui_dump_heap
endif
ui_addr = 1429863524
ui_size = 32
ui_kind = 'IM'
call ui_dump
return

:ui_dump_heap
ui_ok = 0
if ui_addr < 1499463680 then
    return
endif
ui_end = ui_addr + ui_size
if ui_end <= ui_addr then
    return
endif
if ui_end > 1516240880 then
    return
endif
ui_align = ui_addr / 4
ui_align = ui_align * 4
if ui_align != ui_addr then
    return
endif
call ui_dump
return

:ui_dump
ui_ok = 0
ui_path = 'C:\XU'
strconcat ui_path ui_kind
strconcat ui_path ui_suffix
strconcat ui_path '.BIN'
filesearch ui_path
if result = 1 then
    return
endif
ui_command = 'SYS_md '
int2str ui_text ui_addr
strconcat ui_command ui_text
strconcat ui_command ' -s '
int2str ui_text ui_size
strconcat ui_command ui_text
strconcat ui_command ' -f '
strconcat ui_command ui_path
sendln ui_command
filestat ui_path ui_length
if result = 0 then
    if ui_length = ui_size then
        ui_ok = 1
    endif
endif
return

:ui_byte
ui_ok = 0
ui_value = 0
filestat ui_path ui_length
if result != 0 then
    return
endif
if ui_offset < 0 then
    return
endif
if ui_offset >= ui_length then
    return
endif
fileopen ui_fd ui_path 0
if ui_fd < 0 then
    return
endif
fileseek ui_fd ui_offset 0
fileread ui_fd 1 ui_char
if result = 0 then
    str2code ui_value ui_char
    ui_ok = 1
endif
fileclose ui_fd
return

:ui_u32
call ui_byte
ui_a = ui_value
ui_a_ok = ui_ok
ui_offset = ui_offset + 1
call ui_byte
ui_b = ui_value
ui_b_ok = ui_ok
ui_offset = ui_offset + 1
call ui_byte
ui_c = ui_value
ui_c_ok = ui_ok
ui_offset = ui_offset + 1
call ui_byte
ui_value = ui_a + ui_b * 256 + ui_c * 65536 + ui_value * 16777216
if ui_a_ok = 0 then
    ui_ok = 0
endif
if ui_b_ok = 0 then
    ui_ok = 0
endif
if ui_c_ok = 0 then
    ui_ok = 0
endif
return
'''
    # Explicit numeric pins, emitted as decimal for the camera's TTL parser.
    pins={1426591040:0x55080D40,1406750472:0x53D94F08,
          1406807152:0x53DA2C70,1429863524:0x5539FC64,
          1499463680:0x59600000,1516240880:0x5A5FFFF0,
          1406140416:0x53D00000,1413480448:0x54400000}
    for decimal,address in pins.items():
        if decimal!=address:raise AssertionError('TTL address conversion error')
    return '\n'.join(lines)+'\n'+helpers,outputs


def build(destination):
    if destination.exists():raise ValueError('destination already exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();evidence=audit(raw)
    prefix,outputs=program()
    original=(ROOT/'examples/probe-sd-usb-session.ttl.example').read_text()
    if hashlib.sha256(original.encode()).hexdigest()!='221d79821b4f7cbd2028477001529b02dcb8f9bfcf016cecffa11c71cf071c59':
        raise ValueError('original protocol 1801 script changed')
    # Run snapshots after successful buildinfo, before publishing protocol 1801.
    body=prefix.partition('\n:ui_snapshot')[0].rstrip()
    if not body.endswith('\nend'):raise ValueError('snapshot entry must terminate before helpers')
    body=body[:-4]
    helpers=prefix[prefix.index(':ui_snapshot'):]
    payload=original.replace('xpb_state = 1801\n',body+'\nxpb_state = 1801\n',1)+helpers
    destination.mkdir(parents=True);(destination/'script').mkdir()
    (destination/'script/startup.ttl').write_text(payload,encoding='ascii')
    (destination/'restore-startup.ttl').write_text(original,encoding='ascii')
    manifest={'schema':'gr4-sd-ui-snapshot-v1','sample_sha256':evidence['sample_sha256'],
              'startup_sha256':hashlib.sha256(payload.encode()).hexdigest(),
              'snapshot_times_seconds_approx':[5,25,45],'output_files':outputs,
              'maximum_SD_snapshot_bytes':3*(460+484+660+400+4+32),
              'camera_RAM_or_settings_written_by_snapshot':False,
              'firmware_written':False,'xpan_installed':False,'deployed':False,
              'USB_protocol_after_snapshots':1801,'original_restore_sha256':hashlib.sha256(original.encode()).hexdigest()}
    manifest['existing_snapshot_behavior']='preserve outputs, skip snapshots, keep original USB protocol active'
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'README.txt').write_text(
        'GR IV 01.11.10.07：拍摄状态菜单对象取样候选包。尚未部署。\n'
        '先备份当前 script/startup.ttl；只替换这一个文件。\n'
        '相机开机后不接 USB，立即打开画面比例菜单并保持至少 75 秒。\n'
        '脚本在约 5、25、45 秒取样；之后退出菜单再接 USB 影像显示。\n'
        '先前连续调用协议 1801 随后等待约 15 分钟，不需等满。\n'
        '只读原厂 RAM，写入卡根目录 XU*.BIN 诊断文件，不改设置或内部系统文件。\n'
        '任一指定输出文件已存在便跳过取样，保留旧记录并继续 USB 协议。\n'
        '恢复：正常关机后将 restore-startup.ttl 还原到 script/startup.ttl。\n'
        '要完全停用实验：备份后移除自己放入的 script/startup.ttl，正常重启。\n'
        '这不是 XPAN 安装包；待验证菜单活动期对象和回调后才能继续原生挂钩。\n')
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path)
    args=p.parse_args();print(json.dumps(build(args.destination),indent=2))
