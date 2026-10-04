import io
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from apps.gr_shutdown_studio.core import Session, WorkflowError, sha, render_image, ttl, filesystem, validate_card as real_validate_card
from tools.pad_jpeg import pad_jpeg


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.card=self.root/'card';self.card.mkdir()
        (self.card/'DCIM').mkdir();(self.card/'DCIM/photo.jpg').write_bytes(b'photo-is-not-a-task-file')
        self.patch=patch('apps.gr_shutdown_studio.core.validate_card');self.patch.start()
        self.session=Session.create(self.root/'session','FAMILY','1.11')
        source=io.BytesIO();Image.new('RGB',(720,480),'navy').save(source,format='JPEG')
        self.original=pad_jpeg(source.getvalue(),12000)
        self.artwork=self.root/'input.png';Image.new('RGB',(1600,900),'orange').save(self.artwork)
    def tearDown(self):
        self.patch.stop();self.tmp.cleanup()
    def backup(self):
        self.session.begin_backup(self.card)
        (self.card/'GBCOPY.TXT').write_bytes((self.card/'GBPROBE.TXT').read_bytes())
        self.session.verify_preflight(self.card)
        (self.card/'GBMODEL.TXT').write_text('HDF')
        (self.card/'GBHDF.JPG').write_bytes(self.original)
        self.session.verify_backup(self.card)
    def test_full_install_restore_and_resume_preserve_photos(self):
        self.backup()
        self.session=Session(self.root/'session')
        self.assertEqual(self.session.state,'backed_up')
        self.assertFalse((self.card/'script/startup.ttl').exists())
        self.session.prepare(self.artwork)
        self.session.begin_install(self.card)
        self.assertEqual(self.session.state,'wait_install')
        (self.card/'GBARM.TXT').write_bytes(b'0')
        (self.card/'GBREAD.JPG').write_bytes((self.root/'session/prepared.jpg').read_bytes())
        self.session.verify_install(self.card)
        self.session.finish(self.card)
        self.session=Session(self.root/'session')
        self.session.begin_restore(self.card)
        (self.card/'GBREST.JPG').write_bytes(self.original)
        self.session.verify_restore(self.card)
        self.session.finish(self.card)
        self.assertEqual((self.card/'DCIM/photo.jpg').read_bytes(),b'photo-is-not-a-task-file')
        self.assertEqual((self.root/'session/original.jpg').read_bytes(),self.original)
    def test_unowned_script_collision_aborts_before_any_deployment(self):
        (self.card/'script').mkdir();(self.card/'script/startup.ttl').write_text('user script')
        with self.assertRaises(WorkflowError):self.session.begin_backup(self.card)
        self.assertEqual(self.session.state,'new')
        self.assertFalse((self.card/'GRSESSION.TXT').exists())
        self.assertFalse((self.card/'DEVELOP.MOD').exists())
        self.assertEqual((self.card/'script/startup.ttl').read_text(),'user script')
    def test_failed_preflight_cannot_prepare_internal_write(self):
        self.session.begin_backup(self.card)
        (self.card/'GBCOPY.TXT').write_bytes(b'wrong')
        with self.assertRaises(WorkflowError):self.session.verify_preflight(self.card)
        self.assertEqual(self.session.state,'wait_preflight')
        self.assertNotIn(b'GoodBye.jpg',(self.card/'script/startup.ttl').read_bytes())
    def test_mismatched_and_empty_readbacks_block_completion(self):
        self.backup();self.session.prepare(self.artwork);self.session.begin_install(self.card)
        for data in [b'',self.original]:
            (self.card/'GBREAD.JPG').write_bytes(data)
            with self.assertRaises(ValueError):self.session.verify_install(self.card)
            self.assertEqual(self.session.state,'wait_install')
        with self.assertRaises(WorkflowError):self.session.finish(self.card)
    def test_corrupt_computer_backup_blocks_install(self):
        self.backup();self.session.prepare(self.artwork)
        (self.root/'session/original.jpg').write_bytes(b'corrupt')
        with self.assertRaises(WorkflowError):self.session.begin_install(self.card)
        self.assertEqual(self.session.state,'prepared')
    def test_wrong_card_marker_rejected(self):
        self.backup();(self.card/'GRSESSION.TXT').write_text('another-session')
        with self.assertRaises(WorkflowError):self.session.begin_restore(self.card)
    def test_repeat_install_never_resets_permit_or_readback(self):
        self.backup();self.session.prepare(self.artwork);self.session.begin_install(self.card)
        (self.card/'GBARM.TXT').write_bytes(b'0')
        with self.assertRaises(WorkflowError):self.session.begin_install(self.card)
        self.assertEqual((self.card/'GBARM.TXT').read_bytes(),b'0')
    def test_symlink_startup_rejected(self):
        (self.card/'script').mkdir()
        try:(self.card/'script/startup.ttl').symlink_to(self.artwork)
        except OSError:self.skipTest('Symbolic links are unavailable on this runner.')
        with self.assertRaises(WorkflowError):self.session.begin_backup(self.card)
    def test_partial_deployment_has_persistent_interrupted_state(self):
        with patch('apps.gr_shutdown_studio.core.atomic', wraps=__import__('apps.gr_shutdown_studio.core',fromlist=['atomic']).atomic) as write:
            original=write._mock_wraps
            def failing(path,data):
                if path.name=='DEVELOP.MOD':raise OSError('simulated removal')
                original(path,data)
            write.side_effect=failing
            with self.assertRaises(OSError):self.session.begin_backup(self.card)
        self.assertEqual(Session(self.root/'session').state,'deployment_incomplete')
        self.assertFalse((self.card/'script/startup.ttl').exists())
    def test_restore_readback_mismatch_cannot_report_success(self):
        self.backup();self.session.begin_restore(self.card)
        (self.card/'GBREST.JPG').write_bytes(b'wrong')
        with self.assertRaises(WorkflowError):self.session.verify_restore(self.card)
        self.assertEqual(self.session.state,'wait_restore')
    def test_unknown_model_does_not_save_original(self):
        self.session.begin_backup(self.card)
        (self.card/'GBCOPY.TXT').write_bytes((self.card/'GBPROBE.TXT').read_bytes())
        self.session.verify_preflight(self.card)
        (self.card/'GBMODEL.TXT').write_text('UNKNOWN')
        with self.assertRaises(WorkflowError):self.session.verify_backup(self.card)
        self.assertFalse((self.root/'session/original.jpg').exists())
    def test_urban_rejects_unverified_original(self):
        other=Session.create(self.root/'urban','URBAN','1.60')
        other.begin_backup(self.card)
        (self.card/'GBCOPY.TXT').write_bytes((self.card/'GBPROBE.TXT').read_bytes())
        other.verify_preflight(self.card)
        (self.card/'URBANBK.JPG').write_bytes(self.original)
        (self.card/'URBOLD.JPG').write_bytes(self.original)
        with self.assertRaises(ValueError):other.verify_backup(self.card)
        self.assertEqual(other.state,'wait_backup')
    def test_render_fit_crop_transparency_and_rotation(self):
        transparent=self.root/'transparent.png';Image.new('RGBA',(100,200),(255,0,0,0)).save(transparent)
        result=render_image(transparent,'contain')
        self.assertEqual(result.size,(720,480))
        self.assertEqual(result.getpixel((360,240)),(17,17,17))
        self.assertEqual(render_image(self.artwork,'crop').size,(720,480))
        with self.assertRaises(WorkflowError):render_image(self.artwork,'invalid')
    def test_deployment_scripts_are_ascii_crlf(self):
        self.backup();self.session.prepare(self.artwork);self.session.begin_install(self.card)
        data=(self.card/'script/startup.ttl').read_bytes()
        self.assertTrue(data.isascii())
        self.assertNotIn(b'\n',data.replace(b'\r\n',b''))


    def test_urban_two_stage_flow_with_synthetic_profile(self):
        # Synthetic JPEG data exercises the app's phase gates, not Urban camera decoding.
        from apps.gr_shutdown_studio import core
        other=Session.create(self.root/'urban-flow','URBAN','1.60')
        candidate=pad_jpeg(self.artwork_to_jpeg(),12000)
        def encode(original,artwork,output):output.write_bytes(candidate)
        with patch.object(core.urban,'SIZE',12000), patch.object(core.urban,'OLD_HASH',sha(self.original)), \
             patch.object(core.urban_jpeg,'validate_original',return_value=[]), \
             patch.object(core.urban_jpeg,'validate_candidate',return_value={}), \
             patch.object(core.urban,'validate_candidate',return_value={}), \
             patch.object(core.urban_jpeg,'encode',side_effect=encode):
            other.begin_backup(self.card)
            (self.card/'GBCOPY.TXT').write_bytes((self.card/'GBPROBE.TXT').read_bytes())
            other.verify_preflight(self.card)
            for name in ['URBANBK.JPG','URBOLD.JPG']:(self.card/name).write_bytes(self.original)
            other.verify_backup(self.card);other.prepare(self.artwork);other.begin_install(self.card)
            self.assertEqual(other.state,'wait_stage1')
            first=(self.card/'script/startup.ttl').read_bytes()
            self.assertNotIn(b"filecopy 'B:\\Resource\\Jpeg\\RB81NW.JPG' 'B:\\Resource\\Jpeg\\GB_Urban.jpg'",first)
            with self.assertRaises((WorkflowError,FileNotFoundError)):other.verify_stage1(self.card)
            self.assertEqual((self.card/'script/startup.ttl').read_bytes(),first)
            for name in ['URBORG8.JPG','URBPRE8.JPG']:(self.card/name).write_bytes(self.original)
            (self.card/'URBIMG8.JPG').write_bytes(candidate)
            (self.card/'URBLOG8.TXT').write_text('started\n1\nerror\n0\ncompleted\n1\nrestored\n0\nattempted\n0\n')
            other.verify_stage1(self.card)
            self.assertEqual(other.state,'wait_install')
            for name in ['URBNW9.JPG','URBRD9.JPG']:(self.card/name).write_bytes(candidate)
            for name in ['URBOR9.JPG','URBPRE9.JPG']:(self.card/name).write_bytes(self.original)
            (self.card/'URBLOG9.TXT').write_text('started\n1\nerror\n0\ncompleted\n1\nrestored\n0\nattempted\n1\n')
            other.verify_install(self.card);other.finish(self.card)
            other.begin_restore(self.card)
            self.assertEqual(other.state,'wait_restore_check')
            self.assertNotIn(b"'B:\\Resource\\Jpeg\\GB_Urban.jpg'\r\n",(self.card/'script/startup.ttl').read_bytes())
            (self.card/'URBRBCHK.JPG').write_bytes(b'wrong')
            (self.card/'URBTGCHK.JPG').write_bytes(candidate)
            with self.assertRaises(WorkflowError):other.verify_restore_check(self.card)
            self.assertEqual(other.state,'wait_restore_check')
            (self.card/'URBRBCHK.JPG').write_bytes(self.original)
            other.verify_restore_check(self.card)
            self.assertEqual(other.state,'wait_restore')
            (self.card/'URBREST.JPG').write_bytes(self.original)
            other.verify_restore(self.card)
            self.assertEqual(other.state,'restored')

    def artwork_to_jpeg(self):
        stream=io.BytesIO();Image.new('RGB',(720,480),'orange').save(stream,format='JPEG')
        return stream.getvalue()

    def test_non_fat32_card_is_rejected(self):
        with patch('apps.gr_shutdown_studio.core.filesystem',return_value='exFAT'):
            with self.assertRaises(WorkflowError):real_validate_card(self.card)

    def test_session_cannot_be_saved_on_a_macos_sd_volume(self):
        if sys.platform != 'darwin':self.skipTest('macOS-specific volume-root check.')
        with patch('apps.gr_shutdown_studio.core.sys.platform','darwin'):
            with self.assertRaises(WorkflowError):Session.create(Path('/Volumes/SDCARD/new-session'),'FAMILY','1.11')



class CommunityBackupTests(unittest.TestCase):
    setUp = WorkflowTests.setUp
    tearDown = WorkflowTests.tearDown
    backup = WorkflowTests.backup
    # Reuse the simulated SD workflow; never write a real volume.
    def test_recovery_copy_is_verified_and_not_overwritten(self):
        self.backup()
        recovery=self.session.directory/'recovery/original.jpg'
        self.assertEqual(recovery.read_bytes(),self.original)
        recovery.write_bytes(b'altered recovery')
        with self.assertRaises(WorkflowError):self.session.prepare(self.artwork)
        self.assertEqual(recovery.read_bytes(),b'altered recovery')
        self.assertEqual((self.session.directory/'original.jpg').read_bytes(),self.original)
        self.assertFalse((self.session.directory/'package').exists())

    def test_corrupt_primary_keeps_verified_recovery_bytes(self):
        self.backup()
        (self.session.directory/'original.jpg').write_bytes(b'altered primary')
        with self.assertRaises(WorkflowError):self.session.begin_restore(self.card)
        self.assertEqual((self.session.directory/'recovery/original.jpg').read_bytes(),self.original)
        self.assertFalse((self.card/'script/startup.ttl').exists())

    def test_unknown_firmware_keeps_backups_and_blocks_internal_writes(self):
        self.session.data['firmware']='1.10'
        self.backup()
        with self.assertRaises(WorkflowError):self.session.prepare(self.artwork)
        with self.assertRaises(WorkflowError):self.session.begin_restore(self.card)
        self.assertEqual(self.session.state,'backed_up')
        self.assertFalse((self.card/'script/startup.ttl').exists())
        self.assertEqual((self.session.directory/'original.jpg').read_bytes(),self.original)
        self.assertEqual((self.session.directory/'recovery/original.jpg').read_bytes(),self.original)

    def test_urban_unknown_version_is_refused_before_card_changes(self):
        other=Session.create(self.root/'unknown-urban','URBAN','1.50')
        before=sorted(str(p.relative_to(self.card)) for p in self.card.rglob('*'))
        with self.assertRaises(WorkflowError):other.begin_backup(self.card)
        self.assertEqual(before,sorted(str(p.relative_to(self.card)) for p in self.card.rglob('*')))
        self.assertEqual(other.state,'new')

    def test_legacy_record_migrates_only_after_validating_original(self):
        self.backup()
        self.session.data.pop('firmware');self.session.save()
        with self.assertRaises(WorkflowError):self.session.prepare(self.artwork)
        self.session.set_firmware('1.11')
        self.session.prepare(self.artwork)
        self.assertEqual(self.session.state,'prepared')
        with self.assertRaises(WorkflowError):self.session.set_firmware('1.12')

    def test_report_omits_private_assets_and_preserves_previous_report(self):
        self.backup()
        destination=self.root/'test-report.json'
        self.session.export_test_report(destination)
        data=json.loads(destination.read_text())
        self.assertEqual(data['original_sha256'],sha(self.original))
        self.assertEqual(data['firmware'],'1.11')
        self.assertNotIn(self.session.data['id'],destination.read_text())
        self.assertNotIn(str(self.root),destination.read_text())
        self.assertNotIn('image',data)
        self.assertFalse(data['camera_display_confirmed_by_user'])
        self.assertFalse(data['full_app_camera_qualified'])
        before=destination.read_bytes()
        with self.assertRaises(WorkflowError):self.session.export_test_report(destination)
        self.assertEqual(destination.read_bytes(),before)

if __name__=='__main__':unittest.main()
