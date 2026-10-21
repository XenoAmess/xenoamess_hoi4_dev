import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools.common import read_json, write_json


class JsonReadSharingTests(unittest.TestCase):
    def test_transient_share_denial_recovers_same_complete_document(self):
        with patch.object(Path, 'read_text', side_effect=[PermissionError('locked'), '{"attempt": 8}']) as read, patch('tools.common.time.sleep') as sleep:
            self.assertEqual(read_json(Path('journal.json')), {'attempt': 8})
        self.assertEqual(read.call_count, 2)
        sleep.assert_called_once()

    def test_persistent_denial_is_bounded_and_surfaces(self):
        with patch.object(Path, 'read_text', side_effect=PermissionError('still locked')) as read, patch('tools.common.time.sleep') as sleep:
            with self.assertRaisesRegex(PermissionError, 'still locked'):
                read_json(Path('journal.json'))
        self.assertLessEqual(read.call_count, 6)
        self.assertEqual(sleep.call_count, read.call_count - 1)

    def test_invalid_document_is_not_retried_or_replaced(self):
        with patch.object(Path, 'read_text', return_value='{') as read, patch('tools.common.time.sleep') as sleep:
            with self.assertRaises(json.JSONDecodeError):
                read_json(Path('journal.json'))
        read.assert_called_once()
        sleep.assert_not_called()

    def test_missing_journal_is_not_treated_as_empty(self):
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError('missing')) as read, patch('tools.common.time.sleep') as sleep:
            with self.assertRaises(FileNotFoundError):
                read_json(Path('journal.json'))
        read.assert_called_once()
        sleep.assert_not_called()


class JsonWriteSharingTests(unittest.TestCase):
    def test_longer_transient_denial_keeps_old_document_until_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            path.write_text('{"old": true}', encoding='utf-8')
            old = path.read_bytes()
            original_replace = Path.replace
            attempts = []

            def replace(temporary, target):
                attempts.append(temporary)
                self.assertEqual(path.read_bytes(), old)
                if len(attempts) <= 6:
                    raise PermissionError('temporary Windows sharing denial')
                return original_replace(temporary, target)

            with patch.object(Path, 'replace', replace), patch('tools.common.time.sleep'):
                write_json(path, {'new': '钢奶龙心'})
            self.assertEqual(read_json(path), {'new': '钢奶龙心'})
            self.assertFalse(path.with_name('record.json.tmp').exists())
            self.assertEqual(len(attempts), 7)

    def test_persistent_denial_preserves_old_and_candidate_and_surfaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            path.write_text('{"old": true}', encoding='utf-8')
            old = path.read_bytes()
            with patch.object(Path, 'replace', side_effect=PermissionError('still locked')) as replace, patch('tools.common.time.sleep') as sleep:
                with self.assertRaises(PermissionError):
                    write_json(path, {'new': True})
            self.assertEqual(path.read_bytes(), old)
            self.assertEqual(read_json(path.with_name('record.json.tmp')), {'new': True})
            self.assertLessEqual(replace.call_count, 9)
            self.assertEqual(sleep.call_count, replace.call_count - 1)

    def test_other_filesystem_failure_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            path.write_text('{"old": true}', encoding='utf-8')
            old = path.read_bytes()
            with patch.object(Path, 'replace', side_effect=OSError('filesystem failure')) as replace, patch('tools.common.time.sleep') as sleep:
                with self.assertRaisesRegex(OSError, 'filesystem failure'):
                    write_json(path, {'new': True})
            replace.assert_called_once()
            sleep.assert_not_called()
            self.assertEqual(path.read_bytes(), old)


if __name__ == '__main__':
    unittest.main()
