import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QLabel,QDialog
from apps.gr_shutdown_studio.app import Studio

APP=QApplication.instance() or QApplication([])

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.settings=QSettings(str(Path(self.tmp.name)/'settings.ini'),QSettings.IniFormat)
        with patch('apps.gr_shutdown_studio.app.QSettings',return_value=self.settings):
            self.window=Studio()
    def tearDown(self):
        self.window.close();self.window.deleteLater();APP.processEvents();self.tmp.cleanup()
    def test_settings_and_language_remain_bilingual(self):
        for language in ['zh','en']:
            self.window.language=language;self.window.translate();self.window.refresh()
            self.assertEqual(self.window.settings_button.text(),'Settings / 设置')
            def check(dialog):
                self.assertEqual(dialog.windowTitle(),'Settings / 设置')
                self.assertIn('Language / 语言',[x.text() for x in dialog.findChildren(QLabel)])
                return 0
            with patch.object(QDialog,'exec',check):self.window.show_settings()
    def test_actions_start_disabled_and_controls_follow_session_state(self):
        self.assertFalse(self.window.action.isEnabled())
        self.assertFalse(self.window.restore_button.isEnabled())
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'session','FAMILY')
        self.window.refresh();self.assertTrue(self.window.action.isEnabled())
        self.assertFalse(self.window.camera.isEnabled())
        self.window.session.data['state']='deployment_incomplete'
        self.window.refresh();self.assertFalse(self.window.action.isEnabled())
        self.assertFalse(self.window.restore_button.isEnabled())

if __name__=='__main__':unittest.main()
