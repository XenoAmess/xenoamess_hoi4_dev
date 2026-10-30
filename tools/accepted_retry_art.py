"""Read-only proof that an exact service retry returned the current rejected PNG."""
import hashlib
from pathlib import Path
from tools.common import read_json,file_sha256,machine_id
from tools.retry_actual_proof import load_actual_request
from mod_nailong.tools.retry_limits import retry_limit


def accepted_retry_art_proofs(root,rows,latest):
    root=Path(root)
    queue=read_json(root/'mod_nailong/data/image-retry-queue.json')['sources']
    settings=read_json(root/'mod_nailong/data/image-retry-policy.json')
    proofs={};unavailable={}
    for key,a in latest.items():
        row=rows.get(key,{})
        if row.get('review')!='rejected' or a.get('status')!='generated_rejected_visual_review' or not a.get('retry_of_attempt'):continue
        try:
            entry=queue[key]
            assert entry['state']=='generated_pending_visual_review','No current successful retry awaiting art'
            assert 1<=entry['retries_used']<=retry_limit(settings,key) and a['cooldown_retry_number']==entry['retries_used']
            assert entry['output_sha256']==row['image_sha256']==a['output_sha256']
            assert a['fullsize_sha256']==row['generated_fullsize_sha256']
            assert file_sha256(root/row['image'])==row['image_sha256']
            assert file_sha256(root/row['generated_fullsize_image'])==row['generated_fullsize_sha256']
            history=read_json(root/row['request_journal'])['attempts']
            assert history[-1]==a,'Latest attempt changed'
            parent=next(p for p in history if p['number']==a['retry_of_attempt']);immediate_parent=parent
            network_ancestors=[];child=a
            while 'moderation_blocked' not in parent.get('error',''):
                assert parent['status']=='failed' and parent.get('error','').strip() in {'image generation failed: connection failed: error sending request','image generation failed: network error: error sending request'}
                assert child.get('terminal_service_transport_retry_of_attempt')==parent['number'],'Network ancestor was not explicitly reconciled'
                assert parent['prompt']==child['prompt'] and parent['inputs']==child['inputs']
                ledger_path=root/f'runtime/production-queue/dispatch/{key}-{parent["number"]:03}.json';ledger=read_json(ledger_path)
                assert ledger['machine_id']==machine_id() and ledger['source_sha256']==key and ledger['attempt_number']==parent['number']
                assert ledger['status']=='tool_error' and ledger.get('call_returned_at_utc') and not ledger.get('returned_image_sha256') and not ledger.get('returned_image')
                error=Path(ledger['actual_error_file']);assert file_sha256(error)==ledger['actual_error_sha256'] and error.read_text(encoding='utf-8')==parent['error']
                payload,pv=load_actual_request(root,key,parent)
                assert pv['actual_recorded_before_call'] is True and payload['prompt']==a['prompt'] and payload['transparent']==a['actual_request_verification']['transparent_background']
                assert [file_sha256(Path(p)) for p in payload['references']]==pv['input_sha256']==a['actual_request_verification']['input_sha256']
                network_ancestors.append({'attempt':parent['number'],'dispatch':ledger_path.relative_to(root).as_posix(),'dispatch_sha256':file_sha256(ledger_path),'actual_error_sha256':ledger['actual_error_sha256']})
                child=parent;parent=next(p for p in history if p['number']==parent['retry_of_attempt'])
            assert parent['status']=='failed' and parent['prompt']==child['prompt'] and parent['inputs']==child['inputs'],'Successful call was not the unchanged failed request'
            actual,verification=load_actual_request(root,key,a)
            assert verification['actual_recorded_before_call'] is True
            assert actual['key']==key and actual['prompt']==a['prompt']
            assert hashlib.sha256(actual['prompt'].encode('utf-8')).hexdigest()==a['prompt_sha256']==file_sha256(root/a['prompt_file'])
            assert actual['transparent']==verification['transparent_background']
            references=[str(root/i['path']) if i.get('path') else str(root/'runtime/references'/(key+'.png')) for i in a['inputs']]
            expected=[i['sha256'] if i.get('path') else i['converted_png_sha256'] for i in a['inputs']]
            assert actual['references']==references and [file_sha256(Path(p)) for p in references]==expected==verification['input_sha256']
            dispatch_path=root/f'runtime/production-queue/dispatch/{key}-{a["number"]:03}.json'
            dispatch=read_json(dispatch_path)
            assert dispatch['machine_id']==machine_id() and dispatch['source_sha256']==key and dispatch['attempt_number']==a['number']
            assert dispatch['status']=='returned_image' and dispatch['returned_image_sha256']==row['generated_fullsize_sha256'],'No actual returned current PNG'
            proofs[key]={'source_sha256':key,'accepted_attempt':a['number'],'failed_parent_attempt':immediate_parent['number'],'failed_moderation_ancestor_attempt':parent['number'],'proven_returned_network_ancestors':network_ancestors,'current_rejected_fullsize_sha256':row['generated_fullsize_sha256'],'current_preview_sha256':row['image_sha256'],'dispatch':dispatch_path.relative_to(root).as_posix(),'dispatch_sha256':file_sha256(dispatch_path),'actual_request_snapshot_sha256':verification['actual_request_snapshot_sha256'],'retries_used_unchanged':entry['retries_used'],'scope':'Current exact retry actually returned and was visually rejected. Only its own historical service hold may enter the existing art preparation proof. Other unresolved family failures and independent art holds remain blocking; no retry allocation or state mutation here.'}
        except (AssertionError,KeyError,FileNotFoundError,StopIteration) as error:
            unavailable[key]=type(error).__name__+': '+str(error)
    return {'proofs':proofs,'unavailable':unavailable}
