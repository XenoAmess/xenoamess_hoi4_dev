"""Read-only audit of actual service refusals and returned cooldown calls."""
import sys,json,hashlib
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now
queue=read_json(ROOT/'mod_nailong/data/image-retry-queue.json')['sources']
failures=read_json(ROOT/'mod_nailong/data/generation-failures.json')['attempts']
blocked={f['source_sha256'] for f in failures if f.get('status')=='blocked'}
returned=Counter();refused=Counter();pending=Counter();details=[];multiple=[]
for key,q in queue.items():
 path=ROOT/f'mod_nailong/data/generation-requests/{key}.json'
 attempts=read_json(path)['attempts'] if path.exists() else []
 retries=[a for a in attempts if a.get('retry_of_attempt') and a['status']!='cancelled_before_generation']
 if len(retries)>1:multiple.append(key)
 for rank,a in enumerate(retries,1):
  result='pending_or_unknown'
  if a.get('output_sha256'):returned[rank]+=1;result='image_returned'
  elif a['status']=='failed' and 'moderation_blocked' in a.get('error',''):refused[rank]+=1;result='refused'
  else:pending[rank]+=1
  details.append({'source_sha256':key,'cooldown_retry_ordinal':rank,'journal_attempt_number':a['number'],'retry_of_attempt':a['retry_of_attempt'],'status':a['status'],'result':result,'output_sha256':a.get('output_sha256'),'fullsize_sha256':a.get('fullsize_sha256'),'not_before_utc':a.get('cooldown_not_before_utc'),'actual_started_at_utc':a.get('actual_request_verification',{}).get('verified_at_utc'),'generated_at_utc':a.get('generated_at_utc'),'queue_state':q['state']})
report={'schema':'naiwa-refusal-retry-statistics-v1','machine_id':machine_id(),'observed_at_utc':utc_now(),'counting_unit':'Distinct original source SHA; a service-returned image is not necessarily art-qualified. Art edits and cancelled drafts are not cooldown retries. Prepared claims are not completed calls.','unique_sources_ever_refused':len(blocked),'queue_unique_sources':len(queue),'untracked_refused_sources':sorted(blocked-set(queue)),'returned_by_cooldown_retry_ordinal':dict(returned),'refused_by_cooldown_retry_ordinal':dict(refused),'pending_or_unknown_by_cooldown_retry_ordinal':dict(pending),'total_completed_cooldown_calls':sum(returned.values())+sum(refused.values()),'multiple_cooldown_attempt_sources':multiple,'queue_state_counts':dict(Counter(q['state'] for q in queue.values())),'details':details}
stamp=report['observed_at_utc'].replace(':','').replace('.','').replace('+','')
destination=ROOT/f'mod_nailong/data/retry-statistics/{stamp}.json';write_json(destination,report)
print(json.dumps({k:v for k,v in report.items() if k not in ('details','multiple_cooldown_attempt_sources')},ensure_ascii=True));print('multiple_cooldown_attempt_sources',len(multiple));print('Evidence',destination)
