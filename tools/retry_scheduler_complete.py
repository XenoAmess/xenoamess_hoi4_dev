"""Close only a batch whose exact claimed calls really returned."""
import sys,os
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now,file_sha256
from mod_nailong.tools.production_queue import attempt_for_snapshot
from mod_nailong.tools.image_retries import policy
from mod_nailong.tools.retry_limits import retry_limit
directory=ROOT/'runtime/retry-scheduler';state_path=directory/'state.json';state=read_json(state_path)
assert state['machine_id']==machine_id();pending=state['pending'];assert pending and pending['batch']==sys.argv[1]
assert file_sha256(ROOT/pending['proof'])==pending['proof_sha256']
proof={c['key']:c for c in read_json(ROOT/pending['proof'])};queue=read_json(ROOT/'mod_nailong/data/image-retry-queue.json')['sources'];records=[]
for key in pending['source_keys']:
 actual=ROOT/f'runtime/dispatch-actual/{pending["batch"]}-{key}.json';sha=file_sha256(actual)
 a=attempt_for_snapshot(key,actual);c=proof[key]
 assert a['status'] not in ['prepared','calling','cancelled_before_generation'] and a.get('retry_of_attempt')==c['verified_failed_attempt']
 expected=c.get('next_retry_number',1)
 assert queue[key]['retries_used']==expected and a.get('cooldown_retry_number',1)==expected and a['prompt']==c['prompt']
 started=a['actual_request_verification']['verified_at_utc'];assert datetime.fromisoformat(started)>=datetime.fromisoformat(c['not_before_utc'])
 records.append({'source_sha256':key,'source':c['source'],'not_before_utc':c['not_before_utc'],'actual_call_verified_at_utc':started,'claimed_attempt_number':a['number'],'retry_of_attempt':a['retry_of_attempt'],'final_call_status':a['status'],'returned_output_sha256':a.get('output_sha256'),'returned_fullsize_sha256':a.get('fullsize_sha256'),'retry_count':queue[key]['retries_used'],'effective_cumulative_retry_limit':retry_limit(policy(),key),'source_scoped_extra_retry_authorization':a.get('source_scoped_extra_retry_authorization'),'exact_actual_request_verification':a['actual_request_verification']})
receipt={'schema':'naiwa-exact-retry-scheduler-batch-v2','machine_id':machine_id(),'observed_at_utc':utc_now(),'batch':pending['batch'],'calls_finished':len(records),'accepted_outputs':sum(bool(r['returned_output_sha256']) for r in records),'records':records,'boundary':'Same single awaited builtin producer. Each unchanged request was manually policy reviewed, claimed before dispatch after its own8h deadline, and actually returned. Default cumulative limit8; only a source with an explicit frozen user-authorized extra round may use its separately recorded additional call. No consumed-count reset. Returned images still need separate visual review; no service-side concurrency or HOI4 runtime acceptance claimed.'}
write_json(ROOT/f'mod_nailong/data/retry-scheduler-batches/{pending["batch"]}.json',receipt)
state['finished_batches'].append(dict(pending,finished_at_utc=utc_now(),state='exact_calls_finished_visual_review_separate'));state.update(pending=None,next_batch_number=state['next_batch_number']+1,observed_at_utc=utc_now())
temp=state_path.with_suffix('.next.json');write_json(temp,state);os.replace(temp,state_path)
print('Closed actual retry calls:',len(records),'accepted outputs:',receipt['accepted_outputs'],'visual approval remains separate')
