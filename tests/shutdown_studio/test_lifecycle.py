"""Exercise real dialog destruction and interpreter exit in isolated processes."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class LifecycleTests(unittest.TestCase):
    def test_dialogs_are_destroyed_before_interpreter_shutdown(self):
        script = '''
import tempfile
from unittest.mock import patch
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QDialog
from shiboken6 import isValid
from apps.gr_shutdown_studio.app import Studio, dispose_window
app = QApplication([])
with tempfile.TemporaryDirectory() as directory:
    settings = QSettings(directory + '/settings.ini', QSettings.IniFormat)
    with patch('apps.gr_shutdown_studio.app.QSettings', return_value=settings):
        window = Studio()
    window.show()
    def close_dialog():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                widget.reject()
    def exercise():
        for action in (window.show_settings, window.show_compatibility, window.show_research, window.show_user_guide) * 3:
            QTimer.singleShot(0, close_dialog)
            action()
        EXIT_ACTION
    QTimer.singleShot(0, exercise)
    assert app.exec() == 0
    dispose_window(window)
    assert not isValid(window)
    assert not app.topLevelWidgets()
'''
        for exit_action in ['window.close()', 'app.quit()']:
            with self.subTest(exit_action=exit_action):
                result = subprocess.run(
                    [sys.executable, '-c', script.replace('EXIT_ACTION', exit_action)],
                    cwd=Path(__file__).resolve().parents[2],
                    env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
