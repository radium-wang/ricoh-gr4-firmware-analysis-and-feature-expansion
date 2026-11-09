#!/usr/bin/env python3
"""Run native adapter instructions locally; intercept allocation and OS calls."""

import argparse
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                              UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR)

from audit_gr4_rom_call_adapter import ADAPTER, ADAPTER_BYTES, audit
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access


def check(raw):
    evidence = audit(raw)
    check_host_cache_access()
    tests = [(0x538C9760, (11, 13, 17), 3, False),
             (0x538E0A24, (8192, 0, 0), 0x59180000, True),
             (0x538E0A60, (0x59180000, 0, 0), 0, True),
             (0x53088470, (0x60000200, 0x01010311, 0), 4096, True)]
    results = []
    for target, arguments, expected, simulated in tests:
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(ADAPTER & ~4095, 4096)
        uc.mem_write(ADAPTER, ADAPTER_BYTES)
        uc.mem_map(target & ~4095, 4096)
        if not simulated:
            uc.mem_write(target, raw[file_offset(target):file_offset(target) + 8])
        uc.mem_map(0x60000000, 0x3000)
        uc.mem_write(0x60000000, struct.pack('<I', 0x60000100))
        uc.mem_write(0x60000100, struct.pack('<5I', target, 0, *reversed(arguments)))
        uc.reg_write(UC_ARM_REG_SP, 0x60002000)
        uc.reg_write(UC_ARM_REG_LR, 0x60001000)
        uc.reg_write(UC_ARM_REG_R0, 0x60000000)
        uc.reg_write(UC_ARM_REG_R1, 0xDEADBEEF)
        uc.reg_write(UC_ARM_REG_R2, 0xCAFEBABE)
        observed = []

        def entry(machine, address, _size, _context):
            if address != target:
                return
            observed.append(tuple(machine.reg_read(r) for r in
                                  (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2)))
            if simulated:
                machine.reg_write(UC_ARM_REG_R0, expected)
                machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))

        uc.hook_add(UC_HOOK_CODE, entry)
        uc.emu_start(ADAPTER, 0x60001000, timeout=1000000, count=100)
        assert uc.reg_read(UC_ARM_REG_PC) == 0x60001000
        assert observed == [arguments]
        assert uc.reg_read(UC_ARM_REG_R0) == expected
        assert uc.reg_read(UC_ARM_REG_SP) == 0x60002000
        results.append({'target': hex(target), 'arguments': list(arguments),
                        'return_value': expected, 'target_simulated': simulated})
    return {'sample_sha256': evidence['sample_sha256'], 'cases_passed': len(results),
            'execution': 'original 13 adapter instructions; original return-3 leaf',
            'camera_accessed': False, 'native_allocation_or_cache_verified': False,
            'camera_installable': False, 'cases': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.sample.read_bytes()), indent=2))
    except RuntimeError as error:
        parser.exit(1, str(error) + '\n')
