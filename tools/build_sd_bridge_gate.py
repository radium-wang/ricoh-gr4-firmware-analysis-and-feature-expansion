#!/usr/bin/env python3
"""Build one-shot, no-patch SD gate for the GR IV Linux command bridge."""
import argparse
import hashlib
import json
from pathlib import Path


SHELL = '''#!/bin/sh
set -eu
case "$0" in /run/SD/*/BRRUN.SH) ;; *) exit 64 ;; esac
card=${0%/BRRUN.SH}
[ -d "$card/DCIM" ] || exit 65
[ ! -e "$card/BRDONE.TXT" ] || exit 0
printf 'XPAN_BRIDGE_EXECUTED\\n' > "$card/BRDONE.TXT"
'''


def build_ttl():
    lines = [
        '; GR IV 1.11.10.7: one boot; no firmware, code or setting writes.',
        '; BRTEST.TXT is created first so a later boot cannot repeat the command.',
        "filesearch 'C:\\BRTEST.TXT'",
        'if result = 1 then', '    end', 'endif',
        "filecreate bf 'C:\\BRTEST.TXT'",
        'if bf < 0 then', '    end', 'endif',
        "filewriteln bf 'bridge gate started'", 'fileclose bf',
        'mpause 10000',
        'da = 1426719488', 'ds = 768', "dn = 'BRBOOT.BIN'", 'call dump_exact',
        'bridge_ok = 0',
        'if dok = 1 then',
        "    ufile = 'C:\\BRBOOT.BIN'", '    uoff = 188', '    call read_u32',
        '    if uok = 1 then',
        '        bridge_addr = uv',
        '        if bridge_addr >= 1509949440 then',
        '            if bridge_addr <= 1526726539 then',
        '                da = bridge_addr', '                ds = 117',
        "                dn = 'BRPRE.BIN'", '                call dump_exact',
        '                bridge_ok = dok',
        '            endif', '        endif', '    endif', 'endif',
        "sendln 'is_linux_boot'", 'ready = result',
        "tag = 'Linux readiness'", 'value = ready', 'call log_value',
        'if ready = 1 then',
        "    sendln 'lcmd \"/bin/sh /run/SD/*/BRRUN.SH\"'",
        '    handler_result = result',
        "    tag = 'lcmd handler result, not execution proof'",
        '    value = handler_result', '    call log_value',
        '    mpause 5000',
        'endif',
        'if bridge_ok = 1 then',
        '    da = bridge_addr', '    ds = 117',
        "    dn = 'BRPOST.BIN'", '    call dump_exact',
        'endif',
        "tag = 'bridge object read available'", 'value = bridge_ok',
        'call log_value',
        "filesearch 'C:\\BRDONE.TXT'",
        "tag = 'Linux script marker exists'", 'value = result',
        'call log_value',
        "fileopen bf 'C:\\BRTEST.TXT' 1",
        "filewriteln bf 'bridge gate finished'", 'fileclose bf', 'end',
        ':log_value',
        'int2str number value',
        "fileopen bf 'C:\\BRTEST.TXT' 1",
        'filewriteln bf tag', 'filewriteln bf number', 'fileclose bf',
        'return',
        ':dump_exact',
        "path = 'C:\\'", 'strconcat path dn',
        'filesearch path', 'dok = 0',
        'if result = 0 then',
        "    cmd = 'SYS_md '",
        '    int2str number da', '    strconcat cmd number',
        "    strconcat cmd ' -s '",
        '    int2str number ds', '    strconcat cmd number',
        "    strconcat cmd ' -f '", '    strconcat cmd path',
        '    sendln cmd',
        '    actual = -1', '    filestat path actual',
        '    if result = 0 then',
        '        if actual = ds then', '            dok = 1',
        '        endif', '    endif',
        'endif',
        'tag = dn', 'value = dok', 'call log_value', 'return',
        ':read_byte',
        'uok = 0', 'uv = 0', 'usize = -1',
        'filestat ufile usize',
        'if result = 0 then',
        '    if uoff >= 0 then',
        '        if usize > uoff then',
        '            fileopen uf ufile 0',
        '            if uf >= 0 then',
        '                fileseek uf uoff 0',
        '                fileread uf 1 uc',
        '                if result = 0 then',
        '                    str2code uv uc', '                    uok = 1',
        '                endif', '                fileclose uf',
        '            endif', '        endif', '    endif', 'endif',
        'return',
        ':read_u32',
        'call read_byte', 'ua = uv', 'ua_ok = uok',
        'uoff = uoff + 1', 'call read_byte',
        'ub = uv', 'ub_ok = uok',
        'uoff = uoff + 1', 'call read_byte',
        'ucode = uv', 'uc_ok = uok',
        'uoff = uoff + 1', 'call read_byte',
        'uv = ua + ub * 256 + ucode * 65536 + uv * 16777216',
        'if ua_ok = 0 then', '    uok = 0', 'endif',
        'if ub_ok = 0 then', '    uok = 0', 'endif',
        'if uc_ok = 0 then', '    uok = 0', 'endif',
        'return',
    ]
    result = '\n'.join(lines) + '\n'
    assert 'SYS_reg' not in result and 'lcmd_resp' not in result
    assert '1426719488' == str(0x550A0300)
    assert '1526726539' == str(0x5B000000 - 117)
    return result


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    data = {'script/startup.ttl': build_ttl().encode('ascii'),
            'BRRUN.SH': SHELL.encode('ascii')}
    for name, contents in data.items():
        p = output / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(contents)
    manifest = {name: {'size':len(contents), 'sha256':hashlib.sha256(contents).hexdigest()}
                for name,contents in data.items()}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    print(json.dumps(build(args.output),indent=2))
