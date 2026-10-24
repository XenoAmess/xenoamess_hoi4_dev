import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from tools.common import file_sha256,read_json,write_json
from mod_nailong.tools import generation_requests as requests
from tests import test_generation_requests as generation_tests

class MatchedOriginalContextTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.mod,self.key,self.source,self.game,self.master,self.row=generation_tests.RequestImportTests().edit_fixture(self.root)
  self.other='d'*64;self.aux=self.root/'runtime/references/matched-scene.png';self.aux.parent.mkdir(parents=True);Image.new('RGBA',(12,16),'silver').save(self.aux)
  c=read_json(self.mod/'data/catalog.json');c['assets'].append({'source_sha256':self.other,'path':'gfx/actual-context.dds','size':[12,16]});write_json(self.mod/'data/catalog.json',c)
  self.context={'source_sha256':self.other,'converted_png_sha256':file_sha256(self.aux),'actually_viewed_same_composition':True,'visual_match_reason':'Actually viewed: same arch, asymmetric group positions and outfit; not inferred from name.'}
  self.addCleanup(patch.stopall)
  patch.object(requests,'ROOT',self.root).start();patch.object(requests,'MOD',self.mod).start();patch.object(requests,'REQUESTS',self.mod/'data/generation-requests').start();patch.object(requests,'original',side_effect=lambda asset:self.aux if asset['source_sha256']==self.other else self.source).start();patch('mod_nailong.tools.image_retries.require_editable_service_state').start()
 def prepare(self,edit=False):return requests.prepare(self.key,'Image1 is primary; Image3 is actually matched room context.',edit,replacement_reason='Independent actual rejected scene repair',supporting_original_context=self.context)
 def test_matched_original_context_has_distinct_role_and_primary_identity(self):
  job=self.prepare();a=read_json(self.mod/f'data/generation-requests/{self.key}.json')['attempts'][-1]
  self.assertEqual(job['key'],self.key);self.assertFalse(a['edit_existing'])
  self.assertEqual(job['references'],[str(self.source),str(self.mod/'assets/reference/naiwa.png'),str(self.aux)])
  self.assertEqual(a['inputs'][0]['raw_sha256'],self.key);self.assertEqual(a['inputs'][2]['raw_sha256'],self.other)
  self.assertEqual(a['inputs'][2]['sha256'],file_sha256(self.aux));self.assertFalse((self.mod/f'data/generation-requests/{self.other}.json').exists())
 def test_matching_name_without_actual_visual_evidence_is_rejected(self):
  self.context['actually_viewed_same_composition']=False
  with self.assertRaisesRegex(ValueError,'actual visual'):self.prepare()
 def test_changed_auxiliary_pixels_block_before_journaling(self):
  self.aux.write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'PNG changed'):self.prepare()
  self.assertFalse((self.mod/f'data/generation-requests/{self.key}.json').exists())
 def test_unknown_or_duplicate_source_context_is_rejected(self):
  self.context['source_sha256']=self.key
  with self.assertRaisesRegex(ValueError,'already a required input'):self.prepare()
  self.context['source_sha256']='e'*64
  with self.assertRaisesRegex(ValueError,'actual catalog'):self.prepare()
 def test_context_cannot_silently_extend_a_prepared_edit_payload(self):
  with self.assertRaisesRegex(ValueError,'independent replacement'):self.prepare(edit=True)

if __name__=='__main__':unittest.main()
