import tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from tools.common import write_json
from tools.checkpoint_schedule import recent_local_checkpoint,automatic_checkpoint_deferral

class CheckpointScheduleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.now=datetime(2026,10,24,10,0,tzinfo=timezone.utc)
  self.addCleanup(patch.stopall);patch('tools.checkpoint_schedule.machine_id',return_value='fixture').start()
 def receipt(self,name='one',**changes):
  body={'machine_id':'fixture','status':'committed_and_pushed','commit':'a'*40,'local_commit_completed_at_utc':'2026-10-24T09:45:00+00:00'};body.update(changes)
  write_json(self.root/f'runtime/checkpoint-{name}.json',body)
 def test_recent_idle_or_window_commit_prevents_a_duplicate_automatic_audit(self):
  self.receipt();result=automatic_checkpoint_deferral(self.root,now=self.now)
  self.assertEqual(result['status'],'deferred_by_recent_local_checkpoint');self.assertEqual(result['previous_actual_local_checkpoint']['age_seconds'],900)
  self.assertEqual(len(list(self.root.rglob('*.json'))),1)
 def test_explicit_force_keeps_real_checkpoint_available(self):
  self.receipt();self.assertIsNone(automatic_checkpoint_deferral(self.root,force=True,now=self.now))
 def test_old_commit_or_no_previous_commit_cannot_suppress_validation(self):
  self.assertIsNone(recent_local_checkpoint(self.root,self.now));self.receipt(local_commit_completed_at_utc='2026-10-24T09:30:00+00:00');self.assertIsNone(recent_local_checkpoint(self.root,self.now))
 def test_other_machine_or_failed_partial_or_deferred_receipts_are_not_a_completed_checkpoint(self):
  self.receipt('other',machine_id='other');self.receipt('failed',status='validation_failed');self.receipt('deferred',status='deferred_by_recent_local_checkpoint');self.assertIsNone(recent_local_checkpoint(self.root,self.now))
 def test_newest_actual_commit_is_used_and_future_clock_is_not_evidence(self):
  self.receipt('older');self.receipt('newer',commit='b'*40,local_commit_completed_at_utc='2026-10-24T09:55:00+00:00');self.receipt('future',local_commit_completed_at_utc='2026-10-24T10:01:00+00:00')
  self.assertEqual(recent_local_checkpoint(self.root,self.now)['commit'],'b'*40)
 def test_pending_network_publish_does_not_block_imports_with_another_local_audit(self):
  self.receipt(status='committed_push_pending');r=automatic_checkpoint_deferral(self.root,now=self.now);self.assertEqual(r['previous_actual_local_checkpoint']['remote_status_at_observation'],'committed_push_pending')

if __name__=='__main__':unittest.main()
