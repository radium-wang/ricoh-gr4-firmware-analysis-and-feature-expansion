#!/usr/bin/env python3
"""Check XPAN state, geometry and descriptor adapters offline; no camera installation."""
import argparse
import ctypes as c
import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class State(c.Structure):
    _fields_ = [('crop', c.c_uint), ('aspect', c.c_uint), ('last_regular_aspect', c.c_uint)]


class Effective(c.Structure):
    _fields_ = [(s, c.c_uint) for s in ('crop', 'aspect', 'factor', 'xpan')]


class Rect(c.Structure):
    _fields_ = [(s, c.c_uint) for s in ('left', 'top', 'width', 'height')]


class Capture(c.Structure):
    _fields_ = [(s,c.c_uint) for s in ('enabled','source_width','source_height',
                                      'raw_width','raw_height','raw_left','raw_top',
                                      'native_crop_factor_bits')] + [('photo',Rect)]


class Undo(c.Structure):
    _fields_ = [('target',c.POINTER(c.c_ubyte)),('kind',c.c_uint),
                ('original',c.c_ubyte*12),('applied',c.c_ubyte*12)]


NativeMenuCallback = c.CFUNCTYPE(c.c_int, c.c_void_p, c.c_uint)
XpanMenuCallback = c.CFUNCTYPE(c.c_int, c.c_void_p)


class MenuOps(c.Structure):
    _fields_ = [('native_label', NativeMenuCallback),
                ('xpan_label', XpanMenuCallback),
                ('native_select', NativeMenuCallback)]


def check(output):
    clang = shutil.which('clang')
    if not clang: raise RuntimeError('clang required')
    source = ROOT / 'firmware/xpan_module.c'
    flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror']
    with tempfile.TemporaryDirectory(prefix='gr4-xpan-core-') as tmp:
        host = Path(tmp) / 'core.dylib'
        subprocess.run([clang, *flags, '-shared', str(source), '-o', str(host)], check=True)
        lib = c.CDLL(str(host))
        lib.gr4_xpan_select_crop.argtypes = [c.POINTER(State), c.c_uint]
        lib.gr4_xpan_select_aspect.argtypes = [c.POINTER(State), c.c_uint]
        lib.gr4_xpan_deactivate.argtypes = [c.POINTER(State)]
        lib.gr4_xpan_effective_settings.argtypes = [c.POINTER(State), c.POINTER(Effective)]
        lib.gr4_xpan_crop_label.argtypes = [c.c_uint]
        lib.gr4_xpan_crop_label.restype = c.c_char_p
        lib.gr4_xpan_aspect_label.argtypes = [c.c_uint]
        lib.gr4_xpan_aspect_label.restype = c.c_char_p
        lib.gr4_xpan_aspect_menu_count.restype = c.c_uint
        lib.gr4_xpan_aspect_menu_label.argtypes = [c.c_uint]
        lib.gr4_xpan_aspect_menu_label.restype = c.c_char_p
        lib.gr4_xpan_aspect_menu_selected.argtypes = [c.POINTER(State),c.c_uint]
        lib.gr4_xpan_aspect_menu_select.argtypes = [c.POINTER(State),c.c_uint]
        lib.gr4_xpan_menu_render_label.argtypes = [c.c_uint,c.POINTER(MenuOps),c.c_void_p]
        lib.gr4_xpan_menu_apply.argtypes = [c.POINTER(State),c.c_uint,
                                            c.POINTER(MenuOps),c.c_void_p]
        lib.gr4_xpan_full_width_rect.argtypes = [c.c_uint]*5 + [c.POINTER(Rect)]
        lib.gr4_xpan_preview_rect.argtypes = [c.c_uint, c.c_uint, c.POINTER(Rect),
                                             c.c_uint, c.c_uint, c.POINTER(Rect)]
        lib.gr4_xpan_capture_begin.argtypes = [c.POINTER(State)]+[c.c_uint]*9+[c.POINTER(Capture)]
        lib.gr4_xpan_capture_preview.argtypes = [c.POINTER(Capture),c.c_uint,c.c_uint,c.POINTER(Rect)]
        lib.gr4_xpan_capture_dng_parameters.argtypes = [c.POINTER(Capture),c.POINTER(c.c_ubyte),c.c_uint]
        lib.gr4_xpan_capture_ycbcr422_source.argtypes = [c.POINTER(Capture),
            c.POINTER(c.c_ubyte),c.c_uint,c.c_uint,c.c_uint]
        lib.gr4_xpan_dng_apply_reversible.argtypes = [c.POINTER(Capture),
            c.POINTER(c.c_ubyte),c.c_uint,c.POINTER(Undo)]
        lib.gr4_xpan_ycbcr422_apply_reversible.argtypes = [c.POINTER(Capture),
            c.POINTER(c.c_ubyte),c.c_uint,c.c_uint,c.c_uint,c.POINTER(Undo)]
        lib.gr4_xpan_buffer_restore.argtypes = [c.POINTER(Undo),c.POINTER(c.c_ubyte),c.c_uint]
        native = c.CFUNCTYPE(None,*([c.POINTER(c.c_ushort)]*4),c.c_float,c.c_uint)
        lib.gr4_xpan_dng_bind.argtypes = [native,c.POINTER(Capture),c.c_uint]
        lib.gr4_xpan_dng_leaf.argtypes = [c.POINTER(c.c_ushort)]*4+[c.c_float,c.c_uint]
        lib.gr4_xpan_dng_disable.restype = None
        factors = [0x3F800000, 0x3FA04F89, 0x3FE23119]
        for aspect in range(4):
            for crop in range(3):
                state, result = State(crop, aspect, aspect), Effective()
                assert lib.gr4_xpan_effective_settings(c.byref(state), c.byref(result))
                assert (result.crop, result.aspect, result.factor, result.xpan) == (
                    crop, aspect, factors[crop], 0)
                assert lib.gr4_xpan_select_aspect(c.byref(state), 4)
                assert lib.gr4_xpan_effective_settings(c.byref(state), c.byref(result))
                assert (result.crop, result.aspect, result.factor, result.xpan) == (
                    crop, 0, factors[crop], 1)
                assert state.aspect == 4 and state.last_regular_aspect == aspect
                assert lib.gr4_xpan_deactivate(c.byref(state))
                assert lib.gr4_xpan_effective_settings(c.byref(state), c.byref(result))
                assert result.aspect == aspect and result.factor == factors[crop]
        state, result = State(2, 4, 0), Effective()
        assert lib.gr4_xpan_select_aspect(c.byref(state), 2)
        assert lib.gr4_xpan_effective_settings(c.byref(state), c.byref(result))
        assert result.aspect == 2 and result.crop == 2 and state.last_regular_aspect == 2
        assert lib.gr4_xpan_select_aspect(c.byref(state), 4)
        assert lib.gr4_xpan_effective_settings(c.byref(state), c.byref(result))
        assert result.xpan == 1 and result.crop == 2 and result.aspect == 0
        assert lib.gr4_xpan_select_crop(c.byref(state), 0)
        assert lib.gr4_xpan_effective_settings(c.byref(state), c.byref(result))
        assert result.xpan == 1 and result.crop == 0
        assert lib.gr4_xpan_deactivate(c.byref(state)) and state.aspect == 2
        assert not lib.gr4_xpan_select_crop(c.byref(state), 3)
        assert not lib.gr4_xpan_select_aspect(c.byref(state), 5)
        assert [lib.gr4_xpan_crop_label(i).decode() for i in range(3)] == [
            'OFF', '35mm', '50mm']
        assert lib.gr4_xpan_crop_label(3) is None
        assert [lib.gr4_xpan_aspect_label(i).decode() for i in range(5)] == [
            '3:2', '4:3', '16:9', '1:1', 'XPAN']
        assert lib.gr4_xpan_aspect_label(5) is None
        assert lib.gr4_xpan_aspect_menu_count() == 5
        assert [lib.gr4_xpan_aspect_menu_label(i).decode() for i in range(5)] == [
            '3:2', '4:3', '1:1', '16:9', 'XPAN']
        assert lib.gr4_xpan_aspect_menu_label(5) is None
        for index, native_aspect in enumerate((0,1,3,2,4)):
            menu_state = State(1,0,0)
            assert lib.gr4_xpan_aspect_menu_select(c.byref(menu_state),index)
            assert menu_state.aspect == native_aspect
            assert [lib.gr4_xpan_aspect_menu_selected(c.byref(menu_state),i)
                    for i in range(5)] == [int(i == index) for i in range(5)]
            before = (menu_state.crop,menu_state.aspect,menu_state.last_regular_aspect)
            assert not lib.gr4_xpan_aspect_menu_select(c.byref(menu_state),5)
            assert before == (menu_state.crop,menu_state.aspect,menu_state.last_regular_aspect)
        # Both target menu descriptors have four native rows. A descriptor
        # adapter must call the original only for rows 0..3 and route row 4
        # through its own label while projecting native selection to row 0.
        menu_calls = []
        selection_succeeds = [True]
        @NativeMenuCallback
        def native_label(_ctx,index):
            menu_calls.append(('native_label',index))
            assert index < 4
            return 1
        @XpanMenuCallback
        def xpan_label(_ctx):
            menu_calls.append(('xpan_label',))
            return 1
        @NativeMenuCallback
        def native_select(_ctx,index):
            menu_calls.append(('native_select',index))
            assert index < 4
            return int(selection_succeeds[0])
        menu_ops = MenuOps(native_label,xpan_label,native_select)
        for index in range(5):
            menu_calls.clear()
            assert lib.gr4_xpan_menu_render_label(index,c.byref(menu_ops),None)
            assert menu_calls == ([('xpan_label',)] if index == 4 else
                                  [('native_label',index)])
        menu_calls.clear()
        assert not lib.gr4_xpan_menu_render_label(5,c.byref(menu_ops),None)
        assert not menu_calls
        menu_state = State(2,2,2)
        assert lib.gr4_xpan_menu_apply(c.byref(menu_state),4,c.byref(menu_ops),None)
        assert menu_calls == [('native_select',0)]
        assert (menu_state.crop,menu_state.aspect,menu_state.last_regular_aspect) == (2,4,2)
        menu_calls.clear()
        assert [lib.gr4_xpan_aspect_menu_selected(c.byref(menu_state),i)
                for i in range(5)] == [0,0,0,0,1]
        assert lib.gr4_xpan_menu_apply(c.byref(menu_state),3,c.byref(menu_ops),None)
        assert menu_calls == [('native_select',3)]
        assert (menu_state.crop,menu_state.aspect,menu_state.last_regular_aspect) == (2,2,2)
        selection_succeeds[0] = False
        menu_calls.clear()
        assert not lib.gr4_xpan_menu_apply(c.byref(menu_state),4,c.byref(menu_ops),None)
        assert menu_calls == [('native_select',0)]
        assert (menu_state.crop,menu_state.aspect,menu_state.last_regular_aspect) == (2,2,2)
        menu_calls.clear()
        assert not lib.gr4_xpan_menu_apply(c.byref(menu_state),5,c.byref(menu_ops),None)
        assert not menu_calls
        missing_label = MenuOps(native_label,XpanMenuCallback(),native_select)
        assert not lib.gr4_xpan_menu_render_label(4,c.byref(missing_label),None)
        invalid = State(0,4,5)
        assert not lib.gr4_xpan_effective_settings(c.byref(invalid),c.byref(result))
        assert not lib.gr4_xpan_select_aspect(c.byref(invalid),1)
        assert not lib.gr4_xpan_deactivate(c.byref(invalid))
        photo, preview = Rect(), Rect()
        assert lib.gr4_xpan_full_width_rect(6192, 4128, 16, 8, 2, c.byref(photo))
        assert (photo.left, photo.top, photo.width, photo.height) == (0, 920, 6192, 2288)
        assert lib.gr4_xpan_preview_rect(6192, 4128, c.byref(photo), 720, 480, c.byref(preview))
        assert (preview.left, preview.top, preview.width, preview.height) == (0, 106, 720, 267)
        # Independent exact arithmetic checks, including in-place output and 32-bit products.
        for sw, sh, pw, ph in [(6192,4128,720,480), (65535,65535,65535,65535),
                              (3504,2336,1920,1280), (4944,3296,160,120)]:
            rect = Rect(2,4,sw-4,sh-8)
            left, top = 2*pw//sw, 4*ph//sh
            expected = (left,top,(sw-2)*pw//sw-left,(sh-4)*ph//sh-top)
            assert lib.gr4_xpan_preview_rect(sw,sh,c.byref(rect),pw,ph,c.byref(rect))
            assert (rect.left,rect.top,rect.width,rect.height) == expected
        assert not lib.gr4_xpan_full_width_rect(6191,4128,16,8,2,c.byref(photo))
        assert not lib.gr4_xpan_full_width_rect(6192,100,16,8,2,c.byref(photo))
        assert not lib.gr4_xpan_full_width_rect(6192,4128,16,3,2,c.byref(photo))
        state, plan = State(0,4,2), Capture()
        assert lib.gr4_xpan_capture_begin(c.byref(state),6192,4128,6320,4224,
                                          54,58,16,8,2,c.byref(plan))
        # Freeze this exposure's window: later menu changes cannot alter it.
        assert lib.gr4_xpan_select_aspect(c.byref(state),1)
        buffer = (c.c_ubyte*64)(*([0xA5]*64))
        assert lib.gr4_xpan_capture_dng_parameters(c.byref(plan),buffer,64)
        assert bytes(buffer)[24:32] == struct.pack('<4H',6192,2288,54,978)
        assert bytes(buffer)[:24] == bytes([0xA5])*24
        assert bytes(buffer)[32:] == bytes([0xA5])*32
        assert lib.gr4_xpan_capture_preview(c.byref(plan),720,480,c.byref(preview))
        assert (preview.left,preview.top,preview.width,preview.height) == (0,106,720,267)
        assert plan.native_crop_factor_bits == factors[0]
        for crop in (1,2):
            xpan_state = State(crop,4,3)
            crop_plan = Capture()
            assert lib.gr4_xpan_capture_begin(c.byref(xpan_state),260,176,272,200,
                                              4,8,4,8,2,c.byref(crop_plan))
            assert crop_plan.native_crop_factor_bits == factors[crop]
            assert (crop_plan.photo.left,crop_plan.photo.top,
                    crop_plan.photo.width,crop_plan.photo.height) == (0,40,260,96)
        delegated = []
        @native
        def original(w,h,x,y,factor,aspect):
            delegated.append((factor,aspect))
            w[0],h[0],x[0],y[0] = 11,12,13,14
        values = [c.c_ushort() for _ in range(4)]
        def leaf(factor,aspect):
            lib.gr4_xpan_dng_leaf(*[c.byref(v) for v in values],factor,aspect)
            return tuple(v.value for v in values)
        lib.gr4_xpan_dng_bind(original,c.byref(plan),0)
        assert leaf(1.0,0) == (11,12,13,14)  # unready integration delegates
        lib.gr4_xpan_dng_bind(original,c.byref(plan),1)  # synthetic ready context only
        assert leaf(1.0,0) == (6192,2288,54,978)
        assert len(delegated) == 1
        assert leaf(1.25,0) == (11,12,13,14)
        assert leaf(1.0,2) == (11,12,13,14)
        # The fifth aspect may be combined with either native focal crop.
        # Only the factor captured for this exposure may use its XPAN window.
        for crop in (1,2):
            crop_state, crop_plan = State(crop,4,0), Capture()
            assert lib.gr4_xpan_capture_begin(c.byref(crop_state),260,176,272,200,
                                              4,8,4,8,2,c.byref(crop_plan))
            lib.gr4_xpan_dng_bind(original,c.byref(crop_plan),1)
            native_factor = struct.unpack('<f',struct.pack('<I',factors[crop]))[0]
            assert leaf(native_factor,0) == (260,96,4,48)
            assert leaf(1.0,0) == (11,12,13,14)
        lib.gr4_xpan_dng_disable()
        assert leaf(1.0,0) == (11,12,13,14)  # rollback retains original delegate
        lib.gr4_xpan_dng_disable()
        assert leaf(1.0,0) == (11,12,13,14)  # repeated disable remains safe
        lib.gr4_xpan_dng_bind(original,c.byref(plan),1)
        before = bytes(buffer)
        assert not lib.gr4_xpan_capture_dng_parameters(c.byref(plan),buffer,31)
        assert bytes(buffer) == before
        plan.raw_height = 100
        assert not lib.gr4_xpan_capture_dng_parameters(c.byref(plan),buffer,64)
        assert bytes(buffer) == before
        assert leaf(1.0,0) == (11,12,13,14)  # invalid snapshot also delegates
        assert not lib.gr4_xpan_capture_begin(c.byref(state),6192,4128,6320,4224,
                                              54,58,16,8,2,c.byref(plan))
        assert plan.enabled == 0
        # Check actual row selection using independent synthetic plane pixels:
        # source 260x176, padded stride 272, exact XPAN 260x96 at row 40.
        state = State(0,4,0)
        assert lib.gr4_xpan_capture_begin(c.byref(state),260,176,272,200,
                                          4,8,4,8,2,c.byref(plan))
        pitch, rows, base_y, base_c = 272,176,0x59001000,0x59010000
        descriptor = bytearray([0xA5]*32)
        descriptor[0] = 1
        struct.pack_into('<II',descriptor,4,base_y,base_c)
        struct.pack_into('<4H',descriptor,0x10,260,176,pitch,rows)
        block = (c.c_ubyte*32).from_buffer_copy(descriptor)
        assert lib.gr4_xpan_capture_ycbcr422_source(c.byref(plan),block,32,
                                                    pitch*rows,pitch*rows)
        cropped = bytes(block)
        y_address, c_address = struct.unpack_from('<II',cropped,4)
        width, height, stride, global_height = struct.unpack_from('<4H',cropped,0x10)
        assert (width,height,stride,global_height) == (260,96,pitch,rows)
        # The descriptor must select the center pixel rows, retaining padding.
        for base,address,multiplier in [(base_y,y_address,1),(base_c,c_address,3)]:
            pixels = bytes(((row*multiplier + column) % 256)
                           for row in range(rows) for column in range(pitch))
            selected = b''.join(pixels[address-base+row*stride:
                                       address-base+row*stride+width] for row in range(height))
            expected = b''.join(pixels[row*pitch:row*pitch+260] for row in range(40,136))
            assert selected == expected
        changed = set(range(4,12)) | set(range(0x10,0x14))
        assert all(cropped[i] == descriptor[i] for i in range(32) if i not in changed)
        assert not lib.gr4_xpan_capture_ycbcr422_source(c.byref(plan),block,32,
                                                        pitch*rows,pitch*rows)
        assert bytes(block) == cropped  # no second application
        for fmt, capacity, address in [(2,pitch*rows,base_y), # 420 rejected
                                       (1,100,base_y),      # allocation too small
                                       (1,pitch*rows,0xfffffff0)]: # address wrap
            invalid = bytearray(descriptor)
            invalid[0] = fmt
            struct.pack_into('<I',invalid,4,address)
            block = (c.c_ubyte*32).from_buffer_copy(invalid)
            assert not lib.gr4_xpan_capture_ycbcr422_source(c.byref(plan),block,32,
                                                           capacity,capacity)
            assert bytes(block) == invalid
        # Reversible adapters: exact original fields, conflict preflight,
        # wrong target, repeated restore and unrelated fields changed by others.
        for kind in (1,2):
            undo = Undo()
            initial = bytes([0xA5]*64) if kind == 1 else bytes(descriptor)
            block = (c.c_ubyte*len(initial)).from_buffer_copy(initial)
            def reversible():
                if kind == 1:
                    return lib.gr4_xpan_dng_apply_reversible(c.byref(plan),block,len(initial),c.byref(undo))
                return lib.gr4_xpan_ycbcr422_apply_reversible(c.byref(plan),block,len(initial),
                                                              pitch*rows,pitch*rows,c.byref(undo))
            assert reversible() and undo.kind == kind
            applied = bytes(block)
            assert not reversible() and bytes(block) == applied  # keep first backup
            wrong = (c.c_ubyte*len(initial)).from_buffer_copy(applied)
            assert not lib.gr4_xpan_buffer_restore(c.byref(undo),wrong,len(initial))
            assert bytes(wrong) == applied and undo.kind == kind
            assert not lib.gr4_xpan_buffer_restore(c.byref(undo),block,10)
            assert bytes(block) == applied
            offset = 0x18 if kind == 1 else 4
            block[offset] ^= 1
            conflict = bytes(block)
            assert not lib.gr4_xpan_buffer_restore(c.byref(undo),block,len(initial))
            assert bytes(block) == conflict and undo.kind == kind
            block[offset] = applied[offset]
            block[2] = 0x5A  # outside this adapter's owned fields
            assert lib.gr4_xpan_buffer_restore(c.byref(undo),block,len(initial))
            expected = bytearray(initial); expected[2] = 0x5A
            assert bytes(block) == expected and undo.kind == 0
            assert lib.gr4_xpan_buffer_restore(c.byref(undo),block,len(initial))
            assert bytes(block) == expected
        obj = Path(tmp) / 'xpan-core.arm.o'
        subprocess.run([clang, '--target=armv7-none-eabi', '-march=armv7-a', '-marm',
                        '-mfpu=vfpv3', '-mfloat-abi=hard', *flags, '-ffreestanding', '-fno-builtin',
                        '-fno-stack-protector', '-c', str(source), '-o', str(obj)], check=True)
        raw = obj.read_bytes()
        assert raw[:7] == b'\x7fELF\x01\x01\x01' and struct.unpack_from('<H',raw,18)[0] == 40
        # Reject unresolved function/data symbols in the relocatable object.
        shoff = struct.unpack_from('<I',raw,32)[0]
        stride, count = struct.unpack_from('<HH',raw,46)
        for i in range(count):
            section = struct.unpack_from('<10I',raw,shoff+i*stride)
            if section[1] != 2: continue
            for pos in range(section[4],section[4]+section[5],section[9]):
                name,_,_,info,_,index = struct.unpack_from('<IIIBBH',raw,pos)
                assert not (name and index == 0 and info >> 4), 'unresolved ARM symbol'
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('xb') as f: f.write(raw)
    return {'host_state_menu_dispatch_geometry_capture_DNG_YCbCr_undo_checks': 'passed', 'arm_relocatable_object': str(output),
            'unresolved_ARM_symbols': 0, 'DNG_leaf_ABI_bridge_implemented': True,
            'host_disable_and_buffer_rollback_checks': 'passed',
            'camera_restore_path_verified': False,
            'native_menu_JPEG_preview_installation': False,
            'camera_installable': False, 'alignment_values_in_test': 'illustrative, unverified on device'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    args = p.parse_args()
    print(json.dumps(check(args.output),indent=2))


if __name__ == '__main__': main()
