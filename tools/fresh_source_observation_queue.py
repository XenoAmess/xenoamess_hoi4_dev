"""Reserve allowed unmade HIGH originals for the two existing visual-review slots."""
import argparse,json,os,re,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from tools.portrait_dispatch_guard import same_service_family

def candidates(root):
 rows=read_json(root/'mod_nailong/data/generated.json')['portraits']
 assets=read_json(root/'mod_nailong/data/catalog.json')['assets']
 priority=read_json(root/'mod_nailong/data/production-priority.json')['sources']
 failures=read_json(root/'mod_nailong/data/generation-failures.json')
 nonperson=set(read_json(root/'mod_nailong/data/nonperson-source-observations.json')['observations'])
 blocked={f['source_sha256'] for f in failures['attempts'] if f.get('status')=='blocked' and not f.get('resolved_by_retry')}
 resolved={a['path'].lower() for a in assets for f in failures['attempts'] if a['source_sha256']==f['source_sha256'] and f.get('resolved_by_retry')}
 held=(set(p.lower() for p in failures.get('held_source_paths',[]))-resolved)|{a['path'].lower() for a in assets if a['source_sha256'] in blocked}
 unique={a['source_sha256']:a for a in assets};out=[]
 for key,a in unique.items():
  if key in rows or key in nonperson or not priority[key]['high_priority'] or key in blocked or a['path'].lower() in held:continue
  if any(same_service_family(key,b,priority[key],priority[b]) for b in blocked):continue
  original=root/f'runtime/references/{key}.png'
  if not original.is_file() or not original.resolve().is_relative_to((root/'runtime/references').resolve()):continue
  journal=root/f'mod_nailong/data/generation-requests/{key}.json';history=None
  if journal.exists():
   attempts=read_json(journal)['attempts']
   if not attempts or any(v['status']!='cancelled_before_generation' for v in attempts) or any((root/'runtime/production-queue/dispatch').glob(key+'-*.json')):continue
   history={'journal_sha256':file_sha256(journal)}
  item={'key':key,'source':a['path'],'original':str(original),'original_png_sha256':file_sha256(original)}
  if history:item['cancelled_request_history']=history
  out.append(item)
 return out

def claim(root,slot):
 assert slot in {'a','b'}
 if (root/'runtime/rolling-review-queue/handoff-stop.json').exists():return {'ready':False,'stop_requested':True,'reason':'user_requested_handoff','slot':slot,'next_step':'Stop polling and do not create a successor; user requested vacation handoff.'}
 folder=root/'runtime/fresh-source-observations';reserved=folder/'reservations';reserved.mkdir(parents=True,exist_ok=True)
 # Resuming observation is read-only with respect to production. Never reserve
 # a second group for a slot whose original observations are unfinished.
 pending=[]
 for path in sorted((folder/'allocations').glob('*.json')):
  body=read_json(path)
  if body['slot']==slot and not (root/f'mod_nailong/data/production-fresh-observation-completions/{body["tag"]}.json').exists():pending.append((path,body))
 assert len(pending)<=1,'Multiple source allocations require explicit reconciliation'
 if pending:
  allocation,body=pending[0];assert body['machine_id']==machine_id()
  if (root/f'mod_nailong/data/production-fresh-source-observations/{body["tag"]}.json').exists():
   return {'ready':False,'reason':'partial_source_observation_completion_requires_reconciliation','allocation':allocation.relative_to(root).as_posix()}
  return {'ready':True,'kind':'fresh_source_observation','slot':slot,'tag':body['tag'],'resume_existing_observation':True,'allocation':allocation.relative_to(root).as_posix(),'allocation_sha256':file_sha256(allocation),'sources':body['sources'],'config':f'runtime/{body["tag"]}-observations.json'}
 selected=[];tag='fresh-observed-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+slot+'-'+uuid.uuid4().hex[:8]
 for item in candidates(root):
  path=reserved/(item['key']+'.json')
  try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
  except FileExistsError:continue
  with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump({'machine_id':machine_id(),'slot':slot,'tag':tag,'reserved_at_utc':utc_now(),'source':item},stream,ensure_ascii=True)
  selected.append(item)
  if len(selected)==4:break
 if not selected:return {'ready':False,'reason':'no_unreserved_allowed_unmade_HIGH_originals','slot':slot}
 allocation=folder/'allocations'/(tag+'.json');assert not allocation.exists()
 body={'machine_id':machine_id(),'slot':slot,'tag':tag,'created_at_utc':utc_now(),'sources':selected,'scope':'Actual original observation required, not art approval or permission to invent a character. No journal preparation, retry claim or image call. Reservations remain after failure for explicit reconciliation.'}
 write_json(allocation,body)
 return {'ready':True,'kind':'fresh_source_observation','slot':slot,'tag':tag,'allocation':allocation.relative_to(root).as_posix(),'allocation_sha256':file_sha256(allocation),'sources':selected,'config':f'runtime/{tag}-observations.json'}

def complete(root,config_path):
 config_path=Path(config_path);config_path=config_path if config_path.is_absolute() else root/config_path
 assert config_path.resolve().is_relative_to(root.resolve())
 config=read_json(config_path);assert config['machine_id']==machine_id() and config['actually_observed'] is True
 path=(root/config['allocation']).resolve();assert path.parent==(root/'runtime/fresh-source-observations/allocations').resolve()
 assert file_sha256(path)==config['allocation_sha256'];allocation=read_json(path)
 assert allocation['machine_id']==machine_id();tag=allocation['tag'];assert re.fullmatch(r'[A-Za-z0-9_-]+',tag)
 done=root/f'mod_nailong/data/production-fresh-observation-completions/{tag}.json';assert not done.exists(),'Do not repeat completed or uncertain observation staging'
 selected={v['key']:v for v in allocation['sources']};descriptions={v['key']:v['description'] for v in config['sources']};held=config.get('held',{})
 assert len(descriptions)==len(config['sources']) and not (set(descriptions)&set(held)) and set(descriptions)|set(held)==set(selected)
 assert all(isinstance(v,str) and v.strip() for v in [*descriptions.values(),*held.values()])
 viewed={v['key']:v for v in config['viewed_originals']};assert set(viewed)==set(selected)
 for key,item in selected.items():
  assert viewed[key]['path']==item['original'] and viewed[key]['sha256']==item['original_png_sha256']==file_sha256(Path(item['original']))
 reference=root/'mod_nailong/assets/reference/naiwa.png';assert config['mascot_reference_sha256']==file_sha256(reference)
 parse=lambda s:datetime.fromisoformat(s.replace('Z','+00:00'))
 assert parse(allocation['created_at_utc'])<=parse(config['review_started_at_utc'])<=parse(config['review_completed_at_utc'])<=parse(utc_now())
 batch='resume-'+tag
 canonical=root/f'mod_nailong/data/production-fresh-source-observations/{tag}.json';assert not canonical.exists()
 body={'machine_id':machine_id(),'tag':tag,'batch':batch,'actually_observed':True,'evidence':[{'path':path.relative_to(root).as_posix(),'sha256':file_sha256(path)},{'path':config_path.relative_to(root).as_posix(),'sha256':file_sha256(config_path)}],'sources':[{**item,'description':descriptions[key]} for key,item in selected.items() if key in descriptions],'held_source_observations':held,'actual_observation':config}
 write_json(canonical,body);intent=None
 if descriptions:
  preparer=root/'tools/prepare_reviewed_fresh_sources.py';intent=root/f'runtime/production-queue/preparation/pending/{tag}.json';intent.parent.mkdir(parents=True,exist_ok=True)
  record={'machine_id':machine_id(),'kind':'reviewed_fresh_sources','queued_at_utc':utc_now(),'preparer_sha256':file_sha256(preparer),'arguments':[canonical.relative_to(root).as_posix()],'evidence':[{'path':canonical.relative_to(root).as_posix(),'sha256':file_sha256(canonical)}],'expected_jobs_file':f'runtime/production-{batch}-jobs.json','expected_source_keys':[v['key'] for v in body['sources']]}
  with intent.open('x',encoding='utf-8',newline='\n') as stream:json.dump(record,stream,ensure_ascii=True,indent=2);stream.write('\n')
 receipt={'machine_id':machine_id(),'completed_at_utc':utc_now(),'slot':allocation['slot'],'allocation':path.relative_to(root).as_posix(),'allocation_sha256':file_sha256(path),'observations':canonical.relative_to(root).as_posix(),'observations_sha256':file_sha256(canonical),'queued_originals':len(descriptions),'held_originals':len(held),'preparation_intent':intent.relative_to(root).as_posix() if intent else None,'image_calls':0,'quota_claims':0,'scope':'Actual visual source descriptions only; same producer rechecks current HIGH/service/history/input gates before preparing. Holds remain in denominator. No canonical portrait/retry mutations.'}
 write_json(done,receipt);return receipt

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['claim','complete']);parser.add_argument('value');args=parser.parse_args()
 print(json.dumps(claim(ROOT,args.value) if args.action=='claim' else complete(ROOT,args.value),ensure_ascii=True))
