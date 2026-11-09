#!/usr/bin/env python3
"""Prepare a supervised SD/USB probe locally. No camera or SD access."""

import argparse
import hashlib
import json
from pathlib import Path

from audit_gr4_rom_call_adapter import audit


def build(sample, destination):
    evidence = audit(sample.read_bytes())
    if destination.exists():
        raise ValueError('output already exists; choose a new directory')
    source = Path(__file__).resolve().parents[1] / 'examples/probe-sd-usb-call-gate.ttl.example'
    script = source.read_bytes()
    sends = [line.strip() for line in script.splitlines() if line.strip().startswith(b'sendln ')]
    if sends != [b"sendln 'SYS_buildinfo'", b'sendln #144#25#59#85'] or any(
            token in script for token in (b"sendln 'SYS_reg", b"sendln 'SYS_cache", b"sendln 'lcmd")):
        raise ValueError('unexpected probe payload')
    if b'str2code xpg_input_code #144#25#59#85' not in script or b'if xpg_input_code != -1877394603 then' not in script:
        raise ValueError('binary input self-check is missing')
    destination.mkdir(parents=True)
    script_dir = destination / 'script'
    script_dir.mkdir()
    (script_dir / 'startup.ttl').write_bytes(script)
    manifest = {'sample_sha256': evidence['sample_sha256'],
                'files': {'script/startup.ttl': {'length': len(script), 'sha256': hashlib.sha256(script).hexdigest()}},
                'script_camera_memory_writes': False, 'host_trial_controller_available': True,
                'host_trial_ram_write_words': 7,
                'host_fault_checks_passed': 10,
                'binary_sendln_verified_on_camera': False, 'camera_installable_xpan': False}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'README.txt').write_text(
        '本地候选实验包，尚未部署。仅适配 GR IV 01.11.10.07。\n'
        'startup.ttl 本身不写相机内存、不改设置或固件，只在 SD 卡追加 XPGATE.TXT 日志。\n'
        '相机启动后需保持 USB 影像显示连接；脚本最多等待约 10 分钟。\n'
        '只读 USB 工具为 tools/mtp_factory_script_context_readonly.py。\n'
        '先核对回调、变量表、原始缓冲和四字节输入自检；未通过时主机拒绝写入。\n'
        '控制器 tools/mtp_factory_rom_adapter_trial.py 默认只读；--trial 只调用原厂返回 3 短函数。\n'
        '只临时改两个 TTL 回调指针和回复缓冲的五个字，恢复时逐字写回备份并读回。\n'
        '异常后 --restore-only 使用写前保存的电脑端日志恢复；USB 须仍可用，脚本代次须匹配。\n'
        '任何返回值不是 -1 时，脚本保存结果并保持 60 秒，随后结束，不再调用工程 shell。\n'
        '若 USB 消失或恢复失败，不继续实验；正常关机重开后先只读检查回调。\n'
        '此前已验证一个诊断 RAM 指针的正常重启恢复；这两个新回调槽的重启恢复仍待实机核对。\n'
        '彻底停用此包需在电脑删除已核对哈希的 script/startup.ttl；XPGATE.TXT 先备份再清理。\n'
        '此包没有安装 XPAN，也没有进行内存分配、缓存发布或新 ARM 代码执行。\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.sample, args.destination), indent=2))
