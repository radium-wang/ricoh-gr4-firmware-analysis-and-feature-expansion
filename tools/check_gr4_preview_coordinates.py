#!/usr/bin/env python3
"""ARM-check shared-plan coordinate calculations against original ARM fixtures.

No camera access, installation, publication, AF or LCD pixel verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile
from audit_xpan_paths import EXPECTED_SHA256
from check_gr4_native_memory_abi import check_host_cache_access

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x61000000


def build(out, extra_sources=(), entry_name='gr4_xpan_preview_coordinates', extra_exports=()):
    sources = ['xpan_preview_coordinates.c', 'xpan_capture.c', 'xpan_core.c', *extra_sources]
    flags = ['--target=armv7-none-eabi', '-march=armv7-a', '-marm', '-mfpu=vfpv3',
             '-mfloat-abi=hard', '-std=c11', '-Oz', '-Wall', '-Wextra', '-Werror',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fPIC',
             '-ffunction-sections', '-fdata-sections']
    objects = []
    for name in sources:
        target = out/(name+'.o'); objects.append(str(target))
        subprocess.run([shutil.which('clang'), *flags, '-c', str(ROOT/'firmware'/name),
                        '-o', str(target)], check=True)
    layout = out/'layout.ld'
    layout.write_text('SECTIONS { . = 0x61000000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } .bss : { *(.bss*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n')
    name = entry_name; elf = out/'coordinates.elf'
    subprocess.run([shutil.which('ld.lld'), '-static', '--no-undefined', '--gc-sections',
                    '--entry='+name, *['--undefined='+n for n in extra_exports],
                    '-T', str(layout), *objects, '-o', str(elf)], check=True)
    chunks = []
    with elf.open('rb') as handle:
        image = ELFFile(handle)
        for section in image.iter_sections():
            assert not (section['sh_type'] in ('SHT_REL', 'SHT_RELA') and section['sh_size'])
            if section['sh_flags'] & 2 and section['sh_size']:
                assert BASE <= section['sh_addr'] and section['sh_addr']+section['sh_size'] <= BASE+0x4000
                chunks.append((section['sh_addr'], bytes(section['sh_size']) if
                               section['sh_type'] == 'SHT_NOBITS' else section.data()))
        entry = image.get_section_by_name('.symtab').get_symbol_by_name(name)[0]['st_value']
    return chunks, entry


def check(chunks, entry, native):
    check_host_cache_access()
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                                  UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    u.mem_map(BASE, 0x4000)
    for address, data in chunks: u.mem_write(address, data)
    u.mem_map(0x60000000, 0x10000)
    plan, domains, original, output = 0x60000100, 0x60000200, 0x60000300, 0x60000400
    stack, stop = 0x6000E000, 0x6000F000
    regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
    pack = lambda values: struct.pack('<%dI' % len(values), *values)
    fixtures = [c for c in native['cases'] if c.get('basis') == 'observed-USB' and c['native_aspect'] == 0]
    assert len(fixtures) == 3
    full = [0x2D0000, 0x1E0000]*2
    dimensions = [(6192, 4128, 2288, 0x3F800000),
                  (4944, 3296, 1824, 0x3FA04F89), (3504, 2336, 1292, 0x3FE23119)]
    cases = []
    def expected(windows, p):
        answer = []
        for start in (0, 4):
            w, h, x, y = windows[start:start+4]
            top = h*p[9]//p[2]; bottom = h*(p[9]+p[11])//p[2]
            answer.extend([w, bottom-top, x, y+top])
        return answer
    def run(p, bound, windows, factor, aspect=0, alias=False, null=None):
        u.mem_write(plan, pack(p)); u.mem_write(domains, pack(bound))
        u.mem_write(original, pack(windows)+b'\xA5'*16); u.mem_write(output, b'\xCC'*48)
        args = [plan, aspect, factor, domains]
        if null == 'plan': args[0] = 0
        if null == 'domains': args[3] = 0
        out = original if alias else output
        extra = [0 if null == 'original' else original, 0 if null == 'output' else out]
        for reg, value in zip(regs, args): u.reg_write(reg, value)
        u.reg_write(UC_ARM_REG_SP, stack); u.reg_write(UC_ARM_REG_LR, stop)
        u.mem_write(stack, pack(extra))
        u.emu_start(entry, stop, count=200000, timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC) == stop and u.reg_read(UC_ARM_REG_SP) == stack
        assert u.mem_read(original+32, 16) == b'\xA5'*16 and u.mem_read(output+32, 16) == b'\xCC'*16
        return u.reg_read(UC_ARM_REG_R0), bytes(u.mem_read(out, 32))
    for fixture, (sw, sh, ph, bits) in zip(fixtures, dimensions):
        p = [1, sw, sh, 6300, 4300, 54, 58, bits, 0, (sh-ph)//2, sw, ph]
        windows = fixture['window']; factor = fixture['factor']
        for alias in (False, True):
            result, actual = run(p, full, windows, factor, alias=alias)
            assert result == 1 and actual == pack(expected(windows, p))
            if not alias: assert u.mem_read(original, 32) == pack(windows)
            cases.append({'case': 'aligned-plan-%d-alias-%s' % (sw, alias),
                          'window': list(struct.unpack('<8I', actual)),
                          'original_ARM_fixture': fixture['case']})
    p = [1, 6192, 4128, 6300, 4300, 54, 58, 0x3F800000, 0, 920, 6192, 2288]
    baseline = fixtures[0]['window']
    # Products exceed 32 bits; exact edge rounding and origins must survive.
    large = [0x7FFFFFFE, 0x7FFFFFFE, 1, 1]*2
    result, actual = run(p, [0x7FFFFFFF]*4, large, 8192)
    assert result == 1 and actual == pack(expected(large, p))
    cases.append({'case': 'wide-products-and-nonzero-origins', 'passed': True})
    faults = ('disabled', 'bad-plan', 'wrong-aspect', 'wrong-factor', 'logical-outside',
              'mapped-outside', 'empty-window', 'collapsed-window', 'zero-domain', 'oversized-domain',
              'null-plan', 'null-domains', 'null-original', 'null-output')
    for fault in faults:
        altered = p[:]; windows = baseline[:]; bound = full[:]; aspect = 0; factor = 8192
        if fault == 'disabled': altered[0] = 0
        if fault == 'bad-plan': altered[9] += 1
        if fault == 'wrong-aspect': aspect = 1
        if fault == 'wrong-factor': factor = 10260
        if fault == 'logical-outside': windows[0] += 1
        if fault == 'mapped-outside': windows[4] += 1
        if fault == 'empty-window': windows[5] = 0
        if fault == 'collapsed-window': windows[5] = 1
        if fault == 'zero-domain': bound[0] = 0
        if fault == 'oversized-domain': bound[2] = 0x80000000
        for alias in (False, True):
            result, actual = run(altered, bound, windows, factor, aspect, alias=alias,
                                 null=fault[5:] if fault.startswith('null-') else None)
            assert result == 0 and actual == (pack(windows) if alias else b'\xCC'*32)
            assert u.mem_read(original, 32) == pack(windows)
            cases.append({'case': fault+'-alias-'+str(alias), 'no_output_writes': True})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-report', type=Path, required=True)
    parser.add_argument('--state-report', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        native = json.loads(args.native_report.read_text())
        assert native['passed'] and native['firmware_sha256'] == EXPECTED_SHA256
        assert native['state_report_sha256'] == hashlib.sha256(args.state_report.read_bytes()).hexdigest()
        chunks, entry = build(args.out); cases = check(chunks, entry, native)
        report = {'schema': 'gr4-preview-plan-coordinates-arm-v1', 'passed': True, 'cases': cases,
                  'original_ARM_fixture_sha256': hashlib.sha256(args.native_report.read_bytes()).hexdigest(),
                  'state_report_sha256': native['state_report_sha256'], 'camera_access': False,
                  'native_window_publication_verified': False, 'LCD_AF_pixels_verified': False,
                  'xpan_installed': False, 'PREVIEW_READY': False, 'unresolved_ARM_symbols': 0}
        (args.out/'checks.json').write_text(json.dumps(report, indent=2)+'\n')
        print('%d ARM coordinate-plan checks passed; not installed' % len(cases))
    except Exception as error:
        (args.out/'failure.json').write_text(json.dumps({'passed': False, 'error': repr(error),
                                                      'camera_access': False}, indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
