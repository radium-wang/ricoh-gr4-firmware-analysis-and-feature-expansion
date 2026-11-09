#!/usr/bin/env python3
"""Execute original menu routing/ABI instructions offline; framework calls mocked."""
import argparse
import json
from pathlib import Path
import struct

from audit_gr4_ui_native_routes import audit
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access


def check(raw):
    evidence=audit(raw)
    check_host_cache_access()
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
        UC_ARM_REG_R3,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC)
    machine=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for start,length in ((0x53185000,0x3000),(0x531C0000,0x1C000),
                         (0x53DA0000,0x20000)):
        machine.mem_map(start,length)
        machine.mem_write(start,raw[file_offset(start):file_offset(start)+length])
    services=(0x5323EA84,0x5323F378,0x5323F018,0x5337FBAC,
              0x5357ADE0,0x532F8490,0x5329C09C)
    for page in sorted(set(a&~0xFFF for a in services)):
        machine.mem_map(page,0x1000)
    machine.mem_map(0x60000000,0x4000)
    events=[]
    current_native=[0]
    def intercept(uc,address,size,context):
        if address not in services+(0x531D76E4,):return
        args=[uc.reg_read(reg) for reg in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
        events.append({'address':hex(address),'args':args})
        value={0x5329C09C:current_native[0],0x5337FBAC:0x60000900}.get(address,0x60000800)
        uc.reg_write(UC_ARM_REG_R0,value)
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
    machine.hook_add(UC_HOOK_CODE,intercept)
    def run(entry,args):
        events.clear()
        for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),args):
            machine.reg_write(reg,value)
        machine.reg_write(UC_ARM_REG_SP,0x60003F00)
        machine.reg_write(UC_ARM_REG_LR,0x60003000)
        machine.emu_start(entry,0x60003000,count=500)
        if machine.reg_read(UC_ARM_REG_PC)!=0x60003000 or machine.reg_read(UC_ARM_REG_SP)!=0x60003F00:
            raise AssertionError('original function did not return with its original stack')
        return machine.reg_read(UC_ARM_REG_R0),list(events)
    cases=[]
    # Original factory code follows already-existing synthetic pointers only.
    # Constructors, malloc and GUI operations are never executed by this test.
    for offset in range(0,0x1CC,4):
        machine.mem_write(0x60000100+offset,struct.pack('<I',0x59000000+offset))
    for ui_id in (0x0200008A,0x020000F0,0x0200012B):
        value,ev=run(0x53185F7C,[0x60000100,ui_id,0])
        assert value==0x590000B0 and not ev
        cases.append({'case':'cached factory route','ui_id':hex(ui_id),'slot':0xB0})
    controller=0x60001000
    machine.mem_write(controller,bytes(0x1E4))
    value,ev=run(0x531D5E8C,[controller,0x0200008A,0])
    assert bytes(machine.mem_read(controller+0x1A4,1))==b'\x22' and not ev
    cases.append({'case':'aspect UI ID maps to descriptor row','row':34})
    value,ev=run(0x531CF298,[controller,0,0]);assert value==4 and not ev
    cases.append({'case':'original count','count':4})
    for index,native in enumerate((0,1,3,2)):
        value,ev=run(0x531D0CCC,[controller,0x60002000,index])
        text=[x for x in ev if x['address']==hex(0x5337FBAC)]
        gui=[x for x in ev if x['address']==hex(0x5357ADE0)]
        assert text[0]['args'][1]==native and gui[0]['args'][:2]==[0x60002000,0x60000900]
        cases.append({'case':'native label ABI','menu_index':index,'native_id':native,
                      'item_argument':'r1','index_argument':'r2'})
        for entry,confirm in ((0x531D2F70,False),(0x531D8FFC,True)):
            value,ev=run(entry,[controller,index,0])
            calls=[x for x in ev if x['address']==hex(0x532F8490)]
            assert calls[0]['args'][1]==native
            refresh=[x for x in ev if x['address']==hex(0x531D76E4)]
            assert len(refresh)==int(confirm)
            if confirm:assert refresh[0]['args'][0]==controller
            cases.append({'case':'confirm ABI' if confirm else 'setter ABI',
                          'menu_index':index,'native_id':native,'refresh_mocked':confirm})
        for native_state in range(4):
            current_native[0]=native_state
            value,ev=run(0x531D4898,[controller,index,0])
            assert value==int(native_state==native)
            cases.append({'case':'selected predicate ABI','menu_index':index,
                          'native_state':native_state,'selected':bool(value)})
    return {'schema':'gr4-ui-native-arm-check-v1','sample_sha256':evidence['sample_sha256'],
            'cases_passed':len(cases),'cases':cases,'original_ARM_instructions_executed':True,
            'camera_accessed':False,'GUI_and_property_services_mocked':True,
            'fifth_index_not_passed_to_original_four_entry_handlers':True,
            'actual_controller_lifetime_or_hook_synchronization_verified':False,
            'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    if args.report.exists():raise ValueError('report already exists')
    result=check((Path(__file__).resolve().parents[1]/'samples/gr4_decoded.bin').read_bytes())
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('Original ARM route/ABI cases passed:',result['cases_passed'])
    print('Framework/property calls were simulated; camera was not accessed.')


if __name__=='__main__':main()
