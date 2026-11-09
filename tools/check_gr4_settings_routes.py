#!/usr/bin/env python3
"""Offline ARM checks of fifth-item refresh, navigation and confirmation.

Execute linked project code, original enable-count, navigation and rectangle
instructions. GUI text, property, lifecycle, division and layout services are
simulated. No installer, real pipeline or camera access is provided.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from check_gr4_settings_backend import build, ROOT, BASE
from check_gr4_native_memory_abi import check_host_cache_access
from audit_gr4_menu_widgets import audit
from audit_xpan_paths import file_offset

NAMES = ['gr4_xpan_settings_' + suffix for suffix in
         ('refresh','activate','list_confirm','button_confirm','event')]
C=0x5A010000
L=0x5A011000
VECTOR=0x5A012000
CTX=0x5A013000
STATE=CTX+0x100
EVENT=CTX+0x200
STOP=0x5A01F000


def check(raw,data,offsets):
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
        UC_ARM_REG_R3,UC_ARM_REG_PC,UC_ARM_REG_SP,UC_ARM_REG_LR)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    pages=(0x53571000,0x53570000,0x53589000,0x538E9000,0x538EA000,0x53E98000)
    for page in pages:
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    services=(0x531DA9D4,0x531DAD8C,0x531D0CCC,0x531D2F70,0x531D8FFC,
              0x53182E9C,0x5357AE1C,0x5357AD40,0x53571100,0x535713BC,
              0x535899FC,0x53571514,0x53570C94,0x53153830,0x5315384C,
              0x538ED930)
    resize=struct.unpack_from('<I',raw,file_offset(0x53E98468+0x18))[0]
    services=(*services,resize)
    for page in sorted({a&~0xFFF for a in services}-set(pages)):u.mem_map(page,4096)
    u.mem_map(C,0x10000);u.mem_map(BASE,8192);u.mem_write(BASE,data)
    records=[VECTOR+0x100+i*8 for i in range(5)]
    items=[C+0x4000+i*0x400 for i in range(5)]
    ascii=C+0x6000
    events=[]
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    def hook(machine,address,size,context):
        if address not in services:return
        args=[machine.reg_read(r) for r in regs];events.append((address,args));ret=0
        if address in (0x531DA9D4,0x531DAD8C):
            machine.mem_write(L+0x108,b'\x04');machine.mem_write(L+0x110,b'\0\0')
        elif address==0x53571100:machine.mem_write(args[0]+0x110,struct.pack('<H',args[1]))
        elif address in (0x53153830,0x5315384C):
            assert args[1]
            ret=args[0]//args[1]
            machine.reg_write(UC_ARM_REG_R1,args[0]%args[1])
        elif address==0x538ED930:raise AssertionError('original assertion reached')
        elif address==resize:
            machine.mem_write(args[0]+0x20,bytes(machine.mem_read(args[1],16)))
        elif address==0x5357AE1C:
            assert bytes(machine.mem_read(args[1],5))==b'XPAN\0'
        machine.reg_write(UC_ARM_REG_R0,ret)
        machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook)
    def reset(aspect=0):
        u.mem_write(C,bytes(0x7000))
        u.mem_write(C,struct.pack('<I',0x53DA2C70));u.mem_write(C+0x124,struct.pack('<I',0x0200008A))
        u.mem_write(C+0x1A4,b'\x22');u.mem_write(C+0x198,struct.pack('<I',L))
        u.mem_write(L,struct.pack('<I',0x53E98468))
        u.mem_write(L+0xF4,struct.pack('<3I',VECTOR,VECTOR+20,VECTOR+256))
        u.mem_write(VECTOR,struct.pack('<5I',*records))
        for record,item in zip(records,items):
            u.mem_write(record,struct.pack('<I',item)+b'\0\x77\xD7\x79')
            u.mem_write(item,struct.pack('<I',0x53E98F18))
        u.mem_write(items[4]+0x100,struct.pack('<I',ascii));u.mem_write(ascii,struct.pack('<I',0x53E97FD8))
        u.mem_write(CTX,struct.pack('<3I',C,STATE,15));u.mem_write(STATE,struct.pack('<3I',2,aspect,0))
        # Native list geometry and row height for original navigation.
        u.mem_write(L+0x20,struct.pack('<4I',60,0,720,300))
        u.mem_write(L+0x108,b'\x05');u.mem_write(L+0x120,struct.pack('<I',60))
    def run(name,args):
        events.clear()
        for r,v in zip(regs,args):u.reg_write(r,v)
        u.reg_write(UC_ARM_REG_SP,C+0xE000);u.reg_write(UC_ARM_REG_LR,STOP)
        u.emu_start(BASE+offsets[name],STOP,count=30000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==STOP and u.reg_read(UC_ARM_REG_SP)==C+0xE000
        return u.reg_read(UC_ARM_REG_R0),list(events)
    cases=[]
    for name in NAMES[:2]:
        for aspect,index in ((0,0),(1,1),(3,2),(2,3),(4,4)):
            reset(aspect);ret,ev=run(name,[CTX,0,0,0]);assert ret==1
            assert u.mem_read(L+0x108,1)==b'\x05'
            assert struct.unpack('<H',u.mem_read(L+0x110,2))[0]==index
            assert u.mem_read(C+0x1A6,1)==bytes([index])
            assert len([a for a,v in ev if a==0x5357AE1C])==1
            assert struct.unpack('<4I',u.mem_read(L+0x20,16))[3]==300
            for record in records:assert u.mem_read(record+4,4)==b'\x01\x77\xD7\x79'
            cases.append({'case':'native refresh/activation followed by five-item presentation',
                          'route':name,'selected_index':index,'padding_preserved':True})
    for readiness in (0,1,3,7):
        reset();u.mem_write(CTX+8,struct.pack('<I',readiness))
        ret,ev=run(NAMES[0],[CTX,0,0,0]);assert ret==0
        assert u.mem_read(L+0x108,1)==b'\x04' and all(a!=0x5357AE1C for a,v in ev)
        cases.append({'case':'incomplete capture/icon readiness does not enable fifth item','flags':readiness})
    for code in (0xD6,0xDA,0xD7,0xDB):
        for index in range(5):
            reset();u.mem_write(L+0x110,struct.pack('<H',index));u.mem_write(EVENT,struct.pack('<H',code))
            ret,ev=run(NAMES[4],[CTX,EVENT,0,0]);assert ret==1
            expected=((index-1)%5 if code==0xD6 else max(index-1,0) if code==0xDA
                      else (index+1)%5 if code==0xD7 else min(index+1,4))
            assert struct.unpack('<H',u.mem_read(L+0x110,2))[0]==expected
            cases.append({'case':'original list navigation uses all five entries',
                          'code':hex(code),'before':index,'after':expected})
    for route in ('list_confirm','button_confirm','event'):
        for index in range(5):
            reset();u.mem_write(L+0x110,struct.pack('<H',index));u.mem_write(EVENT,b'\xE0\0')
            second=index if route=='list_confirm' else EVENT if route=='event' else 0
            ret,ev=run('gr4_xpan_settings_'+route,[CTX,second,0,0]);assert ret==1
            calls=[(a,v) for a,v in ev if a in (0x531D2F70,0x531D8FFC)]
            assert len(calls)==1 and calls[0][1][:2]==[C,0 if index==4 else index]
            assert struct.unpack('<3I',u.mem_read(STATE,12))[:2]==(2,(0,1,3,2,4)[index])
            assert len([a for a,v in ev if a==0x53182E9C])==int(route=='button_confirm')
            cases.append({'case':'all confirmation routes guard fifth index and preserve crop',
                          'route':route,'index':index})
    for fault in ('wrong row','wrong class','four constructed','wrong item','wrong ASCII','bad selection','unrelated event'):
        reset();u.mem_write(EVENT,b'\xE0\0')
        if fault=='wrong row':u.mem_write(C+0x1A4,b'\x21')
        elif fault=='wrong class':u.mem_write(C,bytes(4))
        elif fault=='four constructed':u.mem_write(L+0xF8,struct.pack('<I',VECTOR+16))
        elif fault=='wrong item':u.mem_write(items[4],bytes(4))
        elif fault=='wrong ASCII':u.mem_write(ascii,bytes(4))
        elif fault=='bad selection':u.mem_write(L+0x110,struct.pack('<H',5))
        else:u.mem_write(EVENT,b'\x15\0')
        ret,ev=run(NAMES[4],[CTX,EVENT,0,0]);assert ret==0 and not ev
        cases.append({'case':'invalid or unrelated operation returns to ABI adapter','fault':fault})
    return {'cases_passed':len(cases),'cases':cases,'linked_routes_ARM_executed':True,
            'original_count_navigation_rectangle_ARM_executed':True,
            'GUI_text_property_lifecycle_division_layout_services_simulated':True,
            'readiness_flags_simulated_not_real_pipeline_evidence':True,
            'native_ABI_adapters_installer_quiescence_and_undo_pending':True,
            'camera_accessed':False,'xpan_installed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('immutable output already exists')
    raw=(ROOT/'samples/gr4_decoded.bin').read_bytes();evidence=audit(raw)
    data,offsets=build(a.output,('xpan_settings_routes.c',),NAMES)
    result=check(raw,data,offsets)
    result.update(schema='gr4-settings-routes-check-v1',audit=evidence,backend_bytes=len(data),
                  backend_sha256=hashlib.sha256(data).hexdigest(),entry_offsets=offsets)
    (a.output/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Offline ARM route checks passed:',result['cases_passed'])


if __name__=='__main__':main()
