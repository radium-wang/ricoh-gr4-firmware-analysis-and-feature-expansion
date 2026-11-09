#!/usr/bin/env python3
# License: see LICENSE.
"""Bounded original ARM focus checks using synthetic RAM and intercepted services.

No sensor, motor, display, real task scheduling, camera or firmware writes.
"""

import argparse
import json
from pathlib import Path
import struct

from audit_gr4_focus import audit
from audit_xpan_paths import file_offset


def check(raw):
    static = audit(raw)
    from check_gr4_native_memory_abi import check_host_cache_access
    check_host_cache_access()
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                                   UC_ARM_REG_R3, UC_ARM_REG_PC, UC_ARM_REG_SP, UC_ARM_REG_LR)
    uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    uc.mem_map(0x53000000, 0x1400000)
    uc.mem_write(0x53000000, raw[file_offset(0x53000000):file_offset(0x54400000)])
    uc.mem_map(0x61000000, 0x20000)
    obj, userdata, stack, stop = 0x61001000, 0x61003000, 0x6101e000, 0x6101f000
    regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
    spans, services, events, cases = [], {}, [], []

    def get(index):
        return uc.reg_read(regs[index])

    def intercept(machine, address, _size, _context):
        if address in services:
            value = services[address]()
            if value is not None:
                machine.reg_write(UC_ARM_REG_R0, value)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
        elif not any(lo <= address < hi for lo, hi in spans):
            raise AssertionError(f"unexpected instruction at {address:#x}")

    uc.hook_add(UC_HOOK_CODE, intercept)

    def diagnostic():
        events.append("diagnostic")
        return 0

    def notification():
        events.append(["simulated_event_flag", get(0), get(1)])
        return 0

    def run(entry, arguments, allowed, stubs=None, extra_stack=()):
        events.clear()
        spans[:] = allowed
        services.clear()
        services.update(stubs or {})
        for index, value in enumerate((*arguments, 0, 0, 0, 0)[:4]):
            uc.reg_write(regs[index], value & 0xffffffff)
        uc.reg_write(UC_ARM_REG_SP, stack)
        uc.reg_write(UC_ARM_REG_LR, stop)
        if extra_stack:
            uc.mem_write(stack, struct.pack("<" + "I" * len(extra_stack), *extra_stack))
        uc.emu_start(entry, stop, timeout=1000000, count=100000)
        if uc.reg_read(UC_ARM_REG_PC) != stop:
            raise AssertionError("native function did not return within instruction budget")
        return get(0)

    def reset():
        uc.mem_write(obj, bytes(0x2000))

    def put(offset, value):
        uc.mem_write(obj + offset, struct.pack("<I", value & 0xffffffff))

    def read(offset):
        return struct.unpack("<I", uc.mem_read(obj + offset, 4))[0]

    def require(condition, label):
        if not condition:
            raise AssertionError(label)

    def record(group, **values):
        cases.append(dict(group=group, **values))

    common = (1, 1, 2, 4, 1, 3, 2, 2, 4, 0, 0, 0, 1, 1, 1, 1)
    remote = (0, 2, 2, 2, 3, 4, 5, 9, 9, 6, 7, 8, 0, 0, 10, 1)
    for focus_id in (*range(16), 255):
        invalid = focus_id in (12, 13, 255)
        result = run(0x5329d35c, (focus_id,), [(0x5329d35c, 0x5329d42c)],
                     {0x538ed930: diagnostic})
        require(result == (common[focus_id] if focus_id < 16 else 1)
                and bool(events) == invalid, "common focus mode conversion")
        record("common_mode", focus_id=focus_id, result=result, diagnostic=invalid)
        result = run(0x5337c46c, (obj, focus_id), [(0x5337c46c, 0x5337c554)],
                     {0x538ed930: diagnostic})
        require(result == (remote[focus_id] if focus_id < 16 else 0)
                and bool(events) == invalid, "remote focus mode conversion")
        record("remote_mode", focus_id=focus_id, result=result, diagnostic=invalid)

    for process_id in (0, 1, 2, 3, 4, 5, 255):
        reset()
        pointers = {0x58: 0x61006000, 0x60: 0x61008000, 0x5c: 0x61007000}
        for offset, pointer in pointers.items():
            put(offset, pointer)
        result = run(0x535e4000, (obj, process_id), [(0x535e4000, 0x535e4094)],
                     {0x538ec838: diagnostic})
        offset = {1: 0x58, 2: 0x58, 3: 0x60, 4: 0x5c}.get(process_id, 0x58)
        require(result == pointers[offset] and bool(events) == (process_id not in (1, 2, 3, 4)),
                "process selection")
        record("process_selector", process_id=process_id, selected_offset=hex(offset))

    for common_mode in range(5):
        for request in (0, 1, 5, 6):
            reset()
            put(0x78, 99)
            result = run(0x535e4094, (obj, request), [(0x535e4094, 0x535e4150)],
                         {0x535e9d20: lambda: common_mode})
            expected = request if request in (5, 6) else (
                0 if request == 0 else {1: 1, 2: 2, 3: 2, 4: 4}.get(common_mode, 0))
            require(read(0x7c) == 99 and read(0x78) == expected and not events,
                    "arbitrate mode selection")
            record("arbitrate_mode", common_mode=common_mode, request=request, selected=expected)

    for active in (0, 2, 3, 4):
        for pending in (0, 3):
            for requested in (2, 3, 4):
                reset()
                put(0x84, active)
                put(0x88, pending)
                accepted = active == pending == 0
                result = run(0x535e4264, (obj, requested), [(0x535e4264, 0x535e42a8)],
                             {0x538db424: notification})
                require(result == int(accepted) and read(0x84) == active
                        and read(0x88) == (requested if accepted else pending)
                        and events == ([["simulated_event_flag", obj + 0x24, 2]] if accepted else []),
                        "busy process switch guard")
                record("process_switch_guard", active=active, pending=pending,
                       requested=requested, accepted=accepted)

    def distance_request():
        events.append(["simulated_distance_request", get(1), get(2)])
        return None

    snap_cases = [(0, 10, cm) for cm in (30, 40, 100, 150, 200, 250, 350, 500, 0xffffffff, 50)]
    snap_cases += [(0, 11, 50), (0, 9, 100), (1, 10, 100)]
    for movie, focus_id, cm in snap_cases:
        result = run(0x5339dbc8, (obj, 0), [(0x5339dbc8, 0x5339dd10)], {
            0x5323ea84: lambda: userdata, 0x5323f018: lambda: userdata,
            0x5339da34: lambda: cm, 0x532975f0: lambda: movie,
            0x53297618: lambda: focus_id, 0x5339d3b0: distance_request,
            0x538ed930: diagnostic,
        })
        valid = not movie and (focus_id == 11 or (focus_id == 10 and cm != 50))
        expected = 0xffffffff if focus_id == 11 or cm == 0xffffffff else cm * 10
        wanted = [["simulated_distance_request", expected, 0]] if valid else (
            ["diagnostic"] if not movie and focus_id == 10 else [])
        require(result == int(valid) and events == wanted, "Snap/Infinity distance conversion")
        record("snap_distance", movie=movie, focus_id=focus_id, cm=cm,
               request_mm=expected if valid else None)

    for focus_id, aspect in [(f, a) for f in range(16) for a in range(4)] + [(0, 4), (14, 4), (9, 4), (4, 4)]:
        reset()
        result = run(0x5339e894, (obj, obj + 0x100, focus_id),
                     [(0x5339e894, 0x5339ea7c), (0x538ea14c, 0x538ea190)], {
                         0x5323ea84: lambda: userdata, 0x5323f018: lambda: userdata,
                         0x53298ea0: lambda: aspect, 0x538ed930: diagnostic,
                     })
        invalid = focus_id in (12, 13) or (aspect == 4 and focus_id in (0, 14))
        if invalid:
            expected = (0, 0)
        elif focus_id == 0:
            expected = (480 if aspect == 3 else 560, 360)
        elif focus_id in (14, 15):
            expected = (288 if aspect == 3 else 336, 216)
        elif focus_id in (9, 10, 11):
            expected = (0, 0)
        elif focus_id in (7, 8):
            expected = (590, 380)
        elif focus_id == 4:
            expected = (32, 32)
        else:
            expected = (64, 52)
        actual = tuple(struct.unpack("<2I", uc.mem_read(obj, 8)))
        require(result == obj and actual == expected and bool(events) == invalid,
                f"FocusModel area focus={focus_id} aspect={aspect}: got {actual}, "
                f"expected {expected}; return={result:#x}; events={events}")
        record("focus_area_size", focus_id=focus_id, aspect=aspect,
               size=list(actual), diagnostic=invalid)

    for owner in (0, 2, 3, 4):
        for requester in (1, 2, 3, 4):
            reset()
            put(0x14, owner)
            result = run(0x535e900c, (obj, requester), [(0x535e900c, 0x535e902c)])
            require(result == int(owner == 0 or owner == requester)
                    and read(0x14) == (requester if owner == 0 else owner), "lens ownership")
            record("lens_ownership", owner=owner, requester=requester, accepted=bool(result))

    for busy in (0, 1, 255):
        reset()
        uc.mem_write(obj + 0xcc, bytes([busy]))
        before = bytes(uc.mem_read(obj, 0x100))
        result = run(0x539290fc, (obj, 0x12, 0x8900, 0x3456),
                     [(0x539290fc, 0x53929160)], {0x538db424: notification},
                     (0xaabbccdd, 0x11223344))
        if busy:
            require(result == 1 and bytes(uc.mem_read(obj, 0x100)) == before and not events,
                    "busy lens queue must remain unchanged")
        else:
            require(result == 0 and bytes(uc.mem_read(obj + 0xcc, 1)) == b"\1"
                    and read(0xd0) == 0 and bytes(uc.mem_read(obj + 0xd4, 1)) == b"\x12"
                    and struct.unpack("<H", uc.mem_read(obj + 0xd6, 2))[0] == 0x8900
                    and read(0xd8) == 0x3456 and read(0xdc) == 0xaabbccdd
                    and read(0xe0) == 0x11223344
                    and bytes(uc.mem_read(obj + 0xe4, 1)) == b"\1"
                    and events == [["simulated_event_flag", obj + 0x4c, 1]], "lens request queue")
        record("lens_queue", busy=busy, return_value=result)

    # Original ZAF block selectors, record accessors and result rejection logic.
    # The correlation/predictor sequence itself remains intercepted.
    accessor, config, records, sequence = 0x61006000, 0x61007000, 0x61008000, 0x6100e000

    def zaf_reset(count=1, variant=2, selected=True):
        reset()
        uc.mem_write(accessor, bytes(0x300))
        uc.mem_write(config, bytes(0x100))
        uc.mem_write(records, bytes(0x80 * 165))
        put(8, accessor)
        put(0xc, config)
        put(0x10, sequence)
        uc.mem_write(obj + 0x14, bytes([variant, 0]))
        uc.mem_write(accessor + 0x298, bytes([variant]))
        uc.mem_write(config + 0x11, bytes([int(selected)]))
        uc.mem_write(config + 0x54, struct.pack("<I", count))
        uc.mem_write(accessor + 4, struct.pack("<165I", *(records + i * 0x80 for i in range(165))))

    def zaf_input(index, start=10, length=10, enabled=1, predictor=0, predictor_ok=1,
                  saturated=0, fake_bottom=0, repeated=0, reliability=10):
        address = records + index * 0x80
        uc.mem_write(address + 0x10, struct.pack("<hH", start, length))
        uc.mem_write(address + 0x24, bytes([enabled]))
        uc.mem_write(address + 0x2e, struct.pack("<H", reliability))
        uc.mem_write(address + 0x3d, bytes([predictor_ok]))
        uc.mem_write(address + 0x3e, struct.pack("<h", predictor))
        uc.mem_write(address + 0x44, bytes([repeated, fake_bottom, saturated]))
        return address

    selector_spans = [(0x53616704, 0x53616868), (0x5361518c, 0x53615358),
                      (0x5361562c, 0x53615684)]
    for variant, width in ((0, 251), (1, 251), (2, 453), (3, 453)):
        for start, length in ((-1, 10), (0, 1), (0, width), (0, width + 1),
                              (width - 1, 1), (width - 1, 2), (width, 1), (11, 22)):
            zaf_reset(variant=variant)
            address = zaf_input(0, start=start, length=length, enabled=9)
            run(0x53616850, (obj,), selector_spans, {0x538ed930: diagnostic})
            accepted = start >= 0 and start + length - 1 < width
            actual = bytes(uc.mem_read(address + 0x24, 1))[0]
            require(actual == int(accepted) and not events, "ZAF select block bounds")
            if accepted:
                offset = min(11, start, width - start - length)
                windows = struct.unpack("<6H", uc.mem_read(address + 4, 12))
                require(windows == (length + 2 * offset,) * 3 + (offset,) * 3,
                        "ZAF native correlation margins")
            record("zaf_block_bounds", variant=variant, width=width, start=start,
                   length=length, accepted=accepted)

    for count, selected in ((0, True), (165, True), (166, True), (165, False)):
        zaf_reset(count=count, selected=selected)
        for index in range(165):
            zaf_input(index, enabled=9)
        run(0x53616850, (obj,), selector_spans, {0x538ed930: diagnostic})
        actual = [bytes(uc.mem_read(records + index * 0x80 + 0x24, 1))[0] for index in range(165)]
        require(actual == ([1] * 165 if count == 165 else [9] * 165)
                and bool(events) == (count == 166), "ZAF block count bound")
        record("zaf_block_count", count=count, selected_mode=selected, diagnostic=bool(events))

    def operation_sequence():
        events.append(["simulated_zaf_sequence", get(1), get(2), get(3)])
        return 0

    getters = [(0x53615684, 0x536156b0), (0x53615be8, 0x53615c14),
               (0x53615c94, 0x53615cc0), (0x53615f44, 0x53615f70),
               (0x53615e98, 0x53615ec4), (0x53615dec, 0x53615e18)]
    result_spans = [(0x53616c94, 0x53616dd0), (0x53155f6c, 0x53155f78), *getters]
    scenarios = [("predictor_boundary", dict(predictor=p)) for p in (-513, -512, 0, 512, 513)]
    scenarios += [("disabled", dict(enabled=0)), ("predictor_invalid", dict(predictor_ok=0)),
                  ("saturation", dict(saturated=1)), ("suspected_false_bottom", dict(fake_bottom=1)),
                  ("repeated_texture", dict(repeated=1))]
    for index in (0, 164):
        for label, values in scenarios:
            zaf_reset()
            zaf_input(index, **values)
            run(0x53616c94, (obj,), result_spans, {0x53618a84: operation_sequence})
            enabled = values.get("enabled", 1)
            accepted = bool(enabled and values.get("predictor_ok", 1)
                            and abs(values.get("predictor", 0)) <= 512
                            and not any(values.get(k, 0) for k in ("saturated", "fake_bottom", "repeated")))
            expected = ([["simulated_zaf_sequence", index, 0, 0]] if enabled else [])
            if accepted:
                expected.append(["simulated_zaf_sequence", index, 0, 2])
            require(events == expected, "ZAF predictor/saturation/repetition rejection")
            record("zaf_result_filter", index=index, scenario=label, accepted=accepted)

    for value, predictor_ok, repeated in ((254, 1, 0), (255, 1, 0), (256, 1, 0),
                                         (10, 0, 0), (10, 1, 1)):
        zaf_reset()
        address = zaf_input(0, reliability=value, predictor_ok=predictor_ok, repeated=repeated)
        run(0x53616e48, (obj,), [(0x53616e48, 0x53616ed8),
                                (0x53615a90, 0x53615abc), *getters])
        actual = struct.unpack("<H", uc.mem_read(address + 0x2e, 2))[0]
        expected = value if value <= 255 and predictor_ok and not repeated else 255
        require(actual == expected and not events, "ZAF reliability field invalidation")
        record("zaf_reliability_field", input=value, predictor_ok=predictor_ok,
               repeated=repeated, output=actual)

    return {"schema": "gr4-focus-arm-checks-v2", "sample_sha256": static["sample_sha256"],
            "cases_passed": len(cases), "cases": cases,
            "execution": "bounded original ARM instructions and native size helpers; synthetic RAM",
            "intercepted_services": ["property getters", "Snap distance request", "diagnostics",
                                     "RTOS event flags", "ZAF correlation/predictor sequence"],
            "camera_accessed": False, "firmware_modified": False,
            "limits": ["No complete CAF/ZAF algorithm execution or actual task dispatch.",
                       "No autofocus timing, sensor statistics, calibrated distance or lens motion measurements.",
                       "Area sizes validate the model coordinate calculation, not LCD/sensor pixel alignment."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    parser.add_argument("--output", type=Path, help="new JSON file, never overwrites")
    args = parser.parse_args()
    try:
        result = check(args.sample.read_bytes())
        rendered = json.dumps(result, indent=2) + "\n"
        if args.output:
            with args.output.open("x") as stream:
                stream.write(rendered)
            print(f"Saved {result['cases_passed']} native ARM checks to {args.output}")
        else:
            print(rendered, end="")
    except (OSError, ValueError, RuntimeError, AssertionError, ImportError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
