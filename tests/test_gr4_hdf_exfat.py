# License: see LICENSE
"""Synthetic byte/control-flow tests; not native TTL or camera qualification."""
import subprocess
import sys
import tempfile
import unittest
import importlib
import json
import re
import shlex
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script, files, faults=None, attributes=None):
    """Finite TTL subset; assumes byte copies, zero extension and numeric bytes.

    Does not establish native parser/storage semantics, timing, media safety,
    firmware compatibility, JPEG display, or failure atomicity.
    """
    lines = script.decode('ascii').splitlines()
    labels = {s[1:]: i for i, s in enumerate(lines) if s.startswith(':')}
    variables, handles, copies = {}, {}, []
    pc = 0

    def value(token):
        if token in variables:
            return variables[token]
        try:
            return int(token)
        except ValueError:
            return token

    def write(handle, data):
        name, position = handles[handle]
        files[name] = files[name][:position] + data + files[name][position + len(data):]
        handles[handle][1] += len(data)

    for _ in range(30000):
        if pc >= len(lines):
            return copies
        line = lines[pc].strip()
        pc += 1
        if not line or line.startswith((';', ':')):
            continue
        args = shlex.split(line)
        op = args[0]
        if op == 'if':
            left, right = value(args[1]), value(args[3])
            condition = {'=': lambda: left == right, '<>': lambda: left != right,
                         '<': lambda: left < right, '>': lambda: left > right}[args[2]]()
            if not condition:
                depth = 1
                while depth:
                    skipped = lines[pc].strip()
                    pc += 1
                    depth += int(skipped.startswith('if ')) - int(skipped == 'endif')
        elif op == 'endif':
            pass
        elif op == 'exit':
            return copies
        elif op == 'goto':
            pc = labels[args[1]]
        elif len(args) > 1 and args[1] == '=':
            variables[args[0]] = value(args[2])
        elif op == 'filesearch':
            variables['result'] = int(args[1] in files)
        elif op == 'filestat':
            variables['result'] = 0 if args[1] in files else -1
            variables[args[2]] = len(files[args[1]]) if args[1] in files else -1
        elif op == 'getfileattr':
            variables['result'] = (attributes or {}).get(args[1], 32 if args[1] in files else -1)
        elif op in ('filecreate', 'fileopen'):
            name = args[2]
            if op == 'filecreate':
                files[name] = b''
            handle = max(handles, default=0) + 1 if name in files else -1
            variables[args[1]] = handle
            if handle >= 0:
                handles[handle] = [name, len(files[name]) if op == 'fileopen' and args[3] == '1' else 0]
        elif op == 'fileclose':
            del handles[value(args[1])]
        elif op == 'filetruncate':
            size = int(args[2])
            files[args[1]] = files[args[1]][:size].ljust(size, b'\0')
        elif op == 'fileseek':
            assert args[3] == '0'
            handles[value(args[1])][1] = int(args[2])
        elif op == 'fileread':
            name, position = handles[value(args[1])]
            size = int(args[2])
            variables[args[3]] = files[name][position:position + size].decode('latin1')
            handles[value(args[1])][1] += size
        elif op == 'str2code':
            chunk = value(args[2])
            variables[args[1]] = ord(chunk[0]) if chunk else 0
        elif op == 'int2str':
            variables[args[1]] = str(value(args[2]))
        elif op == 'filewrite':
            write(value(args[1]), bytes(map(int, re.findall(r'#(\d+)', args[2]))))
        elif op == 'filewriteln':
            operand = line.split(maxsplit=2)[2]
            text = operand[1:-1] if operand.startswith("'") else str(value(args[2]))
            write(value(args[1]), (text + '\r\n').encode('ascii'))
        elif op == 'filecopy':
            copies.append((args[1], args[2]))
            fault = (faults or {}).get(len(copies))
            if fault == 'drop':
                continue
            data = files.get(args[1], b'')
            if fault == 'truncate':
                data = data[:7]
            elif fault == 'corrupt':
                data = bytes((data[0] ^ 255,)) + data[1:]
            files[args[2]] = data
        else:
            raise AssertionError(line)
    raise AssertionError('Control-flow step bound exceeded')


def jpeg(color, subsampling=1, progressive=False, mode='RGB', size=(720, 480)):
    from PIL import Image
    from tools.pad_jpeg import pad_jpeg
    stream = BytesIO()
    Image.new(mode, size, color).save(stream, format='JPEG', subsampling=subsampling,
                                    progressive=progressive)
    return pad_jpeg(stream.getvalue(), 56842)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('tools.gr4_hdf_exfat')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {self.module.MODEL: bytes.fromhex('a55a5aa5e1320100')}
        self.old, self.new = jpeg('white'), jpeg('blue')
        self.files[self.module.TARGET] = self.old
        self.current, self.candidate = self.root / 'current.jpg', self.root / 'candidate.jpg'
        self.current.write_bytes(self.old)
        self.candidate.write_bytes(self.new)

    def execute(self, package, name, faults=None, attributes=None):
        copies = run((package / 'script/startup.ttl').read_bytes(), self.files, faults, attributes)
        readbacks = self.root / name
        readbacks.mkdir()
        for path, data in self.files.items():
            if path.startswith('C:\\'):
                (readbacks / path[3:]).write_bytes(data)
        return readbacks, copies

    def probe(self):
        package = self.root / 'probe'
        self.module.probe('EX01', package)
        readbacks, _ = self.execute(package, 'probe-card')
        return package, readbacks

    def temporary(self):
        probe, card = self.probe()
        package = self.root / 'temporary'
        self.module.temporary(probe, card, self.current, self.candidate, 'EX02', package)
        readbacks, _ = self.execute(package, 'temporary-card')
        return package, readbacks

    def test_probe_full_binary_and_zero_readbacks_and_model_guard(self):
        package, card = self.probe()
        self.assertEqual((card / 'EX01ZERO.BIN').read_bytes(), bytes(1024))
        payload = (card / 'EX01DATA.BIN').read_bytes()
        self.assertEqual(set(payload), set(range(256)))
        self.assertTrue(self.module.verify(package, card)['camera_display_must_be_checked_separately'])
        self.files = {self.module.MODEL: bytes(8)}
        run((package / 'script/startup.ttl').read_bytes(), self.files)
        self.assertNotIn('C:\\EX01DATA.BIN', self.files)
        self.assertNotIn('C:\\EX01ZERO.BIN', self.files)

    def test_literal_reconstruction_small_zero_binary_and_line_bounds(self):
        for payload in (b'', b'\0', bytes(120), b'\0\1\xff\0', bytes(range(256)) * 5):
            lines = self.module.literal_lines(payload)
            rebuilt = bytearray(len(payload))
            position = None
            for line in lines:
                if line.startswith('fileseek fh '):
                    position = int(line.split()[2])
                else:
                    values = bytes(map(int, re.findall(r'#(\d+)', line)))
                    self.assertNotIn(0, values)
                    self.assertLessEqual(len(values), 42)
                    rebuilt[position:position + len(values)] = values
                self.assertLess(len(line), 256)
            self.assertEqual(bytes(rebuilt), payload)

    def test_temporary_preserves_active_and_independent_factory_backup(self):
        factory = r'A:\Resource\Jpeg\FACTORY.JPG'
        self.files[factory] = b'factory-keep'
        package, card = self.temporary()
        manifest = self.module.verify(package, card)
        self.assertTrue(manifest['successful_log_verified'])
        self.assertEqual(self.files[self.module.TARGET], self.old)
        self.assertEqual(self.files[r'A:\Resource\Jpeg\EX02OLD.JPG'], self.old)
        self.assertEqual(self.files[r'A:\Resource\Jpeg\EX02NEW.JPG'], self.new)
        self.assertEqual(self.files[factory], b'factory-keep')
        script = (package / 'script/startup.ttl').read_bytes()
        self.assertEqual(script.count(b'\n'), script.count(b'\r\n'))
        self.assertLess(max(map(len, script.splitlines())), 256)
        self.assertNotIn(b"' 'A:\\Resource\\Jpeg\\GB_HDF.jpg'", script)

    def test_successful_install_verify_and_repeat(self):
        source, card = self.temporary()
        package = self.root / 'install'
        self.module.install(source, card, 'EX03', package)
        returned, copies = self.execute(package, 'install-card')
        self.assertEqual(self.files[self.module.TARGET], self.new)
        self.assertEqual(len(copies), 5)
        self.module.verify(package, returned)
        before = self.files.copy()
        self.assertEqual(run((package / 'script/startup.ttl').read_bytes(), self.files), [])
        self.assertEqual(self.files, before)
        self.assertTrue(all(a.startswith('A:') for a, _ in copies))

    def test_missing_or_corrupt_readbacks_and_bad_log_block_next_phase(self):
        probe, card = self.probe()
        path = card / 'EX01DATA.BIN'
        original = path.read_bytes()
        for bad in (original[:-1], b'X' + original[1:]):
            path.write_bytes(bad)
            with self.assertRaises(ValueError):
                self.module.temporary(probe, card, self.current, self.candidate,
                                      'EX02', self.root / 'no-package')
        path.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.module.verify(probe, card)
        path.write_bytes(original)
        log = card / 'EX01LOG.TXT'
        good = log.read_bytes()
        for bad in (good[:-1], good + b'finished\r\n1\r\n', good.replace(b'error\r\n0', b'error\r\n1')):
            log.write_bytes(bad)
            with self.assertRaises(ValueError):
                self.module.verify(probe, card)
        self.assertFalse((self.root / 'no-package').exists())

    def test_install_reverifies_every_temporary_output_instead_of_stamp(self):
        source, card = self.temporary()
        (card / 'verified.json').write_text('{"passed":true}')
        for suffix in ('CUR', 'BAK', 'IMG'):
            path = card / f'EX02{suffix}.JPG'
            original = path.read_bytes()
            path.write_bytes(b'X' + original[1:])
            with self.assertRaises(ValueError):
                self.module.install(source, card, 'EX03', self.root / 'no-install')
            path.write_bytes(original)

    def test_invalid_jpeg_profiles_and_lengths_rejected_without_output(self):
        probe, card = self.probe()
        invalid = [self.new[:-1], b'x' * 56842, jpeg('blue', subsampling=2),
                   jpeg('blue', progressive=True), jpeg(0, mode='L'), jpeg('blue', size=(480, 720))]
        for data in invalid:
            with self.subTest(prefix=data[:12]):
                self.candidate.write_bytes(data)
                with self.assertRaises(ValueError):
                    self.module.temporary(probe, card, self.current, self.candidate,
                                          'EX02', self.root / 'invalid')
                self.assertFalse((self.root / 'invalid').exists())
        self.candidate.write_bytes(self.new)
        self.current.write_bytes(jpeg('white', subsampling=2))
        with self.assertRaises(ValueError):
            self.module.temporary(probe, card, self.current, self.candidate,
                                  'EX02', self.root / 'invalid')

    def test_unsafe_reused_attempts_nonempty_output_and_bad_package_schema(self):
        for attempt in ('EX0', 'EX001', '1X01', 'ex01', 'EX\n1', "E'01", '../x', r'E\01'):
            with self.assertRaises(ValueError):
                self.module.probe(attempt, self.root / 'invalid')
        probe, card = self.probe()
        with self.assertRaises(ValueError):
            self.module.probe('EX09', probe)
        with self.assertRaises(ValueError):
            self.module.temporary(probe, card, self.current, self.candidate, 'EX01', self.root / 'invalid')
        path = probe / 'manifest.json'
        original = path.read_text()
        for key, value in [('schema', 'other'), ('kind', 'install'), ('attempt', '../x'),
                           ('target', 'C:\\Windows'), ('inputs', {'../escape': {}}),
                           ('expected_outputs', {'../escape': {}})]:
            manifest = json.loads(original)
            manifest[key] = value
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                self.module.verify(probe, card)
        path.write_text(original)

    def test_changed_local_sources_or_script_cannot_be_verified(self):
        package, card = self.temporary()
        for relative in ('inputs/current.jpg', 'inputs/candidate.jpg', 'script/startup.ttl',
                         'source/script/startup.ttl', 'source-readbacks/EX01DATA.BIN'):
            path = package / relative
            good = path.read_bytes()
            path.write_bytes(good[:-1] + bytes((good[-1] ^ 1,)))
            with self.assertRaises(ValueError):
                self.module.verify(package, card)
            path.write_bytes(good)

    def test_all_early_guards_preserve_active_and_backup(self):
        source, card = self.temporary()
        package = self.root / 'install'
        self.module.install(source, card, 'EX03', package)
        script = (package / 'script/startup.ttl').read_bytes()
        initial = self.files.copy()
        for changes, attrs in [({self.module.MODEL: bytes(8)}, None),
                               ({self.module.TARGET: b'x'}, None),
                               ({r'A:\Resource\Jpeg\EX02OLD.JPG': b'x'}, None),
                               ({r'A:\Resource\Jpeg\EX02NEW.JPG': b'x'}, None),
                               ({}, {self.module.TARGET: 33}),
                               ({r'C:\EX03OUT.JPG': b'keep'}, None)]:
            files = dict(initial, **changes)
            before = files.copy()
            copies = run(script, files, attributes=attrs)
            self.assertFalse(any(b == self.module.TARGET for _, b in copies))
            self.assertEqual(files[self.module.TARGET], before[self.module.TARGET])
            self.assertEqual(files[r'A:\Resource\Jpeg\EX02OLD.JPG'], before[r'A:\Resource\Jpeg\EX02OLD.JPG'])

    def test_temporary_guards_preserve_preexisting_internal_files(self):
        probe, card = self.probe()
        package = self.root / 'temporary'
        self.module.temporary(probe, card, self.current, self.candidate, 'EX02', package)
        script = (package / 'script/startup.ttl').read_bytes()
        initial = self.files.copy()
        for path in (r'A:\Resource\Jpeg\EX02OLD.JPG', r'A:\Resource\Jpeg\EX02NEW.JPG'):
            files = dict(initial, **{path: b'keep'})
            self.assertEqual(run(script, files), [])
            self.assertEqual(files[path], b'keep')
        for changes, attrs in [({self.module.MODEL: bytes(8)}, None),
                               ({self.module.MODEL: b'short'}, None),
                               ({self.module.TARGET: b'short'}, None),
                               ({}, {self.module.TARGET: 33}),
                               ({r'C:\EX02CUR.JPG': b'keep'}, None)]:
            files = dict(initial, **changes)
            before = files[self.module.TARGET]
            self.assertEqual(run(script, files, attributes=attrs), [])
            self.assertEqual(files[self.module.TARGET], before)
            self.assertNotIn(r'A:\Resource\Jpeg\EX02OLD.JPG', files)
            self.assertNotIn(r'A:\Resource\Jpeg\EX02NEW.JPG', files)

    def test_every_script_has_forward_jumps_and_constrained_mutations(self):
        source, returned = self.temporary()
        self.module.install(source, returned, 'EX03', self.root / 'install')
        self.module.restore(source, returned, self.current, 'EX04', self.root / 'restore')
        for name in ('probe', 'temporary', 'install', 'restore'):
            script = (self.root / name / 'script/startup.ttl').read_bytes()
            self.assertEqual(script.count(b'\n'), script.count(b'\r\n'))
            lines = script.decode('ascii').splitlines()
            labels = {line[1:]: i for i, line in enumerate(lines) if line.startswith(':')}
            for i, line in enumerate(lines):
                self.assertLess(len(line), 256)
                if line.startswith('goto '):
                    self.assertGreater(labels[line[5:]], i)
                if line.startswith('filecopy '):
                    self.assertTrue(shlex.split(line)[1].startswith('A:\\'))
                if line.startswith('filewrite '):
                    self.assertIn(name, ('probe', 'temporary'))
                    values = list(map(int, re.findall(r'#(\d+)', line)))
                    self.assertTrue(1 <= len(values) <= 42)
                    self.assertTrue(all(1 <= x <= 255 for x in values))
                self.assertFalse(line.startswith(('filedelete ', 'setfileattr ', 'exec ', 'include ')))

    def test_source_snapshot_paths_cannot_escape_package(self):
        package, returned = self.temporary()
        source = package / 'source-readbacks'
        external = self.root / 'external-readbacks'
        source.rename(external)
        if sys.platform == 'win32':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(source), str(external)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        else:
            source.symlink_to(external, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.module.verify(package, returned)

    def test_cli_all_phases_and_verification(self):
        source, returned = self.temporary()
        result = subprocess.run([sys.executable, str(ROOT / 'tools/gr4_shutdown.py'), 'exfat',
                                 'temporary', str(self.root / 'probe'), str(self.root / 'probe-card'),
                                 str(self.current), str(self.candidate), 'CL00', str(self.root / 'cli-temporary')],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for phase, extra in [('install', []), ('restore', [str(self.current)])]:
            result = subprocess.run([sys.executable, str(ROOT / 'tools/gr4_shutdown.py'), 'exfat',
                                     phase, str(source), str(returned), *extra,
                                     'CL01' if phase == 'install' else 'CL02', str(self.root / phase)],
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        result = subprocess.run([sys.executable, str(ROOT / 'tools/gr4_shutdown.py'), 'exfat',
                                 'verify', str(source), str(returned)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(json.loads(result.stdout)['camera_display_must_be_checked_separately'])

    def test_each_phase_repeat_preserves_entire_filesystem(self):
        source, returned = self.temporary()
        self.module.install(source, returned, 'EX03', self.root / 'install')
        self.execute(self.root / 'install', 'install-card')
        self.module.restore(source, returned, self.candidate, 'EX04', self.root / 'restore')
        self.execute(self.root / 'restore', 'restore-card')
        for name in ('probe', 'temporary', 'install', 'restore'):
            before = self.files.copy()
            copies = run((self.root / name / 'script/startup.ttl').read_bytes(), self.files)
            self.assertEqual(copies, [])
            self.assertEqual(self.files, before)

    def test_prewrite_failure_rollback_and_same_size_corruption(self):
        source, card = self.temporary()
        package = self.root / 'install'
        self.module.install(source, card, 'EX03', package)
        script = (package / 'script/startup.ttl').read_bytes()
        initial = self.files.copy()
        files = initial.copy()
        copies = run(script, files, {1: 'drop'})
        self.assertFalse(any(b == self.module.TARGET for _, b in copies))
        for faults in ({4: 'truncate'}, {5: 'drop'}):
            files = initial.copy()
            run(script, files, faults)
            self.assertEqual(files[self.module.TARGET], self.old)
            self.assertEqual(files[r'C:\EX03RST.JPG'], self.old)
            self.assertIn(b'rollback_size_ok\r\n1\r\n', files[r'C:\EX03LOG.TXT'])
            self.assertNotIn(b'error\r\n0\r\n', files[r'C:\EX03LOG.TXT'])
        files = initial.copy()
        run(script, files, {4: 'truncate', 5: 'drop'})
        self.assertIn(b'rollback_size_ok\r\n0\r\n', files[r'C:\EX03LOG.TXT'])
        self.files = initial.copy()
        returned, _ = self.execute(package, 'corrupt-card', {4: 'corrupt'})
        with self.assertRaises(ValueError):
            self.module.verify(package, returned)

    def test_restore_uses_temporary_backup_without_install_success(self):
        source, card = self.temporary()
        # Same-length undecodable state can be bound explicitly for recovery.
        self.files[self.module.TARGET] = b'X' * 56842
        active = self.root / 'active.bin'
        active.write_bytes(self.files[self.module.TARGET])
        package = self.root / 'restore'
        self.module.restore(source, card, active, 'EX04', package)
        returned, _ = self.execute(package, 'restore-card')
        self.assertEqual(self.files[self.module.TARGET], self.old)
        self.module.verify(package, returned)
        active.write_bytes(b'')
        with self.assertRaises(ValueError):
            self.module.restore(source, card, active, 'EX05', self.root / 'short-restore')

    def test_phase_ids_cannot_be_reused_from_same_source(self):
        source, card = self.temporary()
        self.module.install(source, card, 'EX03', self.root / 'install')
        with self.assertRaises(ValueError):
            self.module.restore(source, card, self.current, 'EX03', self.root / 'restore')


class DispatchTests(unittest.TestCase):
    def test_optional_exfat_probe_dispatch_creates_only_local_package(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'probe'
            result = subprocess.run([sys.executable, str(ROOT / 'tools/gr4_shutdown.py'),
                                     'exfat', 'probe', 'EX01', str(output)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertTrue((output / 'script/startup.ttl').is_file())
            self.assertTrue((output / 'manifest.json').is_file())
