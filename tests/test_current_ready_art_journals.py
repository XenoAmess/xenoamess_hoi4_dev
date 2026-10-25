import unittest
from pathlib import Path
from unittest.mock import patch

from mod_nailong.tools.prepare_ready_art_reviews import eligible_entries, latest_current_rejections


class CurrentArtJournalTests(unittest.TestCase):
    def test_obsolete_and_approved_findings_do_not_open_journals(self):
        rows = {
            'approved': {'review': 'approved', 'generated_fullsize_sha256': 'a', 'request_journal': 'approved.json'},
            'stale': {'review': 'rejected', 'generated_fullsize_sha256': 'new', 'request_journal': 'stale.json'},
            'current': {'review': 'rejected', 'generated_fullsize_sha256': 'c', 'request_journal': 'current.json'},
        }
        reports = [(Path('old.json'), {'decisions': [
            {'source_sha256': 'approved', 'decision': 'rejected', 'generated_fullsize_sha256': 'a'},
            {'source_sha256': 'stale', 'decision': 'rejected', 'generated_fullsize_sha256': 'old'},
            {'source_sha256': 'current', 'decision': 'rejected', 'generated_fullsize_sha256': 'c'},
        ]}), (Path('new.json'), {'reviewed_at_utc': 'later', 'decisions': [
            {'source_sha256': 'current', 'decision': 'rejected', 'generated_fullsize_sha256': 'c'},
            {'source_sha256': 'absent', 'decision': 'rejected', 'generated_fullsize_sha256': 'x'},
        ]})]
        attempt = {'number': 3, 'status': 'generated_rejected_visual_review'}
        with patch('mod_nailong.tools.prepare_ready_art_reviews.read_json', return_value={'attempts': [attempt]}) as reader:
            latest = latest_current_rejections(Path('/repo'), reports, rows)
        reader.assert_called_once_with(Path('/repo/current.json'))
        self.assertEqual(latest, {'current': attempt})
        expected = eligible_entries(reports, rows, {key: attempt for key in rows})
        self.assertEqual(eligible_entries(reports, rows, latest), expected)
        self.assertEqual(expected[0][0], Path('new.json'))

    def test_each_boundary_reads_the_fresh_latest_attempt(self):
        reports = [(Path('review.json'), {'decisions': [{'source_sha256': 'a', 'decision': 'rejected', 'generated_fullsize_sha256': 'raw'}]})]
        rows = {'a': {'review': 'pending', 'generated_fullsize_sha256': 'raw', 'request_journal': 'a.json'}}
        before = {'number': 1, 'status': 'generated_pending_visual_review'}
        after = {'number': 2, 'status': 'prepared'}
        with patch('mod_nailong.tools.prepare_ready_art_reviews.read_json', side_effect=[{'attempts': [before]}, {'attempts': [before, after]}]) as reader:
            first = latest_current_rejections(Path('/repo'), reports, rows)
            second = latest_current_rejections(Path('/repo'), reports, rows)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(len(eligible_entries(reports, rows, first)), 1)
        self.assertEqual(eligible_entries(reports, rows, second), [])

    def test_missing_current_journal_still_blocks_selection(self):
        reports = [(Path('review.json'), {'decisions': [{'source_sha256': 'a', 'decision': 'rejected', 'generated_fullsize_sha256': 'raw'}]})]
        rows = {'a': {'review': 'rejected', 'generated_fullsize_sha256': 'raw', 'request_journal': 'a.json'}}
        with patch('mod_nailong.tools.prepare_ready_art_reviews.read_json', side_effect=FileNotFoundError('missing current evidence')):
            with self.assertRaises(FileNotFoundError):
                latest_current_rejections(Path('/repo'), reports, rows)


if __name__ == '__main__':
    unittest.main()
