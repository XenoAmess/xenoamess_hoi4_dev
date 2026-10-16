"""Verify cooldown and single-use guards without contacting an image service."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from tools.common import file_sha256, read_json, write_json
from mod_nailong.tools import image_retries as retries


class FixedClock(datetime):
    instant = datetime(2026, 10, 16, 18, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.instant if tz else cls.instant.replace(tzinfo=None)


class ImageRetryGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root / 'mod_nailong'
        (self.mod / 'assets/prompts').mkdir(parents=True)
        self.key = 'a' * 64
        self.original = self.root / 'original.png'
        self.reference = self.mod / 'reference.png'
        Image.new('RGBA', (2, 2), (255, 255, 0, 0)).save(self.original)
        Image.new('RGBA', (2, 2), (255, 255, 0, 255)).save(self.reference)
        self.prompt = 'Exact original prompt\nKeep hair and moustache.\n'
        self.journal = self.mod / 'data/generation-requests' / (self.key + '.json')
        write_json(self.mod / 'data/catalog.json', {'assets': [{'source_sha256': self.key}]})
        write_json(self.mod / 'data/generation-failures.json', {'attempts': [{
            'source_sha256': self.key, 'status': 'blocked', 'observed_at_utc': '2026-10-16T10:00:00+00:00'
        }]})
        write_json(self.journal, {'attempts': [{
            'number': 1, 'status': 'failed', 'prompt': self.prompt, 'error': 'recorded refusal',
            'inputs': [
                {'role': 'original', 'raw_sha256': self.key, 'converted_png_sha256': file_sha256(self.original)},
                {'role': 'reference', 'path': self.reference.relative_to(self.root).as_posix(), 'sha256': file_sha256(self.reference)}
            ], 'edit_existing': False
        }]})
        FixedClock.instant = datetime(2026, 10, 16, 18, tzinfo=timezone.utc)
        patches = [patch.object(retries, 'ROOT', self.root), patch.object(retries, 'MOD', self.mod),
                   patch.object(retries, 'QUEUE', self.mod / 'data/image-retry-queue.json'),
                   patch.object(retries, 'datetime', FixedClock), patch.object(retries, 'machine_id', return_value='test-machine'),
                   patch('mod_nailong.tools.generation_requests.original', return_value=self.original)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_before_eight_hours_does_not_consume_retry(self):
        FixedClock.instant = datetime(2026, 10, 16, 17, 59, 59, tzinfo=timezone.utc)
        with self.assertRaisesRegex(SystemExit, 'cooldown has not elapsed'):
            retries.claim(self.key)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'], 0)
        self.assertEqual(len(read_json(self.journal)['attempts']), 1)

    def test_due_request_preserves_bytes_and_consumes_exactly_once(self):
        retries.claim(self.key)
        job = read_json(self.root / 'runtime/cooldown-retry-job.json')
        self.assertEqual(job['prompt'], self.prompt)
        self.assertEqual(job['references'], [str(self.original), str(self.reference)])
        attempt = read_json(self.journal)['attempts'][-1]
        self.assertEqual((self.root / attempt['prompt_file']).read_bytes(), self.prompt.encode('utf-8'))
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'], 1)
        with self.assertRaisesRegex(SystemExit, 'Retry already consumed'):
            retries.claim(self.key)
        self.assertEqual(len(read_json(self.journal)['attempts']), 2)

    def test_changed_input_refuses_without_consuming(self):
        self.reference.write_bytes(b'changed input')
        with self.assertRaisesRegex(SystemExit, 'input bytes no longer match'):
            retries.claim(self.key)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'], 0)
        self.assertEqual(len(read_json(self.journal)['attempts']), 1)

    def test_refused_source_cannot_start_a_reworded_request(self):
        retries.sync()
        with self.assertRaisesRegex(SystemExit,'Service-held source'):
            retries.require_editable_service_state(self.key,None,None,False)
        self.assertFalse(read_json(self.mod/'data/generation-failures.json')['attempts'][0].get('resolved_by_retry'))

    def test_returned_exact_retry_can_receive_separate_art_correction(self):
        retries.claim(self.key)
        digest=file_sha256(self.original)
        queue=read_json(retries.QUEUE);queue['sources'][self.key].update(state='generated_pending_visual_review',output_sha256=digest);write_json(retries.QUEUE,queue)
        row={'image':self.original.relative_to(self.root).as_posix(),'image_sha256':digest,'review':'rejected'}
        latest={'retry_of_attempt':1,'status':'generated_rejected_visual_review','output_sha256':digest}
        retries.require_editable_service_state(self.key,row,latest,True)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],1)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['state'],'service_retry_succeeded_art_correction_pending')
        result=read_json(self.mod/'data/generation-failures.json')['attempts'][0]['resolved_by_retry']
        self.assertEqual(result['status'],'service_returned_image_art_correction_pending')
        self.assertTrue(result['original_refusal_preserved'])


if __name__ == '__main__':
    unittest.main()
