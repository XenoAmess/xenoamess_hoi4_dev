import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools.common import read_json,write_json
from tools.rolling_production_queue import synchronize_retry_allowances


class RetryAllowanceBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.keys=['a'*64,'b'*64];self.other='c'*64
        self.policy={'max_cooldown_retries_per_source':8,'source_scoped_extra_retry_rounds':[{'authorization_id':'fixture','authorization_manifest':'mod_nailong/data/fixture.json','authorization_manifest_sha256':'f'*64,'additional_retries_per_selected_source':1,'retries_used_at_authorization':8,'source_keys':self.keys}]}
        self.path=self.root/'mod_nailong/data/image-retry-queue.json'
        self.queue={'sources':{key:{'retries_used':8,'max_cooldown_retries':8,'state':'retry_limit_reached','not_before_utc':'2026-10-24T10:00:00+00:00'} for key in [*self.keys,self.other]}}
        write_json(self.root/'mod_nailong/data/image-retry-policy.json',self.policy);write_json(self.path,self.queue)

    def test_owner_migrates_once_before_read_only_due_probe(self):
        calls=[]
        def run(command):
            calls.append(command);q=read_json(self.path)
            for key in self.keys:q['sources'][key].update(max_cooldown_retries=9,state='cooling_down')
            write_json(self.path,q)
            return subprocess.CompletedProcess(command,0,'','')
        result=synchronize_retry_allowances(self.root,run)
        self.assertTrue(result['synchronized']);self.assertEqual(result['quota_claims'],0)
        self.assertEqual(calls[0][-2:],['mod_nailong/tools/image_retries.py','sync'])
        after=read_json(self.path)['sources']
        self.assertTrue(all(e['retries_used']==8 for e in after.values()))
        self.assertEqual(after[self.other],self.queue['sources'][self.other])
        self.assertTrue(all(e['not_before_utc']=='2026-10-24T10:00:00+00:00' for e in after.values()))
        self.assertFalse(synchronize_retry_allowances(self.root,run)['synchronized']);self.assertEqual(len(calls),1)

    def test_migration_cannot_reset_counters(self):
        def run(command):
            q=copy.deepcopy(self.queue)
            for key in self.keys:q['sources'][key].update(max_cooldown_retries=9,retries_used=0)
            write_json(self.path,q);return subprocess.CompletedProcess(command,0,'','')
        with self.assertRaisesRegex(AssertionError,'consumed counters'):synchronize_retry_allowances(self.root,run)

    def test_no_migration_during_an_unresolved_call(self):
        write_json(self.root/'runtime/production-queue/dispatch/owned.json',{'status':'calling'})
        with self.assertRaisesRegex(AssertionError,'Unresolved actual call'):synchronize_retry_allowances(self.root,lambda c:self.fail('Must not migrate'))


if __name__=='__main__':unittest.main()
