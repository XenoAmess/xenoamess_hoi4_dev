"""Verify rolling cooldown, eight-call allowance, and immutable retry inputs."""
from datetime import datetime, timezone, timedelta
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
        write_json(self.mod/'data/image-retry-policy.json',{'cooldown_hours':8,'max_cooldown_retries_per_source':8,'user_instruction_date':'2026-10-18'})
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

    def test_near_opaque_retry_keeps_actual_false_flag_across_retry_chain(self):
        Image.new('RGBA',(2,2),(100,100,100,254)).save(self.original)
        data=read_json(self.journal)
        data['attempts'][0]['inputs'][0]['converted_png_sha256']=file_sha256(self.original)
        data['attempts'][0]['actual_request_verification']={'actual_recorded_before_call':True,'transparent_background':False}
        write_json(self.journal,data)
        retries.claim(self.key)
        self.assertIs(read_json(self.root/'runtime/cooldown-retry-job.json')['transparent'],False)
        self.assertIs(read_json(self.journal)['attempts'][-1]['cooldown_retry_tool_transparent_background'],False)
        self.refuse_latest();FixedClock.instant+=timedelta(hours=8)
        retries.claim(self.key)
        self.assertIs(read_json(self.root/'runtime/cooldown-retry-job.json')['transparent'],False)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],2)

    def test_conflicting_retry_flag_refuses_before_quota_consumption(self):
        data=read_json(self.journal)
        data['attempts'][0].update(cooldown_retry_tool_transparent_background=False,actual_request_verification={'actual_recorded_before_call':True,'transparent_background':True})
        write_json(self.journal,data)
        with self.assertRaisesRegex(SystemExit,'transparency conflicts'):retries.claim(self.key)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],0)
        self.assertEqual(len(read_json(self.journal)['attempts']),1)

    def test_retry_reuses_recovered_actual_text_with_a_new_recording_boundary(self):
        data=read_json(self.journal)
        actual='Exact recovered label: \ufffd\ufffd\ufffd\ufffd\n'
        data['attempts'][0].update(prompt=actual,intended_prompt='Original intended label',intended_prompt_file='old.txt',intended_prompt_sha256='old-sha',prompt_transport_correction={'actual_recorded_before_call':False},actual_request_verification={'verified_at_utc':'old-attempt-time'})
        write_json(self.journal,data)
        retries.claim(self.key)
        result=read_json(self.journal)
        self.assertEqual(result['attempts'][-1]['prompt'],actual)
        self.assertEqual((self.root/result['attempts'][-1]['prompt_file']).read_bytes(),actual.encode('utf-8'))
        self.assertNotIn('prompt_transport_correction',result['attempts'][-1])
        self.assertNotIn('intended_prompt',result['attempts'][-1])
        self.assertNotIn('actual_request_verification',result['attempts'][-1])
        self.assertFalse(result['attempts'][0]['prompt_transport_correction']['actual_recorded_before_call'])

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

    def refuse_latest(self):
        journal=read_json(self.journal)
        journal['attempts'][-1].update(status='failed',error='moderation_blocked: actual refusal',observed_at_utc=FixedClock.instant.isoformat())
        write_json(self.journal,journal)

    def test_each_refusal_restarts_eight_hours_and_eighth_retry_is_final(self):
        for number in range(1,9):
            retries.claim(self.key)
            a=read_json(self.journal)['attempts'][-1]
            self.assertEqual(a['cooldown_retry_number'],number)
            self.assertEqual(a['retry_root_attempt'],1)
            self.assertEqual(a['prompt'],self.prompt)
            self.assertEqual(a['inputs'],read_json(self.journal)['attempts'][0]['inputs'])
            self.refuse_latest()
            retries.sync()
            self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],number)
            if number<8:
                FixedClock.instant+=timedelta(hours=8,seconds=-1)
                with self.assertRaisesRegex(SystemExit,'cooldown has not elapsed'):retries.claim(self.key)
                self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],number)
                FixedClock.instant+=timedelta(seconds=1)
        FixedClock.instant+=timedelta(hours=8)
        with self.assertRaisesRegex(SystemExit,'Retry limit reached'):retries.claim(self.key)
        self.assertEqual(len(read_json(self.journal)['attempts']),9)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['state'],'retry_limit_reached')

    def test_old_exhausted_source_reopens_without_resetting_quota_or_cd(self):
        retries.claim(self.key);self.refuse_latest()
        q=read_json(retries.QUEUE);q['sources'][self.key].update(state='retry_failed_no_more_automatic_retries');write_json(retries.QUEUE,q)
        migrated=retries.sync()['sources'][self.key]
        self.assertEqual(migrated['retries_used'],1)
        self.assertEqual(migrated['not_before_utc'],'2026-10-17T02:00:00+00:00')
        self.assertEqual(migrated['state'],'cooling_down')
        self.assertEqual(migrated['policy_migrations'][0]['previous_state'],'retry_failed_no_more_automatic_retries')
        with self.assertRaisesRegex(SystemExit,'cooldown has not elapsed'):retries.claim(self.key)
        FixedClock.instant+=timedelta(hours=8);retries.claim(self.key)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],2)

    def test_returned_image_stops_cooldown_retries(self):
        retries.claim(self.key)
        journal=read_json(self.journal);journal['attempts'][-1].update(status='generated_pending_visual_review',output_sha256='result');write_json(self.journal,journal)
        q=read_json(retries.QUEUE);q['sources'][self.key].update(state='generated_pending_visual_review',output_sha256='result');write_json(retries.QUEUE,q)
        FixedClock.instant+=timedelta(hours=24)
        with self.assertRaisesRegex(SystemExit,'Retry already consumed or result unresolved/returned'):retries.claim(self.key)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],1)

    def test_changed_retry_chain_cannot_consume_second_allowance(self):
        retries.claim(self.key);self.refuse_latest()
        journal=read_json(self.journal);journal['attempts'][-1]['prompt']='changed';write_json(self.journal,journal)
        FixedClock.instant+=timedelta(hours=8)
        with self.assertRaisesRegex(SystemExit,'Retry chain prompt or ordered input identities changed'):retries.claim(self.key)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],1)


if __name__ == '__main__':
    unittest.main()
