"""Actor-only idle-boundary allocation; --inspect-only is fully read-only."""
import sys,os,json,hashlib,argparse
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now,file_sha256
from mod_nailong.tools.image_retries import policy,sync
from tools.retry_actual_proof import load_actual_request
from mod_nailong.tools.retry_limits import retry_limit
from tools.production_priority_gate import low_enabled
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--inspect-only',action='store_true')
parser.add_argument('--high-only',action='store_true')
parser.add_argument('--limit',type=int,choices=range(1,13),default=12)
args=parser.parse_args()
inspect=args.inspect_only
directory=ROOT/'runtime/retry-scheduler';state_path=directory/'state.json';state=read_json(state_path)
assert state['machine_id']==machine_id()
if state['pending']:
 if inspect:print(json.dumps({'count':0,'pending_requires_reconciliation':state['pending']},ensure_ascii=True));raise SystemExit(0)
 raise RuntimeError('A selected retry batch is already pending. Inspect exact jobs and returned records; never claim it twice.')
pool=read_json(directory/'approved-pool.json');assert pool['machine_id']==machine_id()
queue=(read_json(ROOT/'mod_nailong/data/image-retry-queue.json') if inspect else sync())['sources'];priority=read_json(ROOT/'mod_nailong/data/production-priority.json')['sources']
settings=policy()
now=datetime.now(timezone.utc);ready=[];unavailable=[]
for key,c in pool['requests'].items():
 q=queue[key]
 if q['retries_used']>=retry_limit(settings,key) or q['state']!='cooling_down' or (not priority[key]['high_priority'] and (args.high_only or not low_enabled(ROOT))) or datetime.fromisoformat(q['not_before_utc'])>now:continue
 try:
  a=read_json(ROOT/f'mod_nailong/data/generation-requests/{key}.json')['attempts'][-1]
  assert a['status']=='failed' and 'moderation_blocked' in a['error']
  assert c['original_actual_prompt_verified'] and c['policy_reviewed'] is True
  assert c.get('requires_manual_policy_review') is True,'Exact current request needs a retained manual-review requirement'
  assert file_sha256(ROOT/c['manual_review_source'])==c['manual_review_source_sha256'],'Manual-review evidence changed'
  actual,v=load_actual_request(ROOT,key,a,c)
  assert a['prompt']==c['prompt']==actual['prompt'] and c['references']==actual['references'],'approval_payload_outdated: manually reconcile the latest failed frozen prompt and ordered inputs; no quota claimed'
  assert actual['transparent']==c['transparent']==v['transparent_background'],'approval_tool_flags_outdated: manually reconcile the latest frozen tool flag; no quota claimed'
  assert hashlib.sha256(c['prompt'].encode('utf-8')).hexdigest()==a['prompt_sha256']
  assert [file_sha256(Path(p)) for p in c['references']]==c['input_sha256']==v['input_sha256'],'approval_input_bytes_mismatch: keep request held for exact-byte reconciliation; no quota claimed'
  # Previous manual content review remains valid only for identical prompt/input bytes.
  ready.append(dict(c,not_before_utc=q['not_before_utc'],verified_failed_attempt=a['number'],verified_actual_snapshot_sha256=v['actual_request_snapshot_sha256'],retries_used_before_claim=q['retries_used'],next_retry_number=q['retries_used']+1))
 except (AssertionError,KeyError,FileNotFoundError) as error:unavailable.append({'source_sha256':key,'reason':type(error).__name__+': '+str(error)})
ready.sort(key=lambda c:(not priority[c['key']]['high_priority'],c['not_before_utc'],c['key']));ready=ready[:args.limit]
if ready and priority[ready[0]['key']]['high_priority']:ready=[c for c in ready if priority[c['key']]['high_priority']]
elif ready:ready=ready[:1]
if inspect or not ready:
 print(json.dumps({'count':len(ready),'source_keys':[c['key'] for c in ready],'unavailable':unavailable,'inspect_only':inspect},ensure_ascii=True));raise SystemExit(0)
# This process is invoked by the same producer only after its previous batch ended.
assert not any(read_json(p).get('status')=='calling' for p in (ROOT/'runtime/production-queue/dispatch').glob('*.json')),'A builtin call is still active; no allocation or claim at this boundary'
number=f'{state["next_batch_number"]:03}';batch='cooldown-'+number
proof=directory/(batch+'-proof.json');jobs=ROOT/f'runtime/{batch}-jobs.json'
assert not proof.exists() and not jobs.exists(),'Existing batch requires explicit recovery, not replacement'
write_json(proof,ready)
pending={'machine_id':machine_id(),'selected_at_utc':utc_now(),'numeric_id':number,'batch':batch,'proof':proof.relative_to(ROOT).as_posix(),'proof_sha256':file_sha256(proof),'jobs':jobs.relative_to(ROOT).as_posix(),'source_keys':[c['key'] for c in ready],'count':len(ready),'state':'selected_before_claim'}
state.update(pending=pending,observed_at_utc=utc_now());temp=state_path.with_suffix('.next.json');write_json(temp,state);os.replace(temp,state_path)
print(json.dumps(pending,ensure_ascii=True))
