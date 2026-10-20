import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.common import read_json,write_json,file_sha256
from tools import retry_scheduler_merge as merge
from tools.retry_scheduler_claim import expected_transparency

class RetryApprovalVersionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.key='a'*64;self.machine='fixture-machine'
  self.addCleanup(patch.stopall)
  patch.object(merge,'machine_id',return_value=self.machine).start()
  patch.object(merge,'policy',return_value={'max_cooldown_retries_per_source':8}).start()
  self.refs=[]
  for name in ['raw-target','source','user']:
   p=self.root/(name+'.png');p.write_bytes(name.encode('ascii'));self.refs.append(str(p))
  hashes=[file_sha256(Path(p)) for p in self.refs];self.target=hashes[0]
  self.old={'key':self.key,'prompt':'old complete prompt','references':self.refs[1:],'input_sha256':hashes[1:],'transparent':True,'manual_review_source':'old-review.json','verified_failed_attempt':4,'opaque_old_metadata':{'retained':'complete historical approval'}}
  self.old_success={'number':5,'status':'generated_rejected_visual_review','prompt':self.old['prompt'],'fullsize_sha256':'b'*64,'actual_request_verification':{'input_sha256':hashes[1:],'transparent_background':True}}
  self.target_return={'number':6,'status':'generated_rejected_visual_review','fullsize_sha256':self.target}
  self.job={'key':self.key,'prompt':'exact current failed art prompt','references':self.refs,'transparent':True}
  snapshot=self.root/'runtime/actual.json';write_json(snapshot,self.job)
  self.failed={'number':8,'status':'failed','machine_id':self.machine,'error':'moderation_blocked output receipt','prompt':self.job['prompt'],'prompt_sha256':hashlib.sha256(self.job['prompt'].encode()).hexdigest(),'edit_existing':True,'inputs':[{'role':'previous generated fullsize edit target','sha256':self.target}],'actual_request_verification':{'machine_id':self.machine,'actual_recorded_before_call':True,'actual_request_snapshot_sha256':file_sha256(snapshot),'input_sha256':hashes,'transparent_background':True}}
  self.attempts=[self.old_success,self.target_return,self.failed]
  self.journal=self.root/f'mod_nailong/data/generation-requests/{self.key}.json';write_json(self.journal,{'attempts':self.attempts})
  write_json(self.root/f'runtime/production-queue/dispatch/{self.key}-008.json',{'status':'failed','actual_request_snapshot_file':str(snapshot)})
  self.queue=self.root/'mod_nailong/data/image-retry-queue.json'
  write_json(self.queue,{'sources':{self.key:{'retries_used':2,'state':'cooling_down','not_before_utc':'2026-10-19T18:12:20+00:00','cooldown_origin_attempt':8}}})
  self.pool=self.root/'runtime/retry-scheduler/approved-pool.json';write_json(self.pool,{'machine_id':self.machine,'requests':{self.key:self.old}})
  write_json(self.root/'runtime/retry-scheduler/state.json',{'pending':None})
  write_json(self.root/'mod_nailong/data/generated.json',{'portraits':{self.key:{'review':'rejected','generated_fullsize_sha256':self.target}}})
  self.candidate=dict(self.job,input_sha256=hashes,original_actual_prompt_verified=True,policy_reviewed=True,manual_policy_review={'machine_id':self.machine},not_before_utc='2026-10-19T18:12:20+00:00',approval_supersession={'previous_entry_sha256':merge.entry_digest(self.old),'previous_prompt_sha256':hashlib.sha256(self.old['prompt'].encode()).hexdigest(),'previous_input_sha256':self.old['input_sha256'],'previous_service_success_attempt':5,'failed_attempt_number':8,'failed_actual_snapshot_sha256':file_sha256(snapshot),'edit_target_fullsize_sha256':self.target,'reason':'Actual old service success followed by rejected art target and exact failed correction.','retry_counter_reset':False})
  self.proposal=self.root/'mod_nailong/data/review-proposal.json'

 def run_merge(self):
  write_json(self.proposal,[self.candidate]);return merge.merge_candidates(self.proposal,self.root)

 def test_supersession_archives_complete_old_approval_without_mutating_quota_or_journal(self):
  qsha=file_sha256(self.queue);jsha=file_sha256(self.journal)
  result=self.run_merge();self.assertEqual(result['archived_previous_versions'],1)
  entry=read_json(self.pool)['requests'][self.key];version=entry['approval_versions'][0]
  archive=self.root/version['archive'];self.assertEqual(file_sha256(archive),version['archive_sha256'])
  self.assertEqual(read_json(archive)['approval_entry'],self.old)
  self.assertEqual(entry['prompt'],self.job['prompt']);self.assertEqual(entry['input_sha256'],self.candidate['input_sha256'])
  self.assertIs(entry['original_tool_transparent_background'],True)
  self.assertIs(entry['requires_manual_policy_review'],True)
  self.assertEqual(file_sha256(self.queue),qsha);self.assertEqual(file_sha256(self.journal),jsha)
  self.assertEqual(result['quota_claims'],0);self.assertEqual(result['image_calls'],0)

 def test_changed_payload_requires_explicit_proof(self):
  del self.candidate['approval_supersession']
  with self.assertRaises(AssertionError):self.run_merge()
  self.assertEqual(read_json(self.pool)['requests'][self.key],self.old)

 def test_stale_previous_approval_is_rejected(self):
  self.candidate['approval_supersession']['previous_entry_sha256']='0'*64
  with self.assertRaises(AssertionError):self.run_merge()

 def test_no_prior_service_success_cannot_be_relabelled_as_art_supersession(self):
  self.attempts[0].pop('fullsize_sha256');write_json(self.journal,{'attempts':self.attempts})
  with self.assertRaises(AssertionError):self.run_merge()

 def test_active_call_blocks_pool_mutation(self):
  write_json(self.root/'runtime/production-queue/dispatch/another.json',{'status':'calling'})
  before=file_sha256(self.pool)
  with self.assertRaises(AssertionError):self.run_merge()
  self.assertEqual(file_sha256(self.pool),before)

 def test_changed_actual_input_bytes_are_rejected(self):
  Path(self.refs[0]).write_bytes(b'changed target')
  with self.assertRaises(AssertionError):self.run_merge()

 def test_claim_derives_missing_flag_only_from_exact_actual_snapshot(self):
  c=dict(self.candidate,verified_actual_snapshot_sha256=self.failed['actual_request_verification']['actual_request_snapshot_sha256'])
  self.assertIs(expected_transparency(c,self.failed),True)
  c['verified_actual_snapshot_sha256']='0'*64
  with self.assertRaises(AssertionError):expected_transparency(c,self.failed)

 def test_claim_rejects_flag_conflicting_with_actual_request(self):
  c=dict(self.candidate,original_tool_transparent_background=False)
  with self.assertRaises(AssertionError):expected_transparency(c,self.failed)

 def test_exhausted_source_is_skipped_without_reset(self):
  q=read_json(self.queue);q['sources'][self.key]['retries_used']=8;write_json(self.queue,q)
  before=file_sha256(self.queue);result=self.run_merge()
  self.assertEqual(result['added'],0);self.assertEqual(result['already_used_skipped'],1)
  self.assertEqual(file_sha256(self.queue),before);self.assertEqual(read_json(self.pool)['requests'][self.key],self.old)

if __name__=='__main__':unittest.main()
