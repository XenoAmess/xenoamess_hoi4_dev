"""Plan up to eight unchanged retries, eight hours after each service refusal."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,utc_now,machine_id,file_sha256
from PIL import Image
from mod_nailong.tools.retry_limits import retry_limit,extra_retry_authorization
MOD=ROOT/'mod_nailong';QUEUE=MOD/'data/image-retry-queue.json'

def policy():
    settings=read_json(MOD/'data/image-retry-policy.json')
    assert settings['cooldown_hours']==8
    assert settings['max_cooldown_retries_per_source']==8
    for grant in settings.get('source_scoped_extra_retry_rounds',[]):
        extra_retry_authorization(settings,grant['source_keys'][0])
        path=(ROOT/grant['authorization_manifest']).resolve()
        assert path.is_relative_to((MOD/'data/extra-retry-rounds').resolve())
        assert file_sha256(path)==grant['authorization_manifest_sha256'],'Extra-round authorization changed'
        frozen=read_json(path)
        assert frozen['authorization_id']==grant['authorization_id']
        assert frozen['source_count']==len(frozen['sources'])==len(grant['source_keys'])==31
        assert frozen['additional_retries_per_selected_source']==1 and frozen['preserve_consumed_counts'] is True
        assert {e['source_sha256'] for e in frozen['sources']}==set(grant['source_keys'])
        assert all(e['retries_used_at_authorization']==8 and e['additional_authorized_cooldown_retries']==1 and e['max_cooldown_retries_after_authorization']==9 for e in frozen['sources'])
    return settings

def refresh_refusal(entry, latest, settings, *, source_key=None):
    """Migrate an exhausted old allowance without resetting consumed calls."""
    limit=retry_limit(settings,source_key)
    entry['max_cooldown_retries']=limit
    if not latest or latest['status']!='failed':return
    if 'moderation_blocked' not in latest.get('error',''):return
    observed=latest.get('observed_at_utc')
    if not observed:return
    deadline=(datetime.fromisoformat(observed.replace('Z','+00:00'))+timedelta(hours=settings['cooldown_hours'])).isoformat()
    # Never weaken a previously conservative lower bound or an existing CD.
    if datetime.fromisoformat(entry['not_before_utc'])>datetime.fromisoformat(deadline):deadline=entry['not_before_utc']
    old_state=entry['state']
    new_state='cooling_down' if entry['retries_used']<limit else 'retry_limit_reached'
    if old_state=='retry_limit_reached' and new_state=='cooling_down':
        grant=extra_retry_authorization(settings,source_key);assert grant
        entry.setdefault('policy_migrations',[]).append({'machine_id':machine_id(),'observed_at_utc':utc_now(),'previous_state':old_state,'previous_retries_used':entry['retries_used'],'new_max_cooldown_retries':limit,'authorization_id':grant['authorization_id'],'authorization_manifest_sha256':grant['authorization_manifest_sha256'],'reason':'User explicitly authorized one additional retry for this frozen exhausted HIGH source; preserve all consumed calls and latest8h deadline.'})
    if old_state in ('retry_failed_no_more_automatic_retries','new_art_request_refused_retry_quota_exhausted'):
        entry.setdefault('policy_migrations',[]).append({'machine_id':machine_id(),'observed_at_utc':utc_now(),
            'previous_state':old_state,'previous_retries_used':entry['retries_used'],
            'new_max_cooldown_retries':limit,'user_instruction_date':settings['user_instruction_date'],
            'reason':'User raised the cumulative source allowance to eight; preserve old failures and consumed calls.'})
    entry.update(state=new_state,last_refusal_receipt_utc=observed,not_before_utc=deadline,
                 cooldown_origin_attempt=latest['number'])

def require_editable_service_state(key,record,latest,edit_existing):
    """Only a returned exact retry can release a held source for an art edit."""
    path=MOD/'data/generation-failures.json';failures=read_json(path)
    held=[f for f in failures.get('attempts',[]) if f['source_sha256']==key and f.get('status')=='blocked' and not f.get('resolved_by_retry')]
    if not held:return
    queue=read_json(QUEUE);entry=queue.get('sources',{}).get(key,{})
    proof=(edit_existing and record and latest and 1<=entry.get('retries_used',0)<=retry_limit(policy(),key)
           and entry.get('state')=='generated_pending_visual_review'
           and latest.get('retry_of_attempt')
           and latest.get('status') in ('generated_pending_visual_review','generated_rejected_visual_review')
           and entry.get('output_sha256')==record.get('image_sha256')==latest.get('output_sha256')
           and file_sha256(ROOT/record['image'])==record['image_sha256'])
    if not proof:raise SystemExit('Service-held source: only an eligible exact cooldown retry is allowed; no new prompt or input')
    for failure in held:
        failure['resolved_by_retry']={'status':'service_returned_image_art_correction_pending','output_sha256':record['image_sha256'],'observed_at_utc':utc_now(),'original_refusal_preserved':True}
    entry.update(state='service_retry_succeeded_art_correction_pending',accepted_retry_output_sha256=record['image_sha256'],art_correction_started_at_utc=utc_now())
    write_json(path,failures);write_json(QUEUE,queue)

def sync():
    settings=policy()
    queue=read_json(QUEUE) if QUEUE.exists() else {'schema':'naiwa-image-retry-queue-v1','sources':{}}
    for failure in read_json(MOD/'data/generation-failures.json').get('attempts',[]):
        if failure.get('status')!='blocked':continue
        key=failure['source_sha256']
        if key in queue['sources']:continue
        observed=failure.get('observed_at_utc')
        # A new receipt is a conservative lower bound for old, imprecisely timed failures.
        if not observed or any('approx' in str(v).lower() for k,v in failure.items() if 'time' in k or 'precision' in k):
            observed=utc_now();basis='New verified receipt; old refusal time not precise'
        else:basis='Recorded refusal receipt UTC'
        started=datetime.fromisoformat(observed.replace('Z','+00:00'))
        queue['sources'][key]={'first_refusal_receipt_utc':observed,'time_basis':basis,
            'not_before_utc':(started+timedelta(hours=settings['cooldown_hours'])).isoformat(),'retries_used':0,'state':'cooling_down',
            'request_id':failure.get('request_id'),'machine_id':machine_id(),'recorded_at_utc':utc_now(),
            'eligibility':'Must confirm underlying request is allowed and tool permits retry; keep exact original prompt and inputs'}
    for key,entry in queue['sources'].items():
        path=MOD/'data/generation-requests'/(key+'.json')
        attempts=read_json(path)['attempts'] if path.exists() else []
        refresh_refusal(entry,attempts[-1] if attempts else None,settings,source_key=key)
    queue['policy']={'user_instruction_date':settings['user_instruction_date'],
                     'cooldown_hours':settings['cooldown_hours'],'max_cooldown_retries_per_source':settings['max_cooldown_retries_per_source']}
    if settings.get('source_scoped_extra_retry_rounds'):
        queue['policy']['source_scoped_extra_retry_rounds']=settings['source_scoped_extra_retry_rounds']
    write_json(QUEUE,queue)
    return queue

def claim(key):
    queue=sync();entry=queue['sources'][key]
    settings=policy();limit=retry_limit(settings,key)
    if entry['retries_used']>=limit:raise SystemExit('Retry limit reached; cumulative source allowance already consumed')
    if datetime.now(timezone.utc)<datetime.fromisoformat(entry['not_before_utc']):raise SystemExit('Eight-hour cooldown has not elapsed')
    journal_path=MOD/'data/generation-requests'/(key+'.json')
    if not journal_path.exists():raise SystemExit('Original full prompt/inputs need recovery before retry')
    journal=read_json(journal_path)
    original=journal['attempts'][-1]
    if original['status']!='failed':raise SystemExit('Retry already consumed or result unresolved/returned; do not claim another call')
    if entry['state']!='cooling_down':raise SystemExit('Unresolved or non-service failure; inspect before claiming a retry')
    root=original
    while root.get('retry_of_attempt'):
        previous=next(a for a in journal['attempts'] if a['number']==root['retry_of_attempt'])
        if root['prompt']!=previous['prompt'] or root['inputs']!=previous['inputs']:
            raise SystemExit('Retry chain prompt or ordered input identities changed; recover exact evidence')
        root=previous
    from mod_nailong.tools.generation_requests import original as export_original
    asset=next(a for a in read_json(MOD/'data/catalog.json')['assets'] if a['source_sha256']==key)
    references=[]
    for source in original['inputs']:
        if source.get('path'):
            p=ROOT/source['path'];expected=source['sha256']
        else:
            p=export_original(asset);expected=source['converted_png_sha256']
        if file_sha256(p)!=expected:raise SystemExit('Original input bytes no longer match; recover evidence before retry')
        references.append(str(p))
    # A cooldown repeats the actual tool flag even if future alpha policy changes.
    verification=original.get('actual_request_verification',{})
    verified_alpha=verification.get('transparent_background')
    frozen_alpha=original.get('cooldown_retry_tool_transparent_background')
    if verification.get('actual_recorded_before_call') and isinstance(verified_alpha,bool):
        transparent=verified_alpha
        if isinstance(frozen_alpha,bool) and frozen_alpha!=transparent:
            raise SystemExit('Recorded retry transparency conflicts with actual call; reconcile before consuming quota')
    elif isinstance(frozen_alpha,bool):
        transparent=frozen_alpha
    else:
        source_image=export_original(asset)
        with Image.open(source_image) as source:
            transparent=source.convert('RGBA').getchannel('A').getextrema()[0]<255
    number=len(journal['attempts'])+1
    promptfile=MOD/'assets/prompts'/f'{key}-{number:03}.txt'
    promptfile.write_text(original['prompt'],encoding='utf-8',newline='\n')
    retry_number=entry['retries_used']+1
    attempt={**original,'number':number,'status':'prepared','prompt_file':promptfile.relative_to(ROOT).as_posix(),
        'prompt_sha256':file_sha256(promptfile),'prepared_at_utc':utc_now(),'retry_of_attempt':original['number'],
        'retry_root_attempt':root['number'],'cooldown_retry_number':retry_number,
        'cooldown_not_before_utc':entry['not_before_utc'],'cooldown_retry_tool_transparent_background':transparent,
        'eligibility_confirmed_by':'Codex reviewed allowed request and tool conditions before --confirm-eligible'}
    if retry_number>settings['max_cooldown_retries_per_source']:
        grant=extra_retry_authorization(settings,key);assert grant
        attempt['source_scoped_extra_retry_authorization']={k:grant[k] for k in ['authorization_id','authorization_manifest','authorization_manifest_sha256','additional_retries_per_selected_source']}
    for field in ['error','observed_at_utc','output','output_sha256','fullsize_sha256','fullsize_image','generated_at_utc','review','reviewed_at_utc','rejection_reason','prompt_transport_correction','intended_prompt','intended_prompt_file','intended_prompt_sha256','actual_request_verification']:attempt.pop(field,None)
    entry.update(retries_used=retry_number,state='claimed_before_call',claimed_at_utc=utc_now())
    write_json(QUEUE,queue)
    journal['attempts'].append(attempt);write_json(journal_path,journal)
    write_json(ROOT/'runtime/cooldown-retry-job.json',{'key':key,'prompt':original['prompt'],'references':references,
        'transparent':transparent,'journal':journal_path.relative_to(ROOT).as_posix()})
    print(f'Cooldown retry {retry_number}/{limit} consumed and exact original request prepared; call only built-in imagegen')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['sync','due','claim']);p.add_argument('--key');p.add_argument('--confirm-eligible',action='store_true')
    a=p.parse_args()
    if a.command=='claim':
        if not a.confirm_eligible:raise SystemExit('Review request/tool eligibility before claiming')
        claim(a.key);return
    queue=sync();now=datetime.now(timezone.utc)
    for key,e in queue['sources'].items():
        due=now>=datetime.fromisoformat(e['not_before_utc'])
        if a.command=='sync' or due and e['state']=='cooling_down' and e['retries_used']<retry_limit(policy(),key):print(key[:12],e['not_before_utc'],e['state'],f"used={e['retries_used']}")

if __name__=='__main__':main()
