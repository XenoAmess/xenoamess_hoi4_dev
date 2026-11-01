import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import local_model_batch as batch

FAKE_CALL = '''
import argparse,json,time
from pathlib import Path
def prepare_request(path,config):
    p=Path(path);s=json.loads(p.read_text(encoding='utf-8'))
    source=(p.parent/s['stable_source_path']).read_text(encoding='utf-8') if 'stable_source_path' in s else '\\n'.join((p.parent/n).read_text(encoding='utf-8') for n in s['source_files'])
    return {'messages':[{'role':'system','content':'fixed'},{'role':'user','content':source},{'role':'user','content':(p.parent/s['task_path']).read_text(encoding='utf-8')}],'max_tokens':s['max_tokens']},None
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('spec');p.add_argument('task');p.add_argument('--output');p.add_argument('--config');p.add_argument('--machine-id');p.add_argument('--owner');a=p.parse_args()
    out=Path(a.output);start=time.time_ns();(out/'BEGIN.json').write_text(json.dumps({'at':start,'task':a.task}))
    time.sleep(.25);(out/'END.json').write_text(json.dumps({'at':time.time_ns()}))
    (out/'ATTEMPT1-CONTENT.txt').write_text('raise RuntimeError("candidate must never execute")')
    print('中文诊断')
    raise SystemExit(75 if a.task=='needs_repair' else 1 if a.task=='bad' else 0)
'''


class LocalModelBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project with spaces'
        self.root.mkdir()
        self.patch = patch.object(batch, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.ops = Path(self.temp.name) / 'operations'
        (self.ops / 'scripts').mkdir(parents=True)
        (self.ops / 'config').mkdir()
        (self.ops / 'AGENTS.md').write_text('rules', encoding='utf-8')
        (self.ops / 'config/executor.json').write_text(json.dumps({'base_url':'http://127.0.0.1:1/v1'}), encoding='utf-8')
        (self.ops / 'scripts/call.py').write_text(FAKE_CALL, encoding='utf-8')
        (self.ops / 'scripts/check_opencode.py').write_text('print("daily check")', encoding='utf-8')
        self.folder = self.root / 'runtime/local-model-operations/plans'
        self.folder.mkdir(parents=True)
        (self.folder / 'source.txt').write_text('actual source 中文', encoding='utf-8')
        (self.folder / 'task.txt').write_text('actual unfinished task', encoding='utf-8')

    def plan(self, ids=('one','two')):
        tasks=[]
        for name in ids:
            (self.folder / (name+'.json')).write_text(json.dumps({'stable_source_path':'source.txt','task_path':'task.txt','max_tokens':100}), encoding='utf-8')
            tasks.append({'task_id':name,'spec':name+'.json','output':'../outputs/'+name})
        path=self.folder/'plan.json';path.write_text(json.dumps({'tasks':tasks}), encoding='utf-8')
        return path,tasks

    def run_plan(self, path, jobs=2):
        return batch.run_batch(path,self.ops,'test-machine','test-owner',jobs)

    def no_dispatch(self):
        self.assertEqual([],list(self.root.rglob('BEGIN.json')))

    def test_real_child_intervals_overlap_and_candidates_are_not_executed(self):
        path,_=self.plan();code,receipt=self.run_plan(path)
        self.assertEqual(0,code)
        out=self.folder.parent/'outputs'
        spans=[(json.loads((out/n/'BEGIN.json').read_text())['at'],json.loads((out/n/'END.json').read_text())['at']) for n in ['one','two']]
        self.assertLess(max(a for a,b in spans),min(b for a,b in spans))
        for n in ['one','two']:
            frozen=json.loads((out/n/'FROZEN-SPEC.json').read_text(encoding='utf-8'))
            self.assertEqual('actual source 中文',frozen['messages'][1]['content'])
            self.assertIn('中文诊断',(out/n/'caller.log').read_text(encoding='utf-8'))
            self.assertFalse(json.loads((out/n/'RUNNER-RESULT.json').read_text())['adopted'])
        self.assertFalse(json.loads((receipt/'result.json').read_text())['adopted'])

    def test_whole_plan_missing_material_stops_before_any_dispatch(self):
        path,_=self.plan();(self.folder/'two.json').write_text(json.dumps({'source_files':['absent.py'],'task_path':'task.txt','max_tokens':100}))
        with self.assertRaises(ValueError):self.run_plan(path)
        self.no_dispatch()

    def test_duplicate_ids_specs_outputs_and_overlap_are_rejected(self):
        for field in ['task_id','spec','output']:
            with self.subTest(field=field):
                path,tasks=self.plan();tasks[1][field]=tasks[0][field];path.write_text(json.dumps({'tasks':tasks}))
                with self.assertRaises(ValueError):self.run_plan(path)
                self.no_dispatch()
        path,tasks=self.plan();tasks[1]['output']=tasks[0]['output']+'/child';path.write_text(json.dumps({'tasks':tasks}))
        with self.assertRaises(ValueError):self.run_plan(path)
        self.no_dispatch()

    def test_existing_or_escaping_output_is_rejected(self):
        path,tasks=self.plan();(self.folder.parent/'outputs/one').mkdir(parents=True)
        with self.assertRaises(ValueError):self.run_plan(path)
        tasks[0]['output']=str(Path(self.temp.name)/'outside');path.write_text(json.dumps({'tasks':tasks}))
        with self.assertRaises(ValueError):self.run_plan(path)
        self.no_dispatch()

    def test_binary_missing_task_and_invalid_budget_are_rejected(self):
        path,_=self.plan()
        for data in [{'stable_source_path':'source.png','task_path':'task.txt','max_tokens':100},{'stable_source_path':'source.txt','max_tokens':100},{'stable_source_path':'source.txt','task_path':'task.txt','max_tokens':True}]:
            (self.folder/'source.png').write_bytes(b'not text')
            (self.folder/'one.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):self.run_plan(path)
            self.no_dispatch()

    def test_daily_failure_preserves_diagnostic_and_no_dispatch(self):
        path,_=self.plan();(self.ops/'scripts/check_opencode.py').write_text('print("repair needed");raise SystemExit(75)')
        code,receipt=self.run_plan(path)
        self.assertEqual(75,code);self.no_dispatch()
        self.assertIn('repair needed',(receipt/'maintenance.log').read_text())

    def test_missing_daily_checker_fails_closed(self):
        path,_=self.plan();(self.ops/'scripts/check_opencode.py').unlink()
        with self.assertRaises(ValueError):self.run_plan(path)
        self.no_dispatch()

    def test_child_failures_are_preserved_and_75_stops_unstarted_tasks(self):
        path,_=self.plan(('needs_repair','later'));code,receipt=self.run_plan(path,jobs=1)
        self.assertEqual(75,code)
        self.assertEqual(1,len(list(self.root.rglob('BEGIN.json'))))
        records=json.loads((receipt/'result.json').read_text())['results']
        self.assertTrue(any(r.get('status')=='not_started_after_maintenance_failure' for r in records))

    def test_nonzero_model_process_is_not_treated_as_adoption(self):
        path,_=self.plan(('bad',));code,receipt=self.run_plan(path)
        self.assertEqual(1,code)
        record=json.loads((receipt/'result.json').read_text())['results'][0]
        self.assertEqual(1,record['exit_code']);self.assertFalse(record['adopted'])

    def test_daily_checker_receives_selected_config_and_diagnostic_path(self):
        path,_=self.plan(('one',))
        (self.ops/'scripts/check_opencode.py').write_text('import argparse,json\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument("--config",required=True);a=p.parse_args();print(json.loads(Path(a.config).read_text())["base_url"])',encoding='utf-8')
        with patch.dict(os.environ,{'LOCAL_MODEL_CONFIG':str(self.root/'wrong-config.json')}):
            code,receipt=self.run_plan(path)
        self.assertEqual(0,code)
        result=json.loads((receipt/'result.json').read_text())
        self.assertEqual(str(receipt/'maintenance.log'),result['maintenance_log'])
        self.assertIn('http://127.0.0.1:1/v1',Path(result['maintenance_log']).read_text())

    def test_invalid_top_level_and_external_symlink_are_rejected(self):
        path,_=self.plan();path.write_text('[]')
        with self.assertRaises(ValueError):self.run_plan(path)
        path,_=self.plan();outside=Path(self.temp.name)/'outside.txt';outside.write_text('outside source')
        link=self.folder/'outside-link.txt'
        try:link.symlink_to(outside)
        except OSError as error:self.skipTest('Symlink privilege unavailable: '+str(error))
        (self.folder/'one.json').write_text(json.dumps({'stable_source_path':link.name,'task_path':'task.txt','max_tokens':100}))
        with self.assertRaises(ValueError):self.run_plan(path)
        self.no_dispatch()


if __name__=='__main__':
    unittest.main()
