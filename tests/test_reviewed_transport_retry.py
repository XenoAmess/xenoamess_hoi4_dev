import copy
import tempfile
import unittest
from pathlib import Path
from tools.common import read_json,write_json,file_sha256,machine_id
from tools.prepare_reviewed_transport_retry import prepare_transport_retry,CONNECTION_ERROR

class ReviewedTransportRetryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.key='a'*64
  self.journal=self.root/f'mod_nailong/data/generation-requests/{self.key}.json'
  self.raw=self.root/'mod_nailong/assets/generated_fullsize/raw.png';self.raw.parent.mkdir(parents=True);self.raw.write_bytes(b'actual target')
  self.original=self.root/'runtime/references/original.png';self.original.parent.mkdir(parents=True);self.original.write_bytes(b'actual original')
  self.reference=self.root/'mod_nailong/assets/reference/ref.png';self.reference.parent.mkdir(parents=True);self.reference.write_bytes(b'actual reference')
  self.refs=[str(p) for p in [self.raw,self.original,self.reference]];self.shas=[file_sha256(Path(p)) for p in self.refs]
  self.prompt=self.root/'mod_nailong/assets/prompts/old.txt';self.prompt.parent.mkdir(parents=True);self.prompt.write_text('Exact full prompt',encoding='utf-8')
  self.snapshot=self.root/'runtime/dispatch-actual/failed.json'
  self.actual={'key':self.key,'prompt':'Exact full prompt','transparent':True,'references':self.refs,'journal':self.journal.relative_to(self.root).as_posix(),'source':'portrait.dds'}
  write_json(self.snapshot,self.actual)
  self.error=self.root/'runtime/error.txt';self.error.write_text(CONNECTION_ERROR+'\n',encoding='utf-8',newline='\n')
  self.dispatch=self.root/f'runtime/production-queue/dispatch/{self.key}-002.json'
  ledger={'status':'tool_error','source_sha256':self.key,'attempt_number':2,'machine_id':machine_id(),'call_returned_at_utc':'2026-10-24T10:00:00+00:00','actual_error_file':str(self.error),'actual_error_sha256':file_sha256(self.error),'actual_request_snapshot_file':str(self.snapshot),'actual_request_snapshot_sha256':file_sha256(self.snapshot),'actual_prompt_verified_before_call':True,'input_sha256':self.shas}
  write_json(self.dispatch,ledger)
  last={'number':2,'status':'failed','error':CONNECTION_ERROR+'\n','prompt':'Exact full prompt','prompt_file':self.prompt.relative_to(self.root).as_posix(),'prompt_sha256':file_sha256(self.prompt),'inputs':[{'sha256':s} for s in self.shas],'actual_request_verification':{'actual_recorded_before_call':True,'actual_request_snapshot_sha256':file_sha256(self.snapshot),'transparent_background':True,'input_sha256':self.shas}}
  write_json(self.journal,{'attempts':[{'number':1,'status':'generated_rejected_visual_review'},last]})
  write_json(self.root/'mod_nailong/data/generated.json',{'portraits':{self.key:{'review':'rejected','generated_fullsize_sha256':self.shas[0],'generated_fullsize_image':self.raw.relative_to(self.root).as_posix()}}})
  write_json(self.root/'mod_nailong/data/production-priority.json',{'sources':{self.key:{'high_priority':True,'characters':['one'],'paths':['portrait.dds']}}})
  write_json(self.root/'mod_nailong/data/generation-failures.json',{'attempts':[]});write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':[]})
  self.config={'machine_id':machine_id(),'complete_prompt_actually_read':True,'source_sha256':self.key,'failed_attempt_number':2,'failed_dispatch_sha256':file_sha256(self.dispatch),'actual_request_snapshot_sha256':file_sha256(self.snapshot),'exact_prompt_sha256':file_sha256(self.prompt),'ordered_viewed_inputs':[{'path':p,'sha256':s,'actually_viewed':True} for p,s in zip(self.refs,self.shas)],'reviewed_at_utc':'2026-10-24T11:00:00+00:00'}
 def run_prepare(self):return prepare_transport_retry(self.root,'transport',0,self.config)
 def test_exact_connection_retry_preserves_payload_and_old_failure(self):
  before=read_json(self.journal)['attempts'][-1];result=self.run_prepare();history=read_json(self.journal)['attempts']
  self.assertEqual(history[-2],before);self.assertEqual(history[-1]['transport_retry_of_attempt'],2);self.assertNotIn('actual_request_verification',history[-1]);self.assertNotIn('error',history[-1])
  self.assertEqual(read_json(self.root/'runtime/production-transport-jobs.json'),[self.actual]);self.assertEqual((self.root/history[-1]['prompt_file']).read_bytes(),self.prompt.read_bytes())
  self.assertFalse((self.root/'mod_nailong/data/image-retry-queue.json').exists());self.assertEqual(result['prepared'],1)
 def test_moderation_error_never_enters_transport_path(self):
  j=read_json(self.journal);j['attempts'][-1]['error']='moderation_blocked';write_json(self.journal,j)
  with self.assertRaises(AssertionError):self.run_prepare()
 def test_unknown_or_active_call_is_never_replayed(self):
  d=read_json(self.dispatch);d['status']='interrupted_outcome_unknown';write_json(self.dispatch,d);self.config['failed_dispatch_sha256']=file_sha256(self.dispatch)
  with self.assertRaises(AssertionError):self.run_prepare()
 def test_input_byte_change_blocks_before_preparation(self):
  self.original.write_bytes(b'changed')
  with self.assertRaises(AssertionError):self.run_prepare()
  self.assertEqual(len(read_json(self.journal)['attempts']),2)
 def test_false_manual_observation_or_changed_flag_is_rejected(self):
  self.config['ordered_viewed_inputs'][0]['actually_viewed']=False
  with self.assertRaises(AssertionError):self.run_prepare()
 def test_service_family_hold_is_not_bypassed(self):
  write_json(self.root/'mod_nailong/data/generation-failures.json',{'attempts':[{'source_sha256':self.key,'status':'blocked'}]})
  with self.assertRaises(AssertionError):self.run_prepare()
 def test_prior_transport_retry_or_service_retry_blocks_automatic_loop(self):
  for field in ['transport_retry_of_attempt','retry_of_attempt']:
   j=read_json(self.journal);j['attempts'][-1][field]=1;write_json(self.journal,j)
   with self.assertRaises(AssertionError):self.run_prepare()
   del j['attempts'][-1][field];write_json(self.journal,j)

if __name__=='__main__':unittest.main()
