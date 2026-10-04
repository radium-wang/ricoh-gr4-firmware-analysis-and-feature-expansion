"""Persistent desktop workflow. No USB access or firmware installation."""
from __future__ import annotations

import hashlib
import io
import json
import os
import plistlib
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
# Existing CLI tools use sibling imports; keep their original implementations.
sys.path.insert(0, str(ROOT / 'tools'))
import gr4_shutdown as family
import gr3x_urban_jpeg as urban_jpeg
import gr3x_urban_shutdown as urban
import create_factory_entry as entry
family.ROOT = ROOT

SIZE = (720, 480)
TOKEN = 'GRSESSION.TXT'
PROBE = 'GBPROBE.TXT'
COPY = 'GBCOPY.TXT'
BACKUPS = family.BACKUPS
MAX_FILE = 4 * 1024 * 1024


class WorkflowError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path, limit=MAX_FILE) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise WorkflowError(f'Missing file or symbolic link: {path.name}')
    if not 0 < path.stat().st_size <= limit:
        raise WorkflowError(f'Empty or oversized file: {path.name}')
    return path.read_bytes()


def atomic(path: Path, data: bytes):
    if path.is_symlink() or path.parent.is_symlink():
        raise WorkflowError('Symbolic links are not supported.')
    temporary = path.with_name(path.name + '.studio-tmp')
    if temporary.exists() or temporary.is_symlink():
        raise WorkflowError(f'Interrupted write exists: {temporary.name}')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def filesystem(card: Path) -> str:
    """Only real volume roots can be used by the desktop installer."""
    card = Path(os.path.abspath(card))
    if card.is_symlink() or not card.is_dir():
        raise WorkflowError('Select the SD card root.')
    if sys.platform == 'darwin':
        if card.parent != Path('/Volumes'):
            raise WorkflowError('Select a mounted SD card under /Volumes.')
        result = subprocess.run(['diskutil', 'info', '-plist', str(card)],
                                capture_output=True, check=True, timeout=15)
        info = plistlib.loads(result.stdout)
        if Path(info.get('MountPoint', '')) != card:
            raise WorkflowError('Select the volume root, not a folder.')
        if info.get('Internal', True) or info.get('ReadOnlyVolume', False):
            raise WorkflowError('Select a writable external SD card.')
        return str(info.get('FilesystemName', info.get('FilesystemType', '')))
    if sys.platform == 'win32':
        import ctypes
        if card != Path(card.anchor):
            raise WorkflowError('Select the SD drive root, such as E:\\.')
        kernel = ctypes.windll.kernel32
        kernel.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        kernel.GetDriveTypeW.restype = ctypes.c_uint
        kernel.GetVolumeInformationW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
        kernel.GetVolumeInformationW.restype = ctypes.c_int
        if kernel.GetDriveTypeW(str(card)) not in (2, 3):
            raise WorkflowError('Select a removable or external SD drive.')
        # Never install to the Windows system volume.
        if card.anchor.casefold() == Path(os.environ.get('SystemRoot', 'C:\\Windows')).anchor.casefold():
            raise WorkflowError('The system drive cannot be used.')
        name = ctypes.create_unicode_buffer(64)
        if not kernel.GetVolumeInformationW(str(card), None, 0, None, None, None, name, len(name)):
            raise WorkflowError('Cannot read the SD card filesystem.')
        return name.value
    raise WorkflowError('SD deployment is supported on macOS and Windows.')


def validate_card(card: Path):
    value = filesystem(card).lower()
    if 'fat32' not in value and value != 'ms-dos fat32':
        raise WorkflowError('Use a FAT32 SD card. This app does not format cards.')
    if shutil.disk_usage(card).free < 10 * 1024 * 1024:
        raise WorkflowError('The SD card needs at least 10 MB free.')


def render_image(path: Path, mode='crop', horizontal=0.5, vertical=0.5, background='#111111') -> Image.Image:
    with Image.open(path) as source:
        source.load()
        image = ImageOps.exif_transpose(source).convert('RGBA')
    canvas = Image.new('RGB', image.size, background)
    canvas.paste(image, mask=image.getchannel('A'))
    if mode == 'crop':
        return ImageOps.fit(canvas, SIZE, method=Image.Resampling.LANCZOS,
                            centering=(horizontal, vertical))
    if mode == 'contain':
        image = ImageOps.contain(canvas, SIZE, method=Image.Resampling.LANCZOS)
        result = Image.new('RGB', SIZE, background)
        result.paste(image, ((720-image.width)//2, (480-image.height)//2))
        return result
    raise WorkflowError('Unknown crop mode.')


def jpeg_check(data: bytes):
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.format != 'JPEG' or image.size != SIZE:
            raise WorkflowError('Backup must be a readable 720 × 480 JPEG.')


def ttl(text: str) -> bytes:
    return ('\r\n'.join(text.splitlines()) + '\r\n').encode('ascii')


class Session:
    """One body, one computer backup, one persistent sequence of SD attempts."""
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.file = self.directory / 'session.json'
        self.data = json.loads(read(self.file).decode('utf-8'))
        if self.data.get('format') != 'gr-shutdown-studio-v1':
            raise WorkflowError('Unknown session format.')
        uuid.UUID(self.data['id'])
        if self.data['kind'] not in ('FAMILY', 'URBAN'):
            raise WorkflowError('Unknown camera workflow.')

    @classmethod
    def create(cls, directory: Path, kind: str):
        if kind not in ('FAMILY', 'URBAN'):
            raise WorkflowError('Unknown camera workflow.')
        if directory.exists():
            raise WorkflowError('Choose a new session directory.')
        directory = Path(os.path.abspath(directory))
        if sys.platform == 'darwin' and directory.parts[:2] == ('/', 'Volumes'):
            raise WorkflowError('Save the session on your computer, not on an external card.')
        if sys.platform == 'win32':
            import ctypes
            drive = ctypes.windll.kernel32.GetDriveTypeW
            drive.argtypes = [ctypes.c_wchar_p]
            drive.restype = ctypes.c_uint
            if drive(directory.anchor) != 3:
                raise WorkflowError('Save the session on a local computer drive.')
        directory.mkdir(parents=True)
        data = {'format': 'gr-shutdown-studio-v1', 'id': str(uuid.uuid4()),
                'kind': kind, 'state': 'new', 'managed': {}, 'attempt': 0}
        atomic(directory / 'session.json', json.dumps(data, indent=2).encode())
        return cls(directory)

    @property
    def state(self):
        return self.data['state']

    def save(self):
        atomic(self.file, json.dumps(self.data, indent=2).encode())

    def require(self, *states):
        if self.state not in states:
            raise WorkflowError(f'Finish the current step first: {self.state}')

    def card(self, path: Path, new=False):
        path = Path(os.path.abspath(path))
        validate_card(path)
        token = path / TOKEN
        if token.exists():
            if read(token).decode('ascii') != self.data['id']:
                raise WorkflowError('This SD card belongs to another session. Use that saved session.')
        elif not new:
            raise WorkflowError('Session marker missing. Reconnect the same SD card.')
        return path

    def deploy(self, card: Path, payload: dict[str, bytes], state: str, new=False):
        card = self.card(card, new)
        payload = dict(payload)
        payload[TOKEN] = self.data['id'].encode('ascii')
        managed = self.data['managed']
        # Validate every destination before touching any file. Photos are never destinations.
        for name, data in payload.items():
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or len(relative.parts) > 2:
                raise WorkflowError('Invalid deployment destination.')
            dest = card / relative
            if dest.is_symlink() or dest.parent.is_symlink():
                raise WorkflowError('SD card contains a symbolic link.')
            if dest.exists():
                digest = sha(dest.read_bytes()) if dest.is_file() else ''
                if digest != sha(data) and digest != managed.get(name):
                    raise WorkflowError(f'Existing file is not owned by this session: {name}. Save it before using this card.')
        # Persist intent before deployment. Any interruption is visible after reopening.
        previous = self.state
        self.data['state'] = 'deployment_incomplete'
        self.data['previous_state'] = previous
        self.data['attempt'] += 1
        self.data['intended_state'] = state
        self.data['managed'].update({name: sha(data) for name, data in payload.items()})
        self.save()
        archive = self.directory / 'deployments' / str(self.data['attempt'])
        archive.mkdir(parents=True)
        # Write startup last: the camera can never run a script lacking its prepared inputs.
        for name in sorted(payload, key=lambda name: name == 'script/startup.ttl'):
            dest = card / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            stored = archive / name
            stored.parent.mkdir(parents=True, exist_ok=True)
            stored.write_bytes(payload[name])
            atomic(dest, payload[name])
        self.data['state'] = state
        self.save()

    def begin_backup(self, card: Path):
        self.require('new')
        probe = f'GR-SHUTDOWN-STUDIO:{self.data["id"]}\r\n'.encode('ascii')
        script = ttl("filesearch 'C:\\GBCOPY.TXT'\nif result = 1 then\nexit\nendif\nfilecopy 'C:\\GBPROBE.TXT' 'C:\\GBCOPY.TXT'\nexit")
        files = entry.FILES if self.data['kind'] == 'FAMILY' else entry.GR3X_URBAN_160_FILES
        self.data['probe_sha256'] = sha(probe)
        self.deploy(card, {**files, PROBE: probe, 'script/startup.ttl': script}, 'wait_preflight', new=True)

    def archive(self, card: Path, names: list[str]):
        directory = self.directory / 'readbacks' / f'{self.data["attempt"]}-{self.state}-{uuid.uuid4().hex[:8]}'
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            source = card / name
            if source.is_symlink():
                raise WorkflowError('Readback symbolic links are not supported.')
            if source.is_file():
                if source.stat().st_size > MAX_FILE:
                    raise WorkflowError(f'Unexpected readback size: {name}')
                data = source.read_bytes()
                destination = directory / name
                # Each verification keeps a separate snapshot, including failed attempts.
                destination.write_bytes(data)

    def verify_preflight(self, card: Path):
        self.require('wait_preflight')
        card = self.card(card)
        self.archive(card, [PROBE, COPY])
        if sha(read(card / COPY)) != self.data['probe_sha256']:
            raise WorkflowError('SD copy check failed. No internal image write has been prepared.')
        names = ['GBMODEL.TXT', *BACKUPS.values()] if self.data['kind'] == 'FAMILY' else ['URBANBK.JPG', 'URBOLD.JPG']
        if any((card/name).exists() for name in names):
            raise WorkflowError('This card already contains backup outputs. Use a clean working card or the matching session.')
        template = 'backup-gr4-family.ttl.example' if self.data['kind'] == 'FAMILY' else 'gr3x-urban-backup.ttl.example'
        self.deploy(card, {'script/startup.ttl': ttl((ROOT/'examples'/template).read_text())}, 'wait_backup')

    def verify_backup(self, card: Path):
        self.require('wait_backup')
        card = self.card(card)
        if self.data['kind'] == 'FAMILY':
            model = read(card/'GBMODEL.TXT', 64).decode('ascii').strip()
            if model not in BACKUPS:
                raise WorkflowError('Camera model is unknown. Stop here.')
            name = BACKUPS[model]
            data = read(card/name)
            jpeg_check(data)
            self.archive(card, ['GBMODEL.TXT', name])
        else:
            model, name = 'URBAN', 'URBANBK.JPG'
            data = read(card/name)
            urban_jpeg.validate_original(data)
            if sha(read(card/'URBOLD.JPG')) != sha(data):
                raise WorkflowError('Urban internal backup differs from the original.')
            self.archive(card, [name, 'URBOLD.JPG'])
        original = self.directory/'original.jpg'
        if original.exists() and original.read_bytes() != data:
            raise WorkflowError('Saved original differs. It will not be overwritten.')
        if not original.exists():
            atomic(original, data)
        self.data.update(model=model, original_sha256=sha(data), original_size=len(data), state='backed_up')
        self.save()
        self.stop_script(card)

    def original(self):
        data = read(self.directory/'original.jpg')
        if len(data) != self.data['original_size'] or sha(data) != self.data['original_sha256']:
            raise WorkflowError('The computer backup changed. Stop and recover an intact backup.')
        jpeg_check(data)
        return data

    def prepare(self, image: Path, mode='crop', horizontal=0.5, vertical=0.5, background='#111111'):
        self.require('backed_up')
        self.original()
        image = render_image(image, mode, horizontal, vertical, background)
        image.save(self.directory/'artwork.png')
        package = self.directory/'package'
        if package.exists():
            # A failed generator may have left output; preserve it for inspection.
            raise WorkflowError('An earlier package exists. Inspect it before trying another image.')
        if self.data['kind'] == 'FAMILY':
            inputs = self.directory/'inputs'
            inputs.mkdir(exist_ok=True)
            (inputs/'GBMODEL.TXT').write_text(self.data['model'])
            (inputs/BACKUPS[self.data['model']]).write_bytes(self.original())
            manifest = family.prepare(inputs, self.directory/'artwork.png', package)
            candidate = package/'NEWGB.JPG'
            self.data['quality'] = manifest['jpeg_quality']
        else:
            candidate = self.directory/'candidate.jpg'
            urban_jpeg.encode(self.directory/'original.jpg', self.directory/'artwork.png', candidate)
            urban.build(self.directory/'original.jpg', candidate, package)
        data = read(candidate)
        jpeg_check(data)
        atomic(self.directory/'prepared.jpg', data)
        self.data.update(candidate_sha256=sha(data), state='prepared')
        self.save()

    def package_check(self):
        self.original()
        candidate = read(self.directory/'prepared.jpg')
        if sha(candidate) != self.data['candidate_sha256'] or len(candidate) != self.data['original_size']:
            raise WorkflowError('Prepared image changed. Installation is blocked.')
        package = self.directory/'package'
        if self.data['kind'] == 'FAMILY':
            family.verify(package, self.directory/'prepared.jpg')
        else:
            urban_jpeg.validate_candidate(self.original(), candidate)
            manifest = json.loads(read(package/'manifest.json').decode())
            if manifest.get('candidate_sha256') != sha(candidate) or manifest.get('original_sha256') != sha(self.original()):
                raise WorkflowError('The Urban package manifest changed.')
            expected_first = urban.temporary_script(candidate)[0]
            expected_second = urban.install_script()[0]
            if read(package/'01-temporary-only/script/startup.ttl') != expected_first or read(package/'02-install-after-readback/script/startup.ttl') != expected_second:
                raise WorkflowError('The Urban installation script changed.')
        return package

    def begin_install(self, card: Path):
        self.require('prepared')
        package = self.package_check()
        card = self.card(card)
        if self.data['kind'] == 'FAMILY':
            if read(card/BACKUPS[self.data['model']]) != self.original():
                raise WorkflowError('The SD backup differs from this session.')
            if read(card/'GBMODEL.TXT',64).decode().strip() != self.data['model']:
                raise WorkflowError('The SD model report differs.')
            if (card/'GBREAD.JPG').exists():
                raise WorkflowError('Existing GBREAD.JPG: preserve and inspect it before installing.')
            script = ttl(family.generate_write(self.data['model'],self.data['original_size']))
            self.deploy(card, {'NEWGB.JPG': read(self.directory/'prepared.jpg'), 'GBARM.TXT': b'1',
                               'script/startup.ttl': script}, 'wait_install')
        else:
            names=['URBLOG8.TXT','URBIMG8.JPG','URBORG8.JPG','URBPRE8.JPG']
            if any((card/n).exists() for n in names):
                raise WorkflowError('Urban stage-one outputs already exist. Do not reset or reuse them.')
            stage=package/'01-temporary-only'
            self.deploy(card, {'URBLOG8.TXT': b'', 'script/startup.ttl': read(stage/'script/startup.ttl')}, 'wait_stage1')

    def verify_stage1(self, card: Path):
        self.require('wait_stage1')
        card=self.card(card)
        self.archive(card,['URBLOG8.TXT','URBIMG8.JPG','URBORG8.JPG','URBPRE8.JPG'])
        urban.verify(self.directory/'package/manifest.json',card,1)
        self.package_check()
        if any((card/n).exists() for n in ['URBLOG9.TXT','URBNW9.JPG','URBOR9.JPG','URBPRE9.JPG','URBRD9.JPG']):
            raise WorkflowError('Urban stage-two outputs already exist.')
        script=read(self.directory/'package/02-install-after-readback/script/startup.ttl')
        self.deploy(card,{'URBLOG9.TXT':b'','script/startup.ttl':script},'wait_install')

    def verify_install(self, card: Path):
        self.require('wait_install')
        self.package_check()
        card=self.card(card)
        if self.data['kind']=='FAMILY':
            self.archive(card,['GBREAD.JPG','GBARM.TXT'])
            family.verify(self.directory/'package',card/'GBREAD.JPG')
        else:
            self.archive(card,['URBLOG9.TXT','URBNW9.JPG','URBOR9.JPG','URBPRE9.JPG','URBRD9.JPG','URBRS9.JPG'])
            urban.verify(self.directory/'package/manifest.json',card,2)
        self.data['state']='verified'
        self.save()
        self.stop_script(card)

    def begin_restore(self, card: Path):
        self.require('backed_up','prepared','wait_stage1','wait_install','verified','complete')
        self.original()
        card=self.card(card)
        if self.data['kind']=='FAMILY':
            if (card/'GBREST.JPG').exists():
                raise WorkflowError('Existing GBREST.JPG: preserve and inspect it before restoring.')
            model=self.data['model']
            # Restore only to an equal-length target; no truncation or deletion.
            script=ttl(family.generate_write(model,self.data['original_size'],True))
            payload={BACKUPS[model]:self.original(),'GBARM.TXT':b'1','script/startup.ttl':script}
            # After a camera consumes the permit, accept only the known consumed value.
            arm=card/'GBARM.TXT'
            if arm.exists() and read(arm,64)==b'0':
                self.data['managed']['GBARM.TXT']=sha(b'0')
        else:
            if (card/'URBREST.JPG').exists():
                raise WorkflowError('Existing URBREST.JPG: preserve and inspect it before restoring.')
            payload={'script/startup.ttl':ttl((ROOT/'examples/gr3x-urban-restore.ttl.example').read_text())}
        self.deploy(card,payload,'wait_restore')

    def verify_restore(self, card: Path):
        self.require('wait_restore')
        card=self.card(card)
        self.original()
        name='GBREST.JPG' if self.data['kind']=='FAMILY' else 'URBREST.JPG'
        self.archive(card,[name])
        data=read(card/name)
        if len(data)!=self.data['original_size'] or sha(data)!=self.data['original_sha256']:
            raise WorkflowError('Restored readback differs from the original.')
        self.data['state']='restored'
        self.save()
        self.stop_script(card)

    def stop_script(self, card: Path):
        startup=card/'script/startup.ttl'
        if startup.exists():
            if startup.is_symlink() or sha(startup.read_bytes())!=self.data['managed'].get('script/startup.ttl'):
                raise WorkflowError('The startup script changed. It was not removed.')
            startup.unlink()

    def finish(self, card: Path):
        self.require('verified','restored')
        card=self.card(card)
        self.stop_script(card)
        # Retain entry files so the user can still disable Script from the factory menu.
        self.data['last_result']=self.state
        self.data['state']='complete'
        self.save()
