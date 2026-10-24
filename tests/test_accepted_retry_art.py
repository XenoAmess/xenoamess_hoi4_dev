import tempfile,unittest
from pathlib import Path
from tools.common import read_json,write_json,file_sha256,machine_id
from tools.accepted_retry_art import accepted_retry_art_proofs


class AcceptedRetryArtTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.key='a'*64
  for name,value in [('raw.png',b'unchanged raw PNG'),('preview.png',b'derived preview'),('source.png',b'exact source'),('mascot.png',b'user reference'),('prompt.txt',b'Exact original request')]:
   (self.root/name).write_bytes(value)
  refs=[str(self.root/'source.png'),str(self.root/'mascot.png')];inputs=[{'path':Path(p).name,'sha256':file_sha256(Path(p))} for p in refs]
  actual={'key':self.key,'prompt':'Exact original request','references':refs,'transparent':True};self.snapshot=self.root/'actual.json';write_json(self.snapshot,actual)
  verification={'machine_id':machine_id(),'actual_recorded_before_call':True,'actual_request_snapshot_sha256':file_sha256(self.snapshot),'input_sha256':[i['sha256'] for i in inputs],'transparent_background':True}
  parent={'number':1,'status':'failed','error':'moderation_blocked','prompt':actual['prompt'],'inputs':inputs}
  self.a={'number':2,'machine_id':machine_id(),'status':'generated_rejected_visual_review','retry_of_attempt':1,'cooldown_retry_number':1,'prompt':actual['prompt'],'prompt_file':'prompt.txt','prompt_sha256':file_sha256(self.root/'prompt.txt'),'inputs':inputs,'actual_request_verification':verification,'output_sha256':file_sha256(self.root/'preview.png'),'fullsize_sha256':file_sha256(self.root/'raw.png')}
  self.journal=self.root/f'mod_nailong/data/generation-requests/{self.key}.json';write_json(self.journal,{'attempts':[parent,self.a]})
  self.rows={self.key:{'review':'rejected','image':'preview.png','image_sha256':self.a['output_sha256'],'generated_fullsize_image':'raw.png','generated_fullsize_sha256':self.a['fullsize_sha256'],'request_journal':self.journal.relative_to(self.root).as_posix()}}
  self.dispatch=self.root/f'runtime/production-queue/dispatch/{self.key}-002.json';write_json(self.dispatch,{'machine_id':machine_id(),'source_sha256':self.key,'attempt_number':2,'status':'returned_image','actual_request_snapshot_file':str(self.snapshot),'actual_request_snapshot_sha256':file_sha256(self.snapshot),'input_sha256':verification['input_sha256'],'returned_image_sha256':self.a['fullsize_sha256']})
  write_json(self.root/'mod_nailong/data/image-retry-queue.json',{'sources':{self.key:{'state':'generated_pending_visual_review','retries_used':1,'output_sha256':self.a['output_sha256']}}})
  write_json(self.root/'mod_nailong/data/image-retry-policy.json',{'max_cooldown_retries_per_source':8})
 def proof(self):return accepted_retry_art_proofs(self.root,self.rows,{self.key:self.a})
 def change(self,path,**values):
  body=read_json(path);body.update(values);write_json(path,body)
 def test_actual_success_current_rejection_proof_is_read_only(self):
  before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
  result=self.proof();self.assertIn(self.key,result['proofs']);self.assertEqual(result['unavailable'],{})
  self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)
 def test_latest_failure_cannot_reuse_earlier_success(self):
  self.a['status']='failed';self.assertNotIn(self.key,self.proof()['proofs'])
 def test_changed_current_raw_is_held(self):
  (self.root/'raw.png').write_bytes(b'changed');self.assertIn(self.key,self.proof()['unavailable'])
 def test_unresolved_or_different_return_cannot_release_service_hold(self):
  for values in [{'status':'calling'},{'status':'returned_image','returned_image_sha256':'b'*64}]:
   self.change(self.dispatch,**values);self.assertIn(self.key,self.proof()['unavailable'])
 def test_changed_actual_payload_and_input_bytes_are_held(self):
  self.snapshot.write_text('{}',encoding='utf-8');self.assertIn(self.key,self.proof()['unavailable'])
 def test_earlier_retry_success_does_not_match_changed_latest_journal(self):
  body=read_json(self.journal);body['attempts'].append({'number':3,'status':'failed'});write_json(self.journal,body)
  self.assertIn(self.key,self.proof()['unavailable'])
 def test_cooling_state_or_different_output_stays_held(self):
  path=self.root/'mod_nailong/data/image-retry-queue.json';body=read_json(path);body['sources'][self.key]['state']='cooling_down';write_json(path,body)
  self.assertIn(self.key,self.proof()['unavailable'])
 def test_successful_retry_must_preserve_exact_failed_parent_inputs(self):
  body=read_json(self.journal);body['attempts'][0]['inputs']=[];write_json(self.journal,body)
  self.assertIn(self.key,self.proof()['unavailable'])

if __name__=='__main__':unittest.main()
