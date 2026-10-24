import tempfile,unittest
from pathlib import Path
from tools.common import write_json,file_sha256
from mod_nailong.tools.art_preparation_guard import select_review_cases


class ExactArtReviewSelectionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.key='a'*64;self.raw='f'*64;self.cases=[]
  for name,reason in [('old','Old alpha finding'),('new','Actual new outfit finding')]:
   relative='mod_nailong/data/'+name+'.json';entry={'source_sha256':self.key,'generated_fullsize_sha256':self.raw,'decision':'rejected','reason':reason};write_json(self.root/relative,{'decisions':[entry]});self.cases.append((entry,relative))
  relative='mod_nailong/data/new.json';self.selection={'schema':'naiwa-exact-art-review-selection-v1','entries':[{'source_sha256':self.key,'generated_fullsize_sha256':self.raw,'report':relative,'report_sha256':file_sha256(self.root/relative)}]}
 def test_exact_selection_keeps_one_intended_report_when_many_reports_repeat_source(self):
  selected=select_review_cases(self.cases,self.selection,self.root,file_sha256)
  self.assertEqual(len(selected),1);self.assertEqual(selected[0][0]['reason'],'Actual new outfit finding')
 def test_changed_report_and_wrong_current_sha_are_rejected(self):
  self.selection['entries'][0]['generated_fullsize_sha256']='b'*64
  with self.assertRaises(AssertionError):select_review_cases(self.cases,self.selection,self.root,file_sha256)
  self.selection['entries'][0]['generated_fullsize_sha256']=self.raw;(self.root/'mod_nailong/data/new.json').write_text('{}',encoding='utf-8')
  with self.assertRaises(AssertionError):select_review_cases(self.cases,self.selection,self.root,file_sha256)
 def test_old_unique_key_selection_remains_supported_but_ambiguous_one_stays_blocked(self):
  self.assertEqual(select_review_cases(self.cases[:1],[self.key],self.root,file_sha256),self.cases[:1])
  with self.assertRaises(AssertionError):select_review_cases(self.cases,[self.key],self.root,file_sha256)
 def test_duplicate_source_in_explicit_selection_cannot_prepare_twice(self):
  self.selection['entries']*=2
  with self.assertRaises(AssertionError):select_review_cases(self.cases,self.selection,self.root,file_sha256)

if __name__=='__main__':unittest.main()
