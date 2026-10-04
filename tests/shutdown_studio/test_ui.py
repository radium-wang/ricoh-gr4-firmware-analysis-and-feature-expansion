import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QLabel,QDialog,QComboBox,QRadioButton,QTableWidget
from apps.gr_shutdown_studio.app import Studio, dispose_window

APP=QApplication.instance() or QApplication([])

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.settings=QSettings(str(Path(self.tmp.name)/'settings.ini'),QSettings.IniFormat)
        with patch('apps.gr_shutdown_studio.app.QSettings',return_value=self.settings):
            self.window=Studio()
    def tearDown(self):
        self.window.close();dispose_window(self.window);self.tmp.cleanup()
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
        self.assertFalse(self.window.action.isEnabled())
        self.window.firmware_input.setCurrentIndex(1)
        self.assertTrue(self.window.action.isEnabled())
        self.assertFalse(self.window.restore_button.isEnabled())
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'session','FAMILY','1.11')
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
        self.assertEqual(self.window.findChildren(QComboBox),[self.window.firmware_input])
        self.window.session=Session.create(Path(self.tmp.name)/'stages','FAMILY','1.11')
        for state in ['wait_preflight','wait_backup','wait_stage1','wait_install','wait_restore','wait_restore_check','verified','restored']:
            self.window.session.data['state']=state;self.window.refresh();APP.processEvents()
            self.assertIs(self.window.pages.currentWidget(),self.window.camera_page)
            self.assertTrue(self.window.card_panel.isVisible())
            self.assertFalse(self.window.mode.isVisible())
            self.assertFalse(self.window.preview_panel.isVisible())
            self.assertEqual(self.window.display.isVisible(),state in ['verified','restored'])
        self.window.session.data.update(state='backed_up',model='HDF');self.window.refresh();APP.processEvents()
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

    def test_changing_camera_requires_a_fresh_version_selection(self):
        self.window.firmware_input.setCurrentIndex(1)
        self.assertEqual(self.window.firmware_version(),'1.11')
        self.window.camera.options[1].setChecked(True)
        self.assertEqual(self.window.firmware_version(),'')
        self.assertFalse(self.window.action.isEnabled())
        self.window.firmware_input.setCurrentIndex(1)
        self.assertEqual(self.window.firmware_version(),'1.60')

    def test_other_version_cancel_or_invalid_input_cannot_start_session(self):
        from PySide6.QtWidgets import QInputDialog
        for value,accepted in [('2.00',False),('1.1',True)]:
            with patch.object(QInputDialog,'getText',return_value=(value,accepted)),patch.object(self.window,'error'):
                self.window.firmware_input.setCurrentIndex(self.window.firmware_input.findData('other'))
            self.assertEqual(self.window.firmware_version(),'')
            self.assertFalse(self.window.action.isEnabled())

    def test_open_session_displays_its_saved_version_without_reusing_selection(self):
        from apps.gr_shutdown_studio.core import Session
        from PySide6.QtWidgets import QFileDialog
        saved = Session.create(Path(self.tmp.name)/'saved','URBAN','1.60')
        self.window.firmware_input.setCurrentIndex(1)
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(saved.directory/'session.json'),'')):
            self.window.open_session()
        self.assertEqual(self.window.camera.currentIndex(),1)
        self.assertEqual(self.window.firmware_version(),'1.60')

    def test_design_and_finish_require_photo_and_confirmation(self):
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'gates','FAMILY','1.11')
        self.window.card_input.setText('/test-card')
        self.window.session.data.update(state='backed_up',model='HDF');self.window.refresh()
        self.assertFalse(self.window.action.isEnabled())
        self.window.image=Path('/selected-image.jpg');self.window.update_action()
        self.assertTrue(self.window.action.isEnabled())
        self.window.image=None
        self.window.session.data['state']='verified';self.window.refresh()
        self.assertFalse(self.window.action.isEnabled())
        self.window.display.setChecked(True)
        self.assertTrue(self.window.action.isEnabled())


    def test_design_does_not_present_original_as_the_selected_photo(self):
        from PIL import Image
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'design','FAMILY','1.11')
        Image.new('RGB',(720,480),'navy').save(self.window.session.directory/'original.jpg')
        self.window.session.data.update(state='backed_up',model='HDF');self.window.refresh()
        self.assertEqual(self.window.preview_label.text(),self.window.t('empty_preview'))
        photo=self.window.session.directory/'photo.jpg'
        Image.new('RGB',(720,480),'orange').save(photo)
        self.window.image=photo;self.window.preview();self.window.update_action()
        self.assertTrue(self.window.action.isEnabled())
        self.assertGreater(self.window.preview_label.pixmap().toImage().pixelColor(10,10).red(),240)


    def test_compatibility_lists_pending_editions_without_enabling_them(self):
        def inspect(dialog):
            table=dialog.findChild(QTableWidget)
            self.assertEqual(table.rowCount(),10)
            self.assertEqual(table.item(0,0).text(),'GR III')
            self.assertEqual(table.item(0,2).text(),self.window.t('pending'))
            return 0
        with patch.object(QDialog,'exec',inspect):self.window.show_compatibility()

    def test_unqualified_version_has_no_install_or_restore_action(self):
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'unqualified','FAMILY','1.10')
        self.window.session.data.update(state='backed_up',model='HDF')
        self.window.refresh()
        self.window.image=Path('/selected.jpg');self.window.update_action()
        self.assertTrue(self.window.action.isEnabled())
        self.assertEqual(self.window.action.text(),self.window.t('test_report'))
        self.assertIs(self.window.pages.currentWidget(),self.window.result_page)
        self.assertFalse(self.window.restore_button.isEnabled())
        self.assertFalse(self.window.preview_panel.isVisible())
        self.assertEqual(self.window.description.text(),self.window.t('blocked_profile'))
        with patch.object(self.window,'export_report') as export:
            self.window.next_step()
            export.assert_called_once_with()


    def test_restore_preview_shows_original_after_finishing(self):
        from PIL import Image
        from apps.gr_shutdown_studio.core import Session
        self.window.session=Session.create(Path(self.tmp.name)/'restore-session','FAMILY','1.11')
        Image.new('RGB',(720,480),'navy').save(self.window.session.directory/'original.jpg')
        Image.new('RGB',(720,480),'orange').save(self.window.session.directory/'prepared.jpg')
        self.window.session.data.update(state='complete',last_result='restored')
        self.window.refresh()
        color=self.window.preview_label.pixmap().toImage().pixelColor(10,10)
        self.assertLess(color.red(),10)
        self.assertGreater(color.blue(),100)

if __name__=='__main__':unittest.main()
