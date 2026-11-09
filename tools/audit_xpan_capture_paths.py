#!/usr/bin/env python3
"""Verify metadata, DNG and YCbCr descriptor paths offline; no hook installation."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_xpan_paths import EXPECTED_SHA256, file_offset, require
from audit_sd_shell_path import require_branch


def audit(raw):
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise ValueError('unsupported sample')
    for address, text in [(0x53FA00A0,b'ImageContents/Writer/src/PentaxMakernoteEntryDataSetter.cpp\0'),
                          (0x53FCE418,b'src/ImageMapParameterSettingStillKb588.cpp\0'),
                          (0x53FCE570,b'src/ImageMapParameterSettingStillKb636.cpp\0'),
                          (0x53FD7588,b'src/ImageResolutionTranslatorKb636.cpp\0'),
                          (0x53ECCCF0,b'ProcessModule/src/BackResizeMacroProcess.cpp\0'),
                          (0x53D7C8E0,b'Model/FocusModel.cpp\0'),
                          (0x53ECD088,b'dstInfo->GetFormat() == ImageProcessCommonItem::YCbCrFormat_420\0'),
                          (0x53ECD0C8,b'srcInfo->GetFormat() == ImageProcessCommonItem::YCbCrFormat_422\0')]:
        require(raw,file_offset(address),text,'source identity')
    require_branch(raw,0x5380D21C,0x537E7134,link=False)
    require(raw,file_offset(0x537E7140),bytes.fromhex('01 20 c3 e7'),
            'Makernote enum stored as byte, not a crop operation')
    for address, expected in [(0x5387B104,'44 20 82 e2'),(0x5387B11C,'28 30 83 e2'),
                              (0x5387E1E8,'36 20 82 e2'),(0x5387E200,'3a 30 83 e2')]:
        require(raw,file_offset(address),bytes.fromhex(expected),'DNG origin variant')
    require_branch(raw,0x5387E3D0,0x5387E108)
    for address, expected in [(0x5387E3F0,'b8 01 c4 e1'),(0x5387E3F4,'ba 11 c4 e1'),
                              (0x5387E3F8,'bc 21 c4 e1'),(0x5387E3FC,'be 31 c4 e1')]:
        require(raw,file_offset(address),bytes.fromhex(expected),'Kb636 DNG parameter stores')
    require(raw,file_offset(0x5387E178),bytes.fromhex('08 c0 93 e5'),
            'Kb636 current-window dimension method')
    require(raw,file_offset(0x5387E1B0),bytes.fromhex('08 c0 93 e5'),
            'Kb636 full-source dimension method')
    require(raw,file_offset(0x5387E1B4),bytes.fromhex('09 10 a0 e1'),
            'full-source size-index argument is zero')
    require(raw,file_offset(0x5387E1B8),bytes.fromhex('09 20 a0 e1'),
            'full-source aspect argument is zero')
    # The descriptor copier and center-window operation identify fields without
    # executing their code. Runtime source format/allocation bounds remain unknown.
    for address, expected, label in [
        (0x538D337C,'04 90 91 e5 08 80 91 e5','two plane pointers'),
        (0x538D3388,'b0 61 d1 e1 b2 51 d1 e1 b4 41 d1 e1','width, height, pitch'),
        (0x536FB0B8,'94 0c 0c e0','vertical offset multiplied by pitch'),
        (0x536FB0C8,'0c 10 81 e0 0c 20 82 e0 50 1a 83 e5 54 2a 83 e5',
         'same byte offset applied to both source planes'),
        (0x536FB224,'08 c0 9e e5 3c ff 2f e1','destination dimension calculator call'),
        (0x536FB234,'b0 21 c7 e1 b2 31 c7 e1','destination width and height'),
        (0x53702D78,'02 00 40 e2','assertion maps 420 to format 2'),
        (0x53702DA4,'01 00 40 e2','assertion maps 422 to format 1')]:
        require(raw,file_offset(address),bytes.fromhex(expected),label)
    require_branch(raw,0x536FB7DC,0x536FB040)
    require_branch(raw,0x536FB820,0x536FB0DC)
    return {'metadata_only_aspect_writer': '0x5380d1d0',
            'metadata_only_writer_is_not_a_JPEG_pixel_hook': True,
            'DNG_variants': {'Kb588':{'function':'0x5387b024','origin':[68,40]},
                             'Kb636':{'function':'0x5387e108','origin':[54,58]}},
            'Kb636_parameter_offsets': {'width':'0x18','height':'0x1a','left':'0x1c','top':'0x1e'},
            'shared_size_method_called_twice_in_DNG': True,
            'global_dimension_hook_would_destroy_full_source_reference': True,
            'runtime_parameter_object_vtable_verified': False,
            'FocusModel_layout_is_not_verified_full_live_image_viewport': True,
            'YCbCr_descriptor': {'copy':'0x538d336c','center_source':'0x536fb040',
                'destination_dimensions':'0x536fb0dc','format_422':1,'format_420':2,
                'planes':['0x4','0x8'],'width':'0x10','height':'0x12','pitch':'0x14'},
            'runtime_main_source_format_and_allocation_bounds_verified': False,
            'JPEG_pixel_hook_verified': False,
            'camera_installable': False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('sample',type=Path)
    args=p.parse_args()
    print(json.dumps(audit(args.sample.read_bytes()),indent=2))


if __name__=='__main__':main()
