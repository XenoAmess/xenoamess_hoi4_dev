import copy
import json
import unittest
from pathlib import Path

from tools import legacy_low_request as legacy
from tools import retry_actual_proof as proof
from tools.common import read_json

ROOT = Path(__file__).resolve().parents[1]


class AuditedLowRequestTests(unittest.TestCase):
    def cases(self):
        contracts = read_json(legacy.CONTRACT_FILE)['contracts']
        for key, contract in contracts.items():
            archive = read_json(ROOT / f'mod_nailong/data/legacy-request-recoveries/{key}-{contract["failed_attempt"]:03}.json')
            events = {name: json.loads(record['raw_utf8']) for name, record in archive['events'].items()}
            attempts = read_json(ROOT / f'mod_nailong/data/generation-requests/{key}.json')['attempts']
            attempt = next(a for a in attempts if a['number'] == contract['failed_attempt'])
            yield key, archive, events, attempt

    def test_all_four_retained_requests_and_actual_refusals_validate_without_calls(self):
        cases = list(self.cases())
        self.assertEqual(len(cases), 4)
        receipt_types = set()
        for key, archive, events, attempt in cases:
            with self.subTest(key=key):
                before = copy.deepcopy(archive)
                job = legacy.validate_cached_job(key, archive, events)
                legacy.validate_refusal(key, attempt, events)
                self.assertEqual(job['prompt'], attempt['prompt'])
                self.assertTrue(job['transparent'])
                self.assertFalse(archive['actual_recorded_before_call'])
                self.assertEqual(archive, before)
                receipt_types.add(events['refusal_receipt']['payload']['type'])
        self.assertEqual(receipt_types, {'item_completed', 'custom_tool_call_output'})

    def test_rehashed_changes_cannot_replace_pinned_historical_event_bytes(self):
        key, archive, events, _ = next(self.cases())
        for name in archive['events']:
            with self.subTest(name=name):
                changed = copy.deepcopy(archive)
                event = copy.deepcopy(events[name])
                event['timestamp'] = '2026-10-17T00:00:00Z'
                raw = json.dumps(event) + '\n'
                changed['events'][name].update(raw_utf8=raw, raw_line_sha256=legacy.digest(raw))
                current = dict(events, **{name: event})
                with self.assertRaises(AssertionError):
                    legacy.validate_cached_job(key, changed, current)

    def test_unknown_or_missing_intervening_cache_access_is_held(self):
        key, archive, events, _ = next(self.cases())
        for edit in ('remove', 'insert', 'reorder'):
            with self.subTest(edit=edit):
                changed = copy.deepcopy(archive)
                accesses = changed['cache_accesses']
                if edit == 'remove':
                    accesses.pop(1)
                elif edit == 'insert':
                    accesses.insert(1, copy.deepcopy(accesses[0]))
                else:
                    accesses[0], accesses[1] = accesses[1], accesses[0]
                with self.assertRaises(AssertionError):
                    legacy.validate_cached_job(key, changed, events)

    def test_interval_or_cache_or_attempt_cannot_be_rebound(self):
        key, archive, events, _ = next(self.cases())
        for field, value in [('cache_name', 'unknown'), ('failed_attempt', 99), ('machine_id', 'another machine')]:
            with self.subTest(field=field):
                changed = copy.deepcopy(archive)
                changed[field] = value
                with self.assertRaises(AssertionError):
                    legacy.validate_cached_job(key, changed, events)
        changed = copy.deepcopy(archive)
        changed['cache_interval_proof']['interval_sha256'] = '0' * 64
        with self.assertRaises(AssertionError):
            legacy.validate_cached_job(key, changed, events)
        with self.assertRaises(AssertionError):
            legacy.validate_cached_job('0' * 64, archive, events)

    def test_custom_error_receipt_must_match_the_actual_dispatch_call_id(self):
        for key, _, events, attempt in self.cases():
            if events['refusal_receipt']['payload']['type'] == 'custom_tool_call_output':
                changed = copy.deepcopy(events)
                changed['refusal_receipt']['payload']['call_id'] = 'another call'
                with self.assertRaises(AssertionError):
                    legacy.validate_refusal(key, attempt, changed)

    def test_each_refusal_matches_its_frozen_journal_request_id_and_time(self):
        for key, _, events, attempt in self.cases():
            changed = dict(attempt, error='moderation_blocked request ID 00000000-0000-0000-0000-000000000000')
            with self.assertRaises(AssertionError):
                legacy.validate_refusal(key, changed, events)
            changed = dict(attempt, observed_at_utc='2026-10-15T00:00:00+00:00')
            with self.assertRaises(AssertionError):
                legacy.validate_refusal(key, changed, events)

    def test_v2_integration_rejects_false_pre_call_recording_and_changed_prompt(self):
        key, archive, _, attempt = next(self.cases())
        changed = dict(archive, actual_recorded_before_call=True)
        with self.assertRaises(AssertionError):
            proof.validate_legacy_archive(ROOT, key, attempt, changed)
        changed = dict(attempt, prompt='replacement intended text')
        with self.assertRaises(AssertionError):
            proof.validate_legacy_archive(ROOT, key, changed, archive)


if __name__ == '__main__':
    unittest.main()
