#!/usr/bin/env python3
"""Execute original size helpers for the observed manager mode 3/source 2.

This tests the interpretation of a captured manager, not LCD output or the
identity of the active hardware consumer. No camera access.
"""
import argparse
import json
from pathlib import Path
from check_gr4_preview_resolution import check
from audit_xpan_paths import EXPECTED_SHA256


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result={'schema':'gr4-live-preview-mode-checks-v1','sample_sha256':EXPECTED_SHA256,
            'camera_access':False,'LCD_pixels_verified':False,'xpan_installed':False,
            'observed_manager_bytes':{'aspect':1,'source_mode':2,'resolution':3,'external':1}}
    try:
        result['cases']=check(Path('samples/gr4_decoded.bin').read_bytes(),(3,),(2,),external=1)
        result['passed']=True
    except Exception as e:
        result.update(passed=False,error=repr(e))
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
