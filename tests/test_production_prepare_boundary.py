import tempfile
import io
from contextlib import redirect_stdout
import unittest
from pathlib import Path
from types import SimpleNamespace
from tools.common import file_sha256, read_json, write_json
from tools.production_prepare_boundary import consume, run_boundary


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

    def test_original_replacement_intent_is_bound_to_its_distinct_preparer(self):
        script=self.root/'tools/prepare_reviewed_original_replacements.py';script.write_text('different trusted preparer fixture',encoding='utf-8')
        self.intent.update(kind='reviewed_original_replacements',preparer_sha256=file_sha256(script));self.queue()
        self.assertTrue(consume(self.root,'test',self.good_runner)['prepared'])

    def test_combined_boundary_applies_reviews_before_preparation(self):
        self.queue()
        order = []
        def apply():
            order.append('reviews')
            return {'applied': 1}
        def prepare(intent):
            self.assertEqual(order, ['reviews'])
            order.append('preparation')
            return self.good_runner(intent)
        result = run_boundary(self.root, 'test', apply_reviews=apply, runner=prepare)
        self.assertEqual(order, ['reviews', 'preparation'])
        self.assertTrue(result['prepared'])
        self.assertEqual(result['review_application'], {'applied': 1})

    def test_combined_boundary_never_applies_reviews_during_call(self):
        self.queue()
        write_json(self.root / 'runtime/production-queue/dispatch/current.json', {'status': 'calling'})
        result = run_boundary(self.root, 'test', apply_reviews=lambda: self.fail('active call'),
                              runner=lambda _: self.fail('active call'))
        self.assertFalse(result['reviews_applied'])
        self.assertTrue(self.pending.exists())

    def test_background_refill_follows_review_application_at_same_safe_boundary(self):
        order = []
        def apply():order.append('review');return {'applied':1}
        def refill(root, machine):
            self.assertEqual(order,['review']);order.append('future preparation')
            return {'prepared':True,'index':8}
        result=run_boundary(self.root,'test',apply_reviews=apply,refill=refill)
        self.assertEqual(order,['review','future preparation'])
        self.assertEqual(result['backlog_refill']['index'],8)

    def test_failed_review_application_does_not_claim_preparation(self):
        self.queue()
        def fail():
            raise ValueError('keep staged review for reconciliation')
        with self.assertRaisesRegex(ValueError, 'keep staged review'):
            run_boundary(self.root, 'test', apply_reviews=fail, runner=self.good_runner)
        self.assertTrue(self.pending.exists())

    def test_actual_review_console_messages_are_kept_inside_json_result(self):
        def apply():
            print('Rejected 1 actual image')
            print('Approved 2 actual images')
            return {'applied': 3}
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = run_boundary(self.root, 'test', apply_reviews=apply)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(result['review_application_stdout'],
                         'Rejected 1 actual image\nApproved 2 actual images\n')
        self.assertEqual(result['review_application'], {'applied': 3})

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
