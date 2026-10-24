"""Append-only, SHA-bound manual review inbox; never mutates portrait state."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now

def report_path(name,root=ROOT):
    if Path(name).name!=name or '/' in name or '\\' in name or not name.endswith('.json'):
        raise ValueError('Review must be a single JSON filename under mod data')
    return root/'mod_nailong/data'/name

def inbox_dir(batch,root=ROOT):
    if not batch or not batch.replace('-','').isalnum():raise ValueError('Invalid explicit batch identity')
    return root/'runtime/ready-art-inbox'/batch

def enqueue(batch,name,root=ROOT):
    path=report_path(name,root);body=read_json(path)
    if body.get('machine_id')!=machine_id() or body.get('decisions_staged') is not True:
        raise ValueError('Only completed same-machine staged manual reviews may enter inbox')
    digest=file_sha256(path);ticket=inbox_dir(batch,root)/(digest+'.json')
    value={'machine_id':machine_id(),'queued_at_utc':utc_now(),'batch':batch,'report':name,'sha256':digest,'scope':'Actual completed manual report pointer only; producer retains current-SHA, request-boundary, HIGH, cooldown and full input/prompt checks.'}
    if ticket.exists():
        old=read_json(ticket)
        assert old['batch']==batch and old['report']==name and old['sha256']==digest
    else:write_json(ticket,value)
    return ticket

def reports(batch,root=ROOT):
    result=[]
    for ticket in sorted(inbox_dir(batch,root).glob('*.json')):
        body=read_json(ticket)
        if body.get('machine_id')!=machine_id() or body.get('batch')!=batch:raise ValueError('Inbox identity mismatch')
        path=report_path(body['report'],root)
        if file_sha256(path)!=body['sha256']:raise ValueError('Manual report bytes changed after queueing')
        result.append((path,{'path':ticket.relative_to(root).as_posix(),'sha256':file_sha256(ticket),'report':body['report'],'report_sha256':body['sha256']}))
    return result

def independent_art_holds(root=ROOT):
    """Explicit per-source art investigation; no service cooldown is changed."""
    held=set()
    for path in (root/'mod_nailong/data/independent-art-tasks').glob('*.json'):
        body=read_json(path)
        if body.get('schema')=='naiwa-independent-art-hold-v1' and body.get('status')=='pending_independent_method':
            assert body['machine_id']==machine_id() and len(body['source_sha256'])==64
            held.add(body['source_sha256'])
    return held

if __name__=='__main__':
    batch,name=sys.argv[1:]
    print(enqueue(batch,name))
