#!/usr/bin/env python3
"""Execute scoped JPEG adapter, original calculator and BackResize descriptors.

Synthetic objects/buffers. Factory selection simulated;
no pixel engine, encoder, worker synchronization, USB access or installer.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from elftools.elf.elffile import ELFFile
from audit_gr4_jpeg_native import audit
from audit_xpan_paths import file_offset
from check_gr4_native_memory_abi import check_host_cache_access

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x61000000


def build(out):
    out.mkdir(parents=True)
    flags = ['--target=armv7-none-eabi', '-march=armv7-a', '-marm', '-mfpu=vfpv3',
             '-mfloat-abi=hard', '-std=c11', '-Oz', '-Wall', '-Wextra', '-Werror',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fPIC',
             '-fvisibility=hidden', '-ffunction-sections', '-fdata-sections']
    objects = []
    for source in ('xpan_jpeg_native.c', 'xpan_capture.c', 'xpan_core.c'):
        obj = out/(source+'.o'); objects.append(str(obj))
        subprocess.run([shutil.which('clang'), *flags, '-c', str(ROOT/'firmware'/source), '-o', str(obj)], check=True)
    helper = out/'copy.c'
    helper.write_text('void __aeabi_memcpy(void *d,const void *s,unsigned int n) { unsigned char *a=d; const unsigned char *b=s; while(n--) *a++=*b++; }\n')
    helper_obj = out/'copy.o'; objects.append(str(helper_obj))
    subprocess.run([shutil.which('clang'), *flags, '-c', str(helper), '-o', str(helper_obj)], check=True)
    layout = out/'layout.ld'
    layout.write_text('SECTIONS { . = 0x61000000; .text : { *(.text*) } .rodata : { *(.rodata*) } .data : { *(.data*) *(.got*) } .bss : { *(.bss*) } /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } }\n')
    names = ['gr4_xpan_jpeg_native_bind', 'gr4_xpan_jpeg_native_virtual', 'gr4_xpan_capture_begin']
    elf = out/'jpeg.elf'
    subprocess.run([shutil.which('ld.lld'), '-static', '--no-undefined', '--gc-sections',
        '--entry='+names[0], *['--undefined='+n for n in names], '-T', str(layout), *objects, '-o', str(elf)], check=True)
    chunks = []
    with elf.open('rb') as f:
        e = ELFFile(f)
        for s in e.iter_sections():
            if s['sh_type'] in ('SHT_REL', 'SHT_RELA') and s['sh_size']: raise ValueError('relocation remains')
            if s['sh_flags']&2 and s['sh_size']:
                assert BASE <= s['sh_addr'] < BASE+8192
                chunks.append((s['sh_addr'], bytes(s['sh_size']) if s['sh_type']=='SHT_NOBITS' else s.data()))
        syms = e.get_section_by_name('.symtab')
        entries = {n: syms.get_symbol_by_name(n)[0]['st_value'] for n in names}
    return chunks, entries


def check(raw, chunks, entries):
    check_host_cache_access()
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R8, UC_ARM_REG_R11,
        UC_ARM_REG_S0, UC_ARM_REG_S16, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
        UC_ARM_REG_FPEXC, UC_ARM_REG_C1_C0_2)
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for page in (0x538CF000, 0x538D0000, 0x538D3000, 0x538ED000, 0x54354000, 0x53A78000,
                 0x536FB000, 0x53711000):
        u.mem_map(page, 4096); u.mem_write(page, raw[file_offset(page):file_offset(page)+4096])
    u.mem_map(BASE, 8192)
    for a, data in chunks: u.mem_write(a, data)
    u.mem_map(0x60000000, 0x20000)
    u.reg_write(UC_ARM_REG_C1_C0_2, 0xF00000); u.reg_write(UC_ARM_REG_FPEXC, 1<<30)
    regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
    calc, vt, binding, plan = 0x60000100, 0x60000200, 0x60000300, 0x60000400
    width, height, state = 0x60000600, 0x60000604, 0x60000700
    stack, stop = 0x6001E000, 0x6001F000
    process, config, owner = 0x60001000, 0x6000C000, 0x60008000
    source, destination = 0x60000800, 0x60000900
    calls = []
    stop_at = [stop]
    def hook(m, address, size, unused):
        if address == stop_at[0]:
            m.emu_stop(); return
        if address == 0x538ED930 or address == 0x53A786C0: raise AssertionError('native assertion')
        if address == 0x538CFBF8:
            sp = m.reg_read(UC_ARM_REG_SP)
            calls.append({'size': m.reg_read(UC_ARM_REG_R1), 'aspect': m.reg_read(UC_ARM_REG_R2),
                          'crop': m.reg_read(UC_ARM_REG_S0), 'width': m.reg_read(UC_ARM_REG_R3),
                          'height': struct.unpack('<I', m.mem_read(sp, 4))[0]})
            return # Execute original calculator, including crop and size tables.
        if address in (0x538D05F0, 0x538D0764, 0x60000A00):
            m.reg_write(UC_ARM_REG_R0, 0 if address == 0x60000A00 else calc)
        else: return
        m.reg_write(UC_ARM_REG_PC, m.reg_read(UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE, hook)
    def invalid(m, access, address, size, value, unused):
        raise RuntimeError('unmapped emulator access %s size %d PC %s r0..3 %s' %
            (hex(address), size, hex(m.reg_read(UC_ARM_REG_PC)),
             [hex(m.reg_read(r)) for r in regs]))
    u.hook_add(UC_HOOK_MEM_INVALID, invalid)
    def word(a, n): u.mem_write(a, struct.pack('<I', n))
    def half(a, n): u.mem_write(a, struct.pack('<H', n))
    def gethalf(a): return struct.unpack('<H', u.mem_read(a, 2))[0]
    def run(entry, args, extra=(), crop=0x3F800000, end=stop):
        stop_at[0] = end
        for r, n in zip(regs, args): u.reg_write(r, n)
        u.reg_write(UC_ARM_REG_S0, crop); u.reg_write(UC_ARM_REG_SP, stack); u.reg_write(UC_ARM_REG_LR, end)
        if extra: u.mem_write(stack, struct.pack('<%dI'%len(extra), *extra))
        try:
            u.emu_start(entry, end, count=100000, timeout=2000000)
        except Exception as error:
            raise RuntimeError('ARM emulation failed at PC %s, arguments %s, crop %s, LR scope %s' %
                               (hex(u.reg_read(UC_ARM_REG_PC)), args, hex(crop), hex(end))) from error
        assert u.reg_read(UC_ARM_REG_PC)==end and u.reg_read(UC_ARM_REG_SP)==stack
    def dims(crop, size=0, aspect=0):
        run(0x538CFBF8, [calc, size, aspect, width], [height], crop)
        return gethalf(width), gethalf(height)
    def bind(crop, source_size=0, dest_size=0):
        sw, sh = dims(crop, source_size)
        crop_choice = (0x3F800000, 0x3FA04F89, 0x3FE23119).index(crop)
        u.mem_write(state, struct.pack('<3I', crop_choice, 4, 0))
        # Alignment 1/4/2 is a model, not a verified camera pipeline constraint.
        run(entries['gr4_xpan_capture_begin'], [state, sw, sh, sw],
            [sh, 0, 0, 1, 4, 2, plan])
        assert u.reg_read(UC_ARM_REG_R0)==1
        u.mem_write(binding, struct.pack('<9I', calc, plan, vt, 1, source_size, dest_size, 1, 4, 2))
        run(entries['gr4_xpan_jpeg_native_bind'], [binding, 0, 0, 0])
        word(calc, vt); word(vt+8, entries['gr4_xpan_jpeg_native_virtual']); word(vt+0x30, 0x60000A00)
        values = struct.unpack('<12I', u.mem_read(plan, 48))
        return sw, sh, values[9], values[11]
    cases = []
    for crop in (0x3F800000, 0x3FA04F89, 0x3FE23119):
        sw, sh, top, ph = bind(crop)
        # Both exact caller scopes, every other caller and the two full-source
        # identities. Check s0/stack arguments and two-byte output canaries.
        for lr in (0x53711460, 0x536FB22C, 0x537114A4, 0x5387E1C4, stop):
            u.mem_write(width, b'\xAA\xAA\x77\x88'); u.mem_write(height, b'\xBB\xBB\x99\x66'); calls.clear()
            run(entries['gr4_xpan_jpeg_native_virtual'], [calc, 0, 0, width], [height], crop, lr)
            actual = gethalf(width), gethalf(height)
            assert actual == ((sw, ph) if lr in (0x53711460, 0x536FB22C) else (sw, sh))
            assert calls == [{'size': 0, 'aspect': 0, 'crop': crop, 'width': width, 'height': height}]
            assert u.mem_read(width+2, 2)==b'\x77\x88' and u.mem_read(height+2, 2)==b'\x99\x66'
            cases.append({'case': 'caller scope', 'crop_bits': hex(crop), 'caller': hex(lr), 'pixels': list(actual)})
        # Real publisher fragment calls the adapter, stores B70/B72, makes a
        # SEPARATE aspect=0/size=0/crop=1 full-source call, then stores B74/B76.
        word(owner+0x688, config); word(0x543549BC, 0xABCD1234)
        u.mem_write(config+0x7DA, b'\0'); word(config+0x7DC, crop)
        fp = stack-0x100
        word(fp-0x38, 0xABCD1234)
        for register, value in ((UC_ARM_REG_R5, owner), (UC_ARM_REG_R6, 0x543549BC), (UC_ARM_REG_R11, fp)):
            u.reg_write(register, value)
        u.reg_write(UC_ARM_REG_SP, stack); calls.clear()
        stop_at[0] = 0x537114CC
        u.emu_start(0x5371140C, 0x537114CC, count=100000, timeout=2000000)
        assert u.reg_read(UC_ARM_REG_PC)==0x537114CC
        assert (gethalf(config+0xB70), gethalf(config+0xB72))==(sw, ph)
        assert (gethalf(config+0xB74), gethalf(config+0xB76))==dims(0x3F800000)
        # Original descriptor copier and centre operation, starting from the
        # FULL 3:2 descriptor for all crop modes. 35/50 mm must also preserve
        # native horizontal cropping, not only a pre-cropped model buffer.
        word(process+0x8A48, config)
        u.mem_write(source, bytes(32)); u.mem_write(source, b'\x01')
        word(source+4, 0x62000000); word(source+8, 0x64000000)
        full_w, full_h = dims(0x3F800000)
        u.mem_write(source+0x10, struct.pack('<3H', full_w, full_h, full_w))
        run(0x536FB040, [process, source, 0, 0])
        assert u.reg_read(UC_ARM_REG_R0)==process+0x8A4C
        assert (gethalf(process+0x8A5C), gethalf(process+0x8A5E))==(sw, ph)
        plane_offset = ((full_h-ph)//2)*full_w+(full_w-sw)//2
        assert struct.unpack('<2I', u.mem_read(process+0x8A50, 8))==(0x62000000+plane_offset, 0x64000000+plane_offset)
        assert u.mem_read(process+0x8A60,2)==struct.pack('<H',full_w)
        # Original destination routine calls via the cloned calculator table.
        u.mem_write(destination, b'\xCC'*32); u.mem_write(config+0x7E0, b'\0')
        run(0x536FB0DC, [process, destination, 0, 0], [0, 0], crop)
        assert (gethalf(destination+0x10), gethalf(destination+0x12))==(sw, ph)
        assert u.mem_read(destination+4, 8)==u.mem_read(process+0x8A50, 8)
        cases.append({'case': 'original source publisher and BackResize descriptors', 'crop_bits': hex(crop),
                      'source': [sw, sh], 'descriptor_source': [full_w,full_h],
                      'cropped': [sw, ph], 'plane_offset_bytes': plane_offset,
                      'full_source_fields_preserved': True})
    sw, sh, _, ph = bind(0x3F800000)
    for fault in ('disabled', 'unbound', 'other object', 'other vtable', 'other crop',
                  'other aspect', 'other size', 'invalid plan', 'source dimensions mismatch', 'invalid alignment'):
        bind(0x3F800000); self, size, aspect, crop, lr = calc, 0, 0, 0x3F800000, 0x53711460
        if fault=='disabled': word(binding+12, 0)
        if fault=='unbound': run(entries['gr4_xpan_jpeg_native_bind'], [0, 0, 0, 0])
        if fault=='other object': self=calc+16; word(self, vt)
        if fault=='other vtable': word(calc, 0x53FD89A0)
        if fault=='other crop': crop=0x3FA04F89
        if fault=='other aspect': aspect=1
        if fault=='other size': size=1
        if fault=='invalid plan': word(plan, 0)
        if fault=='source dimensions mismatch': word(plan+4, sw-1); word(plan+40, sw-1)
        if fault=='invalid alignment': lr=0x536FB22C; word(binding+28, 3)
        expected = dims(crop, size, aspect)
        run(entries['gr4_xpan_jpeg_native_virtual'], [self, size, aspect, width], [height], crop, lr)
        assert (gethalf(width), gethalf(height))==expected
        cases.append({'case': fault, 'original_dimensions_preserved': True})
    for size in (1, 2, 3):
        sw, sh, _, _ = bind(0x3F800000, dest_size=size)
        ow, oh = dims(0x3F800000, size)
        run(entries['gr4_xpan_jpeg_native_virtual'], [calc, size, 0, width], [height], end=0x536FB22C)
        dw, dh = gethalf(width), gethalf(height)
        assert dw==ow and dh<oh and dh%4==0 and (oh-dh)%4==0
        cases.append({'case': 'destination size', 'size': size, 'original': [ow, oh], 'XPAN': [dw, dh]})
    return {'cases_passed': len(cases), 'cases': cases, 'original_calculator_ARM_executed': True,
            'original_source_publisher_fragment_ARM_executed': True,
            'original_source_center_and_destination_ARM_executed': True,
            'original_descriptor_copier_ARM_executed': True, 'factory_selection_simulated': True,
            'alignment_is_synthetic_not_camera_verified': True,
            'actual_JPEG_pixels_encoder_and_worker_synchronization_verified': False,
            'camera_accessed': False, 'xpan_installed': False}


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise ValueError('immutable output exists')
    raw = (ROOT/'samples/gr4_decoded.bin').read_bytes(); evidence = audit(raw)
    chunks, entries = build(a.output); result = check(raw, chunks, entries)
    result.update(schema='gr4-jpeg-native-check-v1', sample_sha256=hashlib.sha256(raw).hexdigest(), entries=entries,
                  build_is_fixed_emulator_address_not_installable=True)
    (a.output/'checks.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Scoped JPEG ARM checks passed:', result['cases_passed'])
