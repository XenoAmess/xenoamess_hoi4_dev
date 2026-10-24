"""Coordinate built-in calls and SHA-bound reviews; never calls an image API.

Codex's single built-in generation worker imports images and applies decisions
between calls. The reviewer only stages small decisions while that worker runs.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools import portraits

def mod(): return ROOT/'mod_nailong'
def control(): return ROOT/'runtime/production-queue'
def journal(key):
    return read_json(mod()/f'data/generation-requests/{key}.json')['attempts'][-1]

@contextmanager
def short_guard(name):
    directory=control();directory.mkdir(parents=True,exist_ok=True)
    lock=directory/(name+'.lock');deadline=time.monotonic()+2
    while True:
        try:
            fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd);break
        except FileExistsError:
            if time.monotonic()>=deadline: raise RuntimeError(f'Guard busy; inspect before recovery: {lock}')
            time.sleep(.02)
    try: yield
    finally: lock.unlink()

def export_job(jobs_file,key):
    # ASCII JSON survives Windows CP936 stdout followed by UTF-8 transport.
    # JSON.parse restores the exact Unicode prompt, never replacement characters.
    job=next(j for j in read_json(Path(jobs_file)) if j['key']==key)
    return json.dumps(job,ensure_ascii=True)

def attempt_for_snapshot(key, actual_job_file):
    """Equal payloads on separate retries need distinct dispatch identities."""
    actual=Path(actual_job_file).resolve();digest=file_sha256(actual)
    history=read_json(mod()/f'data/generation-requests/{key}.json')
    matches=[]
    for attempt in history['attempts']:
        path=control()/f'dispatch/{key}-{attempt["number"]:03}.json'
        if not path.exists():continue
        dispatch=read_json(path)
        snapshot=dispatch.get('actual_request_snapshot_file')
        if not snapshot or Path(snapshot).resolve()!=actual:continue
        if dispatch.get('actual_request_snapshot_sha256')!=digest:raise ValueError('Dispatch snapshot bytes changed')
        proof=attempt.get('actual_request_verification',{})
        if proof.get('actual_request_snapshot_sha256')!=digest or proof.get('machine_id')!=dispatch.get('machine_id'):raise ValueError('Attempt verification does not match its actual dispatch')
        if dispatch.get('attempt_number')!=attempt['number'] or dispatch.get('source_sha256')!=key:raise ValueError('Dispatch source/attempt identity changed')
        matches.append(attempt)
    if len(matches)!=1:raise ValueError('Expected one uniquely dispatched attempt for this snapshot path')
    return matches[0]

def begin(job,actual_job_file=None):
    key=job['key'];a=journal(key)
    if a['status']!='prepared': raise ValueError('Request is not prepared; do not call imagegen again')
    if job['prompt']!=a['prompt'] or file_sha256(ROOT/a['prompt_file'])!=a['prompt_sha256']:
        raise ValueError('Frozen prompt changed')
    if len(job['references'])!=len(a['inputs']): raise ValueError('Input count changed')
    for path,ref in zip(job['references'],a['inputs']):
        if file_sha256(Path(path))!=ref.get('sha256',ref.get('converted_png_sha256')):
            raise ValueError('Frozen input changed')
    directory=control()/'dispatch';directory.mkdir(parents=True,exist_ok=True)
    path=directory/f'{key}-{a["number"]:03}.json'
    with short_guard('dispatch'):
        if path.exists(): raise ValueError('Call already claimed; reconcile its actual result, never regenerate blindly')
        if any(read_json(p)['status']=='calling' for p in directory.glob('*.json')):
            raise ValueError('Another built-in call is still active or has an unknown outcome')
        record={'source_sha256':key,'attempt_number':a['number'],'machine_id':machine_id(),'status':'calling','call_started_at_utc':utc_now(),'prompt_sha256':a['prompt_sha256'],'input_sha256':[file_sha256(Path(p)) for p in job['references']]}
        if actual_job_file:
            actual_job_file=Path(actual_job_file)
            if read_json(actual_job_file)!=job:raise ValueError('Actual request snapshot changed')
            record.update(actual_request_snapshot_file=str(actual_job_file.resolve()),actual_request_snapshot_sha256=file_sha256(actual_job_file),actual_prompt_verified_before_call=True)
        with path.open('x',encoding='utf-8',newline='\n') as stream:
            json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
        if actual_job_file:
            journal_path=mod()/f'data/generation-requests/{key}.json'
            history=read_json(journal_path)
            if history['attempts'][-1]['number']!=a['number']:raise ValueError('Request changed during dispatch verification')
            history['attempts'][-1]['actual_request_verification']={'machine_id':record['machine_id'],'verified_at_utc':record['call_started_at_utc'],'actual_recorded_before_call':True,'actual_request_snapshot_sha256':record['actual_request_snapshot_sha256'],'prompt_sha256':a['prompt_sha256'],'input_sha256':record['input_sha256'],'transparent_background':job.get('transparent',False)}
            write_json(journal_path,history)
    return path

def returned(key,image=None,error_file=None):
    a=journal(key);path=control()/f'dispatch/{key}-{a["number"]:03}.json'
    record=read_json(path)
    if record['status']!='calling': raise ValueError('Call result already recorded')
    if bool(image)==bool(error_file): raise ValueError('Provide one actual image or actual tool error')
    record.update(status='returned_image' if image else 'tool_error',call_returned_at_utc=utc_now())
    record['call_interval_seconds_including_tool_transport']=(datetime.fromisoformat(record['call_returned_at_utc'])-datetime.fromisoformat(record['call_started_at_utc'])).total_seconds()
    if image:record.update(returned_image=str(Path(image).resolve()),returned_image_sha256=file_sha256(Path(image)))
    else:record.update(actual_error_file=str(Path(error_file).resolve()),actual_error_sha256=file_sha256(Path(error_file)))
    write_json(path,record)

def stage_review(key,image_sha,decision,evidence_file,reason=''):
    if decision not in {'approved','rejected'}:raise ValueError('Invalid visual decision')
    row=read_json(mod()/'data/generated.json')['portraits'][key];a=journal(key)
    if row['image_sha256']!=image_sha or file_sha256(ROOT/row['image'])!=image_sha or a.get('output_sha256')!=image_sha:
        raise ValueError('Reviewed image changed or latest request is not bound to it')
    evidence_file=Path(evidence_file);evidence=read_json(evidence_file)
    matches=[(p,e) for p in evidence['pages'] for e in p['entries'] if e['source_sha256']==key and e['image_sha256']==image_sha]
    if len(matches)!=1:raise ValueError('Review evidence does not bind this exact image')
    page,entry=matches[0]
    fullsize_sha=entry.get('generated_fullsize_sha256')
    if entry.get('attempt_number') is not None and entry['attempt_number']!=a['number']:
        raise ValueError('Reviewed request attempt changed')
    if fullsize_sha and (row.get('generated_fullsize_sha256')!=fullsize_sha or a.get('fullsize_sha256')!=fullsize_sha or not row.get('generated_fullsize_image') or file_sha256(ROOT/row['generated_fullsize_image'])!=fullsize_sha):
        raise ValueError('Reviewed fullsize image changed')
    if file_sha256(Path(page['path']))!=page['sha256']:raise ValueError('Reviewed contact sheet changed')
    path=control()/f'reviews/pending/{key}-{image_sha}.json';path.parent.mkdir(parents=True,exist_ok=True)
    record={'source_sha256':key,'image_sha256':image_sha,'attempt_number':a['number'],'decision':decision,'reason':reason,'machine_id':machine_id(),'reviewed_and_staged_at_utc':utc_now(),'review_evidence_sha256':file_sha256(evidence_file),'review_page_sha256':page['sha256'],'reviewer':'Codex actual manual comparison; staging itself is not automatic visual approval'}
    if fullsize_sha:record['generated_fullsize_sha256']=fullsize_sha
    if path.exists():
        old=read_json(path)
        if any(old[f]!=record[f] for f in ['source_sha256','image_sha256','attempt_number','decision','reason']):raise ValueError('Conflicting pending review')
        return path
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
    return path

def _review_matches(row,a,decision):
    valid=(row.get('image_sha256')==decision['image_sha256'] and a['number']==decision['attempt_number'] and a.get('output_sha256')==decision['image_sha256'] and file_sha256(ROOT/row['image'])==decision['image_sha256'])
    if valid and decision.get('generated_fullsize_sha256'):
        fullsize=decision['generated_fullsize_sha256']
        valid=(row.get('generated_fullsize_sha256')==fullsize and a.get('fullsize_sha256')==fullsize and bool(row.get('generated_fullsize_image')) and file_sha256(ROOT/row['generated_fullsize_image'])==fullsize)
    return valid

def _finish_review(path,completed,decision):
    target=completed/path.name
    if target.exists():
        # A later policy may legitimately re-review the same unchanged output.
        # Keep the exact earlier application bytes before advancing its pointer.
        old_sha=file_sha256(target)
        archive=mod()/'data/production-review-application-history'/(old_sha+'.json')
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists():
            assert file_sha256(archive)==old_sha,'Review application archive changed'
        else:
            shutil.copyfile(target,archive)
            assert file_sha256(archive)==old_sha
    write_json(target,decision);path.unlink()

def _apply_reviews_in_order():
    # Only the generation worker calls this between import and the next call.
    pending=control()/'reviews/pending';completed=control()/'reviews/completed';completed.mkdir(parents=True,exist_ok=True)
    applied=stale=0
    with short_guard('review-apply'):
        for path in sorted(pending.glob('*.json')):
            decision=read_json(path);key=decision['source_sha256']
            row=read_json(mod()/'data/generated.json')['portraits'].get(key,{})
            a=journal(key)
            valid=_review_matches(row,a,decision)
            if not valid:
                decision['application']='stale_not_applied';stale+=1
            else:
                if decision['decision']=='approved':
                    if row.get('review')!='approved':portraits.approve([key])
                elif row.get('review')!='rejected' or row.get('review_reason')!=decision['reason']:
                    portraits.reject([key],decision['reason'])
                decision['application']='applied';applied+=1
            decision['applied_or_rejected_at_utc']=utc_now()
            _finish_review(path,completed,decision)
    return {'applied':applied,'stale_not_applied':stale}

def apply_reviews():
    # One executor, between imports/calls. Group independent manual approvals
    # so coverage/index work is performed once rather than once per portrait.
    pending=control()/'reviews/pending';completed=control()/'reviews/completed'
    paths=sorted(pending.glob('*.json'))
    if not paths:return {'applied':0,'stale_not_applied':0}
    decisions=[read_json(path) for path in paths]
    keys=[d['source_sha256'] for d in decisions]
    if len(set(keys))!=len(keys):
        return _apply_reviews_in_order()  # Preserve ordering across source versions.
    applied=stale=0;completed.mkdir(parents=True,exist_ok=True)
    with short_guard('review-apply'):
        rows=read_json(mod()/'data/generated.json')['portraits'];plans=[];approvals=[]
        for path,decision in zip(paths,decisions,strict=True):
            key=decision['source_sha256'];row=rows.get(key,{})
            valid=_review_matches(row,journal(key),decision)
            plans.append((path,decision,row,valid))
            if valid and decision['decision']=='approved' and row.get('review')!='approved':approvals.append(key)
        if approvals:portraits.approve(approvals)
        for path,decision,row,valid in plans:
            if valid:
                if decision['decision']=='rejected' and (row.get('review')!='rejected' or row.get('review_reason')!=decision['reason']):
                    portraits.reject([decision['source_sha256']],decision['reason'])
                decision['application']='applied';applied+=1
            else:decision['application']='stale_not_applied';stale+=1
            decision['applied_or_rejected_at_utc']=utc_now()
            _finish_review(path,completed,decision)
    return {'applied':applied,'stale_not_applied':stale}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['export-job','begin','returned','review','apply-reviews']);p.add_argument('--key');p.add_argument('--jobs-file',type=Path);p.add_argument('--actual-job-file',type=Path);p.add_argument('--image',type=Path);p.add_argument('--error-file',type=Path);p.add_argument('--image-sha');p.add_argument('--decision',choices=['approved','rejected']);p.add_argument('--evidence-file',type=Path);p.add_argument('--reason',default='')
    args=p.parse_args()
    if args.command=='export-job':print(export_job(args.jobs_file,args.key))
    elif args.command=='begin':
        if not args.actual_job_file:raise SystemExit('Freeze the exact JS worker request to --actual-job-file before dispatch; a source job file alone cannot verify transported text')
        j=read_json(args.actual_job_file)
        if args.key and args.key!=j['key']:raise SystemExit('Actual request source key differs')
        begin(j,args.actual_job_file);print('CALL_STARTED',j['key'])
    elif args.command=='returned':returned(args.key,args.image,args.error_file)
    elif args.command=='review':stage_review(args.key,args.image_sha,args.decision,args.evidence_file,args.reason);print('Queued SHA-bound review',args.key)
    else:
        result=apply_reviews()
        if result['applied'] or result['stale_not_applied']:print(result)

if __name__=='__main__':main()
