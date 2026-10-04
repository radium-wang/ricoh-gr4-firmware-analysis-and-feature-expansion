import plistlib
import tempfile
import unittest
from pathlib import Path
from apps.gr_shutdown_studio.build import check_macos_bundle


class BundleTests(unittest.TestCase):
    def test_packaging_rejects_missing_or_default_app_version(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            contents = bundle/'Contents'
            contents.mkdir()
            for info in [{}, {'CFBundleShortVersionString': '0.0.0'},
                         {'CFBundleShortVersionString': '0.2.1', 'CFBundleVersion': '0.2.0'}]:
                (contents/'Info.plist').write_bytes(plistlib.dumps(info))
                with self.assertRaises(RuntimeError):
                    check_macos_bundle(bundle, '0.2.1', '6.11.2')

    def test_packaging_rejects_stale_qt_even_with_correct_app_version(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            qt = bundle/'Contents/Frameworks/PySide6/Qt/lib/QtCore.framework/Resources'
            qt.mkdir(parents=True)
            (bundle/'Contents/Info.plist').write_bytes(plistlib.dumps({
                'CFBundleShortVersionString': '0.2.1', 'CFBundleVersion': '0.2.1'}))
            (qt/'Info.plist').write_bytes(plistlib.dumps({'CFBundleVersion': '6.8.3'}))
            with self.assertRaises(RuntimeError):
                check_macos_bundle(bundle, '0.2.1', '6.11.2')
            (qt/'Info.plist').write_bytes(plistlib.dumps({'CFBundleVersion': '6.11.2'}))
            check_macos_bundle(bundle, '0.2.1', '6.11.2')


if __name__ == '__main__':
    unittest.main()
