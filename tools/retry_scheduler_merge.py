"""Add already manually reviewed exact originals; never claim a retry."""
import sys,os,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools.image_retries import policy
source=ROOT/sys.argv[1];candidates=read_json(source);machine=machine_id()
directory=ROOT/'runtime/retry-scheduler';directory.mkdir(parents=True,exist_ok=True)
path=directory/'approved-pool.json'
pool=read_json(path) if path.exists() else {'schema':'naiwa-approved-exact-retry-pool-v1','machine_id':machine,'requests':{}}
assert pool['machine_id']==machine
queue=read_json(ROOT/'mod_nailong/data/image-retry-queue.json')['sources'];added=[];skipped=[]
for c in candidates:
 key=c['key'];assert c['original_actual_prompt_verified'] and c.get('policy_reviewed') is True
 assert c['manual_policy_review']['machine_id']==machine
 if queue[key]['retries_used']>=policy()['max_cooldown_retries_per_source'] or queue[key]['state']!='cooling_down':
  skipped.append(key);continue
 a=read_json(ROOT/f'mod_nailong/data/generation-requests/{key}.json')['attempts'][-1]
 assert a['status']=='failed' and 'moderation_blocked' in a['error'] and a['machine_id']==machine
 v=a['actual_request_verification'];assert v['actual_recorded_before_call'] and v['machine_id']==machine
 d=read_json(ROOT/f'runtime/production-queue/dispatch/{key}-{a["number"]:03}.json')
 snapshot=Path(d['actual_request_snapshot_file']);assert file_sha256(snapshot)==v['actual_request_snapshot_sha256']
 j=read_json(snapshot)
 assert c['prompt']==j['prompt']==a['prompt'] and c['references']==j['references'] and c['transparent']==j['transparent']==v['transparent_background']
 assert hashlib.sha256(c['prompt'].encode('utf-8')).hexdigest()==a['prompt_sha256'] and c['input_sha256']==v['input_sha256']
 assert c['not_before_utc']==queue[key]['not_before_utc']
 entry=dict(c,verified_failed_attempt=a['number'],verified_actual_snapshot_sha256=v['actual_request_snapshot_sha256'],manual_review_source=source.relative_to(ROOT).as_posix(),manual_review_source_sha256=file_sha256(source))
 if key in pool['requests']:
  old=pool['requests'][key]
  assert old['prompt']==entry['prompt'] and old['references']==entry['references'] and old['input_sha256']==entry['input_sha256']
  entry['previous_approval_sources']=old.get('previous_approval_sources',[])+[{'manual_review_source':old['manual_review_source'],'verified_failed_attempt':old['verified_failed_attempt']}]
 pool['requests'][key]=entry;added.append(key)
pool['observed_at_utc']=utc_now();temp=path.with_suffix('.next.json');write_json(temp,pool);os.replace(temp,path)
state=directory/'state.json'
if not state.exists():write_json(state,{'schema':'naiwa-exact-retry-scheduler-state-v1','machine_id':machine,'observed_at_utc':utc_now(),'next_batch_number':10,'pending':None,'finished_batches':[]})
print({'approved_pool_total':len(pool['requests']),'added':len(added),'already_used_skipped':len(skipped),'quota_claims':0,'image_calls':0})
