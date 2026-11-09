#!/usr/bin/env python3
"""Build an SD recovery diagnostic offline. Default is read-only.

--arm-ram-probe permits a single temporary native diagnostic handler pointer
change. It executes only existing ROM code, restores before SD operations,
and uses a second normal boot for a read-only check. It does not install XPAN.
Reference bytes derived from the user's firmware stay in the private output.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
from audit_xpan_paths import EXPECTED_SHA256,file_offset
from audit_xpan_runtime_loader import COMMANDS,TEST_RETURN,REFERENCE_RANGES,audit
from build_sd_batch_probe import build as prior_probe

HOLDER=0x553A094C
ORIGINAL=COMMANDS['SYS_buildinfo'][1]
PROPERTIES=0x55085D63


def controls():
    return {'XCCTRL.REF':b'\0\1\xff\0','XCEQ.BIN':b'\0\1\xff\0',
            'XCDIFF.BIN':b'\0\2\xff\0','XCSHORT.BIN':b'\0\1\xff',
            'XCEXTRA.BIN':b'\0\1\xff\0\x7f'}


def build(armed=False,recovery_only=False,prefix='XR'):
    if len(prefix)!=2 or not prefix.isascii() or not prefix.isalpha() or not prefix.isupper():
        raise ValueError('output prefix must be two uppercase ASCII letters')
    lines=[]
    def emit(s):lines.extend(s.strip().splitlines())
    emit(f"""
; GR IV 01.11.10.07 only. Verify against the companion .REF files.
; Default read-only. ARM pointer test enabled: {int(armed)}.
; Recovery-only entry: {int(recovery_only)}. No firmware/resource/image-setting writes.
; The only possible RAM write is SYS_buildinfo's aligned command-table word.
; Original ROM code is used throughout; no new code, allocator or cache command.
armed = {int(armed)}
recovery_only = {int(recovery_only)}
phase = 1
filesearch 'C:\\XRTRY.TXT'
if result = 1 then
    phase = 2
endif
if recovery_only = 1 then
    phase = 3
endif
int2str number phase
logfile = 'C:\\XR'
strconcat logfile number
strconcat logfile 'LOG.TXT'
filesearch logfile
if result = 1 then
    end
endif
filecreate lf logfile
if lf < 0 then
    end
endif
filewriteln lf 'Recovery diagnostic started; no XPAN installation'
fileclose lf
mpause 10000
good = 1
original_result = -999
""")
    # Establish actual filestat/byte-comparison behavior on the camera BEFORE
    # any write is possible. All four controls must classify correctly.
    for tag,expected,size in [('EQ',1,4),('DIFF',0,4),('SHORT',0,3),('EXTRA',0,5)]:
        emit(f"""
path = 'C:\\XC{tag}.BIN'
ref = 'C:\\XCCTRL.REF'
control_size = -1
control_ref_size = -1
filestat path control_size
control_status = result
filestat ref control_ref_size
control_ref_status = result
tag = 'control {tag} size; expected {size}'
value = control_size
call record
if control_status = 0 then
    if control_ref_status = 0 then
        if control_size = {size} then
            if control_ref_size = 4 then
                goto control_{tag}_precheck_ok
            endif
        endif
    endif
endif
good = 0
goto finish
:control_{tag}_precheck_ok
compare_bytes = 4
skip_bytes = 0
call compare_files
tag = 'comparison control {tag}; expected {expected}'
value = equal
call record
if actual_stat = 0 then
    if ref_stat = 0 then
        if actual_size = {size} then
            if ref_size = 4 then
                if actual_stat_after = 0 then
                    if ref_stat_after = 0 then
                        if actual_size_after = {size} then
                            if ref_size_after = 4 then
                                goto control_{tag}_size_ok
                            endif
                        endif
                    endif
                endif
            endif
        endif
    endif
endif
good = 0
goto finish
:control_{tag}_size_ok
if equal = {expected} then
    good = 1
else
    good = 0
    goto finish
endif
""")
    def dump(tag,address,size,heap=False):
        emit(f"da = {address}\nds = {size}\nitem = '{tag[2:]}'\ncall {'dump_heap' if heap else 'dump_fixed'}")
    def compare(tag,length,skip=0):
        emit(f"ref = 'C:\\{tag}.REF'\ncompare_bytes = {length}\nskip_bytes = {skip}\ncall compare_files")
    # Exact comparison of all relevant command bodies and the short-copy path,
    # not a camera-side assumption based solely on the version string.
    for tag,address,size in REFERENCE_RANGES:
        dump(tag,str(address),size);compare(tag,size)
    dump('XRHOLD',str(HOLDER),8)
    emit("""
ufile = path
uoff = 0
call read_u32
table = uv
if uok = 0 then
    good = 0
endif
uoff = 4
call read_u16
if uok = 0 then
    good = 0
endif
if uv = 651 then
    alignment = table / 4
    alignment = alignment * 4
    if alignment = table then
        table_end = table + 33852
        if table >= 1493172224 then
            if table_end <= 1509949440 then
                if table_end > table then
                    goto table_ok
                endif
            endif
        endif
    endif
endif
good = 0
goto finish
:table_ok
""")
    for name,(index,_) in COMMANDS.items():
        tag={'SYS_md':'XRMDROW','SYS_reg':'XRRGROW','SYS_buildinfo':'XRBIROW'}[name]
        size=4+len(name)+1
        dump(tag,f'table + {index*52}',size,True)
        # Recovery entry accepts only original or the exact native test leaf.
        compare(tag,size-4 if name=='SYS_buildinfo' and recovery_only else size,
                4 if name=='SYS_buildinfo' and recovery_only else 0)
        if name=='SYS_buildinfo':
            emit("""
ufile = path
uoff = 0
call read_u32
saved_handler = uv
if uok = 0 then
    good = 0
endif
""")
    dump('XRPROPS',str(PROPERTIES),5)
    emit(f"""
if good = 0 then
    goto finish
endif
if saved_handler = {ORIGINAL} then
    goto handler_ok
endif
if recovery_only = 1 then
    if saved_handler = {TEST_RETURN} then
        goto handler_ok
    endif
endif
good = 0
goto finish
:handler_ok
address = table + {COMMANDS['SYS_buildinfo'][0]*52}
tag = 'same-boot table address'
value = table
call record
tag = 'same-boot handler address'
value = address
call record
int2str number address
patch_command = 'SYS_reg set '
strconcat patch_command number
strconcat patch_command ' 4 {TEST_RETURN}'
restore_command = 'SYS_reg set '
strconcat restore_command number
strconcat restore_command ' 4 {ORIGINAL}'
if phase = 3 then
    if saved_handler = {TEST_RETURN} then
        sendln restore_command
        restore_result = result
    endif
    goto restored_check
endif
sendln 'SYS_buildinfo'
baseline_result = result
if baseline_result = 0 then
    if phase = 1 then
        if armed = 1 then
            goto prepare
        endif
    endif
    goto restored_check
endif
good = 0
goto finish
:prepare
; Readable SD marker is written BEFORE modification. Never retry this write test.
filecreate mf 'C:\\XRTRY.TXT'
if mf < 0 then
    good = 0
    goto finish
endif
filewriteln mf 'RAM pointer test prepared; original row backed up'
fileclose mf
ufile = 'C:\\XRTRY.TXT'
uoff = 0
call read_byte
if uok = 1 then
    if uv = 82 then
        goto transaction
    endif
endif
good = 0
goto finish
:transaction
; No SD operations, waits, subroutine calls or branches before restoration.
sendln patch_command
patch_result = result
sendln 'SYS_buildinfo'
test_result = result
sendln restore_command
restore_result = result
; Restore is attempted regardless of patch_result/test_result.
tag = 'patch handler return'
value = patch_result
call record
tag = 'immutable ROM test return; expected 3'
value = test_result
call record
tag = 'restore handler return'
value = restore_result
call record
if patch_result = 0 then
    if test_result = 3 then
        if restore_result = 0 then
            goto restored_check
        endif
    endif
endif
good = 0
:restored_check
""")
    dump('XRPOST','address',4,True)
    emit(f"""
ufile = path
uoff = 0
call read_u32
tag = 'restored handler word'
value = uv
call record
if uok = 1 then
    if uv = {ORIGINAL} then
        sendln 'SYS_buildinfo'
        original_result = result
        if original_result = 0 then
            goto property_check
        endif
    endif
endif
good = 0
:property_check
""")
    dump('XRPPOST',str(PROPERTIES),5)
    # Preserve each boot's original properties, independent of the fixed refs.
    emit("""
ref = 'C:\\XR'
int2str number phase
strconcat ref number
strconcat ref 'PROPS.BIN'
compare_bytes = 5
skip_bytes = 0
call compare_files
:finish
tag = 'original command return after check; expected 0'
value = original_result
call record
tag = 'phase'
value = phase
call record
tag = 'all checks passed'
value = good
call record
fileopen lf logfile 1
if lf >= 0 then
    filewriteln lf 'Recovery diagnostic finished; inspect all checks'
    fileclose lf
endif
end

:record
int2str record_number value
fileopen lf logfile 1
if lf >= 0 then
    filewriteln lf tag
    filewriteln lf record_number
    fileclose lf
endif
return

:dump_fixed
path = 'C:\\XR'
int2str number phase
strconcat path number
strconcat path item
strconcat path '.BIN'
filesearch path
dump_ok = 0
if result = 0 then
    cmd = 'SYS_md '
    int2str number da
    strconcat cmd number
    strconcat cmd ' -s '
    int2str number ds
    strconcat cmd number
    strconcat cmd ' -f '
    strconcat cmd path
    sendln cmd
    filesearch path
    dump_ok = result
endif
if dump_ok = 0 then
    good = 0
endif
return

:dump_heap
dump_ok = 0
last = da + ds
if da >= 1493172224 then
    if ds >= 1 then
        if ds <= 33852 then
            if last > da then
                if last <= 1509949440 then
                    call dump_fixed
                    return
                endif
            endif
        endif
    endif
endif
good = 0
return

:compare_files
; Compare every byte, including NULs, and require exact total file length.
; Actual/ref may have different offsets only for the recovery row's pointer.
; GR IV fileread returns 0 even beyond EOF: NEVER use it as a length check.
actual_handle = -1
ref_handle = -1
equal = 0
compared = 0
actual_code = -1
ref_code = -1
actual_size = -1
ref_size = -1
filestat path actual_size
actual_stat = result
filestat ref ref_size
ref_stat = result
required_size = skip_bytes + compare_bytes
if actual_stat = 0 then
    if ref_stat = 0 then
        if actual_size = required_size then
            if ref_size = required_size then
                goto compare_lengths_ok
            endif
        endif
    endif
endif
goto compare_finished
:compare_lengths_ok
fileopen actual_handle path 0
fileopen ref_handle ref 0
if actual_handle >= 0 then
    if ref_handle >= 0 then
        fileseek actual_handle skip_bytes 0
        fileseek ref_handle skip_bytes 0
        compared = 0
        equal = 1
        while compared < compare_bytes
            fileread actual_handle 1 actual_char
            actual_status = result
            fileread ref_handle 1 ref_char
            ref_status = result
            if actual_status = 0 then
                if ref_status = 0 then
                    str2code actual_code actual_char
                    str2code ref_code ref_char
                    if actual_code = ref_code then
                        compared = compared + 1
                    else
                        equal = 0
                        compared = compare_bytes
                    endif
                else
                    equal = 0
                    compared = compare_bytes
                endif
            else
                equal = 0
                compared = compare_bytes
            endif
        endwhile
    endif
endif
:compare_finished
if actual_handle >= 0 then
    fileclose actual_handle
endif
if ref_handle >= 0 then
    fileclose ref_handle
endif
; Recheck lengths after reading. Never read uninitialized data beyond EOF.
actual_size_after = -1
ref_size_after = -1
filestat path actual_size_after
actual_stat_after = result
filestat ref ref_size_after
ref_stat_after = result
if actual_stat_after = 0 then
    if ref_stat_after = 0 then
        if actual_size_after = required_size then
            if ref_size_after = required_size then
                goto compare_size_stable
            endif
        endif
    endif
endif
equal = 0
:compare_size_stable
if equal = 0 then
    good = 0
endif
return
""")
    # Reuse the previously audited NUL-safe read helpers, not a guessed parser.
    _,sep,tail=prior_probe().partition('\n:read_byte\n')
    if not sep:raise ValueError('audited read helpers missing')
    tail=tail.replace('uv = 0\nfileopen uf ufile 0', '''uv = 0
usize = -1
filestat ufile usize
if result = 0 then
    if uoff >= 0 then
        if usize > uoff then
            goto byte_present
        endif
    endif
endif
return
:byte_present
fileopen uf ufile 0''',1)
    emit(':read_byte\n'+tail)
    result='\n'.join(lines)+'\n'
    # Reference filenames stay XR*.REF; only per-run outputs are renamed.
    result=result.replace("'C:\\XR'",f"'C:\\{prefix}'")
    result=result.replace("'C:\\XRTRY.TXT'",f"'C:\\{prefix}TRY.TXT'")
    return result


def references(raw):
    refs={tag+'.REF':raw[file_offset(address):file_offset(address)+size]
          for tag,address,size in REFERENCE_RANGES}
    for name,(_,handler) in COMMANDS.items():
        tag={'SYS_md':'XRMDROW','SYS_reg':'XRRGROW','SYS_buildinfo':'XRBIROW'}[name]
        refs[tag+'.REF']=struct.pack('<I',handler)+name.encode()+b'\0'
    return refs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sample',type=Path);p.add_argument('command_table',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--arm-ram-probe',action='store_true')
    p.add_argument('--output-prefix',default='XR')
    args=p.parse_args();raw=args.sample.read_bytes()
    report=audit(raw,args.command_table.read_bytes())
    args.output.mkdir(parents=True,exist_ok=False)
    files={**references(raw),**controls()}
    files['startup.ttl']=build(args.arm_ram_probe,prefix=args.output_prefix).encode('ascii')
    files['recovery.ttl']=build(False,True,prefix=args.output_prefix).encode('ascii')
    for name,data in files.items():
        with (args.output/name).open('xb') as f:f.write(data)
    report.update(armed=args.arm_ram_probe,output_prefix=args.output_prefix,files={name:{'bytes':len(data),
        'sha256':hashlib.sha256(data).hexdigest()} for name,data in files.items()},
        no_camera_access=True,reference_bytes_are_private_firmware_derivatives=True)
    (args.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(args.output),'armed':args.arm_ram_probe,
                      'temporary_RAM_write_bytes':4 if args.arm_ram_probe else 0,
                      'new_code_executed':False,'camera_installable_XPAN':False,
                      'SD_deployed':False},indent=2))


if __name__=='__main__':main()
