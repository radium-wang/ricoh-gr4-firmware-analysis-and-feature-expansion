import tempfile
import unittest
from pathlib import Path
from apps.gr_shutdown_studio.compatibility import PROFILES, installation_allowed
from tools.audit_shutdown_compatibility import inspect


class CompatibilityTests(unittest.TestCase):
    def test_registry_covers_editions_without_wildcard_installers(self):
        self.assertEqual(len(PROFILES),10)
        self.assertEqual(len({p.id for p in PROFILES}),10)
        self.assertTrue(installation_allowed('FAMILY','HDF','1.11'))
        self.assertTrue(installation_allowed('URBAN','URBAN','1.60'))
        for version in [None,'1.10','1.12','2.10','1.11.10.7']:
            self.assertFalse(installation_allowed('FAMILY','STANDARD',version))
        self.assertFalse(installation_allowed('FAMILY','MONO','1.11'))
        self.assertFalse(installation_allowed('URBAN','HDF','1.60'))
        self.assertFalse(installation_allowed('GRIII','STANDARD','2.10'))

    def test_name_presence_cannot_qualify_installation_or_identify_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            header=bytearray(128)
            header[:8]=b'RICOH\0\0\0';header[8:13]=b'GR IV';header[0x38:0x3c]=bytes([1,11,10,7])
            (root/'update.bin').write_bytes(header)
            (root/'decoded.bin').write_bytes(b'GoodBye.jpg\0GB_HDF.jpg\0GB_Mono.jpg\0')
            report=inspect(root/'update.bin',root/'decoded.bin')
            self.assertEqual(report['header_version'],'1.11.10.7')
            self.assertEqual(len(report['resource_name_evidence']),3)
            self.assertFalse(report['installation_qualified'])
            self.assertFalse(report['installed_body_identified'])
            self.assertFalse(report['decoded_correspondence_verified'])
            self.assertNotIn(str(root),str(report))

    def test_foreign_or_short_container_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'update.bin'
            for data in [b'',b'RICOH\0\0\0',bytes(128)]:
                path.write_bytes(data)
                with self.assertRaises(ValueError):inspect(path)
