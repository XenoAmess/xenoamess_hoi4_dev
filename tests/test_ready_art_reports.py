import tempfile
import unittest
from pathlib import Path
from tools.common import write_json,machine_id
from mod_nailong.tools.ready_art_reports import enqueue,reports,report_path,independent_art_holds

class ReadyReportBindingTests(unittest.TestCase):
    def fixture(self,root):
        path=root/'mod_nailong/data/review.json'
        write_json(path,{'machine_id':machine_id(),'decisions_staged':True,'decisions':[]})
        return path

    def test_report_changed_after_enqueue_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.fixture(root)
            enqueue('batch','review.json',root)
            self.assertEqual(len(reports('batch',root)),1)
            path.write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'bytes changed'):reports('batch',root)

    def test_other_machine_or_unfinished_review_cannot_enter(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=self.fixture(root)
            for value in [{'machine_id':'another-machine','decisions_staged':True},{'machine_id':machine_id(),'decisions_staged':False}]:
                write_json(path,value)
                with self.assertRaises(ValueError):enqueue('batch','review.json',root)

    def test_parent_and_absolute_report_paths_are_rejected(self):
        for name in ['../review.json','..\\review.json','C:\\review.json','/review.json']:
            with self.assertRaises(ValueError):report_path(name)

    def test_independent_method_hold_is_isolated_from_other_sources_and_resolved_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'mod_nailong/data/independent-art-tasks'
            write_json(base/'held.json',{'schema':'naiwa-independent-art-hold-v1','machine_id':machine_id(),'status':'pending_independent_method','source_sha256':'a'*64})
            write_json(base/'resolved.json',{'schema':'naiwa-independent-art-hold-v1','machine_id':machine_id(),'status':'resolved','source_sha256':'b'*64})
            write_json(base/'other-evidence.json',{'purpose':'independent observations only'})
            self.assertEqual(independent_art_holds(root),{'a'*64})

    def test_independent_art_hold_from_another_machine_is_not_silently_applied(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write_json(root/'mod_nailong/data/independent-art-tasks/held.json',{'schema':'naiwa-independent-art-hold-v1','machine_id':'another-machine','status':'pending_independent_method','source_sha256':'a'*64})
            with self.assertRaises(AssertionError):independent_art_holds(root)

if __name__=='__main__':unittest.main()
