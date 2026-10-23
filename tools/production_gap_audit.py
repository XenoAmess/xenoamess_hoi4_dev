"""Read existing production ledgers to measure preparation and dispatch gaps."""
import argparse,json,statistics,math,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,machine_id
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--start',required=True,help='First local date, YYYY-MM-DD')
parser.add_argument('--end',required=True,help='Exclusive ISO8601 cutoff with UTC offset')
parser.add_argument('--machine-id',default=machine_id())
parser.add_argument('--output',required=True,help='New report; existing files are never overwritten')
args=parser.parse_args()

U=timezone.utc;L=timezone(timedelta(hours=8));machine=args.machine_id
def dt(v):return datetime.fromisoformat(v.replace('Z','+00:00')) if v else None
def iso(t):return t.astimezone(L).isoformat()
def stats(v):
 v=sorted(v);return {'n':len(v),'median':round(statistics.median(v),3) if v else None,'mean':round(statistics.mean(v),3) if v else None,'p90':round(v[math.ceil(len(v)*.9)-1],3) if v else None,'sum':round(sum(v),3)}
cache={};rows=[]
for p in (ROOT/'runtime/production-queue/dispatch').glob('*.json'):
 r=json.loads(p.read_text(encoding='utf-8'))
 if r.get('machine_id')!=machine:continue
 key=r['source_sha256']
 if key not in cache:
  j=json.loads((ROOT/'mod_nailong/data/generation-requests'/(key+'.json')).read_text(encoding='utf-8'))
  cache[key]={a['number']:a for a in j['attempts']}
 a=cache[key][r['attempt_number']]
 r.update(start=dt(r['call_started_at_utc']),end=dt(r.get('call_returned_at_utc')),prepared=dt(a.get('prepared_at_utc')),imported=dt(a.get('generated_at_utc') or a.get('failed_at_utc')),edit_existing=a.get('edit_existing'),ledger=p.relative_to(ROOT).as_posix())
 r['batch']=Path(r.get('actual_request_snapshot_file','')).stem.removesuffix('-'+key)
 rows.append(r)
rows.sort(key=lambda r:r['start'])
checkpoints=[]
for p in (ROOT/'runtime').glob('checkpoint-*.json'):
 try:r=json.loads(p.read_text(encoding='utf-8'))
 except (ValueError,OSError):continue
 if r.get('machine_id')!=machine or not r.get('started_at_utc') or not r.get('local_commit_completed_at_utc'):continue
 a,b=dt(r['started_at_utc']),dt(r['local_commit_completed_at_utc'])
 checkpoints.append({'start':a,'end':b,'seconds':(b-a).total_seconds(),'batch':r.get('inflight_batch'),'receipt':p.relative_to(ROOT).as_posix()})
def union_seconds(spans):
 spans=sorted((a,b) for a,b in spans if b>a);merged=[]
 for a,b in spans:
  if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
  else:merged.append((a,b))
 return sum((b-a).total_seconds() for a,b in merged)
days=[];gaps=[]
cutoff=dt(args.end)
assert cutoff.tzinfo is not None, 'Cutoff requires an explicit UTC offset'
local_date=datetime.fromisoformat(args.start).replace(tzinfo=L)
assert local_date<cutoff
windows=[]
while local_date<cutoff:
 windows.append((local_date.date().isoformat(),min(local_date+timedelta(days=1),cutoff).isoformat()))
 local_date+=timedelta(days=1)
for date,endlocal in windows:
 begin=dt(date+'T00:00:00+08:00');end=dt(endlocal);selected=[r for r in rows if begin<=r['start']<end]
 batches=Counter(r['batch'] for r in selected);cross=[];inside=[];parts=[]
 for x,y in zip(rows,rows[1:]):
  if not x['end'] or not(begin<=y['start']<end):continue
  a=max(begin,x['end']);b=min(end,y['start']);s=max(0,(b-a).total_seconds())
  if x['batch']==y['batch']:inside.append(s);continue
  cross.append(s)
  prep=y['prepared'];ready_at=max(a,prep) if prep else None
  imported=x['imported'];localoverlap=union_seconds([(max(a,c['start']),min(b,c['end'])) for c in checkpoints])
  import_overlap=max(0,(min(b,imported)-a).total_seconds()) if imported else None
  g={'date':date,'gap_seconds':round(s,3),'gap_start_local':iso(a),'next_dispatch_local':iso(b),'previous_batch':x['batch'],'next_batch':y['batch'],'next_first_request_prepared_local':iso(prep) if prep else None,'next_first_request_prepared_after_previous_return':bool(prep and prep>a),'seconds_before_next_first_request_prepared':round(max(0,(min(b,prep)-a).total_seconds()),3) if prep else None,'seconds_ready_but_not_dispatched':round(max(0,(b-max(a,prep)).total_seconds()),3) if prep else None,'previous_last_return_to_import_overlap_seconds':round(import_overlap,3) if import_overlap is not None else None,'local_checkpoint_overlap_seconds':round(localoverlap,3),'previous_dispatch_ledger':x['ledger'],'next_dispatch_ledger':y['ledger']}
  gaps.append(g);parts.append(g)
 success=[(r['end']-r['start']).total_seconds() for r in selected if r['status']=='returned_image' and r['end']]
 ck=[c for c in checkpoints if begin<=c['start']<end]
 days.append({'date':date,'window_start_local':iso(begin),'window_end_local':iso(end),'dispatches':len(selected),'batches_with_dispatches':len(batches),'calls_per_batch':stats(list(batches.values())),'edit_calls':sum(bool(r['edit_existing']) for r in selected),'first_calls':sum(r['attempt_number']==1 for r in selected),'png_returns':sum(r['status']=='returned_image' and r['end'] and begin<=r['end']<end for r in rows),'success_recorded_call_seconds':stats(success),'within_batch_gap_seconds':stats(inside),'between_batch_gap_seconds':stats(cross),'between_gap_before_next_prepared_seconds':round(sum(g['seconds_before_next_first_request_prepared'] or 0 for g in parts),3),'between_gap_ready_but_not_dispatched_seconds':round(sum(g['seconds_ready_but_not_dispatched'] or 0 for g in parts),3),'between_gaps_next_request_not_prepared_count':sum(g['next_first_request_prepared_after_previous_return'] for g in parts),'between_gap_checkpoint_overlap_seconds':round(sum(g['local_checkpoint_overlap_seconds'] for g in parts),3),'local_checkpoint_seconds':stats([c['seconds'] for c in ck]),'gap_over_15min_count':sum(g['gap_seconds']>900 for g in parts)})
report={'machine_id':machine,'observed_at_utc':datetime.now(U).isoformat(),'scope':'Read-only causal timing audit. Explicit local windows and cutoff. Preparation timestamps belong only to the NEXT actual first dispatched request; they do not prove that no other ready work existed, or that all eligibility checks were finished. No time is attributed solely to human review, LLM thinking or network without instrumentation. Checkpoint overlap and import overlap can overlap unprepared/ready intervals and must NOT be summed as disjoint causes.','daily':days,'inter_batch_gaps':gaps,'local_checkpoints':[dict(c,start=iso(c['start']),end=iso(c['end'])) for c in checkpoints]}
p=ROOT/args.output;assert not p.exists(), 'Refuse to overwrite existing report'
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(days,ensure_ascii=True,indent=2))
