#!/usr/bin/env python3
"""Execute original coordinate/guide ARM on synthetic objects, not LCD pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from audit_gr4_preview_native import audit
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access


def check(raw, observed=None):
    check_host_cache_access()
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
        UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
        UC_ARM_REG_FPEXC, UC_ARM_REG_C1_C0_2)
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    pages = (0x53153000, 0x53154000, 0x53155000, 0x53156000,
             0x53183000, 0x53216000, 0x5323E000,
             0x5323F000, 0x53576000, 0x53577000, 0x53589000, 0x53886000,
             0x53887000, 0x538ED000, 0x538EE000, 0x538DF000, 0x53FE1000)
    for page in pages:
        u.mem_map(page, 4096)
        u.mem_write(page, raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(0x60000000, 0x20000)
    u.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000)
    u.reg_write(UC_ARM_REG_FPEXC, 1 << 30)
    regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
    obj, controller, widget, prop = 0x60000100, 0x60004000, 0x60004400, 0x60005000
    children = [0x60006000 + 0x400*i for i in range(4)]
    stack, stop = 0x6001E000, 0x6001F000
    events = []
    scenario = {'id': 0x0400003F, 'asserted': False}

    def word(address, value): u.mem_write(address, struct.pack('<I', value))
    def words(address, count): return list(struct.unpack('<%dI' % count, u.mem_read(address, count*4)))
    def hook(m, address, size, unused):
        if address == stop:
            m.emu_stop(); return
        values = [m.reg_read(r) for r in regs]
        if address == 0x538ED930:
            scenario['asserted'] = True
            m.emu_stop(); return
        result = None
        if address == 0x53183E14: result = scenario['id']
        elif address in (0x5323EA84, 0x5323FDA8): result = prop
        elif address == 0x538DFE24:
            assert values[0] == obj+0x24E8
            events.append(('lock', values[0])); result = 0
        elif address == 0x538DFF78:
            assert values[0] == obj+0x24E8
            events.append(('unlock', values[0])); result = 0
        elif address == 0x53589AB4:
            events.append(('visible', values[0], values[1])); result = 0
        elif address in (0x535899FC, 0x53577944):
            events.append(('invalidate-or-layout', values[0])); result = 0
        if result is not None:
            m.reg_write(UC_ARM_REG_R0, result)
            m.reg_write(UC_ARM_REG_PC, m.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook)

    def run(entry, args):
        events.clear(); scenario['asserted'] = False
        for register, value in zip(regs, args): u.reg_write(register, value)
        u.reg_write(UC_ARM_REG_SP, stack); u.reg_write(UC_ARM_REG_LR, stop)
        try:
            u.emu_start(entry, stop, count=100000, timeout=2000000)
        except Exception as error:
            raise RuntimeError('ARM PC=%08x entry=%08x args=%s events=%s' %
                (u.reg_read(UC_ARM_REG_PC), entry, args, events)) from error
        if not scenario['asserted']:
            assert u.reg_read(UC_ARM_REG_PC) == stop and u.reg_read(UC_ARM_REG_SP) == stack

    cases = []
    # Deliberately coherent synthetic coordinate domains, not camera fields or
    # pixel dimensions. +4/+8 also supply the second window's centering base.
    bases = [('synthetic', 0x2D0000, 0x1E0000, 0x2D0000, 0x1E0000, 1)]
    if observed is not None:
        fields = {f['role']: bytes.fromhex(f['hex']) for f in observed['fields']}
        values = struct.unpack('<16I', fields['bases_and_two_virtual_windows'])
        divisor, = struct.unpack('<I', fields['coordinate_divisor'])
        assert (values[0], values[1], values[4], values[5], divisor) == (
            0x2D0000, 0x1E0000, 0x2D0000, 0x1E0000, 4096)
        bases.append(('observed-USB', values[0], values[1], values[4], values[5], divisor))
    for basis, bw, bh, mw, mh, divisor in bases:
      for crop, bits in [('off', 0x3F800000), ('35-model', 0x3FA04F89),
                       ('50-model', 0x3FE23119)]:
        factor = int(struct.unpack('<f', struct.pack('<I', bits))[0]*8192+0.5)
        for aspect in range(6):
            u.mem_write(obj, bytes(0x2600))
            for offset, value in [(4, bw), (8, bh), (0x14, mw), (0x18, mh), (0x1CD4, divisor)]:
                word(obj+offset, value)
            run(0x538876B8, [obj, 0, aspect, factor])
            assert not scenario['asserted']
            assert events == [('lock', obj+0x24E8), ('unlock', obj+0x24E8)]
            window = words(obj+0x24, 8)
            w, h, x, y, pw, ph, px, py = window
            assert 0 < w <= 0x2D0000 and 0 < h <= 0x1E0000
            assert x == (0x2D0001-w)//2 and y == (0x1E0001-h)//2
            # The square branch uses a literal 400 basis for mapped width,
            # unlike the other branches. Do not infer a uniform pixel mapping.
            expected_pw = ((400*w+(bh//divisor)//2)//(bh//divisor) if aspect == 3 else
                           ((mw//divisor)*w+(bw//divisor)//2)//(bw//divisor))
            expected_ph = ((mh//divisor)*h+(bh//divisor)//2)//(bh//divisor)
            assert (pw, ph) == (expected_pw, expected_ph), (basis, crop, aspect, window)
            assert px == (0x2D0000-pw)//2 and py == (0x1E0000-ph)//2
            cases.append({'case': 'virtual-window-%s-%s-aspect-%d' % (basis, crop, aspect),
                          'basis': basis, 'native_aspect': aspect,
                          'factor': factor, 'crop_factor_bits': hex(bits),
                          'window': window, 'original_mutex_calls': True})
    run(0x538876B8, [obj, 1, 0, 8192])
    assert scenario['asserted']
    cases.append({'case': 'nonzero-mode-reaches-native-assert',
                  'assert_intercepted_without_resuming': True})

    for aspect in range(6):
        scenario['id'] = 0x0400003F
        u.mem_write(widget, bytes(0x200))
        word(controller+0x170, widget)
        for offset, child in zip((0xF4, 0xF8, 0xFC, 0x100), children):
            word(widget+offset, child); u.mem_write(child, bytes(0x200))
        u.mem_write(prop+0x18, bytes([aspect]))
        run(0x53216260, [controller, 0, 0, 0])
        if aspect == 4:
            assert scenario['asserted']
            cases.append({'case': 'guide-aspect-4-asserts', 'safe_to_pass_xpan_enum_to_rom': False})
        elif aspect == 5:
            assert events == [('visible', widget, 0)]
            cases.append({'case': 'guide-aspect-5-hidden'})
        else:
            assert not scenario['asserted']
            resource = struct.unpack('<H', u.mem_read(children[3]+0xEA, 2))[0]
            base = struct.unpack('<H', u.mem_read(children[0]+0xEA, 2))[0]
            assert base == 0x1DB and resource == [0xF1, 0x15B, 0xF0, 0x15D][aspect]
            assert ('visible', widget, 1) in events
            cases.append({'case': 'guide-aspect-%d-resource' % aspect,
                          'resource_id': resource, 'base_resource_id': base})
    for mode in (0x04000040, 0x04000041):
        scenario['id'] = mode
        run(0x53216260, [controller, 0, 0, 0])
        assert events == [('visible', widget, 0)] and not scenario['asserted']
        cases.append({'case': 'guide-mode-%08x-hidden' % mode})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, default=Path('samples/gr4_decoded.bin'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--state-report', type=Path,
                        help='Use an immutable read-only USB baseline as an additional model basis')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    raw = args.sample.read_bytes()
    report = audit(raw)
    (args.out / 'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    try:
        observed = None
        if args.state_report:
            state = json.loads(args.state_report.read_text())
            assert state['sample_sha256'] == report['firmware_sha256']
            assert state['callbacks_scratch_properties_unchanged'] and not state['camera_memory_written']
            assert state['preview']['native_aspect_byte_8d'] == 0
            observed = state['preview']['information_snapshot']
            assert observed and observed['vtable'] == '0x53fd1830'
            report['state_report_sha256'] = hashlib.sha256(args.state_report.read_bytes()).hexdigest()
        cases = check(raw, observed)
        report.update({'passed': True, 'cases': cases, 'synthetic_objects': True,
                       'mutex_gui_services_simulated': True, 'original_arm_executed': True,
                       'actual_lcd_or_pixels_verified': False})
        (args.out / 'checks.json').write_text(json.dumps(report, indent=2)+'\n')
        print('%d original ARM preview/guide checks passed; synthetic objects' % len(cases))
    except Exception as error:
        (args.out / 'failure.json').write_text(json.dumps({'passed': False,
            'error': repr(error), 'camera_access': False}, indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
