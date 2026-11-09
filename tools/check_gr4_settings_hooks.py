#!/usr/bin/env python3
"""Execute patched native UI entries and replay trampolines on synthetic objects.

Original two-instruction prologues, project wrappers, count/navigation/rectangle
ARM execute. Remaining original UI bodies and text/property/lifecycle services
are modeled; this does not verify a real camera, image pixels or task locks.
"""
import argparse
import json
from pathlib import Path
import struct
from build_gr4_settings_hooks import build,SITES,BASE
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access
from check_gr4_settings_routes import C,L,VECTOR,CTX,STATE,EVENT,STOP


def check(raw,data,offsets):
    check_host_cache_access()
    from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,
        UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
        UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,
        UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_CPSR)
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,
        UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,
        UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR)
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    pages=(0x531DA000,0x531D7000,0x531D6000,0x53571000,0x53570000,
           0x53589000,0x538E9000,0x538EA000,0x53E98000)
    for page in pages:
        u.mem_map(page,4096);u.mem_write(page,raw[file_offset(page):file_offset(page)+4096])
    services=(0x531D0CCC,0x531D2F70,0x531D8FFC,0x53182E9C,0x5357AE1C,
        0x5357AD40,0x53571100,0x535713BC,0x535899FC,0x53571514,0x53570C94,
        0x53153830,0x5315384C,0x538ED930)
    resize=struct.unpack_from('<I',raw,file_offset(0x53E98468+0x18))[0]
    services=(*services,resize)
    for page in sorted({a&~0xFFF for a in services}-set(pages)):u.mem_map(page,4096)
    u.mem_map(C,0x10000);u.mem_map(BASE,8192);u.mem_write(BASE,data)
    cases=[]
    # Compare every register, flags and saved stack of relocated prologues
    # against executing the original two instructions at their native address.
    for name,address,original in SITES:
        for flags in (0x10,0xF8000010):
            initial=[0x12340000+i for i in range(15)]
            initial[0]=C;initial[1]=EVENT;initial[13]=C+0xE000;initial[14]=STOP
            u.mem_write(C+0x1A4,b'\x22');u.mem_write(EVENT,b'\xE0\0')
            results=[]
            for entry in (address,BASE+offsets['gr4_xpan_settings_'+name+'_original']):
                u.mem_write(C+0xDF00,b'\xCC'*256)
                u.reg_write(UC_ARM_REG_CPSR,flags)
                for r,v in zip(regs,initial):u.reg_write(r,v)
                u.emu_start(entry,address+8,count=100)
                assert u.reg_read(UC_ARM_REG_PC)==address+8
                results.append(([u.reg_read(r) for r in regs],u.reg_read(UC_ARM_REG_CPSR),
                                bytes(u.mem_read(C+0xDF00,256))))
            assert results[0]==results[1],('prologue replay differs',name,results)
            cases.append(dict(case='original prologue replay identical',entry=name,flags=hex(flags)))
    for name,address,original in SITES:
        u.mem_write(address,bytes.fromhex('04f01fe5')+struct.pack('<I',BASE+offsets['gr4_xpan_settings_'+name+'_hook']))
    records=[VECTOR+0x100+i*8 for i in range(5)]
    items=[C+0x4000+i*0x400 for i in range(5)]
    resumes={address+8:name for name,address,original in SITES}
    events=[];native_index=[0];plan_bound=[False]
    def ret(machine,value=0):
        machine.reg_write(UC_ARM_REG_R0,value)
        machine.reg_write(UC_ARM_REG_PC,machine.reg_read(UC_ARM_REG_LR))
    def intercept(machine,address,size,context):
        if address in resumes:
            name=resumes[address];events.append(('original '+name,machine.reg_read(UC_ARM_REG_R0)))
            if name in ('activate','button'):
                sp=machine.reg_read(UC_ARM_REG_SP)
                saved=struct.unpack('<6I',machine.mem_read(sp,24))
                for r,v in zip((UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R11,UC_ARM_REG_LR),
                               (saved[0],saved[1],saved[2],saved[4])):machine.reg_write(r,v)
                machine.reg_write(UC_ARM_REG_SP,saved[3])
            if name in ('refresh','activate'):
                machine.mem_write(L+0x108,b'\x04')
                machine.mem_write(L+0x110,struct.pack('<H',native_index[0]))
                machine.mem_write(L+0x2C,struct.pack('<I',240))
            if name=='button':events.append(('original close',0))
            ret(machine);return
        if address not in services:return
        args=[machine.reg_read(r) for r in regs[:4]];events.append((hex(address),args))
        if address in (0x531D2F70,0x531D8FFC):
            # Observe publication BEFORE native setter and its nested refresh.
            state=struct.unpack('<3I',machine.mem_read(STATE,12))
            if plan_bound[0]:
                enabled=struct.unpack('<I',machine.mem_read(CTX+0x500,4))[0]
                assert enabled==int(state[1]==4),'observer saw inconsistent state/plan'
            assert args[1]<4
            if state[1]==4:assert args[1]==0
            native_index[0]=args[1]
            machine.reg_write(UC_ARM_REG_PC,0x531DA9D4);return
        if address==0x53571100:machine.mem_write(args[0]+0x110,struct.pack('<H',args[1]))
        elif address in (0x53153830,0x5315384C):
            assert args[1];machine.reg_write(UC_ARM_REG_R1,args[0]%args[1]);ret(machine,args[0]//args[1]);return
        elif address==0x538ED930:raise AssertionError('native assertion')
        elif address==resize:machine.mem_write(args[0]+0x20,bytes(machine.mem_read(args[1],16)))
        elif address==0x5357AE1C:assert bytes(machine.mem_read(args[1],5))==b'XPAN\0'
        ret(machine)
    u.hook_add(UC_HOOK_CODE,intercept)
    def run(entry,args):
        events.clear()
        for r,v in zip(regs[:4],args):u.reg_write(r,v)
        for i,r in enumerate(regs[4:12]):u.reg_write(r,0xACE00000+i)
        u.reg_write(UC_ARM_REG_SP,C+0xE000);u.reg_write(UC_ARM_REG_LR,STOP)
        u.emu_start(entry,STOP,count=50000,timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==STOP and u.reg_read(UC_ARM_REG_SP)==C+0xE000
        assert [u.reg_read(r) for r in regs[4:12]]==[0xACE00000+i for i in range(8)]
        return u.reg_read(UC_ARM_REG_R0),list(events)
    def reset(aspect=0):
        run(BASE+offsets['gr4_xpan_settings_bind_selection'],[0]);plan_bound[0]=False
        u.mem_write(C,bytes(0x7000));u.mem_write(C,struct.pack('<I',0x53DA2C70))
        u.mem_write(C+0x124,struct.pack('<I',0x0200008A));u.mem_write(C+0x1A4,b'\x22')
        u.mem_write(C+0x198,struct.pack('<I',L));u.mem_write(L,struct.pack('<I',0x53E98468))
        u.mem_write(L+0xF4,struct.pack('<3I',VECTOR,VECTOR+20,VECTOR+256))
        u.mem_write(VECTOR,struct.pack('<5I',*records))
        for record,item in zip(records,items):
            u.mem_write(record,struct.pack('<I',item)+b'\0\x77\xD7\x79')
            u.mem_write(item,struct.pack('<I',0x53E98F18))
        u.mem_write(items[4]+0x100,struct.pack('<I',C+0x6000));u.mem_write(C+0x6000,struct.pack('<I',0x53E97FD8))
        u.mem_write(CTX,struct.pack('<3I',C,STATE,15));u.mem_write(STATE,struct.pack('<3I',2,aspect,1))
        u.mem_write(L+0x20,struct.pack('<4I',60,0,720,300));u.mem_write(L+0x108,b'\x05')
        u.mem_write(L+0x120,struct.pack('<I',60));u.mem_write(EVENT,b'\xE0\0')
        u.mem_write(CTX+0x300,struct.pack('<I',CTX+0x304));u.mem_write(CTX+0x304,struct.pack('<I',C))
        native_index[0]=(0,1,3,2,0)[aspect]
        assert run(BASE+offsets['gr4_xpan_settings_hooks_bind'],[CTX])[0]==1
    for name,address,original in SITES[:2]:
        for aspect,index in ((0,0),(1,1),(3,2),(2,3),(4,4)):
            reset(aspect);_,ev=run(address,[C]);assert u.mem_read(L+0x108,1)==b'\x05'
            assert struct.unpack('<H',u.mem_read(L+0x110,2))[0]==index
            assert len([e for e in ev if e[0]=='original '+name])==1
            cases.append(dict(case='patched refresh/activation delegates once then presents five',entry=name,index=index))
    for name,address,original in SITES:
        reset();u.mem_write(C+0x1A4,b'\x21')
        _,ev=run(address,[CTX+0x300 if name=='button' else C,EVENT if name=='event' else 2])
        assert len([e for e in ev if e[0]=='original '+name])==1
        assert not any(e[0]=='0x5357ae1c' for e in ev)
        cases.append(dict(case='other row forwards once',entry=name))
    for route,address in (('list',0x531D7120),('button',0x531D6B50),('event',0x531DACAC)):
        for index in range(5):
            reset();u.mem_write(L+0x110,struct.pack('<H',index))
            r0=CTX+0x300 if route=='button' else C;r1=index if route=='list' else EVENT
            result,ev=run(address,[r0,r1])
            assert len([e for e in ev if e[0] in ('0x531d2f70','0x531d8ffc')])==1
            assert len([e for e in ev if e[0]=='0x53182e9c'])==int(route=='button')
            assert not any(e[0] in ('original event','original list_confirm','original button') for e in ev)
            assert struct.unpack('<3I',u.mem_read(STATE,12))[1]==(0,1,3,2,4)[index]
            if route=='event':assert result==0
            cases.append(dict(case='patched confirmation publishes before nested refresh; single close',route=route,index=index))
    for code in (0xD6,0xD7,0xDA,0xDB):
        for index in range(5):
            reset();u.mem_write(L+0x110,struct.pack('<H',index));u.mem_write(EVENT,struct.pack('<H',code))
            result,ev=run(0x531DACAC,[C,EVENT]);assert result==0
            expected=(index-1)%5 if code==0xD6 else (index+1)%5 if code==0xD7 else max(0,index-1) if code==0xDA else min(4,index+1)
            assert struct.unpack('<H',u.mem_read(L+0x110,2))[0]==expected
            cases.append(dict(case='native event returns zero; five-item navigation',code=hex(code),before=index,after=expected))
    reset();u.mem_write(EVENT,b'\x15\0');result,ev=run(0x531DACAC,[C,EVENT])
    assert result==0 and any(e[0]=='original event' for e in ev)
    cases.append(dict(case='unrelated event delegates'))
    for route,address in (('list',0x531D7120),('button',0x531D6B50),('event',0x531DACAC)):
        for fault in ('readiness lost','invalid index','four constructed'):
            reset(4);u.mem_write(L+0x110,struct.pack('<H',4))
            if fault=='readiness lost':u.mem_write(CTX+8,bytes(4))
            elif fault=='invalid index':u.mem_write(L+0x110,struct.pack('<H',5))
            else:u.mem_write(L+0xF8,struct.pack('<I',VECTOR+16))
            _,ev=run(address,[CTX+0x300 if route=='button' else C,5 if fault=='invalid index' and route=='list' else 4 if route=='list' else EVENT])
            assert not ev
            cases.append(dict(case='failed aspect confirmation never forwards index four to ROM',route=route,fault=fault))
    for last in range(4):
        reset(4);u.mem_write(STATE+8,struct.pack('<I',last));u.mem_write(CTX+8,bytes(4))
        result,ev=run(BASE+offsets['gr4_xpan_settings_hooks_withdraw'],[])
        assert result==1 and u.mem_read(L+0x108,1)==b'\x04'
        assert struct.unpack('<3I',u.mem_read(STATE,12))[1]==last
        assert not any(e[0]=='0x5357ae1c' for e in ev)
        cases.append(dict(case='withdraw restores all four prior aspect choices',last=last))
    reset(4);result,ev=run(BASE+offsets['gr4_xpan_settings_hooks_withdraw'],[])
    assert result==0 and not ev
    cases.append(dict(case='withdraw requires readiness disabled'))
    for crop,(sw,sh) in enumerate(((6192,4128),(4944,3296),(3504,2336))):
        for route,address in (('list',0x531D7120),('button',0x531D6B50),('event',0x531DACAC)):
            reset();u.mem_write(STATE,struct.pack('<3I',crop,1,1))
            u.mem_write(CTX+0x600,struct.pack('<10I',crop,sw,sh,6304,4224,
                28+(6192-sw)//2,24+(4128-sh)//2,1,4,2))
            u.mem_write(CTX+0x400,struct.pack('<3I',STATE,CTX+0x500,CTX+0x600))
            run(BASE+offsets['gr4_xpan_settings_bind_selection'],[CTX+0x400]);plan_bound[0]=True
            u.mem_write(L+0x110,struct.pack('<H',4))
            run(address,[CTX+0x300 if route=='button' else C,4 if route=='list' else EVENT])
            p=struct.unpack('<12I',u.mem_read(CTX+0x500,48))
            assert p[0]==1 and p[10:12]==(sw,(2288,1824,1292)[crop])
            cases.append(dict(case='patched confirmation publishes shared XPAN plan',crop=crop,route=route,WH=list(p[10:12])))
            u.mem_write(CTX+8,bytes(4))
            result,ev=run(BASE+offsets['gr4_xpan_settings_hooks_withdraw'],[])
            assert result==1 and bytes(u.mem_read(CTX+0x500,48))==bytes(48)
            assert struct.unpack('<3I',u.mem_read(STATE,12))==(crop,1,1)
            cases.append(dict(case='withdraw clears shared plan before native observers',crop=crop,route=route))
    # Restore entry bytes, unbind, then the original prologue must execute again.
    for name,address,original in SITES:u.mem_write(address,bytes.fromhex(original))
    run(BASE+offsets['gr4_xpan_settings_hooks_bind'],[0])
    for name,address,original in SITES:
        assert bytes(u.mem_read(address,8)).hex()==original
    cases.append(dict(case='all ten entry words restored before unbinding',words=10))
    return dict(cases_passed=len(cases),cases=cases,patched_native_entries_and_project_ARM_executed=True,
        original_prologue_register_flags_saved_stack_identical=True,
        original_UI_bodies_and_services_modeled=True,camera_accessed=False,xpan_installed=False)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    raw,data,offsets,patch=build(a.out)
    result=check(raw,data,offsets)
    (a.out/'checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Patched native UI entry ARM checks passed:',result['cases_passed'])
