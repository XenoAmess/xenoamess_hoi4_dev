import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.common import write_json,file_sha256,read_json
from tools import retry_actual_proof as proof

class HistoricalActualProofTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.key='a'*64
  self.addCleanup(patch.stopall);patch.object(proof,'machine_id',return_value='fixture').start()
  patch.object(proof,'LEGACY_DIRECT_FORWARDERS',{proof.digest_text('reviewed direct forwarding fixture')}).start()
  original=self.root/'runtime/references'/(self.key+'.png');original.parent.mkdir(parents=True);original.write_bytes(b'exact original PNG bytes')
  user=self.root/'mod_nailong/assets/reference/naiwa.png';user.parent.mkdir(parents=True);user.write_bytes(b'exact user reference bytes')
  self.job={'key':self.key,'prompt':'Complete original \u5976\u9f99 prompt.','references':[str(original),str(user)],'transparent':True,'journal':f'mod_nailong/data/generation-requests/{self.key}.json'}
  prompt=self.root/'mod_nailong/assets/prompts/frozen.txt';prompt.parent.mkdir(parents=True);prompt.write_text(self.job['prompt'],encoding='utf-8')
  self.attempt={'machine_id':'fixture','number':2,'prompt':self.job['prompt'],'prompt_file':prompt.relative_to(self.root).as_posix(),'prompt_sha256':file_sha256(prompt),'error':'moderation_blocked request ID 12345678-1234-1234-1234-123456789abc','observed_at_utc':'2026-10-16T12:03:00+00:00','inputs':[{'role':'original source portrait','raw_sha256':self.key,'converted_png_sha256':file_sha256(original)},{'role':'user mascot reference','path':user.relative_to(self.root).as_posix(),'sha256':file_sha256(user)}]}
  self.archive={'schema':'naiwa-recovered-actual-request-v1','machine_id':'fixture','source_sha256':self.key,'failed_attempt':2,'actual_recorded_before_call':False,'validated_from_retained_historical_tool_events':True,'recovered_at_utc':'2026-10-24T09:15:00+00:00','input_sha256':[file_sha256(original),file_sha256(user)],'events':{}}
  self.set_event('dispatch',{'type':'response_item','timestamp':'2026-10-16T12:00:00Z','payload':{'type':'custom_tool_call','name':'exec','input':'reviewed direct forwarding fixture'}})
  self.set_event('pre_call_job',{'timestamp':'2026-10-16T12:01:00Z','payload':{'type':'item_completed','item':{'type':'CommandExecution','status':'completed','exit_code':0,'command':['cmd.exe','/c','type runtime\\cooldown-retry-job.json'],'stdout':json.dumps(self.job)}}})
  self.set_event('failed_extension',{'timestamp':'2026-10-16T12:02:00Z','payload':{'item':{'type':'Extension','kind':'image_gen.generation','status':'failed','revisedPrompt':self.job['prompt'],'transparentBackground':None}}})
  self.set_event('refusal_receipt',{'timestamp':'2026-10-16T12:02:01Z','payload':{'item':{'type':'FileChange','status':'completed','changes':{self.key+'.txt':{'type':'add','content':self.attempt['error']}}}}})
 def set_event(self,name,event):
  raw=json.dumps(event,ensure_ascii=False)+'\n';self.archive['events'][name]={'raw_utf8':raw,'raw_line_sha256':proof.digest_text(raw)}
 def get_event(self,name):return json.loads(self.archive['events'][name]['raw_utf8'])
 def validate(self):return proof.validate_legacy_archive(self.root,self.key,self.attempt,self.archive)
 def test_recovery_preserves_false_pre_call_boundary_and_does_not_mutate_journal(self):
  before=copy.deepcopy(self.attempt);job,v=self.validate()
  self.assertEqual(job,self.job);self.assertIs(v['actual_recorded_before_call'],False);self.assertTrue(v['validated_from_retained_historical_tool_events']);self.assertEqual(self.attempt,before)
 def test_false_backdating_is_rejected(self):
  self.archive['actual_recorded_before_call']=True
  with self.assertRaises(AssertionError):self.validate()
 def test_actual_prompt_cannot_be_replaced_by_intended_text(self):
  e=self.get_event('failed_extension');e['payload']['item']['revisedPrompt']='different actual prompt';self.set_event('failed_extension',e)
  with self.assertRaises(AssertionError):self.validate()
 def test_retained_input_order_is_enforced(self):
  e=self.get_event('pre_call_job');job=json.loads(e['payload']['item']['stdout']);job['references'].reverse();e['payload']['item']['stdout']=json.dumps(job);self.set_event('pre_call_job',e)
  with self.assertRaises(AssertionError):self.validate()
 def test_unknown_dispatcher_is_not_treated_as_a_direct_forwarder(self):
  e=self.get_event('dispatch');e['payload']['input']='mutate(job.prompt)';self.set_event('dispatch',e)
  with self.assertRaises(AssertionError):self.validate()
 def test_refusal_from_another_request_is_rejected(self):
  e=self.get_event('refusal_receipt');e['payload']['item']['changes'][self.key+'.txt']['content']='moderation_blocked another request';self.set_event('refusal_receipt',e)
  with self.assertRaises(AssertionError):self.validate()
 def test_post_call_job_output_cannot_prove_call_arguments(self):
  e=self.get_event('pre_call_job');e['timestamp']='2026-10-16T12:02:02Z';self.set_event('pre_call_job',e)
  with self.assertRaises(AssertionError):self.validate()
 def test_altered_current_input_bytes_keep_request_held(self):
  Path(self.job['references'][0]).write_bytes(b'different bytes')
  with self.assertRaises(AssertionError):self.validate()
 def test_archive_must_stay_bound_to_the_reviewed_sha(self):
  path=self.root/f'mod_nailong/data/legacy-request-recoveries/{self.key}-002.json';write_json(path,self.archive)
  candidate={'historical_actual_evidence':{'path':path.relative_to(self.root).as_posix(),'sha256':file_sha256(path)}}
  _,v=proof.load_actual_request(self.root,self.key,self.attempt,candidate);self.assertFalse(v['actual_recorded_before_call'])
  changed=read_json(path);changed['recovered_at_utc']='changed';write_json(path,changed)
  with self.assertRaises(AssertionError):proof.load_actual_request(self.root,self.key,self.attempt,candidate)
 def test_existing_modern_verification_cannot_fall_back_to_legacy_to_hide_a_failure(self):
  self.attempt['actual_request_verification']={'actual_recorded_before_call':False}
  with self.assertRaises(AssertionError):proof.load_actual_request(self.root,self.key,self.attempt,{'historical_actual_evidence':{}})
 def test_legacy_manual_merge_preserves_failed_journal_and_consumed_retry_count(self):
  from tools import retry_scheduler_merge as merge
  patch.object(merge,'machine_id',return_value='fixture').start();patch.object(merge,'policy',return_value={'max_cooldown_retries_per_source':8}).start()
  self.attempt['status']='failed';journal=self.root/self.job['journal'];write_json(journal,{'attempts':[self.attempt]})
  queue=self.root/'mod_nailong/data/image-retry-queue.json';deadline='2026-10-16T20:03:00+00:00'
  write_json(queue,{'sources':{self.key:{'retries_used':1,'state':'cooling_down','not_before_utc':deadline,'cooldown_origin_attempt':2}}})
  archive=self.root/f'mod_nailong/data/legacy-request-recoveries/{self.key}-002.json';write_json(archive,self.archive)
  candidate=dict(self.job,input_sha256=self.archive['input_sha256'],original_actual_prompt_verified=True,policy_reviewed=True,manual_policy_review={'machine_id':'fixture'},not_before_utc=deadline,historical_actual_evidence={'path':archive.relative_to(self.root).as_posix(),'sha256':file_sha256(archive),'actual_recorded_before_call':False})
  proposal=self.root/'mod_nailong/data/reviewed.json';write_json(proposal,[candidate]);before=[file_sha256(journal),file_sha256(queue)]
  result=merge.merge_candidates(proposal,self.root)
  self.assertEqual(result['added'],1);self.assertEqual(result['quota_claims'],0);self.assertEqual(result['image_calls'],0)
  self.assertEqual(before,[file_sha256(journal),file_sha256(queue)])
  approved=read_json(self.root/'runtime/retry-scheduler/approved-pool.json')['requests'][self.key]
  self.assertFalse(approved['historical_actual_evidence']['actual_recorded_before_call']);self.assertTrue(approved['original_tool_transparent_background'])

if __name__=='__main__':unittest.main()
