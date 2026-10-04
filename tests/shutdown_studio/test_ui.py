import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QLabel,QDialog,QComboBox,QRadioButton
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
                self.assertEqual([x.text() for x in dialog.findChildren(QRadioButton)],['English','简体中文'])
                self.assertEqual(dialog.findChildren(QComboBox),[])
                return 0
            with patch.object(QDialog,'exec',check):self.window.show_settings()
    def test_primary_action_requires_the_current_step_inputs(self):
        self.assertTrue(self.window.action.isEnabled())
        self.assertFalse(self.window.restore_button.isEnabled())
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'session','FAMILY')
        self.window.refresh();self.assertFalse(self.window.action.isEnabled())
        self.window.card_input.setText('/test-card');self.window.ack.setChecked(True)
        self.assertTrue(self.window.action.isEnabled())
        self.assertFalse(self.window.camera.isEnabled())
        self.window.session.data['state']='deployment_incomplete'
        self.window.refresh();self.assertFalse(self.window.action.isEnabled())
        self.assertFalse(self.window.restore_button.isEnabled())


    def test_only_current_phase_controls_are_visible(self):
        from apps.gr_shutdown_studio.core import Session
        self.window.show();APP.processEvents()
        self.assertTrue(self.window.camera.isVisible())
        self.assertFalse(self.window.card_panel.isVisible())
        self.assertFalse(self.window.preview_panel.isVisible())
        self.assertEqual(self.window.findChildren(QComboBox),[])
        self.window.session=Session.create(Path(self.tmp.name)/'stages','FAMILY')
        for state in ['wait_preflight','wait_backup','wait_stage1','wait_install','wait_restore','verified','restored']:
            self.window.session.data['state']=state;self.window.refresh();APP.processEvents()
            self.assertIs(self.window.pages.currentWidget(),self.window.camera_page)
            self.assertTrue(self.window.card_panel.isVisible())
            self.assertFalse(self.window.mode.isVisible())
            self.assertFalse(self.window.preview_panel.isVisible())
            self.assertEqual(self.window.display.isVisible(),state in ['verified','restored'])
        self.window.session.data['state']='backed_up';self.window.refresh();APP.processEvents()
        self.assertIs(self.window.pages.currentWidget(),self.window.design_page)
        self.assertTrue(self.window.mode.isVisible())
        self.assertTrue(self.window.preview_panel.isVisible())
        self.assertFalse(self.window.card_panel.isVisible())
        self.assertFalse(self.window.ack.isVisible())
        self.window.mode.setCurrentIndex(1);APP.processEvents()
        self.assertFalse(self.window.position_panel.isVisible())

    def test_first_action_opens_backup_folder_selection(self):
        with patch.object(self.window,'new_session') as create:
            self.window.next_step();create.assert_called_once_with()

    def test_design_and_finish_require_photo_and_confirmation(self):
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'gates','FAMILY')
        self.window.card_input.setText('/test-card')
        self.window.session.data['state']='backed_up';self.window.refresh()
        self.assertFalse(self.window.action.isEnabled())
        self.window.image=Path('/selected-image.jpg');self.window.update_action()
        self.assertTrue(self.window.action.isEnabled())
        self.window.image=None
        self.window.session.data['state']='verified';self.window.refresh()
        self.assertFalse(self.window.action.isEnabled())
        self.window.display.setChecked(True)
        self.assertTrue(self.window.action.isEnabled())


    def test_restore_preview_shows_original_after_finishing(self):
        from PIL import Image
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'restore-session','FAMILY')
        Image.new('RGB',(720,480),'navy').save(self.window.session.directory/'original.jpg')
        Image.new('RGB',(720,480),'orange').save(self.window.session.directory/'prepared.jpg')
        self.window.session.data.update(state='complete',last_result='restored')
        self.window.refresh()
        color=self.window.preview_label.pixmap().toImage().pixelColor(10,10)
        self.assertLess(color.red(),10)
        self.assertGreater(color.blue(),100)

if __name__=='__main__':unittest.main()
