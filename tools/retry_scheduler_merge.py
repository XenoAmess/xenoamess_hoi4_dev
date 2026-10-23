"""Version manually reviewed exact requests at an idle boundary; never claim quota."""
import sys,os,hashlib,json,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools.image_retries import policy

def entry_digest(entry):
 return hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=True,separators=(',',':')).encode('ascii')).hexdigest()

def same_payload(left,right):
 return all(left.get(k)==right.get(k) for k in ('prompt','references','input_sha256','transparent'))

def validate_supersession(old,candidate,attempts,row):
 """Changed approval must follow a real service success and rejected raw art target."""
 proof=candidate.get('approval_supersession')
 assert proof and proof['previous_entry_sha256']==entry_digest(old),'Missing or stale approval-version proof'
 assert proof.get('retry_counter_reset') is False and proof.get('reason')
 latest=attempts[-1];v=latest['actual_request_verification']
 assert latest['status']=='failed'
 assert proof['failed_attempt_number']==latest['number']
 assert proof['failed_actual_snapshot_sha256']==v['actual_request_snapshot_sha256']
 assert proof['previous_prompt_sha256']==hashlib.sha256(old['prompt'].encode('utf-8')).hexdigest()
 assert proof['previous_input_sha256']==old['input_sha256']
 success=next(a for a in attempts if a['number']==proof['previous_service_success_attempt'])
 assert success['number']<latest['number'] and success.get('fullsize_sha256')
 assert success['status'].startswith('generated') or success['status']=='approved'
 assert success['prompt']==old['prompt']
 assert success['actual_request_verification']['input_sha256']==old['input_sha256']
 assert success['actual_request_verification']['transparent_background']==old['transparent']
 if latest.get('edit_existing') is True:
  target=latest['inputs'][0]
  assert target['role']=='previous generated fullsize edit target'
  assert target['sha256']==proof['edit_target_fullsize_sha256']==candidate['input_sha256'][0]
  rejected_sha=target['sha256']
 else:
  # An original-based art replacement still requires the actual rejected PNG,
  # the frozen pre-call replacement reason and the exact original/user inputs.
  assert latest.get('edit_existing') is False and proof.get('art_correction_mode')=='regenerate_from_exact_original'
  reason=latest.get('replacement_reason');assert isinstance(reason,str) and reason.strip()
  assert proof['replacement_reason_sha256']==hashlib.sha256(reason.encode('utf-8')).hexdigest()
  original,user=latest['inputs'];assert len(candidate['references'])==len(candidate['input_sha256'])==2
  assert original['role']=='original source portrait' and original['raw_sha256']==candidate['key']==proof['original_source_sha256']
  assert user['role']=='user mascot reference'
  assert candidate['input_sha256']==[original['converted_png_sha256'],user['sha256']]
  rejected_sha=proof['rejected_fullsize_sha256']
 returned=next(a for a in attempts if a.get('fullsize_sha256')==rejected_sha)
 assert success['number']<=returned['number']<latest['number']
 assert returned['status']=='generated_rejected_visual_review'
 assert row['review']=='rejected' and row['generated_fullsize_sha256']==rejected_sha
 return copy.deepcopy(old)

def require_idle(root):
 state=root/'runtime/retry-scheduler/state.json'
 assert not state.exists() or read_json(state)['pending'] is None,'Scheduler already owns a pending batch'
 assert not any(read_json(p).get('status')=='calling' for p in (root/'runtime/production-queue/dispatch').glob('*.json')),'Image call still active'

def merge_candidates(source,root=None):
 root=Path(root or ROOT);source=Path(source)
 if not source.is_absolute():source=root/source
 require_idle(root)
 candidates=read_json(source);machine=machine_id()
 directory=root/'runtime/retry-scheduler';directory.mkdir(parents=True,exist_ok=True)
 path=directory/'approved-pool.json'
 pool=read_json(path) if path.exists() else {'schema':'naiwa-approved-exact-retry-pool-v1','machine_id':machine,'requests':{}}
 assert pool['machine_id']==machine
 queue=read_json(root/'mod_nailong/data/image-retry-queue.json')['sources']
 rows=None;added=[];skipped=[];archives=[]
 for c in candidates:
  key=c['key'];assert c['original_actual_prompt_verified'] and c.get('policy_reviewed') is True
  assert c['manual_policy_review']['machine_id']==machine
  if queue[key]['retries_used']>=policy()['max_cooldown_retries_per_source'] or queue[key]['state']!='cooling_down':
   skipped.append(key);continue
  attempts=read_json(root/f'mod_nailong/data/generation-requests/{key}.json')['attempts'];a=attempts[-1]
  assert a['status']=='failed' and 'moderation_blocked' in a['error'] and a['machine_id']==machine
  v=a['actual_request_verification'];assert v['actual_recorded_before_call'] and v['machine_id']==machine
  d=read_json(root/f'runtime/production-queue/dispatch/{key}-{a["number"]:03}.json')
  snapshot=Path(d['actual_request_snapshot_file']);assert file_sha256(snapshot)==v['actual_request_snapshot_sha256']
  j=read_json(snapshot)
  assert j['key']==key and c['prompt']==j['prompt']==a['prompt'] and c['references']==j['references']
  assert c['transparent']==j['transparent']==v['transparent_background']
  assert hashlib.sha256(c['prompt'].encode('utf-8')).hexdigest()==a['prompt_sha256'] and c['input_sha256']==v['input_sha256']
  assert len(c['references'])==len(c['input_sha256'])
  assert [file_sha256(Path(p)) for p in c['references']]==c['input_sha256'],'Actual input bytes changed'
  assert c['not_before_utc']==queue[key]['not_before_utc']
  assert queue[key].get('cooldown_origin_attempt',a['number'])==a['number']
  entry=dict(c,original_tool_transparent_background=v['transparent_background'],requires_manual_policy_review=True,verified_failed_attempt=a['number'],verified_actual_snapshot_sha256=v['actual_request_snapshot_sha256'],manual_review_source=source.relative_to(root).as_posix(),manual_review_source_sha256=file_sha256(source))
  if key in pool['requests']:
   old=pool['requests'][key]
   if not same_payload(old,entry):
    if rows is None:rows=read_json(root/'mod_nailong/data/generated.json')['portraits']
    previous=validate_supersession(old,entry,attempts,rows[key])
    archive=root/f'mod_nailong/data/retry-approval-versions/{key}-{entry_digest(previous)}.json'
    receipt={'machine_id':machine,'archived_at_utc':utc_now(),'scope':'Complete previous approval preserved at actual payload-version reconciliation. Archive timestamp is current, not a backdated pre-call approval. Source lifetime quota and exact failed request remain unchanged.','previous_entry_sha256':entry_digest(previous),'approval_entry':previous,'superseding_review_source':source.relative_to(root).as_posix(),'superseding_review_source_sha256':file_sha256(source)}
    if archive.exists():assert read_json(archive)['approval_entry']==previous
    else:archives.append((archive,receipt))
    entry['approval_versions']=old.get('approval_versions',[])+[{'archive':archive.relative_to(root).as_posix(),'previous_entry_sha256':entry_digest(previous)}]
   else:
    entry['previous_approval_sources']=old.get('previous_approval_sources',[])+[{'manual_review_source':old['manual_review_source'],'verified_failed_attempt':old['verified_failed_attempt']}]
    if old.get('approval_versions'):entry['approval_versions']=old['approval_versions']
  pool['requests'][key]=entry;added.append(key)
 require_idle(root)
 for archive,receipt in archives:write_json(archive,receipt)
 for entry in pool['requests'].values():
  for version in entry.get('approval_versions',[]):version['archive_sha256']=file_sha256(root/version['archive'])
 pool['observed_at_utc']=utc_now();temp=path.with_suffix('.next.json');write_json(temp,pool);os.replace(temp,path)
 state=directory/'state.json'
 if not state.exists():write_json(state,{'schema':'naiwa-exact-retry-scheduler-state-v1','machine_id':machine,'observed_at_utc':utc_now(),'next_batch_number':10,'pending':None,'finished_batches':[]})
 return {'approved_pool_total':len(pool['requests']),'added':len(added),'already_used_skipped':len(skipped),'archived_previous_versions':len(archives),'quota_claims':0,'image_calls':0}

if __name__=='__main__':print(merge_candidates(sys.argv[1]))
