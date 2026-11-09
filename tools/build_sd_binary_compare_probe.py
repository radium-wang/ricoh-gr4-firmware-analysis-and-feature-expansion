#!/usr/bin/env python3
"""Build a read-only TTL comparison diagnostic after a blocked RAM preflight."""
import argparse
import hashlib
import json
from pathlib import Path
from build_sd_recovery_probe import build
from audit_xpan_runtime_loader import REFERENCE_RANGES


def program():
    source = build()
    compare = source.split(':compare_files\n', 1)[1].split('\n:read_byte\n', 1)[0]
    compare = compare.replace('equal = 0\ncompared = 0',
                              'equal = 0\ncompare_index = -1\ncompared = 0', 1)
    compare = compare.replace('while compared < compare_bytes\n',
                              'while compared < compare_bytes\n            compare_index = compared\n', 1)
    compare = compare.rstrip()
    assert compare.endswith('\nreturn')
    compare = compare[:-len('return')] + '''call comparison_log
return

:comparison_log
fileopen lf logfile 1
if lf >= 0 then
    filewriteln lf path
    filewriteln lf ref
    filewriteln lf 'equal,compared,index,actual_code,ref_code,actual_size,ref_size,actual_stat,ref_stat,actual_size_after,ref_size_after'
'''
    for variable in ('equal','compared','compare_index','actual_code','ref_code',
                     'actual_size','ref_size','actual_stat','ref_stat','actual_size_after','ref_size_after'):
        compare += f'    int2str number {variable}\n    filewriteln lf number\n'
    compare += '    fileclose lf\nendif\nreturn\n'
    lines = ["; Read-only binary comparison diagnostic; no RAM/state/code writes.",
             "logfile = 'C:\\YBCMP.TXT'", "filesearch logfile", 'if result = 1 then',
             '    end', 'endif', 'filecreate lf logfile', 'if lf < 0 then',
             '    end', 'endif', "filewriteln lf 'Binary comparison diagnostic started'",
             'fileclose lf', 'mpause 10000', 'good = 1']
    # Controls exercise embedded NUL, unequal content, short and extra data.
    for tag in ('EQ','DIFF','SHORT','EXTRA'):
        lines += [f"path = 'C:\\YB{tag}.BIN'", "ref = 'C:\\YBCTRL.REF'",
                  'compare_bytes = 4', 'skip_bytes = 0', 'call compare_files']
    for tag, address, size in REFERENCE_RANGES:
        path = 'C:\\YB' + tag[2:] + '.BIN'
        lines += [f"path = '{path}'", 'filesearch path', 'if result = 0 then',
                  f"    sendln 'SYS_md {address} -s {size} -f {path}'", 'endif',
                  f"ref = 'C:\\{tag}.REF'", f'compare_bytes = {size}',
                  'skip_bytes = 0', 'call compare_files']
    lines += ['fileopen lf logfile 1', 'if lf >= 0 then',
              "    filewriteln lf 'Binary comparison diagnostic finished; no RAM writes'",
              '    fileclose lf', 'endif', 'end', '', ':compare_files', compare]
    result = '\n'.join(lines) + '\n'
    assert 'SYS_reg' not in result and 'restore_command' not in result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    files = {'startup.ttl': program().encode('ascii'), 'YBCTRL.REF': b'\0\1\xff\0',
             'YBEQ.BIN': b'\0\1\xff\0', 'YBDIFF.BIN': b'\0\2\xff\0',
             'YBSHORT.BIN': b'\0\1\xff', 'YBEXTRA.BIN': b'\0\1\xff\0\x7f'}
    for name, data in files.items():
        with (args.output/name).open('xb') as f:
            f.write(data)
    manifest = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                for name, data in files.items()}
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({'output': str(args.output), 'RAM_writes': 0, 'boots_needed': 1}))


if __name__ == '__main__':
    main()
