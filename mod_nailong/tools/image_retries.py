"""Plan eight-hour, single-use retries. Never calls an image API or schedules OS jobs."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.common import ROOT,read_json,write_json,utc_now,machine_id,file_sha256
from PIL import Image
MOD=ROOT/'mod_nailong';QUEUE=MOD/'data/image-retry-queue.json'

def require_editable_service_state(key,record,latest,edit_existing):
    """Only a returned exact retry can release a held source for an art edit."""
    path=MOD/'data/generation-failures.json';failures=read_json(path)
    held=[f for f in failures.get('attempts',[]) if f['source_sha256']==key and f.get('status')=='blocked' and not f.get('resolved_by_retry')]
    if not held:return
    queue=read_json(QUEUE);entry=queue.get('sources',{}).get(key,{})
    proof=(edit_existing and record and latest and entry.get('retries_used')==1
           and entry.get('state')=='generated_pending_visual_review'
           and latest.get('retry_of_attempt')
           and latest.get('status') in ('generated_pending_visual_review','generated_rejected_visual_review')
           and entry.get('output_sha256')==record.get('image_sha256')==latest.get('output_sha256')
           and file_sha256(ROOT/record['image'])==record['image_sha256'])
    if not proof:raise SystemExit('Service-held source: only the exact single cooldown retry is allowed; no new prompt or input')
    for failure in held:
        failure['resolved_by_retry']={'status':'service_returned_image_art_correction_pending','output_sha256':record['image_sha256'],'observed_at_utc':utc_now(),'original_refusal_preserved':True}
    entry.update(state='service_retry_succeeded_art_correction_pending',accepted_retry_output_sha256=record['image_sha256'],art_correction_started_at_utc=utc_now())
    write_json(path,failures);write_json(QUEUE,queue)

def sync():
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
            'not_before_utc':(started+timedelta(hours=8)).isoformat(),'retries_used':0,'state':'cooling_down',
            'request_id':failure.get('request_id'),'machine_id':machine_id(),'recorded_at_utc':utc_now(),
            'eligibility':'Must confirm underlying request is allowed and tool permits retry; keep exact original prompt and inputs'}
    write_json(QUEUE,queue)
    return queue

def claim(key):
    queue=sync();entry=queue['sources'][key]
    if entry['retries_used']>=1:raise SystemExit('Retry already consumed; no second automatic retry')
    if datetime.now(timezone.utc)<datetime.fromisoformat(entry['not_before_utc']):raise SystemExit('Eight-hour cooldown has not elapsed')
    journal_path=MOD/'data/generation-requests'/(key+'.json')
    if not journal_path.exists():raise SystemExit('Original full prompt/inputs need recovery before retry')
    journal=read_json(journal_path)
    original=next(a for a in reversed(journal['attempts']) if a['status']=='failed')
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
    number=len(journal['attempts'])+1
    promptfile=MOD/'assets/prompts'/f'{key}-{number:03}.txt'
    promptfile.write_text(original['prompt'],encoding='utf-8',newline='\n')
    attempt={**original,'number':number,'status':'prepared','prompt_file':promptfile.relative_to(ROOT).as_posix(),
        'prompt_sha256':file_sha256(promptfile),'prepared_at_utc':utc_now(),'retry_of_attempt':original['number'],
        'cooldown_not_before_utc':entry['not_before_utc'],'eligibility_confirmed_by':'Codex reviewed allowed request and tool conditions before --confirm-eligible'}
    for field in ['error','observed_at_utc','output','output_sha256','generated_at_utc','review','rejection_reason','prompt_transport_correction','intended_prompt','intended_prompt_file','intended_prompt_sha256','actual_request_verification']:attempt.pop(field,None)
    entry.update(retries_used=1,state='claimed_before_call',claimed_at_utc=utc_now())
    write_json(QUEUE,queue)
    journal['attempts'].append(attempt);write_json(journal_path,journal)
    source_image=export_original(asset)
    transparent=Image.open(source_image).getchannel('A').getextrema()[0]<255
    write_json(ROOT/'runtime/cooldown-retry-job.json',{'key':key,'prompt':original['prompt'],'references':references,
        'transparent':transparent,'journal':journal_path.relative_to(ROOT).as_posix()})
    print('Single retry consumed and exact original request prepared; call only built-in imagegen')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['sync','due','claim']);p.add_argument('--key');p.add_argument('--confirm-eligible',action='store_true')
    a=p.parse_args()
    if a.command=='claim':
        if not a.confirm_eligible:raise SystemExit('Review request/tool eligibility before claiming')
        claim(a.key);return
    queue=sync();now=datetime.now(timezone.utc)
    for key,e in queue['sources'].items():
        due=now>=datetime.fromisoformat(e['not_before_utc'])
        if a.command=='sync' or due and e['retries_used']==0:print(key[:12],e['not_before_utc'],e['state'],f"used={e['retries_used']}")

if __name__=='__main__':main()
