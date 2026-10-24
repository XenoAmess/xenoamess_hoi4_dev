from datetime import timedelta
import copy
import unittest
from unittest.mock import patch
from tools.common import read_json,write_json,file_sha256
from mod_nailong.tools import image_retries as retries
from mod_nailong.tools.retry_limits import retry_limit
from tests import test_image_retries as fixtures


class SourceScopedRetryRoundTests(unittest.TestCase):
    setUp=fixtures.ImageRetryGuards.setUp
    refuse_latest=fixtures.ImageRetryGuards.refuse_latest

    def exhaust(self):
        for _ in range(8):
            retries.claim(self.key);self.refuse_latest()
            fixtures.FixedClock.instant+=timedelta(hours=8)
        retries.sync()

    def authorize(self):
        keys=[self.key]+[f'{i:064x}' for i in range(30)]
        manifest=self.mod/'data/extra-retry-rounds/fixture.json'
        write_json(manifest,{'authorization_id':'fixture-one-round','source_count':31,'additional_retries_per_selected_source':1,'preserve_consumed_counts':True,'sources':[{'source_sha256':key,'retries_used_at_authorization':8,'additional_authorized_cooldown_retries':1,'max_cooldown_retries_after_authorization':9} for key in keys]})
        settings=read_json(self.mod/'data/image-retry-policy.json')
        settings['source_scoped_extra_retry_rounds']=[{'authorization_id':'fixture-one-round','authorization_manifest':manifest.relative_to(self.root).as_posix(),'authorization_manifest_sha256':file_sha256(manifest),'additional_retries_per_selected_source':1,'retries_used_at_authorization':8,'source_keys':keys}]
        write_json(self.mod/'data/image-retry-policy.json',settings)
        return settings,manifest

    def test_selected_ninth_call_is_exact_guarded_and_only_once(self):
        self.exhaust();before=read_json(self.journal)['attempts'][-1]
        settings,_=self.authorize()
        self.assertEqual(retry_limit(settings,self.key),9)
        self.assertEqual(retry_limit(settings,'f'*64),8)
        retries.claim(self.key)
        latest=read_json(self.journal)['attempts'][-1]
        self.assertEqual(latest['cooldown_retry_number'],9)
        self.assertEqual(latest['prompt'],before['prompt']);self.assertEqual(latest['inputs'],before['inputs'])
        self.assertEqual(latest['source_scoped_extra_retry_authorization']['authorization_id'],'fixture-one-round')
        from tools import portrait_dispatch_guard as guard
        with patch.object(guard,'ROOT',self.root),patch('sys.argv',['guard',self.key]):guard.main()
        self.refuse_latest();fixtures.FixedClock.instant+=timedelta(hours=8)
        with self.assertRaisesRegex(SystemExit,'Retry limit reached'):retries.claim(self.key)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],9)
        self.assertEqual(len(read_json(self.journal)['attempts']),10)

    def test_extra_round_keeps_latest_eight_hour_deadline_and_consumed_count(self):
        self.exhaust();self.authorize()
        fixtures.FixedClock.instant-=timedelta(seconds=1)
        with self.assertRaisesRegex(SystemExit,'cooldown has not elapsed'):retries.claim(self.key)
        entry=read_json(retries.QUEUE)['sources'][self.key]
        self.assertEqual(entry['retries_used'],8);self.assertEqual(entry['max_cooldown_retries'],9)
        self.assertEqual(entry['policy_migrations'][-1]['authorization_id'],'fixture-one-round')

    def test_returned_ninth_image_stops_service_retry_and_can_enter_art_review(self):
        self.exhaust();self.authorize();retries.claim(self.key)
        digest=file_sha256(self.original);j=read_json(self.journal)
        j['attempts'][-1].update(status='generated_rejected_visual_review',output_sha256=digest);write_json(self.journal,j)
        q=read_json(retries.QUEUE);q['sources'][self.key].update(state='generated_pending_visual_review',output_sha256=digest);write_json(retries.QUEUE,q)
        with self.assertRaisesRegex(SystemExit,'Retry limit reached'):retries.claim(self.key)
        row={'image':self.original.relative_to(self.root).as_posix(),'image_sha256':digest,'review':'rejected'}
        retries.require_editable_service_state(self.key,row,j['attempts'][-1],True)
        self.assertEqual(read_json(retries.QUEUE)['sources'][self.key]['retries_used'],9)

    def test_unselected_source_is_still_exhausted_at_eight(self):
        self.exhaust();settings,_=self.authorize()
        grant=settings['source_scoped_extra_retry_rounds'][0]
        grant['source_keys'][0]='f'*64
        self.assertEqual(retry_limit(settings,self.key),8)
        self.assertEqual(retry_limit(settings,'f'*64),9)

    def test_authorization_tamper_and_double_round_fail_closed(self):
        settings,manifest=self.authorize()
        duplicate=copy.deepcopy(settings);duplicate['source_scoped_extra_retry_rounds']*=2
        with self.assertRaisesRegex(AssertionError,'accumulate'):retry_limit(duplicate,self.key)
        manifest.write_bytes(manifest.read_bytes()+b' ')
        with self.assertRaisesRegex(AssertionError,'authorization changed'):retries.policy()


if __name__=='__main__':unittest.main()
