import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.common import read_json


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


if __name__ == '__main__':
    unittest.main()
