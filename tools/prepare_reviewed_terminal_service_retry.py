"""Recover one proven terminal transport error inside an exact service chain."""
import argparse
import copy
from datetime import datetime
import json
import re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools import image_retries
from mod_nailong.tools.retry_limits import retry_limit
from tools.retry_actual_proof import load_actual_request

ERRORS={'image generation failed: connection failed: error sending request','image generation failed: network error: error sending request'}

def validate(root,config):
    root=Path(root);key=config['source_sha256'];assert re.fullmatch('[0-9a-f]{64}',key)
    assert config['machine_id']==machine_id() and config['known_terminal_reviewed'] is True
    journal=read_json(root/f'mod_nailong/data/generation-requests/{key}.json');a=journal['attempts'][-1]
    assert a['status']=='failed' and a['number']==config['failed_attempt_number'] and a['error'].strip() in ERRORS
    assert a.get('retry_of_attempt'),'Only an existing counted exact service chain is eligible'
    assert not any(x.get('terminal_service_transport_retry_of_attempt')==a['number'] for x in journal['attempts']),'A returned terminal error may be recovered only once; never replay a claimed recovery'
    queue=read_json(root/'mod_nailong/data/image-retry-queue.json');q=queue['sources'][key]
    settings=image_retries.policy();grant=image_retries.wait_waiver(settings,key)
    assert grant and q['state']=='claimed_before_call' and q['retries_used']==config['consumed_retries_before'] and 0<q['retries_used']<retry_limit(settings,key)
    ledger_path=root/f'runtime/production-queue/dispatch/{key}-{a["number"]:03}.json';assert file_sha256(ledger_path)==config['failed_dispatch_sha256']
    ledger=read_json(ledger_path);assert ledger['status']=='tool_error' and ledger.get('call_returned_at_utc') and not ledger.get('returned_image') and not ledger.get('returned_image_sha256')
    assert ledger['source_sha256']==key and ledger['attempt_number']==a['number'] and ledger['machine_id']==machine_id()
    assert ledger['actual_prompt_verified_before_call'] is True
    error=Path(ledger['actual_error_file']);assert error.resolve().is_relative_to((root/'runtime').resolve())
    assert file_sha256(error)==ledger['actual_error_sha256'] and error.read_text(encoding='utf-8')==a['error']
    old=read_json(root/'runtime/retry-scheduler/approved-pool.json')['requests'][key]
    assert old['policy_reviewed'] is True and old['requires_manual_policy_review'] is True
    manual=old['manual_policy_review']
    flags=[manual[name] for name in ('complete_prompt_read','complete_prompt_actually_read') if name in manual]
    assert flags and all(flag is True for flag in flags),'Retained explicit full-prompt review required; conflicting aliases remain held'
    assert file_sha256(root/old['manual_review_source'])==old['manual_review_source_sha256']
    job,v=load_actual_request(root,key,a,old)
    assert Path(ledger['actual_request_snapshot_file']).resolve().is_relative_to((root/'runtime/dispatch-actual').resolve())
    assert file_sha256(Path(ledger['actual_request_snapshot_file']))==config['actual_request_snapshot_sha256']==v['actual_request_snapshot_sha256']
    assert job['key']==key and job['prompt']==a['prompt']==old['prompt'] and job['references']==old['references']
    assert file_sha256(root/a['prompt_file'])==a['prompt_sha256']==ledger['prompt_sha256']
    assert (root/a['prompt_file']).read_text(encoding='utf-8')==job['prompt']
    assert job['transparent']==old['transparent']==v['transparent_background']
    assert [file_sha256(Path(p)) for p in job['references']]==old['input_sha256']==v['input_sha256']==ledger['input_sha256']==[i.get('sha256',i.get('converted_png_sha256')) for i in a['inputs']]
    assert isinstance(job['source'],str) and job['source'] and job['original'] in job['references']
    probe_path=root/config['later_successful_probe_receipt'];assert file_sha256(probe_path)==config['later_successful_probe_receipt_sha256']
    probe=read_json(probe_path);events=[e for e in probe['events'] if e['phase']=='image_resolved']
    moment=lambda value:datetime.fromisoformat(value.replace('Z','+00:00'))
    assert probe['machine_id']==machine_id() and probe['status']=='completed' and any(not e.get('error') and moment(e['observed_at_utc'])>moment(ledger['call_returned_at_utc']) for e in events),'Actual later successful service return required'
    return journal,queue,job,grant,old

def prepare(root,batch,index,config):
    root=Path(root);assert re.fullmatch('[A-Za-z0-9_-]+',batch)
    assert not any(read_json(p).get('status')=='calling' for p in (root/'runtime/production-queue/dispatch').glob('*.json'))
    assert read_json(root/'runtime/retry-scheduler/state.json')['pending'] is None
    journal,queue,job,grant,old=validate(root,config);key=config['source_sha256'];a=journal['attempts'][-1]
    plan_path=root/'runtime/after128-continuous-plan.json';plan=read_json(plan_path);assert len(plan['batches'])==index
    output=root/f'runtime/production-{batch}-jobs.json';assert not output.exists()
    receipt_path=root/f'mod_nailong/data/production-transport-retries/{batch}.json';assert not receipt_path.exists()
    before=copy.deepcopy(queue['sources'][key]);entry=queue['sources'][key]
    # The old "claimed" state survived a proved returned error; it is not an
    # unresolved call. Restore exact-service admission only after all evidence.
    entry.update(state='cooling_down',not_before_utc=grant['effective_at_utc'],default_eight_hour_not_before_utc=before.get('default_eight_hour_not_before_utc',before['not_before_utc']))
    entry.setdefault('terminal_transport_recoveries',[]).append({'recorded_at_utc':utc_now(),'failed_attempt':a['number'],'previous_state':before['state'],'previous_not_before_utc':before['not_before_utc'],'before_retries_used':before['retries_used'],'evidence':config,'scope':'Known returned transport error, exact manually approved request retained. Restores pre-call admission and then consumes ONE further lifetime service allowance; no error reclassification or free retry.'})
    write_json(root/'mod_nailong/data/image-retry-queue.json',queue)
    image_retries.claim(key)
    current=read_json(root/f'mod_nailong/data/generation-requests/{key}.json');prepared=current['attempts'][-1]
    assert prepared['status']=='prepared' and prepared['number']==a['number']+1 and prepared['cooldown_retry_number']==before['retries_used']+1
    prepared['terminal_service_transport_retry_of_attempt']=a['number'];write_json(root/f'mod_nailong/data/generation-requests/{key}.json',current)
    exported=read_json(root/'runtime/cooldown-retry-job.json');assert exported['prompt']==job['prompt'] and exported['references']==job['references'] and exported['transparent']==job['transparent']
    exported.update(source=job['source'],original=job['original']);write_json(output,[exported])
    plan['batches'].append({'batch':batch,'jobs':output.relative_to(root).as_posix()});write_json(plan_path,plan)
    write_json(receipt_path,{'machine_id':machine_id(),'prepared_at_utc':utc_now(),'source_sha256':key,'failed_attempt':a['number'],'prepared_attempt':prepared['number'],'consumed_before':before['retries_used'],'consumed_after':prepared['cooldown_retry_number'],'prior_queue_entry':before,'evidence':config,'frozen_original_job':job,'scope':'Prepared only after later actual service success. Exactly one additional cumulative allowance consumed by the normal exact claim implementation; no new image call, content/prompt/input/tool change or quota reset. Service rejection history retained.'})
    return {'prepared':1,'batch':batch,'index':index,'receipt':receipt_path.relative_to(root).as_posix()}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch');p.add_argument('index');p.add_argument('config');args=p.parse_args()
    index=len(read_json(ROOT/'runtime/after128-continuous-plan.json')['batches']) if args.index=='auto' else int(args.index)
    print(json.dumps(prepare(ROOT,args.batch,index,read_json(ROOT/args.config)),ensure_ascii=True))
