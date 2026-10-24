import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from tools.common import file_sha256,read_json,write_json
from mod_nailong.tools import generation_requests as requests
from tests import test_generation_requests as generation_tests

class SupportingTargetCropTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.mod,self.key,self.source,self.game,self.master,self.row=generation_tests.RequestImportTests().edit_fixture(self.root)
  self.path=self.mod/'assets/request_context/target-native-crop.png';self.path.parent.mkdir(parents=True)
  self.box=[2,3,14,18]
  with Image.open(self.master) as im:im.crop(self.box).save(self.path)
  self.crop={'path':self.path.relative_to(self.root).as_posix(),'sha256':file_sha256(self.path),'parent_fullsize_sha256':file_sha256(self.master),'crop_box':self.box}
  self.addCleanup(patch.stopall)
  patch.object(requests,'ROOT',self.root).start();patch.object(requests,'MOD',self.mod).start();patch.object(requests,'REQUESTS',self.mod/'data/generation-requests').start();patch.object(requests,'original',return_value=self.source).start();patch('mod_nailong.tools.image_retries.require_editable_service_state').start()
 def test_fourth_input_is_exact_native_target_crop_with_parent_and_box(self):
  before=file_sha256(self.master);job=requests.prepare(self.key,'Image4 only locates remaining human face pixels',True,supporting_crops=[self.crop])
  a=read_json(self.mod/f'data/generation-requests/{self.key}.json')['attempts'][-1]
  self.assertEqual(len(job['references']),4);self.assertEqual(job['references'][-1],str(self.path))
  self.assertEqual(a['inputs'][-1]['parent_fullsize_sha256'],before);self.assertEqual(a['inputs'][-1]['crop_box'],self.box)
  self.assertEqual(file_sha256(self.master),before);self.assertEqual(file_sha256(self.game),self.row['image_sha256'])
 def test_four_input_job_survives_ascii_export_and_actual_snapshot_begin(self):
  from mod_nailong.tools import production_queue as queue
  job=requests.prepare(self.key,'Use the exact 奶龙 reference; Image4 locates remaining skin.',True,supporting_crops=[self.crop])
  jobs=self.root/'jobs.json';write_json(jobs,[job])
  with patch.object(queue,'ROOT',self.root):
   exported=queue.export_job(jobs,self.key);self.assertTrue(exported.isascii())
   actual=json.loads(exported);snapshot=self.root/'actual.json';write_json(snapshot,actual)
   dispatch=read_json(queue.begin(actual,snapshot))
  self.assertEqual(dispatch['input_sha256'],[file_sha256(Path(p)) for p in job['references']])
  self.assertEqual(len(dispatch['input_sha256']),4);self.assertTrue(dispatch['actual_prompt_verified_before_call'])
 def test_changed_crop_pixels_even_with_new_correct_file_hash_are_rejected(self):
  with Image.open(self.path) as im:im.putpixel((0,0),(0,0,255,255));im.save(self.path)
  self.crop['sha256']=file_sha256(self.path)
  with self.assertRaisesRegex(ValueError,'unmodified native'):requests.prepare(self.key,'Exact target crop',True,supporting_crops=[self.crop])
  self.assertFalse((self.mod/f'data/generation-requests/{self.key}.json').exists())
 def test_resized_context_cannot_replace_native_pixels(self):
  with Image.open(self.path) as im:im.resize((24,30)).save(self.path)
  self.crop['sha256']=file_sha256(self.path)
  with self.assertRaisesRegex(ValueError,'unmodified native'):requests.prepare(self.key,'Exact target crop',True,supporting_crops=[self.crop])
 def test_stale_parent_and_changed_crop_bytes_fail_closed(self):
  self.crop['parent_fullsize_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'provenance changed'):requests.prepare(self.key,'Exact target crop',True,supporting_crops=[self.crop])
 def test_bounds_and_retained_context_path_are_checked(self):
  self.crop['crop_box']=[0,0,1000,1000]
  with self.assertRaisesRegex(ValueError,'bounds'):requests.prepare(self.key,'Exact target crop',True,supporting_crops=[self.crop])
  self.crop['crop_box']=self.box;self.crop['path']=self.source.relative_to(self.root).as_posix()
  with self.assertRaisesRegex(ValueError,'retained request-context'):requests.prepare(self.key,'Exact target crop',True,supporting_crops=[self.crop])
 def test_context_cannot_add_people_to_original_only_request(self):
  with self.assertRaisesRegex(ValueError,'current fullsize edit target'):requests.prepare(self.key,'Exact target crop',False,replacement_reason='Actual rejected source',supporting_crops=[self.crop])

if __name__=='__main__':unittest.main()
