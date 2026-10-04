"""Build on the target OS: python apps/gr_shutdown_studio/build.py"""
from pathlib import Path
import os
import plistlib
import shutil
import subprocess
import sys
from importlib.metadata import version

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'app-dist'
TOOLS=['create_factory_entry.py','gr4_model.py','gr4_shutdown.py','pad_jpeg.py',
       'gr3x_urban_jpeg.py','gr3x_urban_shutdown.py','audit_shutdown_compatibility.py']
EXAMPLES=['identify-gr4-model.ttl.example','backup-gr4-family.ttl.example',
          'gr3x-urban-backup.ttl.example','gr3x-urban-restore.ttl.example']
DOCUMENTS=['docs/extensions/shutdown-studio-user-guide.md']


def check_macos_bundle(bundle, app_version, qt_version):
    info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
    if (info.get('CFBundleShortVersionString'), info.get('CFBundleVersion')) != (app_version, app_version):
        raise RuntimeError('Packaged app version differs from the source version.')
    qt_info = bundle / 'Contents/Frameworks/PySide6/Qt/lib/QtCore.framework/Resources/Info.plist'
    if plistlib.loads(qt_info.read_bytes()).get('CFBundleVersion') != qt_version:
        raise RuntimeError('The bundle contains a different Qt runtime.')


def main():
    sys.path.insert(0, str(ROOT))
    from apps.gr_shutdown_studio import __version__
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean',
          '--distpath',str(OUTPUT),'--workpath',str(OUTPUT/'build'),
          str(ROOT/'apps/gr_shutdown_studio/studio.spec')]
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(OUTPUT/'cache'))
    subprocess.run(args,cwd=ROOT,check=True,env=env)
    guide_folder = OUTPUT/'GR Shutdown Studio' if sys.platform == 'win32' else OUTPUT
    shutil.copyfile(ROOT/DOCUMENTS[0], guide_folder/'START-HERE.txt')
    if sys.platform == 'darwin':
        bundle = OUTPUT/'GR Shutdown Studio.app'
        check_macos_bundle(bundle, __version__, version('PySide6-Essentials'))
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(bundle)], check=True)
    print('Built:',OUTPUT)

if __name__=='__main__':main()
