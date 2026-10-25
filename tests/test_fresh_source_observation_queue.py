import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools import fresh_source_observation_queue as queue
from tools.common import read_json,write_json,file_sha256,utc_now

class FreshObservationTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);self.keys=[f'{i:064x}' for i in range(1,9)]
  self.addCleanup(patch.stopall);patch.object(queue,'machine_id',return_value='fixture').start();patch.object(queue,'same_service_family',side_effect=lambda k,b,p,q:p.get('family') is not None and p.get('family')==q.get('family')).start()
  self.data=self.root/'mod_nailong/data'
  write_json(self.data/'generated.json',{'portraits':{}})
  write_json(self.data/'catalog.json',{'assets':[{'source_sha256':k,'path':f'gfx/leaders/{i}.dds'} for i,k in enumerate(self.keys)]})
  write_json(self.data/'production-priority.json',{'sources':{k:{'high_priority':True} for k in self.keys}})
  write_json(self.data/'generation-failures.json',{'attempts':[],'held_source_paths':[]});write_json(self.data/'nonperson-source-observations.json',{'observations':{}})
  for k in self.keys:
   p=self.root/f'runtime/references/{k}.png';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('exact original '+k).encode())
  ref=self.root/'mod_nailong/assets/reference/naiwa.png';ref.parent.mkdir(parents=True);ref.write_bytes(b'exact reference')
  preparer=self.root/'tools/prepare_reviewed_fresh_sources.py';preparer.parent.mkdir();preparer.write_bytes(b'fixture preparer, not executed')
 def claim(self,slot='a'):return queue.claim(self.root,slot)
 def config(self,allocation):
  sources=allocation['sources'];path=self.root/f'runtime/{allocation["tag"]}-observations.json'
  write_json(path,{'machine_id':'fixture','allocation':allocation['allocation'],'allocation_sha256':allocation['allocation_sha256'],'actually_observed':True,'review_started_at_utc':utc_now(),'review_completed_at_utc':utc_now(),'sources':[{'key':s['key'],'description':'Actually viewed exact original features.'} for s in sources],'held':{},'viewed_originals':[{'key':s['key'],'path':s['original'],'sha256':s['original_png_sha256']} for s in sources],'mascot_reference_sha256':file_sha256(self.root/'mod_nailong/assets/reference/naiwa.png')})
  return path
 def test_two_existing_slots_reserve_distinct_groups_of_four(self):
  a,b=self.claim('a'),self.claim('b');self.assertEqual(len(a['sources']),4);self.assertEqual(len(b['sources']),4)
  self.assertFalse({s['key'] for s in a['sources']}&{s['key'] for s in b['sources']});resumed=self.claim();self.assertTrue(resumed['resume_existing_observation']);self.assertEqual(resumed['allocation'],a['allocation'])
  self.assertFalse((self.data/'generation-requests').exists())
 def test_authorized_low_observation_waits_until_high_fresh_supply_is_empty(self):
  from tools.production_priority_gate import POLICY
  write_json(self.data/'production-scheduling-policy.json',{'id':POLICY,'user_authorization_quote':'fixture','allow_low_when_no_immediate_high':True})
  p=read_json(self.data/'production-priority.json');p['sources'][self.keys[0]]['high_priority']=False;write_json(self.data/'production-priority.json',p)
  self.assertNotIn(self.keys[0],{s['key'] for s in queue.candidates(self.root)})
  write_json(self.data/'generated.json',{'portraits':{k:{} for k in self.keys[1:]}})
  self.assertEqual([s['key'] for s in queue.candidates(self.root)],[self.keys[0]])
  self.assertEqual(queue.candidates(self.root,high_only=True),[])
 def test_high_nonperson_generated_and_unresolved_families_are_enforced(self):
  p=read_json(self.data/'production-priority.json');p['sources'][self.keys[0]]['high_priority']=False
  p['sources'][self.keys[3]]['family']=p['sources'][self.keys[4]]['family']='same';write_json(self.data/'production-priority.json',p)
  write_json(self.data/'nonperson-source-observations.json',{'observations':{self.keys[1]:{}}})
  write_json(self.data/'generated.json',{'portraits':{self.keys[2]:{}}})
  write_json(self.data/'generation-failures.json',{'attempts':[{'source_sha256':self.keys[3],'status':'blocked'}]})
  self.assertEqual({s['key'] for s in queue.candidates(self.root)},set(self.keys[5:]))
 def test_uncached_original_decodes_exact_source_without_resizing(self):
  import hashlib
  from PIL import Image
  raw=self.root/'native.png';Image.new('RGBA',(7,9),(23,45,67,253)).save(raw)
  key=hashlib.sha256(raw.read_bytes()).hexdigest();target=self.root/f'runtime/references/{key}.png'
  write_json(self.root/'runtime/source-index.json',{'fixture':{'path':str(raw),'member':None}})
  item=queue.extract_original(self.root,{'key':key,'original':str(target),'original_source_asset_id':'fixture'})
  with Image.open(target) as im:self.assertEqual(im.size,(7,9));self.assertEqual(im.getpixel((2,3)),(23,45,67,253))
  self.assertEqual(item['original_png_sha256'],file_sha256(target))
 def test_uncached_changed_source_is_not_extracted_as_old_identity(self):
  raw=self.root/'changed.bin';raw.write_bytes(b'changed installed source')
  write_json(self.root/'runtime/source-index.json',{'fixture':{'path':str(raw),'member':None}})
  target=self.root/f'runtime/references/{"f"*64}.png'
  with self.assertRaisesRegex(AssertionError,'source changed'):
   queue.extract_original(self.root,{'key':'f'*64,'original':str(target),'original_source_asset_id':'fixture'})
  self.assertFalse(target.exists())
 def test_current_output_feedback_precedes_unbounded_low_source_observation(self):
  from tools.production_priority_gate import POLICY
  write_json(self.data/'production-scheduling-policy.json',{'id':POLICY,'user_authorization_quote':'fixture','allow_low_when_no_immediate_high':True})
  key=self.keys[0];journal=f'mod_nailong/data/generation-requests/{key}.json'
  write_json(self.root/journal,{'attempts':[{'status':'generated_pending_visual_review','fullsize_sha256':'f'*64}]})
  write_json(self.data/'generated.json',{'portraits':{key:{'review':'pending','generated_fullsize_sha256':'f'*64,'request_journal':journal}}})
  with patch('tools.portrait_review_queue.reviewed_outputs',return_value=set()):result=self.claim()
  self.assertFalse(result['ready']);self.assertEqual(result['reason'],'review_current_output_before_more_original_observation')
  self.assertFalse((self.root/'runtime/fresh-source-observations/allocations').exists())
 def supply_fixture(self,queued=0):
  from tools.production_priority_gate import POLICY
  write_json(self.data/'production-scheduling-policy.json',{'id':POLICY,'user_authorization_quote':'fixture','allow_low_when_no_immediate_high':True,'protect_low_generation_supply':True,'low_source_supply_slot':'b','low_source_supply_floor':8})
  write_json(self.data/'production-priority.json',{'sources':{k:{'high_priority':False} for k in self.keys}})
  key=self.keys[0];journal=f'mod_nailong/data/generation-requests/{key}.json'
  write_json(self.root/journal,{'attempts':[{'status':'generated_pending_visual_review','fullsize_sha256':'f'*64}]})
  write_json(self.data/'generated.json',{'portraits':{key:{'review':'pending','generated_fullsize_sha256':'f'*64,'request_journal':journal}}})
  write_json(self.root/'runtime/rolling-review-queue/slot-a.json',{'machine_id':'fixture','slot':'a','status':'assigned','tag':'review-a','source_keys':[key]})
  write_json(self.root/'runtime/rolling-review-queue/slot-b.json',{'machine_id':'fixture','slot':'b','status':'completed'})
  write_json(self.root/'runtime/rolling-production/owner.json',{'machine_id':'fixture','run_id':'fixture-run'})
  write_json(self.root/'runtime/rolling-production/fixture-run.json',{'machine_id':'fixture','run_id':'fixture-run','status':'running','next_index':0})
  write_json(self.root/'runtime/supply-jobs.json',[{'key':f'{i+100:064x}'} for i in range(queued)])
  write_json(self.root/'runtime/after128-continuous-plan.json',{'batches':[{'jobs':'runtime/supply-jobs.json'}] if queued else []})
 def test_empty_generation_supply_can_refill_without_waiting_for_other_slots_review(self):
  self.supply_fixture();protected=[self.data/'generated.json',self.data/'generation-requests'/f'{self.keys[0]}.json',self.root/'runtime/rolling-review-queue/slot-a.json']
  before=[file_sha256(path) for path in protected]
  with patch('tools.portrait_review_queue.reviewed_outputs',return_value=set()):result=self.claim('b')
  self.assertTrue(result['ready']);self.assertEqual(len(result['sources']),4)
  self.assertEqual(result['low_supply_observation']['prepared_requests'],0)
  self.assertEqual(result['low_supply_observation']['other_review_tag'],'review-a')
  self.assertEqual(before,[file_sha256(path) for path in protected]);self.assertFalse((self.root/'runtime/production-queue/dispatch').exists())
  self.assertEqual(read_json(self.root/result['allocation'])['low_supply_observation'],result['low_supply_observation'])
 def test_supply_observation_does_not_starve_review_when_buffer_is_sufficient(self):
  for queued,allowed in [(8,True),(9,False)]:
   with self.subTest(queued=queued):
    self.supply_fixture(queued)
    self.assertEqual(queue.low_supply_observation(self.root,'b') is not None,allowed)
  self.supply_fixture()
  write_json(self.root/'runtime/production-queue/preparation/pending/observed.json',{'expected_source_keys':self.keys+['f'*64]})
  self.assertIsNone(queue.low_supply_observation(self.root,'b'))
 def test_supply_refill_needs_free_original_slot_other_active_review_and_live_owner(self):
  for case in ['own_review_active','other_review_finished','owner_stopped','stop_requested','wrong_machine','policy_disabled','other_slot']:
   with self.subTest(case=case):
    self.supply_fixture()
    if case=='own_review_active':write_json(self.root/'runtime/rolling-review-queue/slot-b.json',{'status':'assigned'})
    elif case=='other_review_finished':write_json(self.root/'runtime/rolling-review-queue/slot-a.json',{'status':'completed'})
    elif case=='owner_stopped':write_json(self.root/'runtime/rolling-production/fixture-run.json',{'machine_id':'fixture','run_id':'fixture-run','status':'stopped_at_safe_boundary','next_index':0})
    elif case=='stop_requested':write_json(self.root/'runtime/rolling-production/fixture-run-stop-requested.json',{})
    elif case=='wrong_machine':write_json(self.root/'runtime/rolling-production/owner.json',{'machine_id':'elsewhere','run_id':'fixture-run'})
    elif case=='policy_disabled':
     p=self.data/'production-scheduling-policy.json';body=read_json(p);body['protect_low_generation_supply']=False;write_json(p,body)
    self.assertIsNone(queue.low_supply_observation(self.root,'a' if case=='other_slot' else 'b'))
    stop=self.root/'runtime/rolling-production/fixture-run-stop-requested.json'
    if stop.exists():stop.unlink()
 def test_supply_refill_still_observes_high_first_and_never_reuses_a_refused_source(self):
  self.supply_fixture()
  write_json(self.data/f'generation-requests/{self.keys[2]}.json',{'attempts':[{'status':'failed'}]})
  priority=read_json(self.data/'production-priority.json');priority['sources'][self.keys[1]]['high_priority']=True;write_json(self.data/'production-priority.json',priority)
  with patch('tools.portrait_review_queue.reviewed_outputs',return_value=set()):result=self.claim('b')
  self.assertEqual([s['key'] for s in result['sources']],[self.keys[1]])
  self.assertNotIn(self.keys[2],{s['key'] for s in queue.candidates(self.root)})
  self.assertFalse((self.root/'runtime/production-queue/dispatch').exists())
 def test_all_cancelled_history_is_allowed_only_without_any_dispatch(self):
  key=self.keys[0];journal=self.data/f'generation-requests/{key}.json';write_json(journal,{'attempts':[{'status':'cancelled_before_generation'}]})
  self.assertEqual(next(s for s in queue.candidates(self.root) if s['key']==key)['cancelled_request_history']['journal_sha256'],file_sha256(journal))
  write_json(self.root/f'runtime/production-queue/dispatch/{key}-001.json',{'status':'failed'})
  self.assertNotIn(key,{s['key'] for s in queue.candidates(self.root)})
 def test_prepared_or_failed_history_never_enters_fresh_path(self):
  for key,status in zip(self.keys[:2],('prepared','failed')):write_json(self.data/f'generation-requests/{key}.json',{'attempts':[{'status':status}]})
  self.assertFalse(set(self.keys[:2])&{s['key'] for s in queue.candidates(self.root)})
 def test_completed_actual_observations_queue_only_a_sha_bound_intent(self):
  a=self.claim();config=self.config(a);before=[file_sha256(self.data/p) for p in ('generated.json','generation-failures.json')]
  result=queue.complete(self.root,config);self.assertEqual(result['queued_originals'],4);self.assertEqual(result['image_calls'],0)
  intent=read_json(self.root/result['preparation_intent']);self.assertEqual(intent['kind'],'reviewed_fresh_sources');self.assertEqual(intent['expected_source_keys'],[s['key'] for s in a['sources']])
  self.assertEqual(before,[file_sha256(self.data/p) for p in ('generated.json','generation-failures.json')]);self.assertFalse((self.data/'generation-requests').exists())
 def test_changed_original_bytes_cannot_reuse_visual_observation(self):
  a=self.claim();config=self.config(a);Path(a['sources'][0]['original']).write_bytes(b'different bytes')
  with self.assertRaises(AssertionError):queue.complete(self.root,config)
  self.assertFalse((self.root/'runtime/production-queue/preparation/pending').exists())
 def test_unallocated_or_missing_source_cannot_be_substituted(self):
  a=self.claim();config=self.config(a);body=read_json(config);body['sources'][0]['key']='f'*64;write_json(config,body)
  with self.assertRaises(AssertionError):queue.complete(self.root,config)
 def test_uncertain_all_held_group_records_no_generation_intent(self):
  a=self.claim();config=self.config(a);body=read_json(config);body['held']={s['key']:'Source ambiguity retained.' for s in a['sources']};body['sources']=[];write_json(config,body)
  result=queue.complete(self.root,config);self.assertEqual(result['held_originals'],4);self.assertIsNone(result['preparation_intent'])
 def test_completed_group_is_never_staged_twice(self):
  a=self.claim();config=self.config(a);queue.complete(self.root,config)
  with self.assertRaises(AssertionError):queue.complete(self.root,config)
 def test_changed_allocation_sha_is_held(self):
  a=self.claim();config=self.config(a);p=self.root/a['allocation'];body=read_json(p);body['sources'].reverse();write_json(p,body)
  with self.assertRaises(AssertionError):queue.complete(self.root,config)
 def test_partial_staging_is_not_automatically_replayed(self):
  a=self.claim();write_json(self.data/f'production-fresh-source-observations/{a["tag"]}.json',{'partial':'retained'})
  result=self.claim();self.assertFalse(result['ready']);self.assertIn('reconciliation',result['reason'])

if __name__=='__main__':unittest.main()
