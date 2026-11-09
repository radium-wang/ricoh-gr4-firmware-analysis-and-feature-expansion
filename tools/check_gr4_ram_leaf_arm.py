#!/usr/bin/env python3
"""Execute original cache argument validation and exact leaf offline.

Privileged cache maintenance itself is intercepted, not performed on a camera.
This checks the real ROM branch for (2,1) versus rejected (3,1), which the
lifecycle model does not emulate.
"""
import json
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

from check_gr4_native_memory_abi import check_host_cache_access
from mtp_factory_ram_leaf_trial import audit, ROM, IALL, CODE


def check(raw):
    audit(raw)
    check_host_cache_access()
    cases=[]
    for arg0,expected in [(3,0xFFEF0000),(2,0)]:
        machine=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        machine.mem_map(0x53087000,0x1000)
        machine.mem_write(IALL,ROM[IALL])
        machine.mem_map(0x60000000,0x3000)
        machine.reg_write(UC_ARM_REG_SP,0x60001000)
        machine.reg_write(UC_ARM_REG_LR,0x60002000)
        machine.reg_write(UC_ARM_REG_R0,arg0)
        machine.reg_write(UC_ARM_REG_R1,1)
        reached=[]
        def intercept(uc,address,size,context):
            if address==0x53087C70:
                reached.append('ICIALLUIS')
                uc.reg_write(UC_ARM_REG_PC,address+4)
        machine.hook_add(UC_HOOK_CODE,intercept)
        machine.emu_start(IALL,0x60002000,count=80,timeout=1000000)
        result=machine.reg_read(UC_ARM_REG_R0)
        assert result==expected and reached==(['ICIALLUIS'] if arg0==2 else [])
        assert machine.reg_read(UC_ARM_REG_SP)==0x60001000
        cases.append({'arguments':[arg0,1],'return':hex(result),'cache_operation_simulated':reached})
    machine=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    machine.mem_map(0x60000000,0x3000)
    machine.mem_write(0x60001000,CODE)
    machine.reg_write(UC_ARM_REG_LR,0x60002000)
    machine.emu_start(0x60001000,0x60002000,count=4,timeout=1000000)
    assert machine.reg_read(UC_ARM_REG_R0)==65
    cases.append({'case':'exact_payload_return','return':65})
    return {'cases_passed':len(cases),'camera_accessed':False,
            'cache_operation_simulated':True,'original_argument_branches_executed':True,'cases':cases}


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    result=check((root/'samples/gr4_decoded.bin').read_bytes())
    report=root/'devkit-output/usb-factory-20261001/ram-leaf-arm-checks.json'
    report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
