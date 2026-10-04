"""Build on the target OS: python apps/gr_shutdown_studio/build.py"""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'app-dist'
TOOLS=['create_factory_entry.py','gr4_model.py','gr4_shutdown.py','pad_jpeg.py',
       'gr3x_urban_jpeg.py','gr3x_urban_shutdown.py']
EXAMPLES=['identify-gr4-model.ttl.example','backup-gr4-family.ttl.example',
          'gr3x-urban-backup.ttl.example','gr3x-urban-restore.ttl.example']


def main():
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed',
          '--name','GR Shutdown Studio','--paths',str(ROOT),'--paths',str(ROOT/'tools'),
          '--distpath',str(OUTPUT),'--workpath',str(OUTPUT/'build'),
          '--specpath',str(OUTPUT/'spec'), '--exclude-module','tkinter']
    for name in TOOLS:
        args.extend(['--add-data',str(ROOT/'tools'/name)+os.pathsep+'tools',
                     '--hidden-import',name[:-3]])
    for name in EXAMPLES:
        args.extend(['--add-data',str(ROOT/'examples'/name)+os.pathsep+'examples'])
    for name in ['LICENSE','NOTICE']:
        args.extend(['--add-data',str(ROOT/name)+os.pathsep+'.'])
    if sys.platform=='darwin':
        args.extend(['--osx-bundle-identifier','io.radium.grshutdownstudio'])
    args.append(str(ROOT/'apps/gr_shutdown_studio/launcher.py'))
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(OUTPUT/'cache'))
    subprocess.run(args,cwd=ROOT,check=True,env=env)
    print('Built:',OUTPUT)

if __name__=='__main__':main()
