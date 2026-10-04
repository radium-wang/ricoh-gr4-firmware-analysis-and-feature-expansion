import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from apps.gr_shutdown_studio.research import ResearchRecord
from apps.gr_shutdown_studio.research_ui import ResearchDialog

APP = QApplication.instance() or QApplication([])


class ResearchInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dialog = ResearchDialog(None, 'zh')

    def tearDown(self):
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.temp.cleanup()

    def test_all_models_available_and_switch_requires_version_selection(self):
        self.assertEqual(self.dialog.camera.count(), 10)
        self.assertFalse(self.dialog.create_button.isEnabled())
        self.dialog.firmware.setCurrentIndex(1)
        self.assertEqual(self.dialog.firmware.currentData(), '2.10')
        self.assertTrue(self.dialog.create_button.isEnabled())
        self.dialog.camera.setCurrentIndex(self.dialog.camera.findData('gr4-mono'))
        self.assertIsNone(self.dialog.firmware.currentData())
        self.assertEqual(self.dialog.firmware.count(), 2)
        self.assertFalse(self.dialog.create_button.isEnabled())

    def test_open_record_restores_camera_version_and_observations(self):
        record = ResearchRecord.create(Path(self.temp.name)/'saved', 'gr3x-hdf', '1.42')
        record.observe('factory_menu', 'visible')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(record.file), '')):
            self.dialog.open_record()
        self.assertEqual(self.dialog.camera.currentData(), 'gr3x-hdf')
        self.assertEqual(self.dialog.firmware.currentData(), '1.42')
        self.assertEqual(self.dialog.observations['factory_menu'].currentData(), 'visible')
        self.assertFalse(self.dialog.camera.isEnabled())
        self.assertTrue(self.dialog.export_button.isEnabled())

    def test_create_record_only_creates_computer_files(self):
        self.dialog.firmware.setCurrentIndex(1)
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=self.temp.name):
            self.dialog.create_record()
        self.assertIsNotNone(self.dialog.record)
        self.assertEqual([p.name for p in self.dialog.record.directory.iterdir()], ['research.json'])
        self.assertFalse(self.dialog.record.report()['camera_scripts_generated'])

    def test_unsupported_camera_can_export_without_firmware_file_or_original(self):
        self.dialog.camera.setCurrentIndex(self.dialog.camera.findData('gr3x'))
        self.dialog.firmware.setCurrentIndex(self.dialog.firmware.findData('1.60'))
        with patch.object(QFileDialog, 'getExistingDirectory', return_value=self.temp.name):
            self.dialog.create_record()
        self.dialog.observations['shutdown_graphic'].setCurrentIndex(
            self.dialog.observations['shutdown_graphic'].findData('present'))
        report = Path(self.temp.name)/'report.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(report), '')), \
                patch.object(QMessageBox, 'information'):
            self.dialog.export_report()
        data = json.loads(report.read_text(encoding='utf-8'))
        self.assertFalse(data['camera_scripts_generated'])
        self.assertFalse(data['installation_qualified'])
        self.assertEqual(data['profile_id'], 'gr3x')
        self.assertEqual(data['observations']['factory_menu'], 'not_checked')
        self.assertEqual(data['observations']['shutdown_graphic'], 'present')
        self.assertEqual(data['original_evidence'], {})
        self.assertEqual(data['firmware_evidence'], {})


if __name__ == '__main__': unittest.main()
