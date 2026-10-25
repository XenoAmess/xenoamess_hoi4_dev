"""Durable sole-owner logical queue; preparation and next windows need no model turn."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now,file_sha256
from tools.production_window_gate import inspect_window
from mod_nailong.tools.ready_art_reports import reports as inbox_reports,independent_art_holds
from mod_nailong.tools.prepare_ready_art_reviews import eligible_entries,service_held_keys,latest_current_rejections
from tools.accepted_retry_art import accepted_retry_art_proofs
from mod_nailong.tools.retry_limits import retry_limit
from tools.production_priority_gate import low_enabled,high_in_item,immediate_high_work,low_feedback_enabled,low_correction_in_item

def no_calling(root):
    assert not any(read_json(p).get('status')=='calling' for p in (root/'runtime/production-queue/dispatch').glob('*.json')),'Unresolved actual call: reconcile, never replay'

def claim(root,run_id,index,after,expected_machine):
    assert re.fullmatch(r'[A-Za-z0-9_-]+',run_id)
    gate=inspect_window(root,after,expected_machine);assert gate['ready'],gate
    assert 0<=index<=len(read_json(root/'runtime/after128-continuous-plan.json')['batches'])
    folder=root/'runtime/rolling-production';folder.mkdir(parents=True,exist_ok=True)
    lease=folder/'owner.json'
    # Keep the lease across the entire logical queue, including idle periods.
    # A stopped owner must be explicitly reconciled before a new run may claim.
    fd=os.open(lease,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump({'run_id':run_id,'machine_id':expected_machine},stream)
    state={'machine_id':expected_machine,'run_id':run_id,'next_index':index,'after_window':after,'status':'running','created_at_utc':utc_now(),'completed_windows':0,'completed_source_requests':0}
    write_json(folder/(run_id+'.json'),state);return state

def validate_prepared(root,item):
    assert re.fullmatch(r'[A-Za-z0-9_-]+',item['batch'])
    path=(root/item['jobs']).resolve();assert path.is_relative_to((root/'runtime').resolve())
    jobs=read_json(path);assert 1<=len(jobs)<=8 and len({j['key'] for j in jobs})==len(jobs)
    for j in jobs:
        assert re.fullmatch(r'[0-9a-f]{64}',j['key'])
        attempt=read_json(root/j['journal'])['attempts'][-1]
        assert attempt['status']=='prepared' and attempt['prompt']==j['prompt'],'Already dispatched or changed prepared payload; stop, never replay'
        assert not (root/f"runtime/production-queue/dispatch/{j['key']}-{attempt['number']:03}.json").exists()
    return len(jobs)

def run_checked(root,command,runner=None):
    result=(runner(command) if runner else subprocess.run(command,cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace'))
    assert result.returncode==0,{'error':'Boundary stopped; preserve partial claims and never automatically replay','stdout':result.stdout,'stderr':result.stderr}
    return result

def merge_reviewed_retries(root,expected_machine,runner=None):
    """Consume explicit immutable review pointers without another model turn."""
    folder=root/'runtime/retry-review-inbox';pending=sorted((folder/'pending').glob('*.json'))
    if not pending:return {'merged':False,'reason':'no_queued_exact_policy_review'}
    scheduler=root/'runtime/retry-scheduler/state.json'
    if scheduler.exists() and read_json(scheduler)['pending'] is not None:
        return {'merged':False,'reason':'retry_batch_still_owned'}
    no_calling(root)
    pointer=pending[0];body=read_json(pointer)
    assert body['machine_id']==expected_machine
    source=(root/body['path']).resolve()
    assert source.is_relative_to((root/'mod_nailong/data').resolve()) and source.suffix=='.json'
    assert file_sha256(source)==body['sha256'],'Queued manual review changed'
    claimed=folder/'claimed'/pointer.name;claimed.parent.mkdir(parents=True,exist_ok=True)
    assert not claimed.exists(),'Prior approval merge requires reconciliation, never replay'
    pointer.rename(claimed)
    outcome=run_checked(root,[sys.executable,'tools/retry_scheduler_merge.py',body['path']],runner)
    receipt=root/'mod_nailong/data/production-retry-approval-merges'/pointer.name
    assert not receipt.exists()
    write_json(receipt,{'machine_id':expected_machine,'completed_at_utc':utc_now(),'pointer':body,'status':'merged_at_sole_producer_boundary','stdout':outcome.stdout,'quota_claims':0,'image_calls':0})
    return {'merged':True,'receipt':receipt.relative_to(root).as_posix()}

def checkpoint_when_idle(root,state,runner=None):
    request=root/'runtime/rolling-production'/(state['run_id']+'-checkpoint-requested.json')
    if not request.exists():return None
    body=read_json(request)
    assert body['machine_id']==state['machine_id'] and body['run_id']==state['run_id']
    if not body.get('allow_idle'):return None
    no_calling(root)
    assert state['next_index']==len(read_json(root/'runtime/after128-continuous-plan.json')['batches']),'Prepared work must continue before idle checkpoint'
    request_id=body.get('request_id','');assert not request_id or re.fullmatch('[A-Za-z0-9_-]{1,64}',request_id)
    suffix=('-'+request_id) if request_id else ''
    batch=state['run_id']+'-idle'+str(state['next_index'])+suffix
    request.rename(request.with_name(state['run_id']+'-checkpoint-claimed-idle-'+str(state['next_index'])+suffix+'.json'))
    result=run_checked(root,[sys.executable,'tools/production_checkpoint.py',batch]+(['--force'] if body.get('force') else []),runner)
    return {'batch':batch,'stdout_tail':result.stdout[-2500:],'scope':'Same sole owner, no unresolved call and no prepared/eligible work. Validation uses otherwise idle supply time; remote publisher remains separate.'}

def synchronize_retry_allowances(root,runner=None):
    """Migrate changed source limits once, at the sole owner's idle boundary."""
    settings_path=root/'mod_nailong/data/image-retry-policy.json'
    if not settings_path.exists():return {'synchronized':False}
    settings=read_json(settings_path)
    grants=settings.get('source_scoped_extra_retry_rounds',[])
    if not grants:return {'synchronized':False}
    queue_path=root/'mod_nailong/data/image-retry-queue.json'
    before=read_json(queue_path)['sources']
    keys={key for grant in grants for key in grant['source_keys']}
    assert keys<=set(before),'Extra-round sources need their original consumed counters'
    if all(before[key].get('max_cooldown_retries')==retry_limit(settings,key) for key in keys):
        return {'synchronized':False,'reason':'source_limits_already_current'}
    no_calling(root)
    run_checked(root,[sys.executable,'mod_nailong/tools/image_retries.py','sync'],runner)
    after=read_json(queue_path)['sources']
    assert all(after[key]['retries_used']==entry['retries_used'] for key,entry in before.items()),'Policy migration changed consumed counters'
    assert all(after[key]['max_cooldown_retries']==retry_limit(settings,key) for key in keys)
    return {'synchronized':True,'selected_sources':len(keys),'quota_claims':0}

def allocate_exact_retry(root,state,runner=None,high_only=False):
    """Only the persistent producer selects and claims unchanged, reviewed retries."""
    scheduler=root/'runtime/retry-scheduler/state.json'
    if not scheduler.exists():return None
    before=read_json(scheduler)
    assert before['machine_id']==state['machine_id'] and before['pending'] is None,'Pending retry batch requires explicit reconciliation'
    synchronize_retry_allowances(root,runner)
    command=[sys.executable,'tools/retry_scheduler_next.py','--limit','8']
    if high_only:command.append('--high-only')
    inspected=json.loads(run_checked(root,command+['--inspect-only'],runner).stdout)
    assert not inspected.get('pending_requires_reconciliation'),inspected
    if not inspected['count']:return None
    pending=json.loads(run_checked(root,command,runner).stdout)
    assert pending['machine_id']==state['machine_id'] and 1<=pending['count']<=8
    assert pending['batch']=='cooldown-'+pending['numeric_id']
    assert read_json(scheduler)['pending']==pending
    assert file_sha256(root/pending['proof'])==pending['proof_sha256']
    run_checked(root,[sys.executable,'tools/retry_scheduler_claim.py',pending['numeric_id'],pending['proof']],runner)
    jobs=read_json(root/pending['jobs'])
    assert [job['key'] for job in jobs]==pending['source_keys'] and len(jobs)==pending['count']
    item={'batch':pending['batch'],'jobs':pending['jobs']}
    validate_prepared(root,item)
    path=root/'runtime/after128-continuous-plan.json';plan=read_json(path)
    assert len(plan['batches'])==state['next_index'] or (low_enabled(root) and all(not high_in_item(root,item,read_json(root/'mod_nailong/data/production-priority.json')['sources']) for item in plan['batches'][state['next_index']:])),'Only uncalled LOW windows may precede a newly due HIGH retry'
    plan['batches'].append(item);write_json(path,plan)
    evidence=root/f"mod_nailong/data/production-retry-refills/{state['run_id']}-{state['next_index']}.json"
    assert not evidence.exists()
    write_json(evidence,{'machine_id':state['machine_id'],'observed_at_utc':utc_now(),'run_id':state['run_id'],'index':state['next_index'],'pending':pending,'jobs_sha256':file_sha256(root/pending['jobs']),'boundary':'Same sole producer; prior manual review reused only after exact frozen prompt, ordered input bytes, tool flag, latest refusal deadline and cumulative allowance checks. No changed request and no concurrent claim.'})
    return item

def finish_exact_retry(root,state,runner=None):
    item=read_json(root/'runtime/after128-continuous-plan.json')['batches'][state['next_index']]
    if not item['batch'].startswith('cooldown-'):return
    scheduler=read_json(root/'runtime/retry-scheduler/state.json')
    assert scheduler['machine_id']==state['machine_id'] and scheduler['pending'] and scheduler['pending']['batch']==item['batch'],'Retry completion needs exact pending batch; reconcile, never replay'
    run_checked(root,[sys.executable,'tools/retry_scheduler_complete.py',item['batch']],runner)
    assert read_json(root/'runtime/retry-scheduler/state.json')['pending'] is None

def ready_art(root,expected_machine):
    reports=[(p,read_json(p)) for p,_ in inbox_reports('global')]
    rows=read_json(root/'mod_nailong/data/generated.json')['portraits']
    for _,body in reports:
        assert body.get('machine_id')==expected_machine and body.get('decisions_staged')
    latest=latest_current_rejections(root,reports,rows)
    priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
    failures=read_json(root/'mod_nailong/data/generation-failures.json')['attempts']
    accepted=accepted_retry_art_proofs(root,rows,latest)
    return eligible_entries(reports,rows,latest,service_held_keys(latest,priority,failures,accepted['proofs'])|independent_art_holds(root),priority)

def prioritize_high(root,state,runner=None):
    """Move uncalled HIGH ahead of LOW without changing frozen jobs or completed windows."""
    if not low_enabled(root):return
    path=root/'runtime/after128-continuous-plan.json';plan=read_json(path);index=state['next_index']
    priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
    if index==len(plan['batches']) or high_in_item(root,plan['batches'][index],priority):return
    assert len(read_json(root/plan['batches'][index]['jobs']))==1,'LOW windows must recheck HIGH before each call'
    high=next((i for i in range(index+1,len(plan['batches'])) if high_in_item(root,plan['batches'][i],priority)),None)
    if high is None:
        ready=ready_art(root,state['machine_id'])
        if any(priority[e['source_sha256']]['high_priority'] for _,e in ready):
            batch=state['run_id']+'-batch'+str(len(plan['batches']))
            run_checked(root,[sys.executable,'mod_nailong/tools/prepare_ready_art_reviews.py',batch,str(len(plan['batches'])),'--inbox'],runner)
        else:allocate_exact_retry(root,state,runner,high_only=True)
        plan=read_json(path)
        high=next((i for i in range(index+1,len(plan['batches'])) if high_in_item(root,plan['batches'][i],priority)),None)
    correction=False
    if high is None and low_feedback_enabled(root) and not low_correction_in_item(root,plan['batches'][index],priority):
        high=next((i for i in range(index+1,len(plan['batches'])) if low_correction_in_item(root,plan['batches'][i],priority)),None)
        correction=high is not None
    if high is not None:
        item=plan['batches'].pop(high);plan['batches'].insert(index,item);write_json(path,plan)
        folder=root/'mod_nailong/data/production-priority-dispatches';receipt=folder/(state['run_id']+'-'+str(index)+'.json');assert not receipt.exists()
        write_json(receipt,{'machine_id':state['machine_id'],'observed_at_utc':utc_now(),'window_index':index,'prior_plan_index':high,('prioritized_LOW_art_correction' if correction else 'prioritized_HIGH'):item,'scope':'Same owner, no active call. Only the uncalled plan suffix reordered; job bytes, attempts, consumed retry counters and completed windows unchanged.'})

def refill_reviewed_backlog(root,expected_machine,runner=None,selector=None):
    """Prepare future windows between imports while the current window continues."""
    owner_path=root/'runtime/rolling-production/owner.json'
    if not owner_path.exists():return {'prepared':False,'reason':'no_logical_owner'}
    owner=read_json(owner_path);assert owner['machine_id']==expected_machine
    state=read_json(owner_path.with_name(owner['run_id']+'.json'))
    assert state['status']=='running' and state['machine_id']==expected_machine
    no_calling(root)
    plan=read_json(root/'runtime/after128-continuous-plan.json')['batches']
    assert state['next_index']<=len(plan)
    queued=sum(len(read_json(root/item['jobs'])) for item in plan[state['next_index']:])
    if queued>=24:
        if not low_feedback_enabled(root):return {'prepared':False,'reason':'prepared_backlog_at_target','queued_requests':queued}
        priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
        if any(low_correction_in_item(root,item,priority) for item in plan[state['next_index']:]):
            return {'prepared':False,'reason':'prepared_LOW_correction_already_available','queued_requests':queued}
    if not (selector or ready_art)(root,expected_machine):return {'prepared':False,'reason':'no_current_allowed_manual_rejection','queued_requests':queued}
    index=len(plan);batch=owner['run_id']+'-batch'+str(index)
    run_checked(root,[sys.executable,'mod_nailong/tools/prepare_ready_art_reviews.py',batch,str(index),'--inbox'],runner)
    item=read_json(root/'runtime/after128-continuous-plan.json')['batches'][index]
    count=sum(validate_prepared(root,v) for v in read_json(root/'runtime/after128-continuous-plan.json')['batches'][index:])
    return {'prepared':True,'batch':batch,'index':index,'requests':count,'queued_before':queued,'scope':'Prepared by sole producer between imports; current window has not ended and reviewers continue independently.'}

def next_item(root,state,runner=None):
    no_calling(root)
    if (root/'runtime/rolling-production'/(state['run_id']+'-stop-requested.json')).exists():
        return {'ready':False,'stop_requested':True,'next_index':state['next_index']}
    merge_reviewed_retries(root,state['machine_id'],runner)
    if root==ROOT:
        from tools.production_prepare_boundary import run_boundary
        from mod_nailong.tools.production_queue import apply_reviews
        boundary=run_boundary(root,state['machine_id'],apply_reviews=apply_reviews)
        assert boundary.get('status')!='preparation_requires_reconciliation',boundary
    prioritize_high(root,state,runner)
    plan=read_json(root/'runtime/after128-continuous-plan.json')['batches'];index=state['next_index']
    assert index<=len(plan),'Logical cursor exceeds durable plan'
    if index<len(plan) and low_enabled(root):
        priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
        if not high_in_item(root,plan[index],priority):
            high=immediate_high_work(root,state['machine_id'])
            if high['available']:return {'ready':False,'reason':'awaiting_available_HIGH_supply','HIGH':high,'next_index':index}
    if index==len(plan):
        ready=ready_art(root,state['machine_id'])
        priority=read_json(root/'mod_nailong/data/production-priority.json')['sources'] if low_enabled(root) else None
        high_art=ready and (priority is None or any(priority[e['source_sha256']]['high_priority'] for _,e in ready))
        retry=None if high_art else allocate_exact_retry(root,state,runner)
        if not high_art and retry is None and not ready:
                checkpoint=checkpoint_when_idle(root,state,runner)
                return {'ready':False,'reason':'no_current_allowed_manual_rejection_prepared_job_or_exact_due_retry','next_index':index,'idle_checkpoint':checkpoint}
        if high_art or (retry is None and ready):
            batch=state['run_id']+'-batch'+str(index)
            command=[sys.executable,'mod_nailong/tools/prepare_ready_art_reviews.py',batch,str(index),'--inbox']
            run_checked(root,command,runner)
        plan=read_json(root/'runtime/after128-continuous-plan.json')['batches']
    item=dict(plan[index]);count=validate_prepared(root,item)
    request=root/'runtime/rolling-production'/(state['run_id']+'-checkpoint-requested.json')
    if request.exists():
        body=read_json(request);assert body['machine_id']==state['machine_id'] and body['run_id']==state['run_id']
        minimum=body.get('min_requests',1);assert isinstance(minimum,int) and 1<=minimum<=8
        if count>=minimum:
            item['checkpointCommand']='python tools\\production_checkpoint.py '+item['batch']+(' --force' if body.get('force') else '')
            request.rename(request.with_name(state['run_id']+'-checkpoint-claimed-'+str(index)+'.json'))
    return {'ready':True,'index':index,'window_id':state['run_id']+'-window'+str(index),'plan':[item],'requests':count}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['claim','next','complete','stop']);parser.add_argument('run_id');parser.add_argument('--index',type=int);parser.add_argument('--after');parser.add_argument('--reason');args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id)
    folder=ROOT/'runtime/rolling-production';path=folder/(args.run_id+'.json')
    if args.action=='claim':result=claim(ROOT,args.run_id,args.index,args.after,machine_id())
    else:
        owner=read_json(folder/'owner.json');state=read_json(path)
        assert owner=={'run_id':args.run_id,'machine_id':machine_id()} and state['status']=='running'
        if args.action=='next':result=next_item(ROOT,state)
        elif args.action=='complete':
            window=args.run_id+'-window'+str(state['next_index']);gate=inspect_window(ROOT,window,machine_id());assert gate['ready'],gate
            finish_exact_retry(ROOT,state)
            receipt=read_json(ROOT/gate['receipt']);state['completed_windows']+=1;state['completed_source_requests']+=receipt['planned_requests'];state['next_index']+=1;state['after_window']=window;state['updated_at_utc']=utc_now();write_json(path,state);result=state
        else:
            no_calling(ROOT)
            stop_request=folder/(args.run_id+'-stop-requested.json')
            if stop_request.exists():
                requested=read_json(stop_request);assert requested['machine_id']==machine_id() and requested['run_id']==args.run_id
                state['stop_request']=requested
            state.update(status='stopped_at_safe_boundary',reason=state.get('stop_request',{}).get('reason',args.reason),stopped_at_utc=utc_now());write_json(path,state)
            evidence=ROOT/f'mod_nailong/data/production-window-timings/{args.run_id}-logical-queue-completed.json';assert not evidence.exists();write_json(evidence,state)
            (folder/'owner.json').rename(folder/(args.run_id+'-released-owner.json'));result=state
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':main()
