"""Two persistent review slots with SHA reservations; never mutate canonical portraits."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now

ALPHA_POLICY='visible-alpha-v1'
SOURCE_POLICY='visible-source-differences-v1'

def source_policy(root):
    path=root/'mod_nailong/data/source-feature-acceptance-policy.json'
    if not path.exists():return None
    policy=read_json(path);assert policy['id']==SOURCE_POLICY
    return policy

def source_reopenings(policy):
    return {(e['source_sha256'],e['generated_fullsize_sha256']) for e in policy.get('reopen_current_pending',[])} if policy else set()

def reviewed_outputs(root):
    """Reopen alpha decisions and explicitly scoped source-detail pending SHAs."""
    policy=read_json(root/'mod_nailong/data/alpha-acceptance-policy.json')
    assert policy['id']==ALPHA_POLICY
    feature_policy=source_policy(root);feature_reopenings=source_reopenings(feature_policy)
    seen=set()
    for p in (root/'mod_nailong/data').glob('resumed-*review.json'):
        report=read_json(p)
        for e in report.get('decisions',[]):
            pair=(e.get('source_sha256'),e.get('generated_fullsize_sha256'))
            if e.get('decision')=='pending' and pair in feature_reopenings and report.get('reviewed_at_utc','')<feature_policy['effective_from_utc']:continue
            if e.get('decision') not in {'pending','rejected'} or report.get('reviewed_at_utc','')>=policy['effective_from_utc']:
                seen.add(pair)
    for p in (root/'runtime/production-queue/reviews/pending').glob('*.json'):
        e=read_json(p);seen.add((e.get('source_sha256'),e.get('generated_fullsize_sha256',e.get('image_sha256'))))
    return seen

def reserve_candidates(root,rows,priority,seen,slot,limit=4,deferred=None):
    folder=root/'runtime/rolling-review-queue';feature_policy=source_policy(root);feature_reopenings=source_reopenings(feature_policy)
    assets={a['source_sha256']:a for a in read_json(root/'mod_nailong/data/catalog.json')['assets']};jobs=[]
    # One slot returns new production feedback promptly; the other drains older
    # pending work. Both still reserve exact current SHAs under the same lock.
    ordered=sorted(rows.items(),key=lambda item:item[1].get('imported_at_utc',''),reverse=slot=='a')
    for key,row in ordered:
        digest=row.get('generated_fullsize_sha256')
        if row.get('review') not in {'pending','rejected'} or not priority[key]['high_priority'] or not digest or (key,digest) in seen:continue
        missing=[field for field in ('request_journal','prompt') if not isinstance(row.get(field),str) or not row[field]]
        if missing:
            # Import publishes portrait pixels before attaching all request metadata.
            # Do not reserve the incomplete snapshot or stop unrelated review work.
            if deferred is not None:deferred.append({'source_sha256':key,'generated_fullsize_sha256':digest,'missing':missing})
            continue
        history=read_json(root/row['request_journal']);latest=history['attempts'][-1]
        expected_status='generated_pending_visual_review' if row['review']=='pending' else 'generated_rejected_visual_review'
        if latest['status']!=expected_status or latest.get('fullsize_sha256')!=digest:continue
        namespace='source-diff-v1' if row['review']=='pending' and (key,digest) in feature_reopenings else ALPHA_POLICY
        reservations=folder/'reservations'/namespace;reservations.mkdir(parents=True,exist_ok=True)
        reservation=reservations/(key+'-'+digest+'.json')
        try:fd=os.open(reservation,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
        except FileExistsError:continue
        reservation_record={'slot':slot,'machine_id':machine_id(),'acceptance_policy':ALPHA_POLICY,'source_sha256':key,'generated_fullsize_sha256':digest,'reserved_at_utc':utc_now()}
        if namespace=='source-diff-v1':reservation_record['source_feature_acceptance_policy']=SOURCE_POLICY
        with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(reservation_record,stream)
        job={'key':key,'source':assets[key]['path'],'original':str(root/'runtime/references'/(key+'.png')),'prompt':row['prompt']}
        if row['review']=='rejected':job['prior_review_reason']=row.get('review_reason','')[-2000:]
        jobs.append(job)
        if len(jobs)==limit:break
    return jobs

def claim(slot):
    assert slot in {'a','b'}
    stop=ROOT/'runtime/rolling-review-queue/handoff-stop.json'
    if stop.exists():
        return {'ready':False,'stop_requested':True,'slot':slot,'allocation_claimed':False,'reason':'user_requested_handoff','next_step':'The user requested vacation handoff. Stop all polling/review writes, do not create a successor, inform root and end. Preserve allocations/reservations and this stop record for explicit resume reconciliation.'}
    if not (ROOT/'mod_nailong/data/alpha-acceptance-policy.json').is_file():
        return {'ready':False,'reason':'acceptance_policy_record_not_available','slot':slot,'allocation_claimed':False}
    folder=ROOT/'runtime/rolling-review-queue';folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'allocation.lock';fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    try:
        statepath=folder/('slot-'+slot+'.json')
        state=read_json(statepath) if statepath.exists() else {'slot':slot,'sequence':0,'status':'available'}
        assert state['status']=='available','Prior assignment must be finalized, not silently repeated'
        rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits'];priority=read_json(ROOT/'mod_nailong/data/production-priority.json')['sources'];seen=reviewed_outputs(ROOT)
        deferred=[];jobs=reserve_candidates(ROOT,rows,priority,seen,slot,deferred=deferred)
        if not jobs:return {'ready':False,'reason':'current_output_metadata_not_yet_complete' if deferred else 'no_unassigned_current_HIGH_output','slot':slot,'metadata_deferred':deferred,'next_step':'Read the newly updated tools/portrait_review_worker.md BEFORE another wait: exact-retry-cooling-slot-SLOT-20261024-v1-candidates.json now has4/a and3/b complete requests for advance manual review during cooling. No invoke/claim/merge. After that finite group hand over the same slot. Continue fresh-source checks before portrait claims, exactly2 slots.'}
        sequence=state['sequence']+1;tag='rolling'+slot+str(sequence);jobpath=ROOT/f'runtime/fine-review4-{tag}-20261024-jobs.json';assert not jobpath.exists();write_json(jobpath,jobs)
        out=ROOT/f'runtime/resumed-20261024-fine-{tag}-alpha'
        result=subprocess.run([sys.executable,'mod_nailong/tools/review_alpha_sheet.py',jobpath.relative_to(ROOT).as_posix(),out.relative_to(ROOT).as_posix(),'--include-rejected'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        assert result.returncode==0,result.stderr
        state={'machine_id':machine_id(),'acceptance_policy':ALPHA_POLICY,'slot':slot,'sequence':sequence,'tag':tag,'status':'assigned','claimed_at_utc':utc_now(),'jobs':jobpath.relative_to(ROOT).as_posix(),'manifest':(out/'manifest.json').relative_to(ROOT).as_posix(),'manifest_sha256':file_sha256(out/'manifest.json'),'config':f'runtime/stage-{tag}-20261024.json','report':f'mod_nailong/data/resumed-20261024-{tag}-agent-review.json','source_keys':[j['key'] for j in jobs]}
        feature_policy=source_policy(ROOT)
        if feature_policy:
            state['source_feature_acceptance_policy']=SOURCE_POLICY
            state['source_feature_policy_sha256']=file_sha256(ROOT/'mod_nailong/data/source-feature-acceptance-policy.json')
            state['review_instruction']='User now confirms visible source differences with uncertain low-resolution details recorded. Read the updated worker instructions and source-feature-acceptance-policy.json BEFORE reviewing. Do not hold solely for genuinely unreadable tiny source features; do reject clearly visible differences. No automatic approvals.'
        state['prior_rejections']=[{'source_sha256':j['key'],'reason':j['prior_review_reason']} for j in jobs if 'prior_review_reason' in j]
        if state['prior_rejections']:state['review_instruction']=state.get('review_instruction','')+' Read the current worker instructions. Reconcile each prior visible finding against the exact source/current raw before approval; visible-alpha-v1 does not waive pose, hair, outfit, note or backing defects. Address a conflicting old non-alpha finding explicitly in the decision.'
        write_json(statepath,state);return {'ready':True,**state}
    finally:os.close(fd);lock.unlink()

def complete(slot,report):
    folder=ROOT/'runtime/rolling-review-queue';path=folder/('slot-'+slot+'.json');state=read_json(path)
    assert state['status']=='assigned' and state['report']==report
    p=ROOT/report;b=read_json(p);assert b['machine_id']==machine_id() and b['decisions_staged']
    assert {e['source_sha256'] for e in b['decisions']}==set(state['source_keys'])
    manifest=read_json(ROOT/state['manifest']);bound={e['source_sha256']:e['generated_fullsize_sha256'] for page in manifest['pages'] for e in page['entries']}
    assert all(e['generated_fullsize_sha256']==bound[e['source_sha256']] for e in b['decisions'])
    receipt=ROOT/f'mod_nailong/data/production-review-slot-completions/{state["tag"]}.json';assert not receipt.exists();write_json(receipt,{**state,'status':'reviewed_and_staged','completed_at_utc':utc_now(),'report_sha256':file_sha256(p)})
    write_json(path,{'slot':slot,'sequence':state['sequence'],'status':'available','last_report':report,'completed_at_utc':utc_now()})
    return {'completed':True,'slot':slot,'next_sequence':state['sequence']+1}

def wait_for_claim(slot,wait_seconds,allocator=None,clock=None,sleeper=None):
    allocator=allocator or claim;clock=clock or time.monotonic;sleeper=sleeper or time.sleep
    deadline=clock()+wait_seconds
    while True:
        try:result=allocator(slot)
        except FileExistsError:
            if clock()>=deadline:return {'ready':False,'reason':'another_review_allocation_owns_lock','slot':slot,'allocation_claimed':False}
            sleeper(1);continue
        if result.get('ready',True) or result.get('stop_requested') or clock()>=deadline:return result
        sleeper(5)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['claim','complete']);parser.add_argument('slot',choices=['a','b']);parser.add_argument('--report');parser.add_argument('--wait-seconds',type=int,default=0);args=parser.parse_args();assert 0<=args.wait_seconds<=50
    result=wait_for_claim(args.slot,args.wait_seconds) if args.action=='claim' else complete(args.slot,args.report)
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':main()
