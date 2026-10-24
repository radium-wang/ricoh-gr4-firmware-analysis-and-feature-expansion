#!/usr/bin/env python3
# License: see LICENSE
"""Generate private, local GR IV HDF 1.11 exFAT literal-write packages.

C: in generated TTL means the camera SD card. This module reads explicitly
supplied files/readbacks and writes local packages, without card discovery or
deployment. Generated scripts contain the supplied image bytes.
The fixed predecessors were camera-tested; this parameterized generator needs
its own qualification. Full host readbacks and physical display checks differ.
"""
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path

SCHEMA = 'gr4-hdf-exfat-v1'
MODEL = r'E:\BlkCtl15.bin'
HEADER = bytes.fromhex('a55a5aa5e1320100')
TARGET = r'A:\Resource\Jpeg\GB_HDF.jpg'
SIZE = 56842
KINDS = {'probe': None, 'temporary': 'probe', 'install': 'temporary', 'restore': 'temporary'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def attempt_id(value):
    if not isinstance(value, str) or not re.fullmatch('[A-Z][A-Z0-9]{3}', value):
        raise ValueError('Attempt ID must be four uppercase alphanumeric characters beginning with a letter')
    return value


def internal(attempt, suffix):
    return fr'A:\Resource\Jpeg\{attempt}{suffix}.JPG'


def card(attempt, suffix, extension='JPG'):
    return fr'C:\{attempt}{suffix}.{extension}'


def literal_lines(payload):
    """Write nonzero runs into a fresh zero-extended file using bounded literals."""
    lines = []
    index = 0
    while index < len(payload):
        if payload[index] == 0:
            index += 1
            continue
        start = index
        while index < len(payload) and payload[index] != 0 and index - start < 42:
            index += 1
        lines.extend((f'fileseek fh {start} 0',
                      'filewrite fh ' + ''.join(f'#{value}' for value in payload[start:index])))
    return lines


class Script:
    def __init__(self, attempt, outputs, writing=False):
        self.log = card(attempt, 'LOG', 'TXT')
        self.writing = writing
        self.log_fields = {'started': '1'}
        self.lines = ['; GR IV HDF, user-reported firmware 1.11; experimental exFAT transport.',
                      '; Private generated payload. C: is camera SD. Verify full bytes and display separately.']
        for path in (self.log, *outputs):
            self.add(f"filesearch '{path}'", 'if result = 1 then', 'exit', 'endif')
        self.add(f"filecreate log '{self.log}'", 'if log < 0 then', 'exit', 'endif',
                 "filewriteln log 'started'", "filewriteln log '1'", 'fileclose log', 'error = 0')
        if writing:
            self.add('attempted = 0', 'rollback_attempted = 0', 'rollback_size_ok = 0')
        self.add('sz = -1', f"filestat '{MODEL}' sz")
        self.guard('sz < 8', 101)
        self.add(f"fileopen fh '{MODEL}' 0")
        self.guard('fh < 0', 102)
        for index in range(8):
            self.add('fileread fh 1 chunk', f'str2code b{index} chunk')
        self.add('fileclose fh')
        for index, value in enumerate(HEADER):
            self.guard(f'b{index} <> {value}', 110 + index)

    def add(self, *lines):
        self.lines.extend(lines)

    def guard(self, condition, code, destination='done'):
        self.add(f'if {condition} then', f'error = {code}', f'goto {destination}', 'endif')

    def size(self, path, code, length=SIZE, destination='done'):
        self.add('sz = -1', f"filestat '{path}' sz")
        self.guard('result <> 0', code, destination)
        self.guard(f'sz <> {length}', code + 1, destination)

    def copy(self, source, destination):
        if not source.startswith('A:\\'):
            raise ValueError('Every filecopy source must be internal A:')
        self.add(f"filecopy '{source}' '{destination}'")

    def checkpoint(self, name):
        self.log_fields[name] = '1'
        self.add(f"fileopen log '{self.log}' 1", 'if log < 0 then', 'exit', 'endif',
                 f"filewriteln log '{name}'", "filewriteln log '1'", 'fileclose log')

    def fresh_literal(self, path, payload, code):
        self.add(f"filecreate fh '{path}'")
        self.guard('fh < 0', code)
        self.add('fileclose fh', f"filetruncate '{path}' {len(payload)}")
        self.size(path, code + 1, len(payload))

    def finish(self):
        self.add(':done', f"fileopen log '{self.log}' 1", 'if log < 0 then', 'exit', 'endif')
        fields = {'error': '0'}
        if self.writing:
            fields.update(attempted='1', rollback_attempted='0', rollback_size_ok='0')
        for name in fields:
            self.add(f'int2str value {name}', f"filewriteln log '{name}'", 'filewriteln log value')
        self.add("filewriteln log 'finished'", "filewriteln log '1'", 'fileclose log', 'exit')
        self.log_fields.update(fields, finished='1')
        if max(map(len, self.lines)) >= 256:
            raise ValueError('Native line buffer exceeded')
        labels = {line[1:]: index for index, line in enumerate(self.lines) if line.startswith(':')}
        for index, line in enumerate(self.lines):
            if line.startswith('goto ') and labels[line[5:]] <= index:
                raise ValueError('Backward interpreted jump forbidden')
        return ('\r\n'.join(self.lines) + '\r\n').encode('ascii')


def _generate(kind, attempt, inputs, source=None):
    """Return script, complete expected output bytes and exact success log."""
    if kind == 'probe':
        payload = bytes(17) + bytes(range(1, 256)) + bytes(256) + bytes(range(255, 0, -1))
        payload = payload.ljust(1024, b'\0')
        outputs = {card(attempt, 'ZERO', 'BIN'): bytes(1024), card(attempt, 'DATA', 'BIN'): payload}
        s = Script(attempt, outputs)
        for suffix, data, code in (('ZERO', bytes(1024), 201), ('DATA', payload, 301)):
            path = card(attempt, suffix, 'BIN')
            s.fresh_literal(path, data, code)
            s.checkpoint('zero_extended' if suffix == 'ZERO' else 'data_extended')
            if suffix == 'DATA':
                s.add(f"fileopen fh '{path}' 0")
                s.guard('fh < 0', 304)
                s.add(*literal_lines(data), 'fileclose fh')
                s.size(path, 305, len(data))
                s.checkpoint('literal_write_finished')
    elif kind == 'temporary':
        old, new = internal(attempt, 'OLD'), internal(attempt, 'NEW')
        outputs = {card(attempt, 'CUR'): inputs['current.jpg'],
                   card(attempt, 'BAK'): inputs['current.jpg'], card(attempt, 'IMG'): inputs['candidate.jpg']}
        s = Script(attempt, outputs)
        s.size(TARGET, 121)
        s.add(f"getfileattr '{TARGET}'")
        s.guard('result <> 32', 123)
        for path, code in ((old, 124), (new, 125)):
            s.add(f"getfileattr '{path}'")
            s.guard('result <> -1', code)
        s.checkpoint('preflight_passed')
        for origin, destination, code in ((TARGET, card(attempt, 'CUR'), 201),
                                          (TARGET, old, 203), (old, card(attempt, 'BAK'), 205)):
            s.copy(origin, destination)
            s.size(destination, code)
        s.checkpoint('original_backup_readbacks_saved')
        s.fresh_literal(new, inputs['candidate.jpg'], 301)
        s.checkpoint('temporary_zero_extended')
        s.add(f"fileopen fh '{new}' 0")
        s.guard('fh < 0', 304)
        s.add(*literal_lines(inputs['candidate.jpg']), 'fileclose fh')
        s.size(new, 305)
        s.checkpoint('temporary_written')
        s.copy(new, card(attempt, 'IMG'))
        s.size(card(attempt, 'IMG'), 307)
        s.checkpoint('temporary_readback_saved')
    else:
        old, new = internal(source['attempt'], 'OLD'), internal(source['attempt'], 'NEW')
        backup = inputs['backup.jpg']
        if kind == 'install':
            outputs = {card(attempt, 'NEW'): inputs['candidate.jpg'], card(attempt, 'BAK'): backup,
                       card(attempt, 'PRE'): backup, card(attempt, 'OUT'): inputs['candidate.jpg']}
            reserved = [*outputs, card(attempt, 'RST')]
            sources = ((new, 201), (old, 203), (TARGET, 205))
            exports = ((new, card(attempt, 'NEW'), 301), (old, card(attempt, 'BAK'), 303),
                       (TARGET, card(attempt, 'PRE'), 305))
        else:
            outputs = {card(attempt, 'BAK'): backup, card(attempt, 'PRE'): inputs['active.bin'],
                       card(attempt, 'OUT'): backup}
            reserved = list(outputs)
            sources = ((old, 201), (TARGET, 203))
            exports = ((old, card(attempt, 'BAK'), 301), (TARGET, card(attempt, 'PRE'), 303))
        s = Script(attempt, reserved, writing=True)
        for path, code in sources:
            s.size(path, code)
        s.add(f"getfileattr '{TARGET}'")
        s.guard('result <> 32', 207)
        for origin, destination, code in exports:
            s.copy(origin, destination)
            s.size(destination, code)
        s.checkpoint('prewrite_readbacks_saved')
        if kind == 'install':
            s.checkpoint('write_started')
        s.add('attempted = 1')
        s.copy(new if kind == 'install' else old, TARGET)
        destination = 'rollback' if kind == 'install' else 'done'
        s.size(TARGET, 401, destination=destination)
        s.copy(TARGET, card(attempt, 'OUT'))
        s.size(card(attempt, 'OUT'), 403, destination=destination)
        if kind == 'install':
            s.add(f"getfileattr '{TARGET}'")
            s.guard('result <> 32', 405, 'rollback')
            s.checkpoint('target_readback_saved')
            s.add('goto done', ':rollback', 'rollback_attempted = 1')
            s.copy(old, TARGET)
            s.size(TARGET, 501)
            s.copy(TARGET, card(attempt, 'RST'))
            s.size(card(attempt, 'RST'), 503)
            s.add(f"getfileattr '{TARGET}'")
            s.guard('result <> 32', 505)
            s.add('rollback_size_ok = 1')
    script = s.finish()
    return script, {path[3:]: data for path, data in outputs.items()}, s.log_fields


def _jpeg(data):
    from PIL import Image, JpegImagePlugin
    if len(data) != SIZE:
        raise ValueError(f'JPEG must have the tested exact length {SIZE}')
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            if (image.format != 'JPEG' or image.mode != 'RGB' or image.size != (720, 480)
                    or image.info.get('progressive') or JpegImagePlugin.get_sampling(image) != 1):
                raise ValueError('JPEG must be baseline RGB 720x480 with 4:2:2 sampling')
        # SOF0 identifies baseline sequential DCT; reject extended sequential too.
        from PIL.JpegImagePlugin import MARKER
        stream = BytesIO(data)
        stream.read(2)
        while True:
            marker = stream.read(2)
            while marker == b'\xff\xff':
                marker = b'\xff' + stream.read(1)
            code = int.from_bytes(marker, 'big')
            if code in (0xFFC0, 0xFFC1, 0xFFC2):
                if code != 0xFFC0:
                    raise ValueError('JPEG must use baseline SOF0')
                break
            if code not in MARKER or len(marker) != 2:
                raise ValueError('Invalid JPEG marker before SOF0')
            length = int.from_bytes(stream.read(2), 'big')
            if length < 2 or len(stream.read(length - 2)) != length - 2:
                raise ValueError('Truncated JPEG marker')
    except (OSError, SyntaxError) as error:
        raise ValueError('JPEG must fully decode') from error


def _metadata(data):
    return {'bytes': len(data), 'sha256': sha(data)}


def _description(kind, attempt, inputs, source=None, source_hash=None):
    script, outputs, log = _generate(kind, attempt, inputs, source)
    manifest = {'schema': SCHEMA, 'kind': kind, 'attempt': attempt,
                'ancestors': [] if source is None else [*source['ancestors'], source['attempt']],
                'model': 'GR IV HDF', 'firmware_user_report': '1.11', 'target': TARGET,
                'inputs': {name: _metadata(data) for name, data in inputs.items()},
                'source_manifest_sha256': source_hash, 'script': _metadata(script),
                'expected_outputs': {name: _metadata(data) for name, data in outputs.items()},
                'expected_log': log}
    return manifest, script, outputs


def _path(package, relative):
    path = package / relative
    if not path.resolve().is_relative_to(package.resolve()):
        raise ValueError('Package path escapes its directory')
    return path


def _read(package, relative):
    return _path(package, relative).read_bytes()


def _load(package, expected_kind=None):
    manifest = json.loads(_read(package, 'manifest.json'))
    keys = {'schema', 'kind', 'attempt', 'ancestors', 'model', 'firmware_user_report', 'target',
            'inputs', 'source_manifest_sha256', 'script', 'expected_outputs', 'expected_log'}
    if not isinstance(manifest, dict) or set(manifest) != keys:
        raise ValueError('Unknown package schema')
    kind = manifest['kind']
    if not isinstance(kind, str) or kind not in KINDS or (expected_kind and kind != expected_kind):
        raise ValueError('Wrong package kind')
    attempt_id(manifest['attempt'])
    names = {'probe': set(), 'temporary': {'current.jpg', 'candidate.jpg'},
             'install': {'backup.jpg', 'candidate.jpg'}, 'restore': {'backup.jpg', 'active.bin'}}[kind]
    if not isinstance(manifest['inputs'], dict) or set(manifest['inputs']) != names:
        raise ValueError('Invalid package input paths')
    inputs = {name: _read(package, 'inputs/' + name) for name in sorted(names)}
    source = None
    source_hash = None
    if KINDS[kind]:
        source_path = _path(package, 'source')
        returned_path = _path(package, 'source-readbacks')
        source, _, _ = _load(source_path, KINDS[kind])
        verify(source_path, returned_path)
        source_hash = sha(_read(package, 'source/manifest.json'))
        source_inputs = {name: _read(package / 'source', 'inputs/' + name) for name in source['inputs']}
        if kind in ('install', 'restore'):
            if inputs['backup.jpg'] != source_inputs['current.jpg']:
                raise ValueError('Backup differs from verified temporary source')
            if kind == 'install' and inputs['candidate.jpg'] != source_inputs['candidate.jpg']:
                raise ValueError('Candidate differs from verified temporary source')
    for name, data in inputs.items():
        if name.endswith('.jpg'):
            _jpeg(data)
        elif len(data) != SIZE:
            raise ValueError('Recovery active reference must have the tested exact length')
    expected, script, outputs = _description(kind, manifest['attempt'], inputs, source, source_hash)
    ids = [*expected['ancestors'], manifest['attempt']]
    if len(set(ids)) != len(ids):
        raise ValueError('Reused attempt ID in package chain')
    if manifest != expected:
        raise ValueError('Changed package manifest or source hashes')
    if _read(package, 'script/startup.ttl') != script:
        raise ValueError('Changed generated script')
    return manifest, inputs, outputs


def _log_bytes(fields):
    return ''.join(f'{key}\r\n{value}\r\n' for key, value in fields.items()).encode('ascii')


def verify(package, readbacks):
    manifest, _, outputs = _load(package)
    for name, expected in outputs.items():
        if _read(readbacks, name) != expected:
            raise ValueError(f'Full readback mismatch: {name}; stop before another phase')
    if _read(readbacks, f"{manifest['attempt']}LOG.TXT") != _log_bytes(manifest['expected_log']):
        raise ValueError('Complete log does not show successful execution')
    return {'kind': manifest['kind'], 'complete_readbacks_verified': manifest['expected_outputs'],
            'successful_log_verified': True, 'camera_display_must_be_checked_separately': True}


def _fresh(output):
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Output must be a new or empty directory; backups are never overwritten')


def _snapshot(source, destination):
    manifest, _, _ = _load(source)
    for relative in ('manifest.json', 'script/startup.ttl', *('inputs/' + name for name in manifest['inputs'])):
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_read(source, relative))
    if KINDS[manifest['kind']]:
        _snapshot(source / 'source', destination / 'source')
        _save_readbacks(source / 'source', source / 'source-readbacks', destination / 'source-readbacks')


def _save_readbacks(source, returned, destination):
    manifest, _, _ = _load(source)
    destination.mkdir(parents=True)
    for name in (*manifest['expected_outputs'], f"{manifest['attempt']}LOG.TXT"):
        (destination / name).write_bytes(_read(returned, name))


def _build(kind, attempt, output, inputs, source=None, returned=None):
    attempt_id(attempt)
    _fresh(output)
    prior = None
    used = []
    if source is not None:
        verify(source, returned)
        prior, _, _ = _load(source, KINDS[kind])
        used = [*prior['ancestors'], prior['attempt']]
        ledger = source / 'used-attempts.json'
        if ledger.exists():
            saved = json.loads(_read(source, 'used-attempts.json'))
            if not isinstance(saved, list) or any(not isinstance(x, str) for x in saved):
                raise ValueError('Invalid local attempt ledger')
            used.extend(attempt_id(x) for x in saved)
        if attempt in used:
            raise ValueError('Reused attempt ID; choose a fresh ID and output directory')
    for name, data in inputs.items():
        if name.endswith('.jpg'):
            _jpeg(data)
        elif len(data) != SIZE:
            raise ValueError('Recovery active reference must have the tested exact length')
    manifest, script, _ = _description(kind, attempt, inputs, prior,
                                       sha(_read(source, 'manifest.json')) if source else None)
    if source is not None:
        # Consume freshness before local output creation; failed builds use a new ID.
        (source / 'used-attempts.json').write_text(json.dumps(sorted(set([*used, attempt]))) + '\n', encoding='ascii')
    (output / 'script').mkdir(parents=True, exist_ok=True)
    (output / 'script/startup.ttl').write_bytes(script)
    for name, data in inputs.items():
        (output / 'inputs').mkdir(exist_ok=True)
        (output / 'inputs' / name).write_bytes(data)
    if source is not None:
        _snapshot(source, output / 'source')
        _save_readbacks(source, returned, output / 'source-readbacks')
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='ascii')
    return manifest


def probe(attempt, output):
    return _build('probe', attempt, output, {})


def temporary(probe_package, probe_readbacks, current, candidate, attempt, output):
    return _build('temporary', attempt, output,
                  {'current.jpg': current.read_bytes(), 'candidate.jpg': candidate.read_bytes()},
                  probe_package, probe_readbacks)


def install(temporary_package, temporary_readbacks, attempt, output):
    _, inputs, _ = _load(temporary_package, 'temporary')
    return _build('install', attempt, output,
                  {'backup.jpg': inputs['current.jpg'], 'candidate.jpg': inputs['candidate.jpg']},
                  temporary_package, temporary_readbacks)


def restore(temporary_package, temporary_readbacks, active_reference, attempt, output):
    """Recover the verified temporary backup; no successful install/display needed.

    The active reference may be corrupt, but must retain the tested exact length.
    A zero/truncated/oversized target requires manual investigation, not this flow.
    """
    _, inputs, _ = _load(temporary_package, 'temporary')
    return _build('restore', attempt, output,
                  {'backup.jpg': inputs['current.jpg'], 'active.bin': active_reference.read_bytes()},
                  temporary_package, temporary_readbacks)


def add_parser(commands):
    parser = commands.add_parser('exfat', help=__doc__)
    phases = parser.add_subparsers(dest='phase', required=True)
    p = phases.add_parser('probe'); p.add_argument('attempt'); p.add_argument('output', type=Path)
    p = phases.add_parser('temporary')
    for name in ('probe_package', 'probe_readbacks', 'current', 'candidate'):
        p.add_argument(name, type=Path)
    p.add_argument('attempt'); p.add_argument('output', type=Path)
    for phase in ('install', 'restore'):
        p = phases.add_parser(phase)
        p.add_argument('temporary_package', type=Path); p.add_argument('temporary_readbacks', type=Path)
        if phase == 'restore':
            p.add_argument('active_reference', type=Path)
        p.add_argument('attempt'); p.add_argument('output', type=Path)
    p = phases.add_parser('verify'); p.add_argument('package', type=Path); p.add_argument('readbacks', type=Path)


def dispatch(args):
    values = vars(args).copy()
    values.pop('command')
    phase = values.pop('phase')
    return {'probe': probe, 'temporary': temporary, 'install': install,
            'restore': restore, 'verify': verify}[phase](**values)
