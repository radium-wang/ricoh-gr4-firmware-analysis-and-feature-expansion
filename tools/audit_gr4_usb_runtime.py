#!/usr/bin/env python3
"""Offline GR IV USB ACM audit using a bounded QEMU kernel memory snapshot.

Reads only the pinned decoded firmware. It never contacts the camera and does
not produce an installable firmware image.
"""

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from audit_xpan_paths import EXPECTED_SHA256
from gr4_firmware_parts import find_parts
from inspect_initfs_readonly import SquashFS


def kernel_config(parts):
    qemu = shutil.which("qemu-system-arm")
    if not qemu:
        raise RuntimeError("qemu-system-arm is required")
    with tempfile.TemporaryDirectory(prefix="gr4-usb-audit-") as directory:
        root = Path(directory)
        (root / "zImage").write_bytes(parts["kernel"].data)
        (root / "initfs").write_bytes(parts["initfs"].data)
        command = [
            qemu, "-M", "virt", "-cpu", "cortex-a7", "-m", "256M",
            "-display", "none", "-serial", "none", "-monitor", "stdio",
            "-nic", "none", "-no-reboot", "-kernel", "zImage",
            "-initrd", "initfs", "-append",
            "console=ttyAMA0,115200 earlycon=pl011,0x09000000 root=/dev/ram0 ro loglevel=8",
        ]
        process = subprocess.Popen(
            command, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(5)
            if process.poll() is not None:
                raise RuntimeError(f"QEMU exited early with status {process.returncode}")
            process.communicate(
                input=b'pmemsave 0x40000000 0x4000000 "ram.bin"\nquit\n',
                timeout=30,
            )
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        memory = (root / "ram.bin").read_bytes()
        if len(memory) != 64 * 1024 * 1024:
            raise RuntimeError("incomplete QEMU RAM snapshot")
    begin = memory.find(b"IKCFG_ST")
    end = memory.find(b"IKCFG_ED", begin + 8)
    if begin < 0 or end < 0:
        raise RuntimeError("decompressed kernel config marker was not found")
    config = gzip.decompress(memory[begin + 8:end]).decode("ascii")
    return config


def audit(sample):
    payload = sample.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError("only pinned GR IV 01.11.10.07 firmware is supported")
    parts = find_parts(payload)
    config = kernel_config(parts)
    required = {
        "CONFIG_USB_DWC3_GADGET=y",
        "CONFIG_USB_LIBCOMPOSITE=m",
        "CONFIG_USB_F_ACM=m",
        "CONFIG_USB_F_MTP=m",
        "CONFIG_USB_CONFIGFS=m",
        "CONFIG_USB_CONFIGFS_ACM=y",
        "CONFIG_USB_CONFIGFS_F_MTP=y",
    }
    lines = set(config.splitlines())
    missing = required - lines
    if missing:
        raise ValueError(f"unexpected kernel USB configuration: {sorted(missing)}")
    fs = SquashFS(parts["initfs"].data)
    modules_dir = "/lib/modules/5.15.190/kernel/drivers/usb/gadget/function"
    modules = {
        name for name, (_ref, kind) in fs.list_dir(fs.resolve(modules_dir)).items()
        if kind == 2
    }
    for name in ("usb_f_acm.ko", "usb_f_mtp.ko", "u_serial.ko"):
        if name not in modules:
            raise ValueError(f"missing gadget module: {name}")
    script = fs.read_file(fs.resolve("/usr/bin/usb30dev_mtp_func.sh"))
    for token in (b"functions/mtp.usb0", b"configs/c.1", b"19c00000.dwc3"):
        if token not in script:
            raise ValueError(f"unexpected stock gadget script: {token!r}")
    return {
        "sample_sha256": digest,
        "kernel_config_sha256": hashlib.sha256(config.encode()).hexdigest(),
        "verified_kernel_options": sorted(required),
        "gadget_function_modules": sorted(modules),
        "stock_usb_script_creates_mtp_config": True,
        "camera_probe_run": False,
        "linux_script_execution_proven": False,
        "runtime_acm_enumeration_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.sample), indent=2))


if __name__ == "__main__":
    main()
