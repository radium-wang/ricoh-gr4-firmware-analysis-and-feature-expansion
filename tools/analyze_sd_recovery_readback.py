#!/usr/bin/env python3
"""Analyze copied recovery outputs offline; never write or access an SD card."""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from audit_xpan_paths import EXPECTED_SHA256
from audit_xpan_runtime_loader import COMMANDS
from build_sd_recovery_probe import ORIGINAL, references


def analyze(root, sample, two_normal_boots_confirmed=False, prefix='XR'):
    if len(prefix)!=2 or not prefix.isascii() or not prefix.isalpha() or not prefix.isupper():
        raise ValueError('output prefix must be two uppercase ASCII letters')
    root = Path(root).resolve()
    if root == Path('/Volumes') or Path('/Volumes') in root.parents:
        raise ValueError('copy the outputs to the computer before analysis')
    raw = Path(sample).read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('wrong decoded firmware sample')
    refs = references(raw)
    phases = {}
    for phase in (1, 2, 3):
        phase_prefix = f'{prefix}{phase}'
        def read(suffix):
            path = root / (phase_prefix + suffix)
            return path.read_bytes() if path.is_file() else b''
        log = read('LOG.TXT').decode('ascii', errors='replace')
        lines = log.splitlines()
        def number(label):
            positions = [i for i, line in enumerate(lines) if line == label]
            if len(positions) != 1:
                return None
            i = positions[0]
            try:
                return int(lines[i+1])
            except (ValueError, IndexError):
                return None
        checks = {'finished': bool(lines) and lines[-1] ==
                  'Recovery diagnostic finished; inspect all checks',
                  'phase_matches': number('phase') == phase,
                  'script_reported_success': number('all checks passed') == 1}
        for tag, expected, size in [('EQ',1,4),('DIFF',0,4),('SHORT',0,3),('EXTRA',0,5)]:
            checks['control_'+tag+'_passed'] = (number(
                f'comparison control {tag}; expected {expected}') == expected and
                number(f'control {tag} size; expected {size}') == size)
        for name, ref in refs.items():
            tag = name[2:-4]
            data = read(tag + '.BIN')
            checks[tag + '_matches'] = data == ref
            if phase == 3 and tag == 'BIROW':
                # Independent recovery may start with the known test pointer.
                from audit_xpan_runtime_loader import TEST_RETURN
                checks[tag + '_matches'] = (len(data) == len(ref) and
                    data[4:] == ref[4:] and struct.unpack_from('<I', data)[0]
                    in (ORIGINAL, TEST_RETURN))
        holder = read('HOLD.BIN')
        base = struct.unpack_from('<I', holder)[0] if len(holder) == 8 else None
        checks['holder_valid'] = (base is not None and base % 4 == 0 and
            0x59000000 <= base <= 0x5A000000 - 651*52 and
            struct.unpack_from('<H', holder, 4)[0] == 651)
        checks['same_boot_addresses_match'] = (checks['holder_valid'] and
            number('same-boot table address') == base and
            number('same-boot handler address') == base + COMMANDS['SYS_buildinfo'][0]*52)
        post = read('POST.BIN')
        checks['original_handler_restored'] = post == struct.pack('<I', ORIGINAL)
        checks['logged_restored_word_matches'] = number('restored handler word') == ORIGINAL
        checks['original_command_returned_zero'] = number(
            'original command return after check; expected 0') == 0
        before, after = read('PROPS.BIN'), read('PPOST.BIN')
        checks['imaging_properties_unchanged'] = len(before) == 5 and before == after
        if phase == 1:
            checks['patch_returned_zero'] = number('patch handler return') == 0
            checks['native_test_returned_three'] = number('immutable ROM test return; expected 3') == 3
            checks['restore_returned_zero'] = number('restore handler return') == 0
        phases[str(phase)] = {'present': bool(log), 'checks': checks,
            'all_checks_passed': all(checks.values()), 'log': log,
            'freshly_read_table_address': hex(base) if base is not None else None}
    first, second = phases['1']['all_checks_passed'], phases['2']['all_checks_passed']
    return {'phases': phases, 'output_prefix':prefix,
        'write_attempt_marker_present': (root/(prefix+'TRY.TXT')).is_file(),
        'temporary_pointer_restore_verified_from_files': first,
        'second_phase_readonly_checks_passed': second,
        'two_normal_boots_confirmed_by_user': two_normal_boots_confirmed,
        'normal_reboot_after_diagnostic_verified': first and second and two_normal_boots_confirmed,
        'no_loader_cold_boot_tested': False, 'independent_recovery_on_camera_tested': False,
        'native_module_loading_verified': False, 'XPAN_installable': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('sample', type=Path)
    parser.add_argument('--two-normal-boots-confirmed', action='store_true',
                        help='only after the user confirms both normal off/on cycles')
    parser.add_argument('--output-prefix', default='XR')
    args = parser.parse_args()
    print(json.dumps(analyze(args.directory, args.sample, args.two_normal_boots_confirmed,
                            args.output_prefix),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
