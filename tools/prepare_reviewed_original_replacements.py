"""Sole-owner preparation of explicit original-based replacements after art rejection."""
import argparse
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools.generation_requests import prepare
from mod_nailong.tools.art_preparation_guard import validate_art_boundary
from mod_nailong.tools.prepare_ready_art_reviews import service_held_keys

def prepare_replacements(root,batch,index,config,preparer=None):
    assert re.fullmatch(r'[A-Za-z0-9_-]+',batch)
    assert config['machine_id']==machine_id() and 1<=len(config['sources'])<=8
    assert not any(read_json(p).get('status')=='calling' for p in (root/'runtime/production-queue/dispatch').glob('*.json'))
    plan_path=root/'runtime/after128-continuous-plan.json';plan=read_json(plan_path);assert len(plan['batches'])==index
    output=root/f'runtime/production-{batch}-jobs.json';assert not output.exists(),'Never replay a partially prepared replacement'
    rows=read_json(root/'mod_nailong/data/generated.json')['portraits'];priority=read_json(root/'mod_nailong/data/production-priority.json')['sources'];failures=read_json(root/'mod_nailong/data/generation-failures.json')['attempts']
    keys=[c['source_sha256'] for c in config['sources']];assert len(set(keys))==len(keys)
    assert not service_held_keys(keys,priority,failures),'Unresolved service family; no alternative request'
    checked=[]
    for c in config['sources']:
        from tools.production_priority_gate import tier_allowed
        key=c['source_sha256'];row=rows[key];assert tier_allowed(root,priority[key]) and row['review']=='rejected'
        assert row['generated_fullsize_sha256']==c['rejected_fullsize_sha256'] and file_sha256(root/row['generated_fullsize_image'])==c['rejected_fullsize_sha256']
        report_path=(root/c['manual_review_report']).resolve();assert report_path.is_relative_to((root/'mod_nailong/data').resolve())
        assert file_sha256(report_path)==c['manual_review_report_sha256'];report=read_json(report_path)
        assert report['machine_id']==machine_id() and report['decisions_staged']
        assert any(e['source_sha256']==key and e['decision']=='rejected' and e['generated_fullsize_sha256']==c['rejected_fullsize_sha256'] for e in report['decisions'])
        assert c['replacement_reason'].strip() and c['prompt'].strip()
        history=read_json(root/row['request_journal'])['attempts']
        assert history[-1]['status'] in {'generated_rejected_visual_review','cancelled_before_generation'}
        families={f['source_sha256'] for a in history for f in a.get('deferred_service_families',[])}
        family_histories={other:read_json(root/f'mod_nailong/data/generation-requests/{other}.json')['attempts'] for other in families}
        boundary=validate_art_boundary(history,key,c['rejected_fullsize_sha256'],root/'runtime/production-queue/dispatch',failures,family_histories)
        checked.append((c,boundary))
    jobs=[];proof=[];preparer=preparer or prepare
    for c,boundary in checked:
        job=preparer(c['source_sha256'],c['prompt'],False,replacement_reason=c['replacement_reason'],opaque_canvas_reason=c.get('opaque_canvas_reason'),supporting_original_context=c.get('supporting_original_context'));jobs.append(job)
        attempt=read_json(root/job['journal'])['attempts'][-1]
        expected_roles=['original source portrait','user mascot reference']
        if c.get('supporting_original_context'):expected_roles.append('composition-matched original context; primary source and independent generation remain distinct')
        assert not attempt['edit_existing'] and [i['role'] for i in attempt['inputs']]==expected_roles
        assert len(job['references'])==len(expected_roles)
        proof.append({'source_sha256':c['source_sha256'],'rejected_fullsize_sha256':c['rejected_fullsize_sha256'],'manual_review_report':c['manual_review_report'],'manual_review_report_sha256':c['manual_review_report_sha256'],'replacement_reason':c['replacement_reason'],'prepared_attempt':attempt['number'],'prompt_sha256':attempt['prompt_sha256'],'preparation_boundary':boundary})
    write_json(output,jobs);plan['batches'].append({'batch':batch,'jobs':output.relative_to(root).as_posix()});write_json(plan_path,plan)
    receipt=root/f'mod_nailong/data/production-original-replacements/{batch}.json';assert not receipt.exists()
    write_json(receipt,{'machine_id':machine_id(),'prepared_at_utc':utc_now(),'followups':proof,'scope':'Explicit different art method after actual PNG success and current-SHA rejection: exact original plus user reference, no rejected edit target. Optional actually viewed composition-matched original context is separately bound in the full inputs; it never merges sources or reuses a generated output across different originals. Same builtin lane; no refused payload modified, no cooldown quota reset. All attempts and original PNG bytes retained.'})
    return {'prepared':len(jobs),'batch':batch,'index':index,'receipt':receipt.relative_to(root).as_posix()}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('batch');parser.add_argument('index',help='Exact plan index, or auto inside the sole preparation owner');parser.add_argument('config');args=parser.parse_args()
    index=len(read_json(ROOT/'runtime/after128-continuous-plan.json')['batches']) if args.index=='auto' else int(args.index)
    print(prepare_replacements(ROOT,args.batch,index,read_json(ROOT/args.config)))
