#!/usr/bin/env python3
# License: see LICENSE.
"""Audit pinned GR IV focus paths offline; no device access or patch output."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from audit_xpan_paths import EXPECTED_SHA256, file_offset


# Filled from the independently inspected 1.11.10.7 decoded sample.
PINS = (
    ('user_focus_parser', 0x533f10dc, 0x324, '832a33d02120a3b21340ed6e2a89ee1561a1e2bd64ef5837b38e8315d0793308'),
    ('common_focus_mode', 0x5329d35c, 0xd0, '758365eb89900302c7b7daa54b2da45dd1bb33bb1ea631e1ca0a190e829759c3'),
    ('remote_focus_mode', 0x5337c46c, 0xe8, '5ee17f2458785ed0716a74a73005450e5fbf75114b66ef997c9dd9fb001e3856'),
    ('arbitrate_initialize', 0x535e3b70, 0x15c, 'ca6b591ab473c40429a801e5eaee6a42d921b2cfa8ba9e2d97f0db4103e12c60'),
    ('process_selector', 0x535e4000, 0x94, 'f09103ed99621c5b050652d52e94baea07ba44c485ed6a76c2c220667894ce53'),
    ('arbitrate_mode_selector', 0x535e4094, 0xbc, 'f188e520e0e5409b65fd514fe61af896a8268f7c5cd07201d1157adcc6d8c74d'),
    ('start_dispatch', 0x535e4598, 0x29c, 'e9dfe90bd33d33ee3728e17693928643948df07441cdfa06d83c3c14dceb8a32'),
    ('process_switch_guard', 0x535e4264, 0x44, '74e2e9266584b147763064d5db80aaac99458d578b6d8f6a08ef8b56371481cf'),
    ('process_control_requests', 0x535e5238, 0x128, '74dd5f8b4ed171c9c8626b2711fe0e3e07362a6d06161b11d56d0292fc142e1e'),
    ('hybrid_initialize', 0x535ecc58, 0x88, 'ad930b540c3bc199609f00a1c2c620b68bb61fd16365877793682c3d76cfa9a4'),
    ('hybrid_forwarders', 0x535ecd58, 0x58, 'b3c85a8b5086f8dd650cf03b93bf1915e9cd2ee24eefcfe737c196dbf3f863f8'),
    ('zaf_enable_request', 0x53619bb4, 0x1c, '1e0df38fc3da7317c7028cc0f1e437b28028898be508bb54e76918c854121db6'),
    ('zaf_start_request', 0x5361a678, 0x3c, '0dff04aae958a6a0e58a723136dd35d6dbcfd8d561ba7a62d3d87fd27afd5aa7'),
    ('zaf_snapshot_methods', 0x53612d84, 0x1a0, '1ed40ce8628a235c7576b09e36af5e611256f4a022d2e12e7b9d0bb57212d04a'),
    ('caf_zaf_start_call', 0x535fd6d8, 0x84, 'd767eb205b8ffa416d8e1a71322c5e1f8c2128ff9d323ccbea1f2b9a24009b84'),
    ('caf_zaf_toggle_calls', 0x535fd310, 0x18, '1b50c8cbc2f500c819f7a26aef83054577791873a81e61086d5f711dce65d650'),
    ('caf_zaf_result_transition', 0x53601978, 0x9c, '64f6e16ead30ff10218c7d5c6b5395a093a3dfc419b025f8b441ecb25f42b45c'),
    ('af_other_snapshot_select', 0x535eade8, 0x44, '77871eb75ada511647d0119e2eebff73c91f07d78b52b3e5d31fa267f6ef9b68'),
    ('snap_distance_apply', 0x5339dbc8, 0x148, '4d76e1befb0012f8bc2767851f3d90cccc5dec456b1481ab906bbc764b161d79'),
    ('focus_area_size', 0x5339e894, 0x1e8, '39a5d3193ba32ceaa73c690db695eedaa096fa828128fb01021f1c5d407ab98e'),
    ('focus_area_publish', 0x5339ee20, 0x210, 'b4a3196976b9fda296f4ff16164a957d135664a35d64fef280648282c7ec51a4'),
    ('native_size_helpers', 0x538ea14c, 0x44, 'c2b1527e82444920e2670644ec7a65186f02dae2b335e267fc14c7e8e7ef6b6c'),
    ('af_lens_initialize', 0x535e8ef0, 0xe0, '1dc39403271a644c73daaf0893dc2c4d32a34e551a19cb98a0cf1a37f5c342ab'),
    ('lens_owner_and_drive_guard', 0x535e900c, 0x8c, '93d569b2f6716bc393cf6c088507f1eeab69bde478045fceb9edda069567f910'),
    ('lens_command_queue', 0x539290fc, 0x64, '96c7b931d1fca853b82530dd9bca1a8142e22bd59dbd6aea3160895d85e8e6e9'),
    ('lens_temperature_coefficients', 0x5392d11c, 0xb4, '5c4d130c89de483c45e2c443dcf08546423e214afe9aed951b12aa426900c6f3'),
    ('zaf_project_selector', 0x5361130c, 0x28, '5e10dcb75c42118b507b475faaa23959f8d06fb5e74b499c5b8df5ccf4ecd569'),
    ('zaf_project_table', 0x53eab62c, 0x7, '4a8d086cd1c1d664cf0e43b077fe0ce2b1547f0dd1b65f354f1ea09e00acfee5'),
    ('af_debug_data_handler', 0x53022730, 0x120, 'c8af7013d2d5ff1621990ff547705877ebddc859c1005ac91b7f9b9a93d9e075'),
    ('af_error_retry_handler', 0x53022850, 0xb4, '1172863ce14599f67fc19b8e8c236ed2b8e9a826b0e14729ee02dd36fe97606a'),
    ('af_error_retry_consumer', 0x535e5d00, 0x48, '277e551e3e1782af75f0117f0188cfef031a6a65a3a90c3ab43932ad8a67bfc7'),
    ('af_range_parser', 0x533f294c, 0xb4, 'cbf8e108e77a5f6e050609db1656e7423211ecccc681fffff9a50d1b2b0e493f'),
    ('focus_limiter_parser', 0x533f2814, 0xb4, '31745c825025e0591d73a7d28c2cf7402c64e5e53f3eca441691618cbc0a9da8'),
    ('capture_zaf_initialize', 0x5385ed68, 0x110, 'd9d4814f87c561faf8075d28fdb1fbcf3cd26b4730719eefac2b851587c9682e'),
    ('caf_buffer_partition', 0x535eee88, 0x1e8, '9b5f6b2e36ba2ea921c7792b024c19158e3becd303e12541021904ceb082c58f'),
    ('zaf_process_initialize', 0x536196b0, 0x1a4, 'c4f78e95c3830ba0314789b7317955daef5e2768cc428e07437b8ea4b778ad8b'),
    ('standard_project_configuration', 0x53fe50d0, 0x18, '72e8b52e4a5e73414a94b8846c2d8fb92448f1e46c873d75c3e15354f38ec3c7'),
    ('zaf_algorithm_select', 0x53616704, 0x164, 'ad830cad2b19579ae85dff322b1e3b5180baff81c2c6449fee632b345e732453'),
    ('zaf_algorithm_candidate_filter', 0x53616c94, 0x13c, '130fc2741646d2788d402bef72d4fe22aacb1485c54a557c34b067cade2ab29f'),
    ('zaf_reliability_invalidation', 0x53616e48, 0x90, 'b029e016d12d2cfbfc755ac5abe1ef88b34afcd0131a5b14221de9b503355080'),
    ('zaf_record_accessors', 0x536150a4, 0x638, 'b8eabc3478fac03229db491d96503e07b8cc1ec39a80d73cacd2c42f14a2164f'),
    ('zaf_result_accessors', 0x53615a90, 0x4fc, 'ec7da0797c0f3e2ff1d1b2ae928210a71216b8ece0cb64a781eea2aa733ba327'),
    ('zaf_processing_tables', 0x53eab4f8, 0x34, 'c84159dff20dde35faa54eb90ea7b8f5185f825078c6a259897d5393ac2570c5'),
    ('zaf_profile_widths', 0x53eab534, 0x10, 'b074230248217919329dbd28e5d1525cb70261e39f6d571f0a1326ef59d6f8eb'),
    ('zaf_predictor_limit', 0x53eab52c, 0x8, '8dfefa928bce3fc28b887e1959530be108e38fc46fb3c67a74529dee61007248'),
    ('zaf_small_block_limit', 0x53eab5f0, 0x8, '1a8b6a04602c3f12bd97d9c37bab4a4b22904260377ecf6d1e7bb8d962f6f27c'),
    ('native_signed_absolute', 0x53155f6c, 0xc, '80aae25b9769bbeff356ba7ce911312a07ee21fd441f65a045a117b9def48fd0'),
    ('zaf_operation_dispatch', 0x53614b98, 0x90, '87f927290885c56008806dccd7c528f8100115e0bb11334afdc88923cda84f43'),
)

MARKERS = {
    0x53d7c8e0: "Model/FocusModel.cpp",
    0x53dbaf50: "FocusToFocusMode",
    0x53dbbf44: "UserDataFocusToCameraControlFocusMode",
    0x53dbd808: "ApplySnapDistance",
    0x53dbd850: "GetFocusAreaSize",
    0x53dbd7cc: "UpdateCommonPropertyFocusArea",
    0x53ea63a8: "GetAfProcessAddress",
    0x53ea63c8: "src/AfArbitrate.cpp",
    0x53ea7434: "src/AfLensControl.cpp",
    0x53ea7590: "src/HybridAfInfo.cpp",
    0x53ea7c70: "src/CafProcess.cpp",
    0x53eaa34c: "src/ZafFactory.cpp",
    0x53eaa67c: "src/ZafProcess.cpp",
    0x53eaa458: "src/ZafInformationCollector.cpp",
    0x53eaa524: "src/ZafOperationAlgorithm.cpp",
    0x53eac118: "GetPredictorOkBackup",
    0x53eac2e8: "GetPredictorBackup",
    0x53eac294: "GetRepetitionDetectedBackup",
    0x53eabe4c: "GetFakeBottomDoubtBackup",
    0x53eac078: "GetZafSaturationBackup",
    0x53eaa69c: "src/ZafWaveData.cpp",
    0x53fc5858: "src/CaptureZafInterface.cpp",
    0x541da528: "src/LensFocusControl.cpp",
    0x541da804: "GetFocusTempratureCoefficient",
    0x53ea71e4: "EnableAfDebugDataSave <0/1> [P/C/Z/O]\n",
    0x53ea7250: "[AF] AfErrorRetry On => Return OK Pattern Test\n",
    0x53ea7280: "[AF] AfErrorRetry On => Return NG Pattern Test\n",
}

EDGES = (
    (0x535e3b84, 0x535e69f8, True),
    (0x535e3c3c, 0x535ed004, True),
    (0x535e3c68, 0x5360df6c, True),
    (0x535e3c94, 0x53612658, True),
    (0x535e40b8, 0x535e9d20, True),
    (0x535e45e0, 0x535e4000, True),
    (0x535e52e4, 0x535e4264, False),
    (0x535ecc6c, 0x53612658, True),
    (0x535ecca8, 0x53612658, True),
    (0x535ecd5c, 0x53612d84, False),
    (0x535ecd64, 0x53612dd8, False),
    (0x535ecd6c, 0x53612e30, False),
    (0x535ecd7c, 0x53612ed4, False),
    (0x535ecd98, 0x53619bb4, False),
    (0x535ecda4, 0x53619bb4, False),
    (0x535ecdac, 0x5361a678, False),
    (0x535fd318, 0x535ecd80, True),
    (0x535fd324, 0x535ecd80, True),
    (0x535fd754, 0x535ecda8, True),
    (0x536019a8, 0x535ecd60, True),
    (0x536019cc, 0x535e5238, True),
    (0x535eae78, 0x535eade8, True),
    (0x53611318, 0x538e7fd0, True),
    (0x5339dc3c, 0x5339d3b0, True),
    (0x5339ee68, 0x5339e894, True),
    (0x5339efb8, 0x532aee90, True),
    (0x535e8f74, 0x53929078, True),
    (0x535e907c, 0x539290fc, True),
    (0x53929154, 0x538db424, True),
    (0x53022800, 0x5361a3ec, True),
    (0x53022894, 0x535e69f8, True),
    (0x53614bd8, 0x53616868, True),
    (0x53614be0, 0x53616c94, True),
    (0x53614be8, 0x53617174, True),
    (0x53616d38, 0x53615be8, True),
    (0x53616d4c, 0x53615c94, True),
    (0x53616d70, 0x53615f44, True),
    (0x53616d84, 0x53615e98, True),
    (0x53616d98, 0x53615dec, True),
    (0x53616db0, 0x53618a84, True),
)

FOCUS_NAMES = (
    "AutoArea", "Select", "SelectContinuous", "SelectMovieRecording",
    "Pinpoint", "Follow", "Continuous", "MovieAf", "MovieRecording",
    "Mf", "Snap", "Infinity", "SameAsShutter", "None", "AutoAreaM", "ZoneSelect",
)


def word(raw, address):
    return struct.unpack_from("<I", raw, file_offset(address))[0]


def mov_immediate(raw, address, register):
    value = word(raw, address)
    if value & 0xfffff000 != 0xe3a00000 | (register << 12):
        raise ValueError(f"not expected ARM MOV immediate at {address:#x}")
    rotation = 2 * ((value >> 8) & 15)
    immediate = value & 255
    return ((immediate >> rotation) | (immediate << (32 - rotation))) & 0xffffffff


def audit(raw):
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"unsupported decoded sample: {digest}")
    pins = []
    for role, address, size, expected in PINS:
        actual = hashlib.sha256(raw[file_offset(address):file_offset(address) + size]).hexdigest()
        if actual != expected:
            raise ValueError(f"changed {role} at {address:#x}")
        pins.append(dict(role=role, runtime_address=hex(address),
                         decoded_offset=hex(file_offset(address)), length=size, sha256=actual))
    for address, marker in MARKERS.items():
        encoded = marker.encode("ascii") + b"\0"
        if raw[file_offset(address):file_offset(address) + len(encoded)] != encoded:
            raise ValueError(f"source marker changed at {address:#x}")
    edges = []
    for site, expected, link in EDGES:
        value = word(raw, site)
        if value & 0xfe000000 != 0xea000000 or bool(value & 0x01000000) != link:
            raise ValueError(f"not expected unconditional ARM B/BL at {site:#x}")
        delta = value & 0xffffff
        if delta & 0x800000:
            delta -= 0x1000000
        target = site + 8 + 4 * delta
        if target != expected:
            raise ValueError(f"branch target changed at {site:#x}")
        edges.append(dict(site=hex(site), target=hex(target), link=link))
    mappings = []
    for focus_id, name in enumerate(FOCUS_NAMES):
        mode_target = word(raw, 0x5329d378 + 4 * focus_id)
        remote_target = word(raw, 0x5337c488 + 4 * focus_id)
        mode = None if mode_target == 0x5329d3f4 else mov_immediate(raw, mode_target, 0)
        remote = None if remote_target == 0x5337c524 else mov_immediate(raw, remote_target, 0)
        mappings.append(dict(user_focus_id=focus_id, parser_name=name,
                             common_mode=mode, remote_mode=remote,
                             common_dispatch=hex(mode_target), remote_dispatch=hex(remote_target)))
    if [m["common_mode"] for m in mappings] != [1, 1, 2, 4, 1, 3, 2, 2, 4, 0, 0, 0, None, None, 1, 1]:
        raise ValueError("focus mode mapping changed")
    variants = list(raw[file_offset(0x53eab62c):file_offset(0x53eab62c) + 7])
    if variants != [1, 0, 2, 2, 3, 2, 2]:
        raise ValueError("ZAF project variant table changed")
    return {
        "schema": "gr4-focus-offline-audit-v2", "firmware_version": "1.11.10.7",
        "sample_sha256": digest, "decoded_length": len(raw),
        "address_mapping": {"rtos_base": "0x53000000", "decoded_rtos_offset": "0x17d10"},
        "evidence": "static instruction, table and source-marker checks; no CPU execution",
        "pins": pins, "branch_edges": edges,
        "markers": [{"runtime_address": hex(a), "text": s} for a, s in MARKERS.items()],
        "focus_modes": mappings,
        "process_selector": {"entry": "0x535e4000", "ids_to_arbitrate_object_offsets":
                             {"1": "0x58", "2": "0x58", "3": "0x60", "4": "0x5c"},
                             "objects": {"0x58": "CafProcess", "0x60": "ZafProcess", "0x5c": "OtherafProcess"}},
        "zaf_project_variants": variants, "standard_gr4_project_type": 2,
        "variant_is_not_boolean_enable": True,
        "snap_distance_branches_cm": [30, 40, 100, 150, 200, 250, 350, 500, -1],
        "snap_distance_conversion": "finite centimetres * 10 -> millimetres; infinity preserves 0xffffffff",
        "zaf_algorithm": {"internal_record_capacity": 165,
                          "profile_sample_widths": list(struct.unpack_from("<4I", raw, file_offset(0x53eab534))),
                          "predictor_magnitude_limit_raw": list(struct.unpack_from("<4H", raw, file_offset(0x53eab52c))),
                          "correlation_margin_cap_raw": 11,
                          "candidate_reject_fields": {"predictor_ok_byte": "0x3d", "predictor_signed_halfword": "0x3e",
                                                      "repetition_byte": "0x44", "fake_bottom_byte": "0x45", "saturation_byte": "0x46"},
                          "capacity_is_not_verified_autofocus_point_count": True,
                          "raw_predictor_unit_verified": False},
        "camera_accessed": False, "firmware_modified": False,
        "limits": ["Parser names include internal modes, not a verified user-visible menu.",
                   "No sensor, motor, autofocus accuracy, timing or live camera-state validation.",
                   "Hybrid snapshot copies and start requests do not establish every switching threshold.",
                   "Focus windows use a 720x480 model coordinate reference, not sensor pixel dimensions.",
                   "All addresses apply only to the pinned decoded sample."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    parser.add_argument("--output", type=Path, help="new JSON file, never overwrites")
    args = parser.parse_args()
    try:
        result = audit(args.sample.read_bytes())
        rendered = json.dumps(result, indent=2) + "\n"
        if args.output:
            with args.output.open("x") as stream:
                stream.write(rendered)
            print(f"Saved {len(PINS)} windows, {len(EDGES)} edges and 16 focus mappings to {args.output}")
        else:
            print(rendered, end="")
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
