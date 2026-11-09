#!/usr/bin/env python3
"""One bounded GetData batch: script task, saved context, MMU and aspect menu.

No SetData, native calls, settings changes, SD writes or firmware updates.
Dynamic pointers are followed only through pinned RTOS registries and classes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import usb.core
import usb.util

from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from mtp_factory_getvalue_readonly import EXPECTED_OPERATIONS, operations_from_device_info
from mtp_factory_pointer_trial import Transport
from mtp_factory_script_context_readonly import collect as script_context
from mtp_probe_readonly import VID, PID, command

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = 0x553A0030
SCRIPT_VTABLE = 0x53FE5880
SCRIPT_NAME = 0x53D7C12C
TCB_TABLE = 0x55824CE0
TASK_LIMIT = 0x55824C74
CURRENT_TCBS = 0x55824C7C
STRIDE = 0x500
TARGET_SECTIONS = (0x531, 0x53D, 0x55A, 0x596, 0x5A0, 0x5A1)


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported firmware sample')
    pins = {
        0x538E1FB8: '304000e33a4545e3',  # thread registry
        0x538E2080: '085094e5',          # node+8 -> thread object
        0x538F0588: '1c219fe5',          # script constructor vtable literal
        0x538F06AC: '8058fe53',
        0x53FE5880: '18058f5340058f53240c8f5300000000',
        0x538F05C0: '4b00a0e3',          # original task configuration index
        0x53FE1F44: '2cc1d7535050001807000000ecbafc53',
        0x538E2F70: '049084e5',          # object+4 task ID
        0x53082EF4: '743c04e3823545e3',  # maximum task index
        0x53082F88: 'e02c04e3',          # TCB table root
        0x53082F94: '053ca0e3930603e0',  # stride 0x500 * low16(ID)
        0x53082FA0: '053c43e2036086e0',  # minus one stride
        0x53086C78: 'bc d0 98 e5 00 00 a0 e3 c0 10 98 e5',
        0x53086C8C: '9a0f07ee101f02eec41098e5301f0dee',
        0x53086CB4: '3cd08de201002de9',
        0x53086CD8: '0040bde803c01ce24a02001a0010bde8',
        0x53086CE8: '0cf06fe10090fde8',  # saved SPSR, exception return
        0x53004000 + 0x570*4: '264c0157',  # identity-mapped RTOS task arena
        0x53004000 + 0x57F*4: '264cf157',
        0x5306AEEC: '141096e55334e1e7b82096e5000053e3087096e51f00a0131300a003010011e30110c1e320008013041002e5',
    }
    for address, expected in pins.items():
        require(raw, file_offset(address), bytes.fromhex(expected), hex(address))
    name = raw[file_offset(SCRIPT_NAME):file_offset(SCRIPT_NAME) + 64].split(b'\0')[0]
    return {'sample_sha256': EXPECTED_SHA256, 'pins': len(pins),
            'script_name_hex': name.hex(), 'script_name': name.decode('ascii'),
            'task_specific_ttbr_field': 'TCB+0xc0',
            'zero_ttbr_means': 'scheduler leaves the previous TTBR unchanged',
            'operation': 'offline byte audit only'}


def ram(address, length):
    if address % 4 or length < 1 or not any(lo <= address and address + length <= hi
            for lo, hi in ((0x55000000, 0x56000000), (0x59000000, 0x5C000000))):
        raise ValueError(f'invalid bounded RAM pointer: {address:#x}/{length}')
    return address


def kernel_ram(address, length):
    # The original kernel TCB pool and task stacks reside in a different
    # identity-mapped arena from the application heap. Never use this for writes.
    if address % 4 or length < 1 or not 0x57000000 <= address < address + length <= 0x58000000:
        raise ValueError(f'invalid kernel task arena pointer: {address:#x}/{length}')
    return address


def collect(read, raw, reads=None):
    evidence = audit(raw)
    if reads is None:
        reads = []
    def checked(address, size):
        data = read(address, size)
        if len(data) != size:
            raise ValueError('short GetData')
        reads.append({'address': hex(address), 'length': size, 'hex': data.hex()})
        return data
    def word(address):
        return struct.unpack('<I', checked(address, 4))[0]

    before = checked(0x55085D63, 5)
    slot = checked(REGISTRY, 4)
    registry = struct.unpack('<I', slot)[0]
    header = checked(ram(registry, 32), 32)
    buckets, bucket_count, head, count = struct.unpack_from('<4I', header)
    ram(buckets, 4)
    if not 1 <= bucket_count <= 1024 or not 1 <= count <= 512:
        raise ValueError('unexpected bounded thread registry size')
    node = head
    seen = set()
    objects = []
    candidates = []
    while node:
        if node in seen or len(seen) >= count:
            raise ValueError('thread list cycle or count mismatch')
        seen.add(node)
        entry = checked(ram(node, 12), 12)
        next_node, task_id, obj = struct.unpack('<3I', entry)
        obj_head = checked(ram(obj, 12), 12)
        vtable, obj_id, name = struct.unpack('<3I', obj_head)
        if obj_id != task_id:
            raise ValueError('thread registry key and object ID disagree')
        objects.append({'node': hex(node), 'object': hex(obj),
                        'id': hex(task_id), 'vtable': hex(vtable), 'name_pointer': hex(name)})
        if vtable == SCRIPT_VTABLE:
            if name != SCRIPT_NAME:
                raise ValueError('script class name does not match pinned task configuration')
            candidates.append((obj, task_id))
        node = next_node
    if len(candidates) != 1:
        raise ValueError('expected exactly one original script task')
    obj, task_id = candidates[0]
    script = checked(obj, 0xB4)
    if struct.unpack_from('<3I', script) != (SCRIPT_VTABLE, task_id, SCRIPT_NAME):
        raise ValueError('script object changed')
    if checked(SCRIPT_VTABLE, 16) != raw[file_offset(SCRIPT_VTABLE):file_offset(SCRIPT_VTABLE)+16]:
        raise ValueError('runtime script vtable mismatch')
    name_len = len(bytes.fromhex(evidence['script_name_hex'])) + 1
    if checked(SCRIPT_NAME, name_len) != raw[file_offset(SCRIPT_NAME):file_offset(SCRIPT_NAME)+name_len]:
        raise ValueError('runtime task name mismatch')
    table_slot = checked(TCB_TABLE, 4)
    table = struct.unpack('<I', table_slot)[0]
    maximum = word(TASK_LIMIT)
    index = task_id & 0xFFFF
    if not 1 <= index <= maximum <= 1024:
        raise ValueError('task ID outside kernel table')
    kernel_ram(table, maximum*STRIDE)
    tcb_address = kernel_ram(table + (index-1)*STRIDE, 0xD0)
    tcb = checked(tcb_address, 0xD0)
    if struct.unpack_from('<I', tcb, 8)[0] != task_id:
        raise ValueError('kernel TCB ID does not match script registry')
    exinf, attributes, entry = struct.unpack_from('<3I', tcb, 0xC)
    if exinf != obj or attributes != 0x21003 or entry != 0x538E1F70:
        raise ValueError('script kernel configuration differs from audited constructor')
    initial_mode = 0x13 if attributes & 0x300 == 0 else 0x1F
    saved_sp, ttbr, context_id = struct.unpack_from('<3I', tcb, 0xBC)
    frame = checked(kernel_ram(saved_sp + 0x3C, 20), 20)
    saved_lr, cpsr, saved_ip, pc, extra = struct.unpack('<5I', frame)
    mode = cpsr & 31
    if mode not in (0x10, 0x13, 0x1F) or not 0x53000000 <= pc < 0x54400000:
        raise ValueError('saved exception frame does not match audited scheduler layout')
    current = checked(CURRENT_TCBS, 16)
    current_tasks = []
    for address in struct.unpack('<4I', current):
        if address == 0:
            current_tasks.append(None)
            continue
        if address < table or address >= table + maximum*STRIDE or (address-table) % STRIDE:
            raise ValueError('current TCB is outside original task pool')
        state = checked(kernel_ram(address, 0xC8), 0xC8)
        current_tasks.append({'tcb': hex(address), 'id': hex(struct.unpack_from('<I', state, 8)[0]),
                              'ttbr': hex(struct.unpack_from('<I', state, 0xC0)[0]),
                              'context_id': hex(struct.unpack_from('<I', state, 0xC4)[0])})
    tables = {0x53004000}
    for value in [ttbr] + [int(x['ttbr'], 16) for x in current_tasks if x]:
        if not value:
            continue
        base = value & 0xFFFFC000
        if base != 0x53004000:
            if 0x57000000 <= base < 0x58000000:
                kernel_ram(base, 0x4000)
            else:
                ram(base, 0x4000)
        tables.add(base)
    mappings = {}
    for base in sorted(tables):
        entries = []
        for section in TARGET_SECTIONS:
            descriptor = word(base + section*4)
            kind = descriptor & 3
            entries.append({'virtual': hex(section << 20), 'descriptor': hex(descriptor),
                            'kind': kind, 'physical': hex(descriptor & 0xFFF00000) if kind == 2 else None,
                            'ap': ((descriptor >> 10) & 3) | ((descriptor >> 13) & 4) if kind == 2 else None,
                            'xn': bool(descriptor & 16) if kind == 2 else None})
        mappings[hex(base)] = entries
    descriptor = checked(0x53D9F8E0, 0x5C)
    if descriptor != raw[file_offset(0x53D9F8E0):file_offset(0x53D9F8E0)+0x5C]:
        raise ValueError('live aspect descriptor differs from pinned firmware')
    if checked(REGISTRY, 4) != slot or checked(registry, 16) != header[:16] or checked(TCB_TABLE, 4) != table_slot:
        raise ValueError('task registry generation changed during batch')
    after = checked(0x55085D63, 5)
    return {'schema': 'gr4-task-mapping-readonly-v1', 'offline_audit': evidence,
            'registry_object': hex(registry), 'threads_observed': objects,
            'script_object': hex(obj), 'script_id': hex(task_id), 'script_tcb': hex(tcb_address),
            'script_ttbr_field': hex(ttbr), 'script_context_id': hex(context_id),
            'script_attributes': hex(attributes), 'script_initial_mode': hex(initial_mode),
            'saved_cpsr': hex(cpsr), 'saved_mode': hex(mode), 'saved_pc': hex(pc),
            'script_active_flag': script[0xB0], 'current_tasks': current_tasks,
            'translation_tables': mappings, 'aspect_descriptor_matches': True,
            'script_context': script_context(checked), 'reads': reads,
            'capture_properties_unchanged': before == after, 'camera_memory_written': False,
            'native_functions_called': False, 'xpan_installed': False,
            'limits': ['TCB TTBR zero leaves inherited active TTBR unresolved.',
                       'Saved task state is a read-only snapshot and may change while scheduling.',
                       'Section descriptors do not resolve coarse/fine page tables.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError('report already exists')
    raw = (ROOT / 'samples/gr4_decoded.bin').read_bytes()
    audit(raw)
    if args.offline:
        result = audit(raw)
    else:
        device = usb.core.find(idVendor=VID, idProduct=PID)
        if device is None or device.bcdDevice != 0x0111:
            raise RuntimeError('expected connected GR IV 01.11.10.07')
        usb.util.claim_interface(device, 0)
        io = Transport(device)
        opened = False
        reads = []
        try:
            response, info, _ = command(device, 0x1001, 0)
            if response != 0x2001 or info is None or operations_from_device_info(info) != EXPECTED_OPERATIONS:
                raise RuntimeError('unexpected MTP device information')
            response, _, _ = command(device, 0x1002, 1, 1)
            opened = response == 0x2001
            if response not in (0x2001, 0x201E):
                raise RuntimeError('OpenSession failed')
            result = collect(io.read, raw, reads)
        except Exception as error:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps({'schema': 'gr4-task-mapping-readonly-v1',
                'error': str(error), 'reads': reads, 'camera_memory_written': False,
                'native_functions_called': False}, indent=2) + '\n')
            raise
        finally:
            try:
                if opened:
                    command(device, 0x1003, io.transaction)
            finally:
                usb.util.release_interface(device, 0)
                usb.util.dispose_resources(device)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('reads', 'threads_observed')}, indent=2))


if __name__ == '__main__':
    main()
