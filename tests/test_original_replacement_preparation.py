import tempfile,unittest
from pathlib import Path
from tools.common import read_json,write_json,file_sha256,machine_id
from tools.prepare_reviewed_original_replacements import prepare_replacements

class OriginalReplacementPreparationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.key='a'*64
  raw=self.root/'mod_nailong/assets/generated_fullsize/old.png';raw.parent.mkdir(parents=True);raw.write_bytes(b'unchanged actual raw fixture');self.raw_sha=file_sha256(raw)
  self.journal='mod_nailong/data/generation-requests/'+self.key+'.json';write_json(self.root/self.journal,{'attempts':[{'number':1,'status':'generated_rejected_visual_review','fullsize_sha256':self.raw_sha}]})
  self.report=self.root/'mod_nailong/data/review.json';write_json(self.report,{'machine_id':machine_id(),'decisions_staged':True,'decisions':[{'source_sha256':self.key,'decision':'rejected','generated_fullsize_sha256':self.raw_sha}]})
  self.config={'machine_id':machine_id(),'sources':[{'source_sha256':self.key,'rejected_fullsize_sha256':self.raw_sha,'manual_review_report':'mod_nailong/data/review.json','manual_review_report_sha256':file_sha256(self.report),'replacement_reason':'Real prior PNG rejected; original-based method avoids inherited error','prompt':'Complete actual source-directed prompt'}]}
  write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':[]});write_json(self.root/'mod_nailong/data/generated.json',{'portraits':{self.key:{'review':'rejected','generated_fullsize_sha256':self.raw_sha,'generated_fullsize_image':raw.relative_to(self.root).as_posix(),'request_journal':self.journal}}})
  write_json(self.root/'mod_nailong/data/production-priority.json',{'sources':{self.key:{'high_priority':True}}});write_json(self.root/'mod_nailong/data/generation-failures.json',{'attempts':[]})
 def fake_prepare(self,key,prompt,edit_existing,**options):
  self.assertEqual(key,self.key);self.assertFalse(edit_existing);self.assertEqual(prompt,self.config['sources'][0]['prompt']);self.assertTrue(options['replacement_reason'])
  history=read_json(self.root/self.journal);history['attempts'].append({'number':len(history['attempts'])+1,'status':'prepared','edit_existing':False,'inputs':[{'role':'original source portrait'},{'role':'user mascot reference'}],'prompt_sha256':'f'*64});write_json(self.root/self.journal,history)
  return {'key':key,'journal':self.journal,'references':['exact original','user reference']}
 def test_actual_rejected_master_yields_two_original_inputs_and_one_plan_append(self):
  result=prepare_replacements(self.root,'replacement',0,self.config,self.fake_prepare)
  self.assertEqual(result['prepared'],1);self.assertEqual(len(read_json(self.root/'runtime/after128-continuous-plan.json')['batches']),1)
  with self.assertRaises(AssertionError):prepare_replacements(self.root,'replacement',0,self.config,lambda *_a,**_k:self.fail('replayed'))
 def test_stale_manual_report_is_rejected_before_any_preparation(self):
  write_json(self.report,{'changed':True})
  with self.assertRaises(AssertionError):prepare_replacements(self.root,'replacement',0,self.config,lambda *_a,**_k:self.fail('changed evidence'))
 def test_failed_service_attempt_cannot_be_replaced_by_new_art_request(self):
  write_json(self.root/self.journal,{'attempts':[{'number':1,'status':'failed','fullsize_sha256':self.raw_sha}]})
  with self.assertRaises(AssertionError):prepare_replacements(self.root,'replacement',0,self.config,lambda *_a,**_k:self.fail('failed payload alternative'))
 def test_partial_preparation_is_preserved_and_not_automatically_replayed(self):
  def interrupted(*args,**kwargs):self.fake_prepare(*args,**kwargs);raise OSError('interruption after prepared journal persisted')
  with self.assertRaises(OSError):prepare_replacements(self.root,'replacement',0,self.config,interrupted)
  self.assertEqual(read_json(self.root/self.journal)['attempts'][-1]['status'],'prepared')
  with self.assertRaises(AssertionError):prepare_replacements(self.root,'replacement',0,self.config,lambda *_a,**_k:self.fail('partial replay'))
 def test_uncalled_cancelled_draft_after_actual_rejection_allows_original_method(self):
  history=read_json(self.root/self.journal)
  history['attempts'].append({'number':2,'status':'cancelled_before_generation'})
  write_json(self.root/self.journal,history)
  result=prepare_replacements(self.root,'replacement',0,self.config,self.fake_prepare)
  receipt=read_json(self.root/result['receipt'])
  boundary=receipt['followups'][0]['preparation_boundary']
  self.assertEqual(boundary['boundary'],'uncalled_cancelled_drafts_after_actual_rejected_png')
  self.assertEqual(boundary['actual_rejected_attempt'],1)
  self.assertEqual(boundary['cancelled_attempts'],[2])
 def test_cancelled_draft_with_dispatch_evidence_blocks_replacement(self):
  history=read_json(self.root/self.journal)
  history['attempts'].append({'number':2,'status':'cancelled_before_generation'})
  write_json(self.root/self.journal,history)
  write_json(self.root/f'runtime/production-queue/dispatch/{self.key}-002.json',{'status':'interrupted_outcome_unknown'})
  with self.assertRaises(ValueError):prepare_replacements(self.root,'replacement',0,self.config,lambda *_a,**_k:self.fail('possible call replay'))
 def test_cancelled_draft_without_actual_rejected_png_blocks_replacement(self):
  write_json(self.root/self.journal,{'attempts':[{'number':1,'status':'cancelled_before_generation'}]})
  with self.assertRaises(ValueError):prepare_replacements(self.root,'replacement',0,self.config,lambda *_a,**_k:self.fail('no rejected PNG'))

if __name__=='__main__':unittest.main()
