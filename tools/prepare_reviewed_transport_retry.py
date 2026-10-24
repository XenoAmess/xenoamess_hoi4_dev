"""Prepare one reviewed exact retry after a definite connection error, once only."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools.prepare_ready_art_reviews import service_held_keys

CONNECTION_ERROR='image generation failed: connection failed: error sending request'

def prepare_transport_retry(root,batch,index,config):
    root=Path(root)
    assert re.fullmatch(r'[A-Za-z0-9_-]+',batch)
    assert config['machine_id']==machine_id() and config['complete_prompt_actually_read'] is True
    key=config['source_sha256'];assert re.fullmatch(r'[0-9a-f]{64}',key)
    directory=root/'runtime/production-queue/dispatch'
    assert not any(read_json(p).get('status')=='calling' for p in directory.glob('*.json'))
    journal_path=root/f'mod_nailong/data/generation-requests/{key}.json'
    journal=read_json(journal_path);last=journal['attempts'][-1]
    assert last['status']=='failed' and last['number']==config['failed_attempt_number']
    assert last['error'].strip()==CONNECTION_ERROR,'Only the explicit returned connection error is accepted'
    assert not any(a.get('transport_retry_of_attempt') for a in journal['attempts']),'At most one reviewed transport retry; never automatic loops'
    assert not last.get('retry_of_attempt'),'Service-refused request chains retain their cooldown path'
    priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
    failures=read_json(root/'mod_nailong/data/generation-failures.json')['attempts']
    assert priority[key]['high_priority'] and not service_held_keys([key],priority,failures)
    dispatch=directory/f'{key}-{last["number"]:03}.json'
    assert file_sha256(dispatch)==config['failed_dispatch_sha256']
    ledger=read_json(dispatch)
    assert ledger['status']=='tool_error' and ledger['source_sha256']==key and ledger['attempt_number']==last['number']
    assert ledger['machine_id']==machine_id() and ledger.get('call_returned_at_utc')
    assert not ledger.get('returned_image') and not ledger.get('returned_image_sha256')
    error=Path(ledger['actual_error_file'])
    assert error.resolve().is_relative_to((root/'runtime').resolve())
    assert file_sha256(error)==ledger['actual_error_sha256']
    assert error.read_text(encoding='utf-8')==last['error']
    snapshot=Path(ledger['actual_request_snapshot_file'])
    assert snapshot.resolve().is_relative_to((root/'runtime/dispatch-actual').resolve())
    assert file_sha256(snapshot)==ledger['actual_request_snapshot_sha256']==config['actual_request_snapshot_sha256']
    actual=read_json(snapshot);verification=last['actual_request_verification']
    assert verification['actual_recorded_before_call'] is True and ledger['actual_prompt_verified_before_call'] is True
    assert verification['actual_request_snapshot_sha256']==file_sha256(snapshot)
    assert actual['key']==key and actual['prompt']==last['prompt']
    assert actual['transparent']==verification['transparent_background']
    assert hashlib.sha256(actual['prompt'].encode('utf-8')).hexdigest()==last['prompt_sha256']==config['exact_prompt_sha256']
    old_prompt=root/last['prompt_file'];assert file_sha256(old_prompt)==last['prompt_sha256']
    assert old_prompt.read_text(encoding='utf-8')==actual['prompt']
    expected=[i.get('sha256',i.get('converted_png_sha256')) for i in last['inputs']]
    viewed=config['ordered_viewed_inputs']
    assert len(viewed)==len(actual['references'])==len(expected)
    assert [v['path'] for v in viewed]==actual['references']
    assert all(v['actually_viewed'] is True for v in viewed)
    assert [file_sha256(Path(p)) for p in actual['references']]==[v['sha256'] for v in viewed]==expected==ledger['input_sha256']==verification['input_sha256']
    row=read_json(root/'mod_nailong/data/generated.json')['portraits'][key]
    assert row['review']=='rejected' and row['generated_fullsize_sha256']==expected[0]
    assert file_sha256(root/row['generated_fullsize_image'])==expected[0]
    plan_path=root/'runtime/after128-continuous-plan.json';plan=read_json(plan_path)
    assert len(plan['batches'])==index
    output=root/f'runtime/production-{batch}-jobs.json';assert not output.exists()
    number=len(journal['attempts'])+1
    prompt_path=root/f'mod_nailong/assets/prompts/{key}-{number:03}.txt';assert not prompt_path.exists()
    prompt_path.write_bytes(old_prompt.read_bytes())
    attempt=copy.deepcopy(last)
    for field in ['error','observed_at_utc','actual_request_verification']:attempt.pop(field,None)
    attempt.update(number=number,status='prepared',prepared_at_utc=utc_now(),prompt_file=prompt_path.relative_to(root).as_posix(),transport_retry_of_attempt=last['number'],transport_failure_proof={'dispatch':dispatch.relative_to(root).as_posix(),'dispatch_sha256':file_sha256(dispatch),'actual_error_sha256':ledger['actual_error_sha256'],'actual_request_snapshot_sha256':file_sha256(snapshot),'manual_reviewed_at_utc':config['reviewed_at_utc'],'scope':'One exact retry of a definite connection error; unchanged prompt, ordered input bytes and transparency. No service quota claim or altered refusal.'})
    journal['attempts'].append(attempt);write_json(journal_path,journal)
    write_json(output,[actual]);plan['batches'].append({'batch':batch,'jobs':output.relative_to(root).as_posix()});write_json(plan_path,plan)
    receipt=root/f'mod_nailong/data/production-transport-retries/{batch}.json';assert not receipt.exists()
    write_json(receipt,{'machine_id':machine_id(),'prepared_at_utc':utc_now(),'source_sha256':key,'failed_attempt_number':last['number'],'prepared_attempt_number':number,'prompt_sha256':last['prompt_sha256'],'inputs_sha256':expected,'transparent_background':actual['transparent'],'proof':attempt['transport_failure_proof'],'scope':'Prepared by sole owner. Actual call/result/art review remain separate; one transport retry maximum, no moderation/cooldown bypass.'})
    return {'prepared':1,'batch':batch,'index':index,'receipt':receipt.relative_to(root).as_posix()}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('batch');p.add_argument('index');p.add_argument('config');args=p.parse_args()
    index=len(read_json(ROOT/'runtime/after128-continuous-plan.json')['batches']) if args.index=='auto' else int(args.index)
    print(json.dumps(prepare_transport_retry(ROOT,args.batch,index,read_json(ROOT/args.config)),ensure_ascii=True))
