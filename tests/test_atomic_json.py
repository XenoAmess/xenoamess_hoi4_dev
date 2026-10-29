"""Readers must never see partial JSON when Windows briefly denies replace."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.common import read_json,write_json,_replace_json

class AtomicJsonTests(unittest.TestCase):
    def test_transient_replace_denial_keeps_old_json_until_success(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'record.json';write_json(path,{'old':True})
            replace=_replace_json;attempts=[]
            def intermittent(source,target):
                attempts.append(source)
                if len(attempts)<3:
                    self.assertEqual(read_json(path),{'old':True})
                    raise PermissionError('simulated open Windows reader')
                return replace(source,target)
            with patch('tools.common._replace_json',intermittent),patch('tools.common.time.sleep'):
                write_json(path,{'new':True})
            self.assertEqual(read_json(path),{'new':True})
            self.assertFalse(path.with_name(path.name+'.tmp').exists())

    def test_persistent_denial_raises_without_destroying_previous_record(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'record.json';write_json(path,{'old':True})
            with patch('tools.common._replace_json',side_effect=PermissionError('persistent denial')),patch('tools.common.time.sleep'):
                with self.assertRaises(PermissionError):write_json(path,{'new':True})
            self.assertEqual(read_json(path),{'old':True})
