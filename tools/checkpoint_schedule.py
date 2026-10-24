"""Coordinate automatic and requested checkpoints without claiming new validation."""
from datetime import datetime,timezone
import re
from tools.common import read_json,machine_id

LOCAL_COMMITTED={'committed_push_pending','committed_and_pushed','committed_pushed_and_originals_verified'}

def recent_local_checkpoint(root,now=None,interval_seconds=1800):
 now=now or datetime.now(timezone.utc);recent=[]
 for path in (root/'runtime').glob('checkpoint-*.json'):
  try:body=read_json(path)
  except (OSError,ValueError):continue # A concurrently updated receipt is not proof.
  if body.get('machine_id')!=machine_id() or body.get('status') not in LOCAL_COMMITTED:continue
  if not re.fullmatch('[0-9a-f]{40}',body.get('commit','')):continue
  try:completed=datetime.fromisoformat(body['local_commit_completed_at_utc'].replace('Z','+00:00'))
  except (KeyError,TypeError,ValueError):continue
  age=(now-completed).total_seconds()
  if 0<=age<interval_seconds:recent.append((completed,path,body))
 if not recent:return None
 _,path,body=max(recent,key=lambda row:row[0])
 return {'path':path.relative_to(root).as_posix(),'commit':body['commit'],'local_commit_completed_at_utc':body['local_commit_completed_at_utc'],'age_seconds':round((now-datetime.fromisoformat(body['local_commit_completed_at_utc'].replace('Z','+00:00'))).total_seconds(),3),'remote_status_at_observation':body['status']}

def automatic_checkpoint_deferral(root,force=False,now=None):
 if force:return None
 previous=recent_local_checkpoint(root,now)
 if previous is None:return None
 return {'status':'deferred_by_recent_local_checkpoint','previous_actual_local_checkpoint':previous,
  'scope':'No new audit, build, commit, push or remote raw-byte verification occurred for this deferred request. Current returned PNGs remain preserved and queued for a later real checkpoint. Existing actual checkpoint evidence is retained. An explicit --force request bypasses only this scheduling delay, never validation.'}
