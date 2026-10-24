"""Finite read-only sampler of prospectively registered contiguous wall intervals."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now

def register_successors(start_path,count):
    previous=read_json(start_path);assert previous['machine_id']==machine_id()
    paths=[start_path];base=start_path.name.removesuffix('-start.json');prefix,number=base.rsplit('b',1)
    for offset in range(1,count):
        start=datetime.fromisoformat(previous['started_at_utc'])+timedelta(seconds=previous['duration_seconds'])
        now=datetime.now(timezone.utc);assert now<start,'Never label a late registration prospective'
        path=start_path.with_name(prefix+'b'+str(int(number)+offset)+'-start.json')
        body={'machine_id':machine_id(),'started_at_utc':start.isoformat(),'registered_at_utc':now.isoformat(),'registered_before_start':True,'duration_seconds':3600,'comparison_png_per_wall_hour':previous['comparison_png_per_wall_hour'],'previous_interval':paths[-1].relative_to(ROOT).as_posix(),'scope':'Prospectively registered contiguous whole wall hour. Includes all idle, code, review, refusal and checkpoint time. No production reset or image filler.'}
        if path.exists():
            existing=read_json(path);assert existing['machine_id']==machine_id() and datetime.fromisoformat(existing['started_at_utc'])==start and existing['registered_before_start'] and datetime.fromisoformat(existing['registered_at_utc'])<start
            body=existing
        else:write_json(path,body)
        paths.append(path);previous=body
    return paths

def observe(paths):
    pending=[(path,minutes) for path in paths for minutes in [15,30,60]]
    while pending:
        remaining=[]
        for start_path,minutes in pending:
            start=read_json(start_path);end=datetime.fromisoformat(start['started_at_utc'])+timedelta(minutes=minutes)
            output=start_path.with_name(start_path.name.replace('-start.json','-'+str(minutes)+'m.json'))
            if output.exists():
                record=read_json(output);assert record['complete'] and record['requested_minutes']==minutes and datetime.fromisoformat(record['end_utc'])==end
                continue
            if datetime.now(timezone.utc)<end:
                remaining.append((start_path,minutes));continue
            command=[sys.executable,'tools/production_benchmark.py','--start-file',start_path.relative_to(ROOT).as_posix(),'--minutes',str(minutes),'--require-complete','--output',output.relative_to(ROOT).as_posix()]
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
            assert result.returncode==0,{'command':command,'stdout':result.stdout,'stderr':result.stderr}
            record=read_json(output);print(json.dumps({'observed_at_utc':utc_now(),'output':output.relative_to(ROOT).as_posix(),'actual_png_returns':record['actual_png_returns'],'actual_tool_errors':record['actual_tool_errors'],'png_per_wall_hour':record['png_per_wall_hour'],'difference_percent':record['difference_percent']},ensure_ascii=True),flush=True)
        pending=remaining
        if pending:time.sleep(10)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--start-file',required=True);parser.add_argument('--intervals',type=int,default=6);parser.add_argument('--register-only',action='store_true');args=parser.parse_args();assert 1<=args.intervals<=6
    start=ROOT/args.start_file;paths=register_successors(start,args.intervals)
    print(json.dumps({'machine_id':machine_id(),'registered_intervals':[p.relative_to(ROOT).as_posix() for p in paths],'image_calls':0,'quota_claims':0},ensure_ascii=True),flush=True)
    if not args.register_only:observe(paths)
