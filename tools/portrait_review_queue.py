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

def reviewed_outputs(root):
    """A changed acceptance rule reopens old pending decisions, never approvals."""
    policy=read_json(root/'mod_nailong/data/alpha-acceptance-policy.json')
    assert policy['id']==ALPHA_POLICY
    seen=set()
    for p in (root/'mod_nailong/data').glob('resumed-*review.json'):
        report=read_json(p)
        for e in report.get('decisions',[]):
            if e.get('decision')!='pending' or report.get('reviewed_at_utc','')>=policy['effective_from_utc']:
                seen.add((e.get('source_sha256'),e.get('generated_fullsize_sha256')))
    for p in (root/'runtime/production-queue/reviews/pending').glob('*.json'):
        e=read_json(p);seen.add((e.get('source_sha256'),e.get('generated_fullsize_sha256',e.get('image_sha256'))))
    return seen

def reserve_candidates(root,rows,priority,seen,slot,limit=4,deferred=None):
    folder=root/'runtime/rolling-review-queue';reservations=folder/'reservations'/ALPHA_POLICY;reservations.mkdir(parents=True,exist_ok=True)
    assets={a['source_sha256']:a for a in read_json(root/'mod_nailong/data/catalog.json')['assets']};jobs=[]
    # One slot returns new production feedback promptly; the other drains older
    # pending work. Both still reserve exact current SHAs under the same lock.
    ordered=sorted(rows.items(),key=lambda item:item[1].get('imported_at_utc',''),reverse=slot=='a')
    for key,row in ordered:
        digest=row.get('generated_fullsize_sha256')
        if row.get('review')!='pending' or not priority[key]['high_priority'] or not digest or (key,digest) in seen:continue
        missing=[field for field in ('request_journal','prompt') if not isinstance(row.get(field),str) or not row[field]]
        if missing:
            # Import publishes portrait pixels before attaching all request metadata.
            # Do not reserve the incomplete snapshot or stop unrelated review work.
            if deferred is not None:deferred.append({'source_sha256':key,'generated_fullsize_sha256':digest,'missing':missing})
            continue
        history=read_json(root/row['request_journal']);latest=history['attempts'][-1]
        if latest['status']!='generated_pending_visual_review' or latest.get('fullsize_sha256')!=digest:continue
        reservation=reservations/(key+'-'+digest+'.json')
        try:fd=os.open(reservation,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
        except FileExistsError:continue
        with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump({'slot':slot,'machine_id':machine_id(),'acceptance_policy':ALPHA_POLICY,'source_sha256':key,'generated_fullsize_sha256':digest,'reserved_at_utc':utc_now()},stream)
        jobs.append({'key':key,'source':assets[key]['path'],'original':str(root/'runtime/references'/(key+'.png')),'prompt':row['prompt']})
        if len(jobs)==limit:break
    return jobs

def claim(slot):
    assert slot in {'a','b'}
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
        if not jobs:return {'ready':False,'reason':'current_output_metadata_not_yet_complete' if deferred else 'no_unassigned_current_HIGH_output','slot':slot,'metadata_deferred':deferred,'next_step':'Read the updated tools/portrait_review_worker.md before waiting again; it now checks fresh_source_observation_queue.py claim SLOT before each portrait claim, including idle loops. Resume an existing fresh allocation if returned. Keep exactly the same two slots.'}
        sequence=state['sequence']+1;tag='rolling'+slot+str(sequence);jobpath=ROOT/f'runtime/fine-review4-{tag}-20261024-jobs.json';assert not jobpath.exists();write_json(jobpath,jobs)
        out=ROOT/f'runtime/resumed-20261024-fine-{tag}-alpha'
        result=subprocess.run([sys.executable,'mod_nailong/tools/review_alpha_sheet.py',jobpath.relative_to(ROOT).as_posix(),out.relative_to(ROOT).as_posix()],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        assert result.returncode==0,result.stderr
        state={'machine_id':machine_id(),'acceptance_policy':ALPHA_POLICY,'slot':slot,'sequence':sequence,'tag':tag,'status':'assigned','claimed_at_utc':utc_now(),'jobs':jobpath.relative_to(ROOT).as_posix(),'manifest':(out/'manifest.json').relative_to(ROOT).as_posix(),'manifest_sha256':file_sha256(out/'manifest.json'),'config':f'runtime/stage-{tag}-20261024.json','report':f'mod_nailong/data/resumed-20261024-{tag}-agent-review.json','source_keys':[j['key'] for j in jobs]}
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
        if result.get('ready',True) or clock()>=deadline:return result
        sleeper(5)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['claim','complete']);parser.add_argument('slot',choices=['a','b']);parser.add_argument('--report');parser.add_argument('--wait-seconds',type=int,default=0);args=parser.parse_args();assert 0<=args.wait_seconds<=50
    result=wait_for_claim(args.slot,args.wait_seconds) if args.action=='claim' else complete(args.slot,args.report)
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':main()
