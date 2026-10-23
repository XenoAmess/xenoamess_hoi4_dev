import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from tools.common import file_sha256, read_json, write_json
from tools.production_prepare_boundary import consume


class PreparationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        script = self.root / 'tools/prepare_reviewed_art_repairs.py'
        script.parent.mkdir(parents=True)
        script.write_text('fixture only', encoding='utf-8')
        proof = self.root / 'review.json'
        write_json(proof, {'immutable': True})
        self.intent = {'machine_id': 'test', 'kind': 'reviewed_art_repairs',
                       'preparer_sha256': file_sha256(script), 'arguments': ['fixture'],
                       'evidence': [{'path': 'review.json', 'sha256': file_sha256(proof)}],
                       'expected_jobs_file': 'runtime/jobs.json', 'expected_source_keys': ['a']}
        self.pending = self.root / 'runtime/production-queue/preparation/pending/one.json'

    def queue(self):
        write_json(self.pending, self.intent)

    def good_runner(self, intent):
        write_json(self.root / intent['expected_jobs_file'], [{'key': 'a'}])
        return SimpleNamespace(returncode=0, stdout='prepared', stderr='')

    def test_empty_queue_does_no_work(self):
        self.assertFalse(consume(self.root, 'test')['prepared'])

    def test_active_actual_call_blocks_preparation_without_claim(self):
        self.queue()
        write_json(self.root / 'runtime/production-queue/dispatch/current.json', {'status': 'calling'})
        self.assertEqual(consume(self.root, 'test', self.good_runner)['reason'], 'actual_call_in_progress')
        self.assertTrue(self.pending.exists())

    def test_success_is_bound_to_script_evidence_and_ordered_keys_and_never_replayed(self):
        self.queue()
        self.assertTrue(consume(self.root, 'test', self.good_runner)['prepared'])
        self.assertFalse(self.pending.exists())
        self.assertFalse(consume(self.root, 'test', lambda _: self.fail('replayed'))['prepared'])

    def test_changed_evidence_is_quarantined_without_running_preparer(self):
        self.queue()
        write_json(self.root / 'review.json', {'changed': True})
        r = consume(self.root, 'test', lambda _: self.fail('must not run'))
        self.assertEqual(r['status'], 'preparation_requires_reconciliation')
        self.assertFalse(self.pending.exists())

    def test_partial_failed_preparer_is_preserved_without_automatic_repeat(self):
        self.queue()
        r = consume(self.root, 'test', lambda _: SimpleNamespace(returncode=1, stdout='', stderr='partial failure'))
        self.assertEqual(r['status'], 'preparation_requires_reconciliation')
        self.assertEqual(read_json(self.root / r['receipt'])['stderr'], 'partial failure')
        self.assertFalse(consume(self.root, 'test', lambda _: self.fail('replayed'))['prepared'])


if __name__ == '__main__':
    unittest.main()
