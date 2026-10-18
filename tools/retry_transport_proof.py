"""Read-only exact transport qualification; no queue sync, claim or image call."""
import sys,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from mod_nailong.tools.image_retries import policy
batch,version=sys.argv[1:3]
base=ROOT/f'runtime/cooldown-{batch}-verified-transport-proof-{version}'
assert not base.with_suffix('.json').exists()
now=datetime.now(timezone.utc);machine=machine_id()
queue=read_json(ROOT/'mod_nailong/data/image-retry-queue.json')['sources']
priority=read_json(ROOT/'mod_nailong/data/production-priority.json')['sources']
jobs=[];unqualified=[];provenance=[]
for key,q in queue.items():
 if q['retries_used']>=policy()['max_cooldown_retries_per_source'] or q['state']!='cooling_down' or not priority[key]['high_priority'] or datetime.fromisoformat(q['not_before_utc'])>now:continue
 try:
  assert datetime.fromisoformat(q['not_before_utc'])-datetime.fromisoformat(q.get('last_refusal_receipt_utc',q['first_refusal_receipt_utc']))>=timedelta(hours=8)
  a=read_json(ROOT/f'mod_nailong/data/generation-requests/{key}.json')['attempts'][-1]
  assert a['status']=='failed' and 'moderation_blocked' in a['error']
  v=a['actual_request_verification'];assert a['machine_id']==v['machine_id']==machine and v['actual_recorded_before_call'] is True
  dispatch=ROOT/f'runtime/production-queue/dispatch/{key}-{a["number"]:03}.json';d=read_json(dispatch)
  assert d['machine_id']==machine
  snapshot=Path(d['actual_request_snapshot_file']);assert file_sha256(snapshot)==v['actual_request_snapshot_sha256']==d['actual_request_snapshot_sha256']
  j=read_json(snapshot);assert j['key']==key and j['prompt']==a['prompt']
  assert hashlib.sha256(j['prompt'].encode('utf-8')).hexdigest()==a['prompt_sha256']==v['prompt_sha256']==file_sha256(ROOT/a['prompt_file'])
  assert j['transparent']==v['transparent_background']
  hashes=[]
  for reference,record in zip(j['references'],a['inputs'],strict=True):
   path=ROOT/record['path'] if record.get('path') else Path(j['original'])
   sha=record.get('sha256',record.get('converted_png_sha256'))
   assert str(path)==reference and file_sha256(path)==sha
   hashes.append(sha)
  assert hashes==v['input_sha256']==d['input_sha256']
  jobs.append(dict(j,not_before_utc=q['not_before_utc'],art_direction=a['art_direction'],input_sha256=hashes,original_actual_prompt_verified=True,original_tool_transparent_background=j['transparent'],requires_manual_policy_review=True,policy_reviewed=False,proof='Exact pre-call actual JS snapshot matches failed journal, dispatch proof, original prompt bytes, ordered reference file hashes and transparency parameter. Technical read-only qualification; manual input/prompt policy review remains required before claim.'))
  provenance.append({'source_sha256':key,'failed_attempt':a['number'],'snapshot':str(snapshot),'snapshot_sha256':file_sha256(snapshot),'original_verification':v})
 except (KeyError,ValueError,AssertionError,FileNotFoundError) as error:
  unqualified.append({'source_sha256':key,'reason':type(error).__name__+': '+str(error)})
write_json(base.with_suffix('.json'),jobs)
pages=[]
for page,start in enumerate(range(0,len(jobs),6),1):
 sheet=Image.new('RGB',(1200,900),'#ddd9d1');draw=ImageDraw.Draw(sheet)
 for n,j in enumerate(jobs[start:start+6]):
  x=(n%3)*400;y=(n//3)*450
  refs=[j['original']]+([j['references'][0]] if len(j['references'])>2 else [])
  for col,reference in enumerate(refs):
   with Image.open(reference) as source:
    im=source.convert('RGBA');im.thumbnail((190,370));im=im.resize((round(im.width*min(190/im.width,370/im.height)),round(im.height*min(190/im.width,370/im.height))),Image.Resampling.NEAREST)
    sheet.paste(im,(x+col*200,y),im.getchannel('A'))
  draw.text((x,y+380),f'{start+n+1} '+Path(j['source']).stem[-44:],fill='black')
  draw.text((x,y+400),j['key'][:20]+' Original / edit target if any',fill='black')
 path=base.parent/(base.name+f'-inputs-{page:02}.png');sheet.save(path);pages.append({'path':str(path),'sha256':file_sha256(path),'sources':[j['key'] for j in jobs[start:start+6]]})
write_json(base.parent/(base.name+'-inspection.json'),{'machine_id':machine,'observed_at_utc':utc_now(),'scope':'Read-only technical qualification and source preview. No retry quota consumed, requests changed or images generated. Manual actual prompt and input review remains pending.','verified_requests':provenance,'unqualified_due':unqualified,'review_pages':pages})
print('Technical proof file:',base.with_suffix('.json'));print('Verified exact requests:',len(jobs),'unqualified due:',unqualified)
for page in pages:print('INPUT REVIEW REQUIRED:',page['path'])
