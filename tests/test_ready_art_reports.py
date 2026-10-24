import tempfile
import unittest
from pathlib import Path
from tools.common import write_json,machine_id
from mod_nailong.tools.ready_art_reports import enqueue,reports,report_path

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

if __name__=='__main__':unittest.main()
