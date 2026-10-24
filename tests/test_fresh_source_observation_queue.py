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
