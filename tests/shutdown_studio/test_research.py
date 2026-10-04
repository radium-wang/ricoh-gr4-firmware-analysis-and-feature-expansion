import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from apps.gr_shutdown_studio.compatibility import PROFILES, installation_allowed, research_versions
from apps.gr_shutdown_studio.core import Session, WorkflowError
from apps.gr_shutdown_studio.research import ResearchRecord


def update_file(path, model, version):
    data = bytearray(128)
    data[:8] = b'RICOH\0\0\0'
    data[8:8+len(model)] = model.encode()
    data[0x38:0x3c] = bytes(version)
    path.write_bytes(data)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.record = ResearchRecord.create(self.root/'record', 'gr3', '2.10')

    def tearDown(self):
        self.temp.cleanup()

    def photo(self, name='source.jpg', color='navy'):
        path = self.root/name
        image = Image.new('RGB', (720,480), color)
        exif = image.getexif()
        exif[0x010F] = 'PRIVATE CAMERA OWNER'
        image.save(path, exif=exif)
        return path

    def test_every_catalog_model_and_other_versions_can_collect_evidence(self):
        for profile in PROFILES:
            record = ResearchRecord.create(self.root/profile.id, profile.id, '9.99')
            report = record.report()
            self.assertEqual(report['declared_firmware'], '9.99')
            self.assertFalse(report['installation_qualified'])
            self.assertFalse(report['camera_scripts_generated'])
            with self.assertRaises(WorkflowError):
                Session(record.directory)
        self.assertEqual(research_versions('gr4-mono'), ())
        self.assertIn('2.00', research_versions('gr3'))

    def test_original_is_copied_without_stripping_or_exporting_private_metadata(self):
        source = self.photo()
        self.record.add_original(source)
        for name in ['original.jpg', 'recovery/original.jpg']:
            self.assertEqual((self.record.directory/name).read_bytes(), source.read_bytes())
        report = self.record.report()
        text = json.dumps(report)
        self.assertTrue(report['original_copies_verified_on_computer'])
        self.assertEqual(report['original_evidence']['width'], 720)
        for private in ['PRIVATE CAMERA OWNER', str(self.root), 'source.jpg']:
            self.assertNotIn(private, text)
        self.assertFalse(report['resource_path_verified'])

    def test_different_original_cannot_replace_either_copy(self):
        first = self.photo()
        self.record.add_original(first)
        with self.assertRaises(WorkflowError):
            self.record.add_original(self.photo('other.jpg', 'orange'))
        for name in ['original.jpg', 'recovery/original.jpg']:
            self.assertEqual((self.record.directory/name).read_bytes(), first.read_bytes())

    def test_corrupt_original_or_recovery_blocks_report_export(self):
        source = self.photo()
        self.record.add_original(source)
        for name in ['original.jpg', 'recovery/original.jpg']:
            target = self.record.directory/name
            target.write_bytes(b'damaged')
            with self.assertRaises(WorkflowError):
                self.record.export(self.root/'report.json')
            self.assertFalse((self.root/'report.json').exists())
            target.write_bytes(source.read_bytes())

    def test_wrong_family_update_is_rejected_and_version_mismatch_is_explicit(self):
        update = self.root/'update.bin'
        update_file(update, 'GR IV', [1,11,10,7])
        with self.assertRaises(WorkflowError):
            self.record.add_firmware(update)
        self.assertNotIn('firmware_evidence', self.record.data)
        update_file(update, 'GR III', [2,0,0,0])
        self.record.add_firmware(update)
        report = self.record.report()
        self.assertFalse(report['header_menu_version_matches'])
        self.assertFalse(report['installed_firmware_authenticated'])
        update_file(update, 'GR III', [2,10,0,0])
        self.record.add_firmware(update)
        self.assertTrue(self.record.report()['header_menu_version_matches'])

    def test_no_evidence_can_enable_an_unqualified_installer(self):
        record = ResearchRecord.create(self.root/'gr4', 'gr4', '1.04')
        record.add_original(self.photo())
        record.observe('factory_menu', 'visible')
        update = self.root/'update.bin'
        update_file(update, 'GR IV', [1,4,0,0])
        record.add_firmware(update)
        self.assertFalse(record.report()['installation_qualified'])
        self.assertFalse(installation_allowed('FAMILY','STANDARD','1.04'))

    def test_reopened_record_keeps_observations_and_existing_reports(self):
        self.record.observe('shutdown_graphic', 'present')
        reopened = ResearchRecord(self.record.directory)
        self.assertEqual(reopened.report()['observations']['shutdown_graphic'], 'present')
        target = self.root/'report.json'
        reopened.export(target)
        original = target.read_bytes()
        with self.assertRaises(WorkflowError): reopened.export(target)
        self.assertEqual(target.read_bytes(), original)
        with self.assertRaises(WorkflowError): reopened.observe('factory_menu', str(self.root))

    def test_non_jpeg_input_does_not_create_original_files(self):
        path = self.root/'photo.png'
        Image.new('RGB', (720,480)).save(path)
        with self.assertRaises(WorkflowError): self.record.add_original(path)
        self.assertFalse((self.record.directory/'original.jpg').exists())


if __name__ == '__main__': unittest.main()
