#!/usr/bin/env python3
"""ARM-check XPAN preparation through original 16:9 selection/message code.

Synthetic objects, allocator, mutex and queue. Does not install or verify pixels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from audit_gr4_preview_selection import audit
from audit_xpan_paths import file_offset
from check_gr4_preview_coordinates import build, BASE
from check_gr4_native_memory_abi import check_host_cache_access


def check(raw, chunks, entry, native):
    check_host_cache_access()
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
        UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for page in (0x5362E000, 0x53634000, 0x5372B000, 0x53757000, 0x53754000,
                 0x53887000, 0x53886000, 0x538DF000, 0x538DD000, 0x538E0000,
                 0x54354000, 0x55397000, 0x53FE1000, 0x5374D000,
                 0x53761000, 0x5375C000, 0x5377A000, 0x53156000):
        u.mem_map(page, 4096)
        u.mem_write(page, raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(BASE, 0x4000)
    for address, data in chunks: u.mem_write(address, data)
    u.mem_map(0x62000000, 0x20000)
    u.mem_map(0x62020000, 0x10000)
    obj, owner, service, process = 0x62001000, 0x62004000, 0x62004100, 0x62005000
    plan, domains, original, output, payload = [0x62010000+i*0x100 for i in range(5)]
    stack, stop = 0x6201E000, 0x6201F000
    manager, current, pending, dirty = 0x62021000, 0x62022000, 0x62024000, 0x62026000
    regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
    pack = lambda v: struct.pack('<%dI' % len(v), *v)
    def write(address, values): u.mem_write(address, pack(values))
    def words(address, n): return list(struct.unpack('<%dI' % n, u.mem_read(address, n*4)))
    write(owner+4, [service]); write(0x55397558, [1]); write(0x543549BC, [0xAC123456])
    events = []
    state = {'model_mode': 0, 'locked': False}
    def hook(m, address, size, unused):
        values = [m.reg_read(r) for r in regs]
        result = None
        if address == 0x5372B620: result = owner
        elif address == 0x537575A8:
            assert values[0] == service
            result = state['model_mode']
        elif address == 0x538DFE24:
            assert values[0] == obj+0x24E8 and not state['locked']
            state['locked'] = True; events.append({'event': 'lock'}); result = 0
        elif address == 0x538DFF78:
            assert values[0] == obj+0x24E8 and state['locked']
            state['locked'] = False; events.append({'event': 'unlock'}); result = 0
        elif address == 0x538E09B0:
            assert values[0] == 16 and state['locked']
            u.mem_write(payload, b'\xAA'*24)
            events.append({'event': 'allocate', 'bytes': 16}); result = payload
        elif address == 0x538DD430:
            assert values == [service, 0, 0x84, payload] and state['locked']
            extra = words(m.reg_read(UC_ARM_REG_SP), 4)
            assert extra[0:2] == [1, 0] and extra[3] == 2
            assert words(extra[2], 2) == [0, 0]
            assert u.mem_read(payload+16, 8) == b'\xAA'*8
            events.append({'event': 'message', 'command': '0x84',
                           'window': words(payload, 4), 'flags': [1, 0, 2]})
            result = 0
        elif address == 0x53156140:
            destination,source=state['copy_pair']
            assert values[:3] == [destination, source, 0x1090]
            assert words(manager,2) == [source,destination]
            u.mem_write(destination, bytes(u.mem_read(source,0x1090)))
            events.append({'event':'property-copy','bytes':0x1090}); result=current
        elif address == 0x538E09EC:
            assert values[0] == payload
            events.append({'event':'payload-free'}); result=0
        if result is not None:
            m.reg_write(UC_ARM_REG_R0, result)
            m.reg_write(UC_ARM_REG_PC, m.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook)
    def run(address, args, extra=()):
        events.clear()
        for reg, value in zip(regs, args): u.reg_write(reg, value)
        u.reg_write(UC_ARM_REG_SP, stack); u.reg_write(UC_ARM_REG_LR, stop)
        if extra: write(stack, extra)
        try: u.emu_start(address, stop, count=200000, timeout=2000000)
        except Exception as error:
            raise RuntimeError('ARM entry=%08x PC=%08x events=%r' % (
                address, u.reg_read(UC_ARM_REG_PC), events)) from error
        assert u.reg_read(UC_ARM_REG_PC) == stop and u.reg_read(UC_ARM_REG_SP) == stack
        assert not state['locked']
        return u.reg_read(UC_ARM_REG_R0)
    full = [0x2D0000, 0x1E0000, 0, 0]
    special = [111, 222, 333, 444]
    def reset_info(window):
        u.mem_write(obj, bytes(0x2600))
        write(obj+4, full); write(obj+0x24, window)
        write(obj+0x54, special); write(obj+0x253C, [service])
    def select_publish(selector, expected):
        run(0x53887D48, [obj, selector, 0, 0])
        assert words(obj+0x64, 4) == expected
        assert [e['event'] for e in events] == ['lock', 'unlock']
        run(0x53887DD4, [obj, 0, 0, 0])
        assert [e['event'] for e in events] == ['lock', 'allocate', 'message', 'unlock']
        assert events[2]['window'] == expected and words(0x55397548, 4) == expected
        assert words(obj+4, 4) == full and words(obj+0x54, 4) == special
    def receive_property(expected, initialize=True):
        # Execute the observed message-84 receiver and original property
        # mutation/dirty-record/swap code. Memcpy/free services are modeled.
        if initialize:
            write(service+0x518,[manager]); write(manager,[current,pending,dirty])
            u.mem_write(current, b'\xA5'*0x1090); u.mem_write(pending,b'\xA5'*0x1090)
            write(current+0x6C0,full); write(pending+0x6C0,full)
            u.mem_write(dirty,bytes(0x500))
        active,stage=words(manager,2)
        previous=words(active+0x6C0,4); count=bytes(u.mem_read(dirty,1))[0]
        state['copy_pair']=[active,stage]; write(payload,expected)
        assert run(0x5374D894,[service,payload,1,0]) == 1
        assert words(manager,2) == [stage,active]
        assert words(stage+0x6C0,4) == expected and words(stage+0xF08,4) == expected
        assert u.mem_read(active,0x1090) == u.mem_read(stage,0x1090)
        assert [e['event'] for e in events] == ['property-copy','payload-free']
        changed = expected != previous
        assert bytes(u.mem_read(dirty,1)) == bytes([count+int(changed)])
        if changed:
            assert u.mem_read(dirty+2+count*2,2) == struct.pack('<H',0x84)
            assert words(dirty+0x194+count*4,1) == [0x28501F01]
    fixtures = [c for c in native['cases'] if c.get('basis') == 'observed-USB']
    assert len(fixtures) == 18
    cases = []
    for fixture in fixtures:
        aspect, factor = fixture['native_aspect'], fixture['factor']
        selector = run(0x5362E3F0, [0, aspect, factor, 0])
        expected_selector = int(aspect != 0 or factor > 8192)
        assert selector == expected_selector
        reset_info(fixture['window'])
        expected = fixture['window'][:4] if selector else full
        select_publish(selector, expected)
        receive_property(expected)
        cases.append({'case': 'native-'+fixture['case'], 'selector': selector,
                      'published_window': expected})
    state['model_mode'] = 1
    assert run(0x5362E3F0, [0, 1, 8192, 0]) == 2
    reset_info(fixtures[0]['window']); select_publish(2, special)
    receive_property(special)
    cases.append({'case': 'native-special-selector-2', 'preserved': True})
    state['model_mode'] = 0
    # Also execute the original process branch: mode/zoom must remain native.
    for aspect, factor, flags, override, mode, expected in [
            (0,8192,2,0,0,0), (1,8192,2,0,0,1), (0,10260,2,0,0,1),
            (0,8192,1,0,0,2), (0,8192,0,1,0,2), (0,8192,2,0,2,2)]:
        u.mem_write(process, bytes(0x9800)); write(process+0x3A0, [obj])
        write(process+0x6C, [flags]); write(process+0x94, [factor])
        u.mem_write(process+0x8D, bytes([aspect])); u.mem_write(process+0x91, bytes([mode]))
        u.mem_write(process+0x97A4, bytes([override]))
        reset_info(fixtures[1]['window'])
        run(0x536342BC, [process,0,0,0])
        assert words(obj+0x64,4) == [full,fixtures[1]['window'][:4],special][expected]
        cases.append({'case': 'native-process-%d' % len(cases), 'selector': expected})
    # Pure C preparation followed by modeled object insertion and ORIGINAL
    # selection/publication. The insertion is not a native hook or mutex adapter.
    dimensions = [(6192,4128,2288), (4944,3296,1824), (3504,2336,1292)]
    source_fixtures = [c for c in fixtures if c['native_aspect'] == 0]
    bound = [full[0],full[1]]*2
    for fixture, (sw, sh, ph) in zip(source_fixtures, dimensions):
        p = [1,sw,sh,6300,4300,54,58,int(fixture['crop_factor_bits'],16),0,(sh-ph)//2,sw,ph]
        expected = []
        for start in (0,4):
            w,h,x,y = fixture['window'][start:start+4]
            top = h*p[9]//sh; bottom = h*(p[9]+ph)//sh
            expected.extend([w,bottom-top,x,y+top])
        for selector in (0,1):
            write(plan,p); write(domains,bound); write(original,fixture['window'])
            u.mem_write(output,b'\xCC'*60)
            assert run(entry,[plan,0,fixture['factor'],domains],[original,selector,output]) == 1
            assert events == [] and words(output,13) == expected+[1]+expected[:4]
            assert u.mem_read(output+52,8) == b'\xCC'*8
            assert words(plan,12) == p and words(original,8) == fixture['window']
            reset_info(fixture['window']); write(obj+0x24,words(output,8))
            select_publish(words(output+32,1)[0],expected[:4])
            receive_property(expected[:4])
            cases.append({'case': 'xpan-source-%d-native-selector-%d' % (sw,selector),
                          'prepared_window': expected,'published_window':expected[:4]})
        # Restore through original selection and the SAME property copies,
        # including dirty notification recording; no model state reset here.
        restored_selector=run(0x5362E3F0,[0,0,fixture['factor'],0])
        restored=fixture['window'][:4] if restored_selector else full
        reset_info(fixture['window']); select_publish(restored_selector,restored)
        receive_property(restored,initialize=False)
        assert bytes(u.mem_read(dirty,1)) == b'\x02'
        cases.append({'case':'xpan-source-%d-native-window-restore'%sw,
                      'restored_window':restored,'notification_recorded':True,
                      'notification_delivery_and_hardware_restore_verified':False})
    # Merely changing crop coordinates is insufficient for OFF/aspect=0.
    reset_info(expected); select_publish(0,full)
    receive_property(full)
    cases.append({'case':'selector-0-still-publishes-full-window','passed':True})
    p = [1,6192,4128,6300,4300,54,58,0x3F800000,0,920,6192,2288]
    faults = ['disabled','bad-plan','regular-aspect-1','regular-aspect-2','regular-aspect-3',
              'wrong-factor','special-selector','unknown-selector','empty-window','outside-domain',
              'null-plan','null-domains','null-original','null-output']
    for fault in faults:
        altered=p[:]; window=source_fixtures[0]['window'][:]; aspect=0; factor=8192; selector=0
        if fault=='disabled': altered[0]=0
        if fault=='bad-plan': altered[9]+=1
        if fault.startswith('regular-aspect-'): aspect=int(fault[-1])
        if fault=='wrong-factor': factor=10260
        if fault=='special-selector': selector=2
        if fault=='unknown-selector': selector=3
        if fault=='empty-window': window[1]=0
        if fault=='outside-domain': window[4]+=1
        write(plan,altered); write(domains,bound); write(original,window)
        u.mem_write(output,b'\xCC'*60)
        args=[0 if fault=='null-plan' else plan,aspect,factor,0 if fault=='null-domains' else domains]
        extra=[0 if fault=='null-original' else original,selector,0 if fault=='null-output' else output]
        assert run(entry,args,extra)==0 and events==[]
        assert u.mem_read(output,60)==b'\xCC'*60 and words(original,8)==window
        cases.append({'case':fault,'delegate_native_without_output_writes':True})
    return cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample',type=Path,default=Path('samples/gr4_decoded.bin'))
    parser.add_argument('--native-report',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); args.out.mkdir(parents=True,exist_ok=False)
    try:
        raw=args.sample.read_bytes(); report=audit(raw)
        native=json.loads(args.native_report.read_text())
        assert native['passed'] and native['firmware_sha256']==report['firmware_sha256']
        chunks,entry=build(args.out,('xpan_preview_route.c',),'gr4_xpan_preview_route_prepare')
        cases=check(raw,chunks,entry,native)
        report.update({'passed':True,'cases':cases,'original_ARM_executed':True,
                       'native_fixture_sha256':hashlib.sha256(args.native_report.read_bytes()).hexdigest(),
                       'synthetic_objects_allocator_mutex_queue':True,'actual_pixels_verified':False,
                       'unresolved_ARM_symbols':0})
        (args.out/'checks.json').write_text(json.dumps(report,indent=2)+'\n')
        print('%d ARM route checks passed; synthetic services, not installed' % len(cases))
    except Exception as error:
        (args.out/'failure.json').write_text(json.dumps({'passed':False,'error':repr(error),
                                                       'camera_access':False},indent=2)+'\n')
        raise


if __name__=='__main__':
    main()
