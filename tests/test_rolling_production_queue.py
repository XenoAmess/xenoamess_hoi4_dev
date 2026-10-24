import tempfile,unittest,json
from types import SimpleNamespace
from pathlib import Path
from tools.common import write_json,read_json,file_sha256
from tools.rolling_production_queue import claim,validate_prepared,next_item,allocate_exact_retry,finish_exact_retry

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
 def test_checkpoint_request_attaches_only_to_next_validated_prepared_window(self):
  item=self.job(1);write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':[item]})
  state=claim(self.root,'run',0,'prior','m')
  request=self.root/'runtime/rolling-production/run-checkpoint-requested.json';write_json(request,{'machine_id':'m','run_id':'run'})
  next=next_item(self.root,state)
  self.assertEqual(next['plan'][0]['checkpointCommand'],'python tools\\production_checkpoint.py b1')
  self.assertFalse(request.exists());self.assertTrue(request.with_name('run-checkpoint-claimed-0.json').exists())
 def test_no_eligible_exact_retry_does_not_claim_allowance(self):
  write_json(self.root/'runtime/retry-scheduler/state.json',{'machine_id':'m','pending':None})
  commands=[]
  def runner(command):
   commands.append(command);return SimpleNamespace(returncode=0,stdout=json.dumps({'count':0}),stderr='')
  self.assertIsNone(allocate_exact_retry(self.root,{'machine_id':'m','run_id':'run','next_index':0},runner))
  self.assertEqual(len(commands),1);self.assertIn('--inspect-only',commands[0])
 def test_exact_retry_uses_original_batch_and_finishes_before_cursor_advance(self):
  scheduler=self.root/'runtime/retry-scheduler/state.json';write_json(scheduler,{'machine_id':'m','pending':None})
  write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':[]})
  proof='runtime/proof.json';write_json(self.root/proof,[{'key':'1'*64}])
  pending={'machine_id':'m','batch':'cooldown-087','numeric_id':'087','count':1,'source_keys':['1'*64],'proof':proof,'proof_sha256':file_sha256(self.root/proof),'jobs':'runtime/cooldown-087-jobs.json'}
  commands=[]
  def runner(command):
   commands.append(command)
   if '--inspect-only' in command:body={'count':1}
   elif command[1].endswith('next.py'):
    write_json(scheduler,{'machine_id':'m','pending':pending});body=pending
   elif command[1].endswith('claim.py'):
    self.assertEqual(command[2:],[pending['numeric_id'],proof]);item=self.job(1)
    write_json(self.root/pending['jobs'],read_json(self.root/item['jobs']));body={}
   else:
    self.assertEqual(command[2],pending['batch']);write_json(scheduler,{'machine_id':'m','pending':None});body={}
   return SimpleNamespace(returncode=0,stdout=json.dumps(body),stderr='')
  state={'machine_id':'m','run_id':'run','next_index':0}
  item=allocate_exact_retry(self.root,state,runner)
  self.assertEqual(item,{'batch':pending['batch'],'jobs':pending['jobs']})
  self.assertEqual(read_json(self.root/'runtime/after128-continuous-plan.json')['batches'],[item])
  finish_exact_retry(self.root,state,runner);self.assertEqual(state['next_index'],0)
  self.assertEqual(len(commands),4)
 def test_partial_claim_stops_and_cannot_claim_again(self):
  scheduler=self.root/'runtime/retry-scheduler/state.json';write_json(scheduler,{'machine_id':'m','pending':{'batch':'cooldown-087'}})
  def runner(command):self.fail('Pending claim must never be selected again')
  with self.assertRaisesRegex(AssertionError,'explicit reconciliation'):
   allocate_exact_retry(self.root,{'machine_id':'m','run_id':'run','next_index':0},runner)

if __name__=='__main__':unittest.main()
