import tempfile
import unittest
from pathlib import Path
from tools.common import write_json
from tools.production_window_gate import inspect_window


class WindowGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'mod_nailong/data/production-window-timings'
        self.folder.mkdir(parents=True)
        self.row = {'machine_id': 'test-machine', 'window_id': 'test', 'status': 'completed',
                    'batches': [{'batch': 'one'}],
                    'events': [{'phase': 'batch_imports_completed', 'batch': 'one'}]}

    def save(self):
        write_json(self.folder / 'test-completed.json', self.row)

    def test_missing_receipt_waits_then_actual_file_creation_releases_gate(self):
        self.assertFalse(inspect_window(self.root, 'test', 'test-machine')['ready'])
        self.save()
        self.assertTrue(inspect_window(self.root, 'test', 'test-machine')['ready'])

    def test_completed_receipt_does_not_override_an_actual_call_in_progress(self):
        self.save()
        dispatch = self.root / 'runtime/production-queue/dispatch'
        dispatch.mkdir(parents=True)
        write_json(dispatch / 'current.json', {'status': 'calling'})
        self.assertFalse(inspect_window(self.root, 'test', 'test-machine')['ready'])
        write_json(dispatch / 'current.json', {'status': 'returned_image'})
        self.assertTrue(inspect_window(self.root, 'test', 'test-machine')['ready'])

    def test_mismatched_machine_and_missing_imports_require_reconciliation(self):
        self.save()
        with self.assertRaises(ValueError):
            inspect_window(self.root, 'test', 'other-machine')
        self.row['events'] = []
        self.save()
        with self.assertRaises(ValueError):
            inspect_window(self.root, 'test', 'test-machine')

    def test_stopped_window_and_path_escape_cannot_continue(self):
        self.save()
        write_json(self.folder / 'test-stopped.json', {'status': 'stopped_requires_reconciliation'})
        with self.assertRaises(ValueError):
            inspect_window(self.root, 'test', 'test-machine')
        with self.assertRaises(ValueError):
            inspect_window(self.root, '../test', 'test-machine')


if __name__ == '__main__':
    unittest.main()
