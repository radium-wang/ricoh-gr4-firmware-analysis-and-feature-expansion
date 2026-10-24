#!/usr/bin/env python3
# License: see LICENSE
"""Generate local, automatic GR IV-family single-image workflows. No card I/O."""
import argparse
import hashlib
import json
import shutil
from io import BytesIO
from pathlib import Path

try:
    from .gr4_model import MODELS
    from .pad_jpeg import pad_jpeg
    from . import gr4_hdf_exfat
except ImportError:
    from gr4_model import MODELS
    from pad_jpeg import pad_jpeg
    import gr4_hdf_exfat

ROOT = Path(__file__).resolve().parents[1]
BACKUPS = {'STANDARD': 'GBSTD.JPG', 'HDF': 'GBHDF.JPG', 'MONO': 'GBMONO.JPG'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identify_script():
    text = (ROOT / 'examples/identify-gr4-model.ttl.example').read_text()
    return text[:text.index(':report')] + ':report\n'


def routing(expected=None):
    text = identify_script()
    if expected:
        text += f"strcompare model '{expected}'\nif result <> 0 then\n    exit\nendif\n"
    text += "target = ''\nbackup = ''\n"
    for label, path in MODELS.values():
        text += f"strcompare model '{label}'\nif result = 0 then\n    target = '{path}'\n    backup = 'C:\\{BACKUPS[label]}'\nendif\n"
    return text + "strcompare model 'UNKNOWN'\nif result = 0 then\n    exit\nendif\n"


def size_gate(path, size):
    return f"sz = -1\nfilestat {path} sz\nif sz <> {size} then\n    exit\nendif\n"


def generate_backup():
    return routing() + """; Only SD-card output; preserve the first backup.
filecreate fh 'C:\\GBMODEL.TXT'
if fh < 0 then
    exit
endif
filewrite fh model
fileclose fh
filesearch backup
if result = 1 then
    exit
endif
sz = -1
filestat target sz
if sz < 4 then
    exit
endif
if sz > 2097152 then
    exit
endif
filecopy target backup
exit
"""


def generate_write(model, length, restore=False):
    output = 'GBREST.JPG' if restore else 'GBREAD.JPG'
    source = 'backup' if restore else "'C:\\NEWGB.JPG'"
    text = routing(model)
    text += f"filesearch 'C:\\{output}'\nif result = 1 then\n    exit\nendif\n"
    text += size_gate('backup', length) + size_gate('target', length)
    if not restore:
        text += size_gate(source, length)
    # Consume the one-shot permit before attempting any target mutation.
    text += "fileopen fh 'C:\\GBARM.TXT' 0\nif fh < 0 then\n    exit\nendif\nfileread fh 1 arm\nfileclose fh\nstrcompare arm '1'\nif result <> 0 then\n    exit\nendif\n"
    text += "filecreate fh 'C:\\GBARM.TXT'\nif fh < 0 then\n    exit\nendif\nfilewrite fh '0'\nfileclose fh\n"
    text += "fileopen fh 'C:\\GBARM.TXT' 0\nif fh < 0 then\n    exit\nendif\nfileread fh 1 arm\nfileclose fh\nstrcompare arm '0'\nif result <> 0 then\n    exit\nendif\n"
    return text + f"filecopy {source} target\nfilecopy target 'C:\\{output}'\nexit\n"


def fresh_output(path):
    if path.exists() and any(path.iterdir()):
        raise ValueError('Output must be a new or empty directory; existing backups are never overwritten')
    (path / 'script').mkdir(parents=True, exist_ok=True)


def prepare(card, image, output):
    from PIL import Image, ImageOps
    model = (card / 'GBMODEL.TXT').read_text().strip()
    if model not in BACKUPS:
        raise ValueError('Missing or unknown model report')
    original = (card / BACKUPS[model]).read_bytes()
    if not 4 <= len(original) <= 2097152:
        raise ValueError('Invalid original size')
    with Image.open(BytesIO(original)) as im:
        im.load()
        if im.format != 'JPEG' or im.size != (720, 480):
            raise ValueError('Original must decode as a 720x480 JPEG')
    with Image.open(image) as im:
        im = ImageOps.exif_transpose(im)
        if im.size != (720, 480):
            raise ValueError('Replacement must be 720x480; resize it explicitly first')
        im = im.convert('RGB')
        prepared = None
        for quality in range(95, 4, -1):
            stream = BytesIO()
            im.save(stream, format='JPEG', quality=quality, subsampling=2, progressive=False, optimize=True)
            try:
                prepared = pad_jpeg(stream.getvalue(), len(original))
                break
            except ValueError:
                continue
        if prepared is None:
            raise ValueError('Image cannot fit original length; use simpler artwork. No package written')
    fresh_output(output)
    (output / BACKUPS[model]).write_bytes(original)
    (output / 'NEWGB.JPG').write_bytes(prepared)
    (output / 'GBARM.TXT').write_text('1')
    (output / 'script/startup.ttl').write_text(generate_write(model, len(original)))
    (output / 'restore.ttl').write_text(generate_write(model, len(original), True))
    manifest = {'model': model, 'backup': BACKUPS[model], 'length': len(original),
                'original_sha256': digest(original), 'replacement_sha256': digest(prepared),
                'jpeg_quality': quality, 'rotation': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def verify(package, readback, restore=False):
    manifest = json.loads((package / 'manifest.json').read_text())
    original = (package / manifest['backup']).read_bytes()
    if digest(original) != manifest['original_sha256']:
        raise ValueError('Saved original has changed')
    expected = manifest['original_sha256' if restore else 'replacement_sha256']
    actual = readback.read_bytes()
    if len(actual) != manifest['length'] or digest(actual) != expected:
        raise ValueError('Full readback mismatch; do not report success or repeat the write blindly')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('backup'); p.add_argument('output', type=Path)
    p = sub.add_parser('prepare'); p.add_argument('card', type=Path); p.add_argument('image', type=Path); p.add_argument('output', type=Path)
    p = sub.add_parser('verify'); p.add_argument('package', type=Path); p.add_argument('readback', type=Path); p.add_argument('--restore', action='store_true')
    p = sub.add_parser('restore'); p.add_argument('package', type=Path); p.add_argument('output', type=Path)
    gr4_hdf_exfat.add_parser(sub)
    args = parser.parse_args()
    try:
        if args.command == 'exfat':
            print(json.dumps(gr4_hdf_exfat.dispatch(args), indent=2))
        elif args.command == 'backup':
            fresh_output(args.output)
            (args.output / 'script/startup.ttl').write_text(generate_backup())
        elif args.command == 'prepare':
            print(json.dumps(prepare(args.card, args.image, args.output), indent=2))
        elif args.command == 'verify':
            verify(args.package, args.readback, args.restore)
            print('Full readback matches. Confirm the actual shutdown display separately.')
        else:
            m = json.loads((args.package / 'manifest.json').read_text())
            original = args.package / m['backup']
            verify(args.package, original, True)
            fresh_output(args.output)
            shutil.copyfile(original, args.output / m['backup'])
            (args.output / 'GBARM.TXT').write_text('1')
            (args.output / 'script/startup.ttl').write_text(generate_write(m['model'], m['length'], True))
    except (ValueError, OSError) as error:
        parser.exit(1, f'Error: {error}\n')



def generate_simple_write(restore=False):
    """Static card template matching the project's copy/run/readback workflow."""
    output = 'GBREST.JPG' if restore else 'GBREAD.JPG'
    source = 'backup' if restore else "'C:\\NEWGB.JPG'"
    text = routing()
    # Same-model binding only; users must keep each body's card backup separate.
    for label in BACKUPS:
        text += f"strcompare model '{label}'\nif result = 0 then\n"
        text += size_gate("'C:\\GBMODEL.TXT'", len(label))
        text += f"fileopen fh 'C:\\GBMODEL.TXT' 0\nif fh < 0 then\n    exit\nendif\nfileread fh {len(label)} saved_model\nfileclose fh\nstrcompare saved_model model\nif result <> 0 then\n    exit\nendif\nendif\n"
    text += f"filesearch 'C:\\{output}'\nif result = 1 then\n    exit\nendif\n"
    text += "original_size = -1\nfilestat backup original_size\nif original_size < 4 then\n    exit\nendif\nif original_size > 2097152 then\n    exit\nendif\n"
    text += size_gate('target', 'original_size')
    if not restore:
        text += size_gate(source, 'original_size')
    # An empty readback reserves this attempt before writing. It is not success.
    text += f"filecreate fh 'C:\\{output}'\nif fh < 0 then\n    exit\nendif\nfileclose fh\n"
    return text + f"filecopy {source} target\nfilecopy target 'C:\\{output}'\nexit\n"


if __name__ == '__main__':
    main()
