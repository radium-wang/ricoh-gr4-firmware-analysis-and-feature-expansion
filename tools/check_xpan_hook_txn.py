#!/usr/bin/env python3
"""Compile fault-injection recovery checks on the host; no camera access."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    binary = args.out / 'hook-txn-test'
    sources = [ROOT / 'tests/xpan_hook_txn_test.c', ROOT / 'firmware/xpan_hook_txn.c']
    command = [shutil.which('clang'), '-std=c11', '-O2', '-Wall', '-Wextra',
               '-Werror', *map(str, sources), '-o', str(binary)]
    subprocess.run(command, check=True)
    run = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    cases = run.stdout.splitlines()
    if len(cases) != 13 or len(set(cases)) != 13:
        raise ValueError('incomplete recovery checks')
    report = {'schema': 'gr4-xpan-hook-recovery-host-v1', 'passed': True,
              'cases': cases, 'camera_access': False, 'native_quiescence_verified': False,
              'native_cache_publication_verified': False, 'installer_available': False,
              'command': command, 'sha256': {
                  str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sources + [ROOT / 'firmware/xpan_hook_txn.h']}}
    (args.out / 'checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print('13 recovery fault checks passed; host model only')


if __name__ == '__main__':
    main()
