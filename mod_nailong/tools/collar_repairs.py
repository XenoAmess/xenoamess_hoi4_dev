"""Prepare recorded built-in image edits for visually identified collar defects."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json
from mod_nailong.tools.art_contract import portrait_ready
from mod_nailong.tools.generation_requests import prepare

def main():
    mod=ROOT/'mod_nailong'
    audit=read_json(mod/'data/collar-fit-audit.json')
    rows=read_json(mod/'data/generated.json')['portraits']
    priority=read_json(mod/'data/production-priority.json')['sources']
    blocked={f['source_sha256'] for f in read_json(mod/'data/generation-failures.json').get('attempts',[]) if f.get('status')=='blocked' and not f.get('resolved_by_retry')}
    keys=[e['key'] for e in audit['baseline_entries'] if e['collar_verdict']=='needs_regeneration' and not portrait_ready(rows[e['key']])]
    keys.sort(key=lambda k:priority[k]['sort_key'])
    prompt=(mod/'assets/collar-fit-edit-prompt.txt').read_text(encoding='utf-8')
    jobs=[];held=[]
    for key in keys:
        if key in blocked:held.append(key);continue
        if not priority[key]['high_priority']:raise SystemExit('Low-priority correction is locked until high group finishes')
        job=prepare(key,prompt,True)
        journal_path=ROOT/job['journal'];journal=read_json(journal_path)
        journal['attempts'][-1]['revision_goal']='collar-fit-v1'
        write_json(journal_path,journal)
        jobs.append(job)
    write_json(ROOT/'runtime/collar-repair-jobs.json',jobs)
    print({'remaining_collar_repairs':len(keys),'prepared_high_priority_repairs':len(jobs),'service_held':held})

if __name__=='__main__':main()
