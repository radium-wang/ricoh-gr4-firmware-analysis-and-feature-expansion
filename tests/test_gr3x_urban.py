# License: see LICENSE (earlier Apache-2.0 grants remain in force)
"""Offline tests only: no camera, SD card, artwork or firmware required."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import gr3x_urban_shutdown as shutdown
from gr3x_urban_jpeg import parse_jpeg


def run_backup_model(name, files, failed_copy=False, prefix="gr3x-urban"):
    """Model the guarded examples, not the camera filesystem/TTL interpreter."""
    variables = {'result': 0}
    active = []
    writes = []
    for line in (ROOT / 'examples' / f'{prefix}-{name}.ttl.example').read_text().splitlines():
        if not line or line.startswith(';'):
            continue
        if line == 'endif':
            active.pop()
            continue
        if line.startswith('if '):
            variable, operator, value = re.fullmatch(r'if (\w+) (=|<>) (-?\d+) then', line).groups()
            condition = variables[variable] == int(value)
            active.append(condition if operator == '=' else not condition)
            continue
        if not all(active):
            continue
        if line == 'exit':
            break
        attr = re.fullmatch(r"getfileattr '([^']+)'", line)
        stat = re.fullmatch(r"filestat '([^']+)' (\w+)", line)
        copy = re.fullmatch(r"filecopy '([^']+)' '([^']+)'", line)
        if attr:
            variables['result'] = 32 if attr[1] in files else -1
        elif stat:
            variables['result'] = 0 if stat[1] in files else -1
            variables[stat[2]] = len(files.get(stat[1], b''))
        elif copy:
            if copy[1] in files and not failed_copy:
                files[copy[2]] = files[copy[1]]
                writes.append(copy[2])
        else:
            raise AssertionError(f'Unexpected command {line}')
    return writes


class FactoryEntryTests(unittest.TestCase):
    def test_model_selection_and_no_overwrite(self):
        for model, entry in [('gr4', '00078560.636'), ('gr3x-urban-160', '00078490.609'),
                             ('gr3x-hdf-160', '00078490.609')]:
            with self.subTest(model=model), tempfile.TemporaryDirectory() as directory:
                command = [sys.executable, str(ROOT / 'tools/create_factory_entry.py'), directory]
                if model != 'gr4':
                    command += ['--model', model]
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual((Path(directory) / entry).read_bytes(), b'[OPEN_FACTORY_DEBUG_MENU]\r\n')
                self.assertEqual((Path(directory) / 'DEVELOP.MOD').read_bytes(), bytes.fromhex('07012c1f10031e16052d'))
                (Path(directory) / entry).write_bytes(b'keep')
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual((Path(directory) / entry).read_bytes(), b'keep')


class PayloadTests(unittest.TestCase):
    def test_literal_writes_reconstruct_binary_including_nuls(self):
        payload = (bytes(range(256)) * 422)[:shutdown.SIZE]
        payload = b'\x00' + payload[1:-1] + b'\x00'
        script, _, _, longest = shutdown.temporary_script(payload)
        memory = bytearray(shutdown.SIZE)
        position = None
        for line in script.decode('ascii').splitlines():
            if line.startswith('fileseek image '):
                position = int(line.split()[2])
            if line.startswith('filewrite image '):
                values = bytes(map(int, re.findall(r'#(\d+)', line)))
                self.assertNotIn(0, values)
                self.assertLessEqual(len(values), 42)
                memory[position:position + len(values)] = values
        self.assertEqual(memory, payload)
        self.assertLess(longest, 256)
        self.assertNotIn(b"' 'B:\\Resource\\Jpeg\\GB_Urban.jpg'", script)
        self.assertNotRegex(script.decode(), r'(?m)^fileread ')
        self.assertEqual(script.count(b'\n'), script.count(b'\r\n'))

    def test_bad_original_is_rejected_without_creating_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'original').write_bytes(b'not the original')
            (root / 'candidate').write_bytes(b'not a jpeg')
            with self.assertRaises(ValueError):
                shutdown.build(root / 'original', root / 'candidate', root / 'package')
            self.assertFalse((root / 'package').exists())


class ReadbackTests(unittest.TestCase):
    def test_complete_bytes_log_and_missing_files(self):
        # Synthetic files stand in for the private JPEG; checks run on full bytes.
        old, new = b'O' * shutdown.SIZE, b'N' * shutdown.SIZE
        old_hash, new_hash = map(lambda b: hashlib.sha256(b).hexdigest(), (old, new))
        with tempfile.TemporaryDirectory() as directory, patch.object(shutdown, 'OLD_HASH', old_hash):
            root = Path(directory)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'format': 'gr3x-urban-160-two-step-v1',
                'image_bytes': shutdown.SIZE, 'original_sha256': old_hash, 'candidate_sha256': new_hash}))
            (root / 'URBIMG8.JPG').write_bytes(new)
            for name in ('URBORG8.JPG', 'URBPRE8.JPG'):
                (root / name).write_bytes(old)
            good_log = 'started\n1\nerror\n0\nattempted\n0\nrestored\n0\ncompleted\n1\n'
            (root / 'URBLOG8.TXT').write_text(good_log)
            self.assertTrue(shutdown.verify(manifest, root, 1)['successful_log_verified'])
            (root / 'URBIMG8.JPG').write_bytes(new[:-1] + b'X')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                shutdown.verify(manifest, root, 1)
            (root / 'URBIMG8.JPG').write_bytes(new)
            for bad in [good_log.replace('error\n0', 'error\n201'), good_log[:-2],
                        good_log + 'completed\n1\n']:
                (root / 'URBLOG8.TXT').write_text(bad)
                with self.assertRaises(ValueError):
                    shutdown.verify(manifest, root, 1)
            (root / 'URBLOG8.TXT').write_text(good_log)
            (root / 'URBORG8.JPG').unlink()
            with self.assertRaises(FileNotFoundError):
                shutdown.verify(manifest, root, 1)

    def test_second_step_requires_final_target_and_attempted_write(self):
        old, new = b'O' * shutdown.SIZE, b'N' * shutdown.SIZE
        old_hash, new_hash = map(lambda b: hashlib.sha256(b).hexdigest(), (old, new))
        with tempfile.TemporaryDirectory() as directory, patch.object(shutdown, 'OLD_HASH', old_hash):
            root = Path(directory)
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'format': 'gr3x-urban-160-two-step-v1',
                'image_bytes': shutdown.SIZE, 'original_sha256': old_hash, 'candidate_sha256': new_hash}))
            for name, data in [('URBNW9.JPG', new), ('URBOR9.JPG', old),
                               ('URBPRE9.JPG', old), ('URBRD9.JPG', new)]:
                (root / name).write_bytes(data)
            log = root / 'URBLOG9.TXT'
            text = 'started\n1\nerror\n0\nattempted\n1\nrestored\n0\ncompleted\n1\n'
            log.write_text(text)
            shutdown.verify(manifest, root, 2)
            log.write_text(text.replace('attempted\n1', 'attempted\n0'))
            with self.assertRaises(ValueError):
                shutdown.verify(manifest, root, 2)
            log.write_text(text)
            (root / 'URBRD9.JPG').write_bytes(old)
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                shutdown.verify(manifest, root, 2)


class ExampleGuardTests(unittest.TestCase):
    def test_backup_preserves_existing_internal_original_and_blocks_repeat(self):
        files = {shutdown.TARGET: b'T' * shutdown.SIZE, shutdown.OLD: b'O' * shutdown.SIZE}
        run_backup_model('backup', files)
        self.assertEqual(files[shutdown.OLD], b'O' * shutdown.SIZE)
        self.assertEqual(files[r'C:\URBOLD.JPG'], files[shutdown.OLD])
        self.assertEqual(run_backup_model('backup', files), [])

    def test_backup_creates_original_once_and_stops_on_bad_target_or_copy(self):
        files = {shutdown.TARGET: b'O' * shutdown.SIZE}
        run_backup_model('backup', files)
        self.assertEqual(files[shutdown.OLD], files[shutdown.TARGET])
        for initial in [{}, {shutdown.TARGET: b'short'}]:
            self.assertEqual(run_backup_model('backup', initial), [])
        files = {shutdown.TARGET: b'O' * shutdown.SIZE}
        self.assertEqual(run_backup_model('backup', files, failed_copy=True), [])
        self.assertNotIn(shutdown.OLD, files)

    def test_restore_requires_backup_matching_length_and_fresh_readback(self):
        good = {shutdown.TARGET: b'N' * shutdown.SIZE, shutdown.OLD: b'O' * shutdown.SIZE}
        files = dict(good)
        run_backup_model('restore', files)
        self.assertEqual(files[shutdown.TARGET], good[shutdown.OLD])
        self.assertEqual(files[r'C:\URBREST.JPG'], good[shutdown.OLD])
        self.assertEqual(run_backup_model('restore', files), [])
        for files in [{shutdown.TARGET: good[shutdown.TARGET]},
                      dict(good, **{shutdown.TARGET: b'short'}),
                      dict(good, **{shutdown.OLD: b'short'})]:
            self.assertEqual(run_backup_model('restore', files), [])


class HDFBackupTests(unittest.TestCase):
    def test_backup_outputs_and_existing_original_are_preserved(self):
        target = r'B:\Resource\Jpeg\GoodBye.jpg'
        original = r'B:\Resource\Jpeg\HD41OL.JPG'
        files = {target: b'O'*7264}
        run_backup_model('backup', files, prefix='gr3x-hdf-160')
        for name in [original, r'C:\HDFBK0.JPG', r'C:\HDFOLD.JPG']:
            self.assertEqual(files[name], files[target])
        self.assertEqual(run_backup_model('backup', files, prefix='gr3x-hdf-160'), [])
        files = {target: b'N'*7264, original: b'O'*7264}
        self.assertEqual(run_backup_model('backup', files, prefix='gr3x-hdf-160'), [])
        self.assertEqual(files[original], b'O'*7264)

    def test_missing_short_target_and_failed_copy_do_not_create_internal_backup(self):
        target = r'B:\Resource\Jpeg\GoodBye.jpg'
        for files in [{}, {target: b'short'}]:
            self.assertEqual(run_backup_model('backup', files, prefix='gr3x-hdf-160'), [])
        files = {target: b'O'*7264}
        self.assertEqual(run_backup_model('backup', files, failed_copy=True, prefix='gr3x-hdf-160'), [])
        self.assertNotIn(r'B:\Resource\Jpeg\HD41OL.JPG', files)


class JPEGBoundsTests(unittest.TestCase):
    def test_truncation_restart_and_trailing_bytes_rejected(self):
        for data in [b'', b'\xff\xd8\xff', b'\xff\xd8\xff\xe0\x00',
                     b'\xff\xd8\xff\xe0\x00\x05x', b'\xff\xd8\xff\xd9x',
                     b'\xff\xd8\xff\xda\x00\x02x\xff\xd0\xff\xd9',
                     b'\xff\xd8\xff\xda\x00\x02x\xff']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_jpeg(data)
        parts = parse_jpeg(b'\xff\xd8\xff\xda\x00\x02x\xff\x00y\xff\xd9')
        self.assertEqual([p['marker'] for p in parts], ['D8', 'DA', 'ENTROPY', 'D9'])


if __name__ == '__main__':
    unittest.main()
