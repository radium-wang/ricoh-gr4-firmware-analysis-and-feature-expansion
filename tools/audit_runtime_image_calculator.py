#!/usr/bin/env python3
"""Audit the sample calculator selected by a saved device vtable, without execution."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from analyze_sd_batch_readback import SAMPLE_SHA


def audit(raw, vtable):
    if hashlib.sha256(raw).hexdigest() != SAMPLE_SHA:
        raise ValueError('unsupported decoded firmware sample')
    if len(vtable) != 64:
        raise ValueError('expected the 64-byte same-boot calculator vtable')
    offset = lambda a: a - 0x53000000 + 0x17D10
    words = struct.unpack('<16I', vtable)
    if words != struct.unpack_from('<16I', raw, offset(0x53FD89A0)):
        raise ValueError('saved vtable differs from the mapped GR IV calculator')
    assert words[2] == 0x538CFBF8 and words[12] == 0x538CFB5C
    assert words[13] == 0x538CFB90

    def dimensions(target):
        # The audited table targets consist of MOV/MOVW immediates and STRH,
        # ending at a B or epilogue. Decode only that restricted sequence.
        registers = {}
        values = []
        for i in range(10):
            instruction = struct.unpack_from('<I', raw, offset(target) + 4*i)[0]
            register = (instruction >> 12) & 15
            if instruction & 0xFFF00000 == 0xE3000000:  # ARM MOVW
                registers[register] = ((instruction >> 4) & 0xF000) | (instruction & 0xFFF)
            elif instruction & 0xFFF00000 == 0xE3A00000:
                # MOV immediate: destination may be r2 or r3, no flags.
                rotation = ((instruction >> 8) & 15) * 2
                imm = instruction & 255
                registers[register] = ((imm >> rotation) | (imm << (32-rotation))) & 0xFFFFFFFF
            elif instruction & 0xFFF00FFF == 0xE1C000B0:  # STRH [r8]/[r9], offset 0
                base = (instruction >> 16) & 15
                if base in (8, 9):
                    values.append((base, registers[register]))
            elif values:
                break
            else:
                raise ValueError(f'unsupported size block at {target + 4*i:#x}')
        sizes = dict(values)
        if set(sizes) != {8, 9}:
            raise ValueError(f'incomplete size block at {target:#x}')
        return [sizes[8], sizes[9]]

    tables = [('3:2', 0x538CFD9C), ('4:3', 0x538CFE90),
              ('16:9', 0x538CFEAC), ('1:1', 0x538CFDB8)]
    matrix = {}
    for aspect, address in tables:
        targets = struct.unpack_from('<4I', raw, offset(address))
        matrix[aspect] = {str(index): {'branch': hex(target), 'pixels': dimensions(target)}
                          for index, target in enumerate(targets)}
    assert matrix['3:2']['0']['pixels'] == [6192, 4128]
    return {'calculator_vtable': '0x53fd89a0', 'dimensions_method': '0x538cfbf8',
            'arguments': {'r1': 'resolution/size index', 'r2': 'aspect ID',
                          's0': 'crop factor (table below uses 1.0)'},
            'size_index_branches_at_crop_factor_1': matrix,
            'index_3_note': 'size index 3; not a fourth crop or XPAN mode',
            'DNG_origin_base_by_parameter_variant': {'Kb588': [68, 40], 'Kb636': [54, 58]},
            'active_DNG_parameter_variant_verified_by_this_tool': False,
            'XPAN_full_width_candidates': [
                {'pixels': [6192, 2286], 'center_offset': [0, 921],
                 'note': 'nearest even height; vertical Bayer phase needs checking'},
                {'pixels': [6192, 2288], 'center_offset': [0, 920],
                 'note': 'even center offset; pipeline alignment still unverified'}],
            'patched_or_installed': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('sample', type=Path)
    p.add_argument('vtable', type=Path)
    args = p.parse_args()
    print(json.dumps(audit(args.sample.read_bytes(), args.vtable.read_bytes()),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
