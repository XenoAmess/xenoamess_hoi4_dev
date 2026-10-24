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
from mod_nailong.tools.ready_art_reports import reports as inbox_reports
from mod_nailong.tools.prepare_ready_art_reviews import eligible_entries,service_held_keys

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

def allocate_exact_retry(root,state,runner=None):
    """Only the persistent producer selects and claims unchanged, reviewed retries."""
    scheduler=root/'runtime/retry-scheduler/state.json'
    if not scheduler.exists():return None
    before=read_json(scheduler)
    assert before['machine_id']==state['machine_id'] and before['pending'] is None,'Pending retry batch requires explicit reconciliation'
    command=[sys.executable,'tools/retry_scheduler_next.py','--limit','8']
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
    assert len(plan['batches'])==state['next_index'],'Queue changed during sole-owner retry claim'
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

def next_item(root,state,runner=None):
    no_calling(root)
    if (root/'runtime/rolling-production'/(state['run_id']+'-stop-requested.json')).exists():
        return {'ready':False,'stop_requested':True,'next_index':state['next_index']}
    if root==ROOT:
        from tools.production_prepare_boundary import run_boundary
        from mod_nailong.tools.production_queue import apply_reviews
        boundary=run_boundary(root,state['machine_id'],apply_reviews=apply_reviews)
        assert boundary.get('status')!='preparation_requires_reconciliation',boundary
    plan=read_json(root/'runtime/after128-continuous-plan.json')['batches'];index=state['next_index']
    assert index<=len(plan),'Logical cursor exceeds durable plan'
    if index==len(plan):
        inbox=inbox_reports('global');reports=[(p,read_json(p)) for p,_ in inbox]
        rows=read_json(root/'mod_nailong/data/generated.json')['portraits'];latest={}
        for _,body in reports:
            assert body.get('machine_id')==state['machine_id'] and body.get('decisions_staged')
            for e in body.get('decisions',[]):
                key=e.get('source_sha256')
                if e.get('decision')=='rejected' and key in rows:latest[key]=read_json(root/rows[key]['request_journal'])['attempts'][-1]
        priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
        failures=read_json(root/'mod_nailong/data/generation-failures.json')['attempts']
        held=service_held_keys(latest,priority,failures)
        ready=eligible_entries(reports,rows,latest,held)
        if not ready:
            if allocate_exact_retry(root,state,runner) is None:
                return {'ready':False,'reason':'no_current_allowed_manual_rejection_prepared_job_or_exact_due_retry','next_index':index}
        else:
            batch=state['run_id']+'-batch'+str(index)
            command=[sys.executable,'mod_nailong/tools/prepare_ready_art_reviews.py',batch,str(index),'--inbox']
            run_checked(root,command,runner)
        plan=read_json(root/'runtime/after128-continuous-plan.json')['batches']
    item=dict(plan[index]);count=validate_prepared(root,item)
    request=root/'runtime/rolling-production'/(state['run_id']+'-checkpoint-requested.json')
    if request.exists():
        body=read_json(request);assert body['machine_id']==state['machine_id'] and body['run_id']==state['run_id']
        item['checkpointCommand']='python tools\\production_checkpoint.py '+item['batch']
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
            no_calling(ROOT);state.update(status='stopped_at_safe_boundary',reason=args.reason,stopped_at_utc=utc_now());write_json(path,state)
            evidence=ROOT/f'mod_nailong/data/production-window-timings/{args.run_id}-logical-queue-completed.json';assert not evidence.exists();write_json(evidence,state)
            (folder/'owner.json').rename(folder/(args.run_id+'-released-owner.json'));result=state
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':main()
