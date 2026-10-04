# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

sys.path.insert(0, str(Path(SPECPATH).parents[1]))
from apps.gr_shutdown_studio import __version__
from apps.gr_shutdown_studio.build import ROOT, TOOLS, EXAMPLES

datas = [(str(ROOT/'tools'/name), 'tools') for name in TOOLS]
datas += [(str(ROOT/'examples'/name), 'examples') for name in EXAMPLES]
datas += [(str(ROOT/name), '.') for name in ['LICENSE', 'NOTICE']]

a = Analysis(
    [str(ROOT/'apps/gr_shutdown_studio/launcher.py')],
    pathex=[str(ROOT), str(ROOT/'tools')],
    binaries=[], datas=datas,
    hiddenimports=[name[:-3] for name in TOOLS],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter'], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='GR Shutdown Studio', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
               upx_exclude=[], name='GR Shutdown Studio')
if sys.platform == 'darwin':
    app = BUNDLE(
        coll, name='GR Shutdown Studio.app', icon=None,
        bundle_identifier='io.radium.grshutdownstudio', version=__version__,
        info_plist={'CFBundleVersion': __version__, 'LSMinimumSystemVersion': '13.0'},
    )
