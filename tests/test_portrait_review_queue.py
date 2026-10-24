import tempfile,unittest
from pathlib import Path
from tools.common import write_json
from tools.portrait_review_queue import reserve_candidates

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

if __name__=='__main__':unittest.main()
