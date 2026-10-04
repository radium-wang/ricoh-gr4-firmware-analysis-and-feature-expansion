"""Local community evidence records. No camera connection or script generation."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

from PIL import Image
from . import __version__
from .compatibility import camera_family, profile_by_id
from .core import WorkflowError, atomic, read, sha
import audit_shutdown_compatibility

OBSERVATIONS = {
    'factory_menu': ('not_checked', 'visible', 'unavailable'),
    'shutdown_graphic': ('not_checked', 'present', 'absent'),
}


def jpeg_metadata(data):
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'JPEG' or image.width * image.height > 16_000_000:
            raise WorkflowError('Use a JPEG of at most 16 million pixels.')
        image.load()
        tables = json.dumps(getattr(image, 'quantization', {}), sort_keys=True).encode()
        return {'sha256': sha(data), 'bytes': len(data), 'width': image.width,
                'height': image.height, 'mode': image.mode,
                'progressive': bool(image.info.get('progressive') or image.info.get('progression')),
                'quantization_sha256': sha(tables),
                'source': 'user_supplied_file_not_camera_attested'}


class ResearchRecord:
    """Kept separate from installer sessions; importing evidence cannot unlock writes."""
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.file = self.directory / 'research.json'
        self.data = json.loads(read(self.file).decode())
        if self.data.get('format') != 'gr-shutdown-research-v1':
            raise WorkflowError('Not a research record.')
        if not profile_by_id(self.data.get('profile_id')) or not re.fullmatch(r'\d{1,2}\.\d{2}', self.data.get('firmware', '')):
            raise WorkflowError('Invalid camera or firmware in research record.')

    @classmethod
    def create(cls, directory, profile_id, firmware):
        if not profile_by_id(profile_id) or not isinstance(firmware, str) or not re.fullmatch(r'\d{1,2}\.\d{2}', firmware):
            raise WorkflowError('Choose a camera and its menu firmware version.')
        directory = Path(directory).resolve()
        if directory.exists():
            raise WorkflowError('Choose a new research directory.')
        if sys.platform == 'darwin' and directory.parts[:2] == ('/', 'Volumes'):
            raise WorkflowError('Keep the research record on your computer, not the SD card.')
        if sys.platform == 'win32':
            import ctypes
            drive = ctypes.windll.kernel32.GetDriveTypeW
            drive.argtypes = [ctypes.c_wchar_p]
            drive.restype = ctypes.c_uint
            if drive(directory.anchor) != 3:
                raise WorkflowError('Keep the research record on a local computer drive.')
        directory.mkdir(parents=True)
        data = {'format': 'gr-shutdown-research-v1', 'profile_id': profile_id,
                'firmware': firmware, 'observations': {key: 'not_checked' for key in OBSERVATIONS}}
        atomic(directory/'research.json', json.dumps(data, indent=2).encode())
        return cls(directory)

    def save(self):
        atomic(self.file, json.dumps(self.data, indent=2).encode())

    def observe(self, key, value):
        if key not in OBSERVATIONS or value not in OBSERVATIONS[key]:
            raise WorkflowError('Unknown observation.')
        self.data['observations'][key] = value
        self.save()

    def add_firmware(self, path):
        report = audit_shutdown_compatibility.inspect(Path(path))
        if report['container_model'] != camera_family(self.data['profile_id']):
            raise WorkflowError('This update file belongs to a different camera family.')
        # The file can be a different release; record rather than claiming a match.
        self.data['firmware_evidence'] = report
        self.save()

    def add_original(self, path):
        data = read(Path(path))
        metadata = jpeg_metadata(data)
        targets = [self.directory/'original.jpg', self.directory/'recovery/original.jpg']
        for target in targets:
            if target.exists() or target.is_symlink():
                if read(target) != data:
                    raise WorkflowError('An existing original differs. It will not be replaced.')
        if targets[1].parent.is_symlink():
            raise WorkflowError('The recovery folder must not be a symbolic link.')
        targets[1].parent.mkdir(exist_ok=True)
        for target in targets:
            if not target.exists():
                atomic(target, data)
            if read(target) != data:
                raise WorkflowError('Original copy verification failed.')
        self.data['original_evidence'] = metadata
        self.save()

    def report(self):
        original = self.data.get('original_evidence')
        if original:
            for name in ['original.jpg', 'recovery/original.jpg']:
                if sha(read(self.directory/name)) != original['sha256']:
                    raise WorkflowError('Original backup changed. Recover an intact copy before exporting.')
        # Only explicit metadata fields; no filenames, EXIF, paths or free-text notes.
        firmware = self.data.get('firmware_evidence', {})
        fw_keys = ['container_model', 'container_sha256', 'container_bytes', 'header_version', 'header_version_components']
        image_keys = ['sha256', 'bytes', 'width', 'height', 'mode', 'progressive', 'quantization_sha256', 'source']
        report = {'format': 'gr-shutdown-research-report-v1', 'app_version': __version__,
                  'camera': profile_by_id(self.data['profile_id']).name,
                  'profile_id': self.data['profile_id'], 'declared_firmware': self.data['firmware'],
                  'firmware_source': 'user_camera_menu',
                  'observations': {key: self.data['observations'].get(key, 'not_checked') for key in OBSERVATIONS},
                  'firmware_evidence': {key: firmware[key] for key in fw_keys if key in firmware},
                  'original_evidence': {key: original[key] for key in image_keys if original and key in original},
                  'original_copies_verified_on_computer': bool(original),
                  'installed_firmware_authenticated': False, 'resource_path_verified': False,
                  'installation_qualified': False, 'full_app_camera_qualified': False,
                  'camera_scripts_generated': False}
        parts = firmware.get('header_version_components', [])
        report['header_menu_version_matches'] = (
            f'{parts[0]}.{parts[1]:02d}' == self.data['firmware'] if len(parts) == 4 else None)
        return report

    def export(self, destination):
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise WorkflowError('Choose a new report filename; existing files are preserved.')
        atomic(destination, (json.dumps(self.report(), indent=2)+'\n').encode())
