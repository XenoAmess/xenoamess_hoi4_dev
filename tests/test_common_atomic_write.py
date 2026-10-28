import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import common


def windows_error(code):
    error = OSError(f'Windows error {code}')
    error.winerror = code
    return error


class AtomicJsonWriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'state.json'
        self.path.write_text('{"old": true}\n', encoding='utf-8')
        self.original = self.path.read_bytes()
        self.candidate = self.path.with_name('state.json.tmp')

    def test_1175_retries_same_complete_candidate_then_publishes(self):
        replacement = common._replace_json
        seen = []

        def first_busy_then_publish(temporary, target):
            self.assertEqual(target.read_bytes(), self.original)
            seen.append(temporary.read_bytes())
            if len(seen) == 1:
                raise windows_error(1175)
            replacement(temporary, target)

        with patch.object(common, '_replace_json', side_effect=first_busy_then_publish) as call, patch.object(common.time, 'sleep') as sleep:
            common.write_json(self.path, {'new': '奶龙'})
        self.assertEqual(call.call_count, 2)
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), {'new': '奶龙'})
        sleep.assert_called_once_with(0.02)
        self.assertFalse(self.candidate.exists())

    def test_1175_exhaustion_preserves_old_file_and_complete_candidate(self):
        error = windows_error(1175)
        with patch.object(common, '_replace_json', side_effect=error) as call, patch.object(common.time, 'sleep') as sleep:
            with self.assertRaises(OSError) as raised:
                common.write_json(self.path, {'new': 1})
        self.assertIs(raised.exception, error)
        self.assertEqual(call.call_count, 11)
        self.assertEqual(sleep.call_count, 10)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(json.loads(self.candidate.read_text(encoding='utf-8')), {'new': 1})

    def test_other_replace_states_fail_immediately(self):
        for code in [1176, 1177]:
            with self.subTest(code=code):
                error = windows_error(code)
                with patch.object(common, '_replace_json', side_effect=error) as call, patch.object(common.time, 'sleep') as sleep:
                    with self.assertRaises(OSError) as raised:
                        common.write_json(self.path, {'new': code})
                self.assertIs(raised.exception, error)
                self.assertEqual(call.call_count, 1)
                sleep.assert_not_called()
                self.assertEqual(self.path.read_bytes(), self.original)

    def test_unrelated_io_error_does_not_retry(self):
        with patch.object(common, '_replace_json', side_effect=OSError(errno.EIO, 'I/O failure')) as call, patch.object(common.time, 'sleep') as sleep:
            with self.assertRaises(OSError):
                common.write_json(self.path, {'new': 1})
        self.assertEqual(call.call_count, 1)
        sleep.assert_not_called()

    def test_permission_error_still_retries(self):
        replacement = common._replace_json
        attempts = 0

        def first_busy_then_publish(temporary, target):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError('reader open')
            replacement(temporary, target)

        with patch.object(common, '_replace_json', side_effect=first_busy_then_publish) as call, patch.object(common.time, 'sleep') as sleep:
            common.write_json(self.path, {'new': 1})
        self.assertEqual(call.call_count, 2)
        sleep.assert_called_once_with(0.02)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), {'new': 1})
        self.assertFalse(self.candidate.exists())


if __name__ == '__main__':
    unittest.main()
