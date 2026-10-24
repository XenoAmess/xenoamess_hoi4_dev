import copy,json,unittest
from unittest.mock import patch
from tools import legacy_cached_request as cache

class CachedRequestTests(unittest.TestCase):
 def setUp(self):
  self.key='a'*64;self.job={'key':self.key,'prompt':'original complete prompt','references':['first.png','second.png'],'transparent':False}
  self.events={
   'cache_loader':{'type':'response_item','timestamp':'2026-10-16T12:00:00Z','payload':{'type':'custom_tool_call','name':'exec','input':'reviewed exact loader'}},
   'pre_call_job':{'timestamp':'2026-10-16T12:01:00Z','payload':{'type':'item_completed','item':{'type':'CommandExecution','status':'completed','exit_code':0,'command':['cmd.exe','/c','type exact historical jobs.json'],'stdout':json.dumps([{'key':'b'*64},self.job])}}},
   'dispatch':{'type':'response_item','timestamp':'2026-10-16T12:02:00Z','payload':{'type':'custom_tool_call','name':'exec','input':'reviewed exact caller'}},
   'failed_extension':{'timestamp':'2026-10-16T12:03:00Z'}}
  records={name:{'raw_utf8':json.dumps(e)+'\n','raw_line_sha256':cache.digest(json.dumps(e)+'\n')} for name,e in self.events.items()}
  records['cache_loader']['source_byte_offset']=100;records['dispatch']['source_byte_offset']=1000
  end=1000+len(records['dispatch']['raw_utf8'].encode('utf-8'))
  self.contract={'key':self.key,'loader':cache.digest('reviewed exact loader'),'dispatch':cache.digest('reviewed exact caller'),'command':'type exact historical jobs.json','index':1,'list_length':2,'interval_sha256':'f'*64,'interval_bytes':end-100}
  self.archive={'schema':'naiwa-recovered-cached-actual-request-v1','cache_name':'fixture_cache','events':records,'cache_interval_proof':{'start_byte_offset':100,'end_byte_offset':end,'interval_bytes':end-100,'interval_sha256':'f'*64,'matching_tool_call_line_sha256':[records['cache_loader']['raw_line_sha256'],records['dispatch']['raw_line_sha256']]}}
  self.addCleanup(patch.stopall);patch.object(cache,'CONTRACTS',{'fixture_cache':self.contract}).start()
 def validate(self):return cache.validate_cached_job(self.key,self.archive,self.events)
 def test_retains_false_flag_and_order_from_the_exact_list_slot(self):
  before=copy.deepcopy(self.archive);self.assertEqual(self.validate(),self.job);self.assertFalse(self.validate()['transparent']);self.assertEqual(self.archive,before)
 def test_other_source_cannot_reuse_known_cache_code(self):
  with self.assertRaises(AssertionError):cache.validate_cached_job('b'*64,self.archive,self.events)
 def test_unknown_loader_or_dispatcher_is_held(self):
  for name in ('cache_loader','dispatch'):
   with self.subTest(name=name):
    old=self.events[name]['payload']['input'];self.events[name]['payload']['input']='changed code'
    with self.assertRaises(AssertionError):self.validate()
    self.events[name]['payload']['input']=old
 def test_wrong_list_position_cannot_select_another_job(self):
  self.contract['index']=0
  with self.assertRaises(AssertionError):self.validate()
 def test_another_read_command_cannot_substitute_for_actual_stdout(self):
  self.events['pre_call_job']['payload']['item']['command'][-1]='type intended-draft.json'
  with self.assertRaises(AssertionError):self.validate()
 def test_cache_mutation_or_missing_interval_proof_is_held(self):
  self.archive['cache_interval_proof']['matching_tool_call_line_sha256'].insert(1,'unknown intervening cache writer')
  with self.assertRaises(AssertionError):self.validate()
 def test_interval_hash_or_size_change_is_held(self):
  for field,value in (('interval_sha256','0'*64),('interval_bytes',2)):
   with self.subTest(field=field):
    old=self.archive['cache_interval_proof'][field];self.archive['cache_interval_proof'][field]=value
    with self.assertRaises(AssertionError):self.validate()
    self.archive['cache_interval_proof'][field]=old
 def test_stdout_after_dispatch_is_not_pre_call_cache_proof(self):
  self.events['pre_call_job']['timestamp']='2026-10-16T12:02:30Z'
  with self.assertRaises(AssertionError):self.validate()

if __name__=='__main__':unittest.main()
