import tempfile,unittest
from unittest.mock import patch
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
 def network_ancestor(self):
  import copy
  history=read_json(self.journal);parent=copy.deepcopy(history['attempts'][0]);oldledger=read_json(self.dispatch)
  parent.update(number=2,status='failed',machine_id=machine_id(),retry_of_attempt=1,error='image generation failed: network error: error sending request',actual_request_verification=copy.deepcopy(self.a['actual_request_verification']))
  error=self.root/'network-error.txt';error.write_text(parent['error'],encoding='utf-8')
  failed=copy.deepcopy(oldledger);failed.update(status='tool_error',call_returned_at_utc='2026-10-29T01:00:00+00:00',actual_error_file=str(error),actual_error_sha256=file_sha256(error));failed.pop('returned_image_sha256');write_json(self.dispatch,failed)
  self.a.update(number=3,retry_of_attempt=2,terminal_service_transport_retry_of_attempt=2,cooldown_retry_number=2)
  self.returned_dispatch=self.dispatch.with_name(self.key+'-003.json');oldledger['attempt_number']=3;write_json(self.returned_dispatch,oldledger)
  write_json(self.journal,{'attempts':[history['attempts'][0],parent,self.a]})
  path=self.root/'mod_nailong/data/image-retry-queue.json';q=read_json(path);q['sources'][self.key]['retries_used']=2;write_json(path,q)
 def test_proven_returned_network_ancestor_retains_exact_chain_and_counter(self):
  self.network_ancestor();result=self.proof();proof=result['proofs'][self.key]
  self.assertEqual(proof['failed_parent_attempt'],2);self.assertEqual(proof['failed_moderation_ancestor_attempt'],1)
  self.assertEqual(len(proof['proven_returned_network_ancestors']),1);self.assertEqual(proof['retries_used_unchanged'],2)
 def test_unknown_network_ancestor_cannot_release_art(self):
  self.network_ancestor();body=read_json(self.dispatch);body['status']='calling';write_json(self.dispatch,body)
  self.assertIn(self.key,self.proof()['unavailable'])
 def test_unmarked_network_recovery_cannot_release_art(self):
  self.network_ancestor();self.a.pop('terminal_service_transport_retry_of_attempt');write_json(self.journal,{'attempts':read_json(self.journal)['attempts'][:-1]+[self.a]})
  self.assertIn(self.key,self.proof()['unavailable'])
 def test_changed_network_error_bytes_cannot_release_art(self):
  self.network_ancestor();(self.root/'network-error.txt').write_bytes(b'changed')
  self.assertIn(self.key,self.proof()['unavailable'])

class OriginalReplacementServiceStateTests(unittest.TestCase):
 setUp=AcceptedRetryArtTests.setUp
 def configure(self):
  from mod_nailong.tools import image_retries
  self.subject=image_retries
  for item in [patch.object(image_retries,'ROOT',self.root),patch.object(image_retries,'MOD',self.root/'mod_nailong'),patch.object(image_retries,'QUEUE',self.root/'mod_nailong/data/image-retry-queue.json')]:
   item.start();self.addCleanup(item.stop)
  write_json(self.root/'mod_nailong/data/image-retry-policy.json',{'cooldown_hours':8,'max_cooldown_retries_per_source':8})
  write_json(self.root/'mod_nailong/data/generation-failures.json',{'attempts':[{'source_sha256':self.key,'status':'blocked'}]})
 def test_explicit_original_art_method_uses_full_success_proof_without_reset(self):
  self.configure();self.subject.require_editable_service_state(self.key,self.rows[self.key],self.a,False,original_replacement_reason='Current actual raw rejected; reconstruct from exact original')
  q=read_json(self.subject.QUEUE)['sources'][self.key]
  self.assertEqual(q['retries_used'],1);self.assertEqual(q['state'],'service_retry_succeeded_art_correction_pending')
 def test_original_method_reason_alone_never_releases_failed_or_unresolved_request(self):
  self.configure();ledger=read_json(self.dispatch);ledger['status']='calling';write_json(self.dispatch,ledger)
  before=self.subject.QUEUE.read_bytes()
  with self.assertRaises(SystemExit):self.subject.require_editable_service_state(self.key,self.rows[self.key],self.a,False,original_replacement_reason='A reason is not success proof')
  self.assertEqual(self.subject.QUEUE.read_bytes(),before)

class OriginalReplacementServiceStateTests(unittest.TestCase):
 setUp=AcceptedRetryArtTests.setUp
 def configure(self):
  from mod_nailong.tools import image_retries
  self.subject=image_retries
  for item in [patch.object(image_retries,'ROOT',self.root),patch.object(image_retries,'MOD',self.root/'mod_nailong'),patch.object(image_retries,'QUEUE',self.root/'mod_nailong/data/image-retry-queue.json')]:
   item.start();self.addCleanup(item.stop)
  write_json(self.root/'mod_nailong/data/image-retry-policy.json',{'cooldown_hours':8,'max_cooldown_retries_per_source':8})
  write_json(self.root/'mod_nailong/data/generation-failures.json',{'attempts':[{'source_sha256':self.key,'status':'blocked'}]})
 def test_explicit_original_art_method_uses_full_success_proof_without_reset(self):
  self.configure();self.subject.require_editable_service_state(self.key,self.rows[self.key],self.a,False,original_replacement_reason='Current actual raw rejected; reconstruct from exact original')
  q=read_json(self.subject.QUEUE)['sources'][self.key]
  self.assertEqual(q['retries_used'],1);self.assertEqual(q['state'],'service_retry_succeeded_art_correction_pending')
 def test_original_method_reason_alone_never_releases_failed_or_unresolved_request(self):
  self.configure();ledger=read_json(self.dispatch);ledger['status']='calling';write_json(self.dispatch,ledger)
  before=self.subject.QUEUE.read_bytes()
  with self.assertRaises(SystemExit):self.subject.require_editable_service_state(self.key,self.rows[self.key],self.a,False,original_replacement_reason='A reason is not success proof')
  self.assertEqual(self.subject.QUEUE.read_bytes(),before)

if __name__=='__main__':unittest.main()
