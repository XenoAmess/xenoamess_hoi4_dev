import tempfile,unittest
from pathlib import Path
from tools.common import write_json,read_json
from tools.rolling_production_queue import claim,validate_prepared,next_item

class LogicalQueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  write_json(self.root/'mod_nailong/data/production-window-timings/prior-completed.json',{'machine_id':'m','window_id':'prior','status':'completed','batches':[{'batch':'old'}],'events':[{'phase':'batch_imports_completed','batch':'old'}]})
 def job(self,number):
  key=str(number)*64;path='runtime/jobs'+str(number)+'.json';journal='mod_nailong/data/generation-requests/'+key+'.json'
  write_json(self.root/journal,{'attempts':[{'number':1,'status':'prepared','prompt':'exact prompt'}]})
  write_json(self.root/path,[{'key':key,'prompt':'exact prompt','journal':journal}]);return {'batch':'b'+str(number),'jobs':path}
 def test_claim_retains_large_prepared_queue_and_excludes_second_owner(self):
  jobs=[self.job(1),self.job(2)];write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':jobs})
  state=claim(self.root,'run',0,'prior','m');self.assertEqual(next_item(self.root,state)['plan'],[jobs[0]])
  with self.assertRaises(FileExistsError):claim(self.root,'second',0,'prior','m')
 def test_returned_attempt_is_never_replayed_from_prepared_plan(self):
  item=self.job(1);j=self.root/('mod_nailong/data/generation-requests/'+'1'*64+'.json')
  body=read_json(j);body['attempts'][-1]['status']='generated_pending_visual_review';write_json(j,body)
  with self.assertRaisesRegex(AssertionError,'Already dispatched'):validate_prepared(self.root,item)
 def test_even_prepared_status_cannot_replay_existing_dispatch_ledger(self):
  item=self.job(1);write_json(self.root/('runtime/production-queue/dispatch/'+'1'*64+'-001.json'),{'status':'returned_image'})
  with self.assertRaises(AssertionError):validate_prepared(self.root,item)
 def test_active_actual_call_prevents_claim(self):
  write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':[]})
  write_json(self.root/'runtime/production-queue/dispatch/active.json',{'status':'calling'})
  with self.assertRaises(AssertionError):claim(self.root,'run',0,'prior','m')

if __name__=='__main__':unittest.main()
