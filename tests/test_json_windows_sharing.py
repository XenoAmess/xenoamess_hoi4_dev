"""Exercise real Windows sharing during inventory replacement, without images."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from tools.common import _open_json_reader, read_json, write_json


class JsonSharingTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Real Windows sharing semantics')
    def test_open_reader_allows_replace_and_keeps_old_complete_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'inventory.json'
            old={'prompt':'完整奶龙原词','number':1};new={'prompt':'下一张原词','number':2}
            write_json(path,old)
            with _open_json_reader(path) as reader:
                write_json(path,new)
                self.assertEqual(json.loads(reader.read().decode('utf-8')),old)
                self.assertEqual(read_json(path),new)
            write_json(path,{'number':3})
            self.assertEqual(read_json(path),{'number':3})

    @unittest.skipUnless(os.name == 'nt', 'Real Windows sharing semantics')
    def test_ordinary_reader_reproduces_sharing_denial(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'inventory.json';candidate=Path(temp)/'candidate.json'
            write_json(path,{'number':1});write_json(candidate,{'number':2})
            with path.open('rb') as reader:
                with self.assertRaises(PermissionError):candidate.replace(path)
                self.assertEqual(json.loads(reader.read()),{'number':1})
            candidate.replace(path)
            self.assertEqual(read_json(path),{'number':2})

    def test_bad_or_missing_json_is_not_replaced_with_cached_data(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'inventory.json';write_json(path,{'number':1})
            self.assertEqual(read_json(path),{'number':1})
            path.write_text('{incomplete',encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError):read_json(path)
            path.unlink()
            with self.assertRaises(FileNotFoundError):read_json(path)


if __name__=='__main__':unittest.main()
