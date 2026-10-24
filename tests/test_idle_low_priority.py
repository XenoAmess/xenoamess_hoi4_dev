import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tools.common import read_json, write_json, file_sha256
from tools.production_priority_gate import low_enabled, append_prepared_windows, service_retry_allowed, POLICY
from tools.rolling_production_queue import prioritize_high
from mod_nailong.tools.production_priority import gate_lower_priority


class IdleLowPriorityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.policy = self.root / 'mod_nailong/data/production-scheduling-policy.json'
        self.priority = {'h': {'high_priority': True}, 'l': {'high_priority': False}, 'm': {'high_priority': False}}
        write_json(self.root / 'mod_nailong/data/production-priority.json', {'sources': self.priority})

    def enable(self):
        write_json(self.policy, {'id': POLICY, 'allow_low_when_no_immediate_high': True, 'user_authorization_quote': 'fixture authorization'})

    def test_no_implicit_or_unknown_policy_unlock(self):
        self.assertFalse(low_enabled(self.root))
        write_json(self.policy, {'id': 'unknown', 'user_authorization_quote': 'fixture'})
        with self.assertRaises(AssertionError): low_enabled(self.root)

    def test_high_refusal_skip_preserves_low_retries_and_priority_inventory(self):
        self.enable()
        self.assertTrue(service_retry_allowed(self.root, self.priority['h']))
        body = read_json(self.policy)
        body['skip_service_refused_high_retries'] = True
        write_json(self.policy, body)
        self.assertFalse(service_retry_allowed(self.root, self.priority['h']))
        self.assertTrue(service_retry_allowed(self.root, self.priority['l']))
        self.assertEqual(read_json(self.root / 'mod_nailong/data/production-priority.json')['sources'], self.priority)
        self.assertTrue(low_enabled(self.root))

    def test_catalog_keeps_incomplete_high_and_requires_idle_authorization(self):
        low = [{'source_sha256': 'l'}]
        self.assertEqual(gate_lower_priority(low, self.priority, {})[0], [])
        self.assertEqual(gate_lower_priority(low, self.priority, {}, idle_low_authorized=True)[0], low)
        self.assertEqual(gate_lower_priority(low, self.priority, {}, idle_low_authorized=True, immediate_high=True)[0], [])
        self.assertEqual(gate_lower_priority(low, self.priority, {}, idle_low_authorized=True)[1], {'h'})

    def test_low_windows_each_contain_one_exact_unchanged_job(self):
        self.enable(); jobs = [{'key': k, 'prompt': 'exact ' + k} for k in ('l', 'h', 'm')]
        plan = {'batches': []}; output = self.root / 'runtime/production-test-jobs.json'
        append_prepared_windows(self.root, plan, 'test', jobs, output)
        self.assertEqual(read_json(output), jobs)
        self.assertEqual([read_json(self.root / i['jobs']) for i in plan['batches']], [[jobs[1]], [jobs[0]], [jobs[2]]])

    def test_high_reorders_only_uncalled_suffix_preserving_frozen_jobs(self):
        self.enable(); plan = {'batches': []}
        for key in ('l', 'm', 'h'):
            path = self.root / ('runtime/' + key + '.json'); write_json(path, [{'key': key, 'prompt': 'frozen ' + key}])
            plan['batches'].append({'batch': key, 'jobs': path.relative_to(self.root).as_posix()})
        plan_path = self.root / 'runtime/after128-continuous-plan.json'; write_json(plan_path, plan)
        before = {i['jobs']: file_sha256(self.root / i['jobs']) for i in plan['batches']}
        prioritize_high(self.root, {'next_index': 1, 'run_id': 'fixture', 'machine_id': 'fixture'})
        self.assertEqual([i['batch'] for i in read_json(plan_path)['batches']], ['l', 'h', 'm'])
        self.assertEqual(before, {p: file_sha256(self.root / p) for p in before})

    def test_newly_due_high_is_selected_before_already_prepared_low(self):
        self.enable(); low = self.root / 'runtime/low.json'; write_json(low, [{'key': 'l'}])
        high = self.root / 'runtime/high.json'; write_json(high, [{'key': 'h'}])
        path = self.root / 'runtime/after128-continuous-plan.json'
        write_json(path, {'batches': [{'batch': 'low', 'jobs': 'runtime/low.json'}]})
        def allocate(root, state, runner, high_only):
            self.assertTrue(high_only)
            body = read_json(path); body['batches'].append({'batch': 'cooldown', 'jobs': 'runtime/high.json'}); write_json(path, body)
        with patch('tools.rolling_production_queue.ready_art', return_value=[]), patch('tools.rolling_production_queue.allocate_exact_retry', side_effect=allocate):
            prioritize_high(self.root, {'next_index': 0, 'run_id': 'fixture', 'machine_id': 'fixture'})
        self.assertEqual([i['batch'] for i in read_json(path)['batches']], ['cooldown', 'low'])

    def test_no_due_high_preserves_next_low_without_new_attempt(self):
        self.enable(); path = self.root / 'runtime/after128-continuous-plan.json'
        write_json(self.root / 'runtime/low.json', [{'key': 'l'}])
        body = {'batches': [{'batch': 'low', 'jobs': 'runtime/low.json'}]}; write_json(path, body)
        with patch('tools.rolling_production_queue.ready_art', return_value=[]), patch('tools.rolling_production_queue.allocate_exact_retry', return_value=None):
            prioritize_high(self.root, {'next_index': 0, 'run_id': 'fixture', 'machine_id': 'fixture'})
        self.assertEqual(read_json(path), body)
        self.assertFalse((self.root / 'mod_nailong/data/generation-requests').exists())


if __name__ == '__main__': unittest.main()
