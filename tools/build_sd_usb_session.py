#!/usr/bin/env python3
"""Build the bounded multi-call protocol locally, without SD or camera access."""

import argparse
import hashlib
import json
from pathlib import Path

from audit_gr4_native_memory_abi import audit as audit_memory
from audit_gr4_rom_call_adapter import audit as audit_adapter
from audit_xpan_paths import require, file_offset
from gr4_usb_call_session import MALLOC, MALLOC_BYTES, FREE, FREE_BYTES
from check_gr4_usb_call_session import check


def build(sample, destination):
    if destination.exists():
        raise ValueError('output already exists')
    raw = sample.read_bytes()
    memory = audit_memory(raw)
    audit_adapter(raw)
    require(raw, file_offset(MALLOC), MALLOC_BYTES, 'complete malloc wrapper')
    require(raw, file_offset(FREE), FREE_BYTES, 'complete free wrapper')
    checks = check()
    source = Path(__file__).resolve().parents[1]/'examples/probe-sd-usb-session.ttl.example'
    payload = source.read_bytes()
    sends = [line.strip() for line in payload.splitlines() if line.strip().startswith(b'sendln ')]
    if sends != [b"sendln 'SYS_buildinfo'", b'sendln #144#25#59#85']:
        raise ValueError('unexpected engineering commands')
    for line in (b'str2code xpb_input_code #144#25#59#85', b'if xpb_go != xpb_done + 1 then',
                 b'xpb_return = result', b'xpb_done = xpb_go', b'if xpb_go > 16 then'):
        if line not in payload:
            raise ValueError('missing protocol guard')
    manifest = {'protocol':1801, 'sample_sha256':memory['sample_sha256'],
                'files':{'script/startup.ttl':{'length':len(payload), 'sha256':hashlib.sha256(payload).hexdigest()}},
                'host_fault_checks_passed':checks['cases_passed'],
                'maximum_native_calls_per_boot':16, 'waiting_minutes_approx':15,
                'trial_allocation_bytes':8192, 'trial_data_bytes':32,
                'cache_trial_owned_output_bytes':20,
                'script_camera_memory_writes':False, 'host_trial_camera_ram_writes':True,
                'native_code_uploaded':False, 'firmware_written':False, 'xpan_installed':False,
                'hardware_allocation_verified':False, 'deployed':False}
    destination.mkdir(parents=True)
    (destination/'script').mkdir()
    (destination/'script/startup.ttl').write_bytes(payload)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (destination/'host-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    (destination/'README.txt').write_text(
        'GR IV 01.11.10.07 连续 USB 调用候选包。尚未部署或执行分配。\n'
        '只替换一个 script/startup.ttl；先备份已核对的旧脚本和项目日志，保留照片与原有文件。\n'
        '开机接 USB 影像显示即可，15 分钟是等待上限，无需等满。\n'
        '每个编号只执行一次；主机完成恢复后才能提交下一个编号。\n'
        'tools/mtp_factory_allocator_trial.py 默认只读；--trial 执行一整轮：\n'
        '原厂返回 3 → malloc(8192) → 自有区域 32 字节读写及原值恢复 → free → 再次返回 3。\n'
        '每次调用均恢复两个回调和 20 字节临时记录。成功释放须原厂返回 1。\n'
        '中断后 --recover 读取已执行编号，不重复 malloc/free；跨重启拒绝使用旧指针。\n'
        '恢复需要 USB 可用及同一脚本会话；阻塞或释放失败时保留记录，正常重启后先只读核对。\n'
        '--cache-trial 可复用脚本：malloc → 内存查询 → 数据/指令缓存维护 → free → 原厂返回 3。\n'
        '缓存测试仅覆盖自有分配内的 64 字节数据及 20 字节输出，逐项恢复。\n'
        '只使用固定原厂函数，不上传/执行新代码、不刷固件或改版本。\n'
        '脚本在卡上追加 XPSESSION.TXT；本包没有安装 XPAN。\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.sample,args.destination),indent=2))
