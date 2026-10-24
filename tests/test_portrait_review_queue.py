import tempfile,unittest
from pathlib import Path
from tools.common import write_json
from tools.portrait_review_queue import reserve_candidates,wait_for_claim,reviewed_outputs,ALPHA_POLICY

class ReviewSlotTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.rows={};self.priority={};assets=[]
  for n in range(6):
   key=str(n)*64;digest=chr(97+n)*64;journal='mod_nailong/data/generation-requests/'+key+'.json'
   write_json(self.root/journal,{'attempts':[{'status':'generated_pending_visual_review','fullsize_sha256':digest}]})
   self.rows[key]={'review':'pending','generated_fullsize_sha256':digest,'request_journal':journal,'prompt':'actual source prompt'}
   self.priority[key]={'high_priority':True};assets.append({'source_sha256':key,'path':'gfx/portrait_'+str(n)+'.dds'})
  write_json(self.root/'mod_nailong/data/catalog.json',{'assets':assets})
 def test_two_slots_reserve_disjoint_actual_outputs_without_canonical_writes(self):
  first=reserve_candidates(self.root,self.rows,self.priority,set(),'a');second=reserve_candidates(self.root,self.rows,self.priority,set(),'b')
  self.assertEqual(len(first),4);self.assertEqual(len(second),2)
  self.assertFalse({j['key'] for j in first}&{j['key'] for j in second})
  self.assertEqual(reserve_candidates(self.root,self.rows,self.priority,set(),'a'),[])
  self.assertFalse((self.root/'mod_nailong/data/generated.json').exists())
 def test_prior_seen_output_and_low_priority_are_not_reassigned(self):
  key='0'*64;seen={(key,self.rows[key]['generated_fullsize_sha256'])};self.priority['1'*64]['high_priority']=False
  jobs=reserve_candidates(self.root,self.rows,self.priority,seen,'a')
  self.assertNotIn(key,{j['key'] for j in jobs});self.assertNotIn('1'*64,{j['key'] for j in jobs})
 def test_changed_current_sha_can_be_reserved_after_old_output(self):
  reserve_candidates(self.root,self.rows,self.priority,set(),'a')
  key='0'*64;self.rows[key]['generated_fullsize_sha256']='f'*64
  write_json(self.root/self.rows[key]['request_journal'],{'attempts':[{'status':'generated_pending_visual_review','fullsize_sha256':'f'*64}]})
  self.assertIn(key,{j['key'] for j in reserve_candidates(self.root,self.rows,self.priority,set(),'b')})
 def test_incomplete_import_snapshot_does_not_stop_or_reserve_review_slot(self):
  key='0'*64;journal=self.rows[key].pop('request_journal');deferred=[]
  jobs=reserve_candidates(self.root,self.rows,self.priority,set(),'a',deferred=deferred)
  self.assertNotIn(key,{j['key'] for j in jobs});self.assertEqual(deferred[0]['missing'],['request_journal'])
  reservation=self.root/'runtime/rolling-review-queue/reservations'/ALPHA_POLICY/(key+'-'+self.rows[key]['generated_fullsize_sha256']+'.json')
  self.assertFalse(reservation.exists())
  self.rows[key]['request_journal']=journal
  self.assertIn(key,{j['key'] for j in reserve_candidates(self.root,self.rows,self.priority,set(),'b')})
 def test_occupied_allocation_lock_times_out_without_crashing_or_stealing(self):
  now=[0];calls=[]
  def occupied(slot):calls.append(slot);raise FileExistsError('other reviewer owns allocation')
  def sleep(seconds):now[0]+=seconds
  result=wait_for_claim('b',2,occupied,lambda:now[0],sleep)
  self.assertFalse(result['ready']);self.assertFalse(result['allocation_claimed']);self.assertEqual(result['reason'],'another_review_allocation_owns_lock')
  self.assertEqual(calls,['b','b','b'])
 def test_waiting_slot_claims_only_after_other_allocator_releases(self):
  now=[0]
  def allocate(slot):
   if now[0]<2:raise FileExistsError('occupied')
   return {'ready':True,'slot':slot}
  result=wait_for_claim('b',5,allocate,lambda:now[0],lambda seconds:now.__setitem__(0,now[0]+seconds))
  self.assertTrue(result['ready']);self.assertEqual(now[0],2)
 def test_policy_reopens_only_old_pending_and_preserves_terminal_history(self):
  write_json(self.root/'mod_nailong/data/alpha-acceptance-policy.json',{'id':ALPHA_POLICY,'effective_from_utc':'2026-10-24T09:10:00+00:00'})
  decisions=[{'source_sha256':str(n)*64,'generated_fullsize_sha256':chr(97+n)*64,'decision':decision} for n,decision in enumerate(['pending','approved','rejected'])]
  write_json(self.root/'mod_nailong/data/resumed-old-agent-review.json',{'reviewed_at_utc':'2026-10-24T08:00:00+00:00','decisions':decisions})
  seen=reviewed_outputs(self.root)
  self.assertNotIn(('0'*64,'a'*64),seen);self.assertIn(('1'*64,'b'*64),seen);self.assertIn(('2'*64,'c'*64),seen)
  write_json(self.root/'mod_nailong/data/resumed-new-agent-review.json',{'reviewed_at_utc':'2026-10-24T09:11:00+00:00','decisions':[decisions[0]]})
  self.assertIn(('0'*64,'a'*64),reviewed_outputs(self.root))
 def test_old_policy_reservation_does_not_block_fresh_two_slot_review(self):
  key='0'*64;digest=self.rows[key]['generated_fullsize_sha256']
  write_json(self.root/'runtime/rolling-review-queue/reservations'/(key+'-'+digest+'.json'),{'slot':'a'})
  first=reserve_candidates(self.root,self.rows,self.priority,set(),'a');second=reserve_candidates(self.root,self.rows,self.priority,set(),'b')
  self.assertIn(key,{j['key'] for j in first});self.assertFalse({j['key'] for j in first}&{j['key'] for j in second})

if __name__=='__main__':unittest.main()
