import copy
import tempfile
import unittest
from pathlib import Path

from tools.adopt_high_delivery import (adopt_portraits, adopt_queue, assert_history_retained,
                                      assert_journal_retained, assert_unchanged, safe_path)
from unittest.mock import patch
import json
from PIL import Image
from tools.common import file_sha256
from mod_nailong.tools.master_files import sync_git


class AdoptHighDeliveryTests(unittest.TestCase):
    def test_only_target_rows_are_adopted_and_operation_is_idempotent(self):
        old = {'portraits': {'high': {'review': 'old'}, 'low': {'review': 'new-local'}}}
        new = {'portraits': {'high': {'review': 'approved', 'source_sha256': 'high'}, 'low': {'review': 'stale'}}}
        with patch('tools.adopt_high_delivery.portrait_ready', return_value=True), patch('tools.adopt_high_delivery.assert_history_retained'):
            adopted = adopt_portraits(old, new, {'high'})
            self.assertEqual(adopted['portraits']['low'], old['portraits']['low'])
            self.assertEqual(adopt_portraits(adopted, new, {'high'}), adopted)
            self.assertEqual(old['portraits']['high'], {'review': 'old'})

    def test_unapproved_incoming_row_is_rejected(self):
        with patch('tools.adopt_high_delivery.portrait_ready', return_value=False):
            with self.assertRaises(ValueError):
                adopt_portraits({'portraits': {}}, {'portraits': {'h': {'source_sha256': 'h'}}}, {'h'})

    def test_missing_old_output_and_prompt_history_is_rejected(self):
        old = {'generated_fullsize_sha256': 'old', 'image_sha256': 'preview', 'prompt': 'actual'}
        with self.assertRaises(ValueError):
            assert_history_retained(old, {'revision_history': []})
        entry = {'previous_fullsize_sha256': 'old', 'previous_image_sha256': 'preview', 'previous_prompt': 'actual'}
        assert_history_retained(old, {'revision_history': [entry]})
        entry['previous_prompt'] = 'changed'
        with self.assertRaises(ValueError):
            assert_history_retained(old, {'revision_history': [entry]})

    def test_prior_revisions_cannot_be_dropped(self):
        old = {'revision_history': [{'previous_fullsize_sha256': 'historic'}]}
        with self.assertRaises(ValueError):
            assert_history_retained(old, {'revision_history': []})

    def test_canonical_path_addition_preserves_existing_revision(self):
        old = {'generated_fullsize_sha256': 'current', 'image_sha256': 'preview', 'prompt': 'actual',
               'revision_history': [{'previous_fullsize_sha256': 'historic'}]}
        history = [{'previous_fullsize_sha256': 'historic',
                    'previous_fullsize_image': 'mod_nailong/assets/generated_fullsize/historic.png'},
                   {'previous_fullsize_sha256': 'current', 'previous_image_sha256': 'preview', 'previous_prompt': 'actual'}]
        assert_history_retained(old, {'revision_history': history})
        history[0]['previous_fullsize_image'] = 'other.png'
        with self.assertRaises(ValueError):
            assert_history_retained(old, {'revision_history': history})

    def test_retry_history_and_local_policy_are_preserved(self):
        old = {'policy': {'cooldown': 'local'}, 'sources': {'h': {'retries_used': 8, 'max_retries': 9, 'last_error': 'retained'}, 'l': {'retries_used': 7}}}
        new = {'sources': {'h': {'retries_used': 8, 'max_retries': 8, 'state': 'approved_external_native_rgba'}}}
        result = adopt_queue(old, new, {'h'})
        self.assertEqual(result['policy'], old['policy'])
        self.assertEqual(result['sources']['l'], old['sources']['l'])
        self.assertEqual(result['sources']['h']['max_retries'], 9)
        self.assertEqual(result['sources']['h']['last_error'], 'retained')
        self.assertEqual(adopt_queue(result, new, {'h'}), result)
        new['sources']['h']['retries_used'] = 0
        with self.assertRaises(ValueError):
            adopt_queue(old, new, {'h'})

    def test_journal_prefix_must_preserve_every_attempt(self):
        old = {'attempts': [{'number': 1, 'status': 'blocked'}]}
        new = {'attempts': old['attempts'] + [{'number': 2, 'status': 'approved'}]}
        assert_journal_retained(old, new)
        changed = copy.deepcopy(new)
        changed['attempts'][0]['status'] = 'approved'
        with self.assertRaises(ValueError):
            assert_journal_retained(old, changed)
        with self.assertRaises(ValueError):
            assert_journal_retained(old, old)

    def test_concurrent_writes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assert_unchanged(root, {'absent': None})
            (root / 'absent').write_text('new writer')
            with self.assertRaises(ValueError):
                assert_unchanged(root, {'absent': None})
            with self.assertRaises(ValueError):
                safe_path(root, '../outside')

    def test_index_refresh_does_not_normalize_other_records_or_journals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / 'raw.png'
            Image.new('RGBA', (4, 4), (200, 100, 20, 255)).save(raw)
            sha = file_sha256(raw)
            folder = root / 'mod_nailong/data/generation-requests'
            folder.mkdir(parents=True)
            generated = folder.parent / 'generated.json'
            journal = folder / 'low.json'
            generated.write_bytes(json.dumps({'portraits': {'low': {'generated_fullsize_sha256': sha}}}).encode())
            journal.write_bytes(json.dumps({'attempts': [{'fullsize_sha256': sha}]}).encode())
            old_generated, old_journal = generated.read_bytes(), journal.read_bytes()
            snapshot = {'current_masters_missing': [], 'historical_fullsize_sha_missing': [],
                        'masters': [{'path': str(raw), 'sha256': sha, 'bytes': raw.stat().st_size,
                                     'size': [4, 4], 'mode': 'RGBA', 'provenance': []}]}
            index = sync_git(snapshot, root, normalize_paths=False)
            self.assertEqual(index['count'], 1)
            self.assertEqual(generated.read_bytes(), old_generated)
            self.assertEqual(journal.read_bytes(), old_journal)


if __name__ == '__main__':
    unittest.main()
