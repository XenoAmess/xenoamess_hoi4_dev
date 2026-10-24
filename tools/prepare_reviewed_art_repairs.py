from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now
from mod_nailong.tools.generation_requests import prepare,alpha_instruction,near_opaque_backdrop_instruction,verified_opaque_canvas_instruction,supporting_crop_inputs
from tools.common import file_sha256
from mod_nailong.tools.art_preparation_guard import validate_art_boundary,select_review_cases
rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits'];priority=read_json(ROOT/'mod_nailong/data/production-priority.json')['sources'];jobs=[];proof=[]
batch=sys.argv[1] if len(sys.argv)>1 else 'resume-20261023-small-repairs3'
reports=['mod_nailong/data/'+name for name in (sys.argv[2] if len(sys.argv)>2 else 'resumed-20261023-small-finer-v3-review.json').split(',')]
expected=int(sys.argv[3]) if len(sys.argv)>3 else 3
plan_index=(len(read_json(ROOT/'runtime/after128-continuous-plan.json')['batches']) if sys.argv[4]=='auto' else int(sys.argv[4])) if len(sys.argv)>4 else 178
canvas_reviews=read_json(ROOT/sys.argv[5])['sources'] if len(sys.argv)>5 else {}
custom_prompts=read_json(ROOT/sys.argv[7]) if len(sys.argv)>7 else {}
assert not any(read_json(p).get('status')=='calling' for p in (ROOT/'runtime/production-queue/dispatch').glob('*.json'))
cases=[(e,report) for report in reports for e in read_json(ROOT/report)['decisions']]
if len(sys.argv)>6:
 cases=select_review_cases(cases,read_json(ROOT/sys.argv[6]),ROOT,file_sha256)
assert len({e['source_sha256'] for e,report in cases if e['decision']=='rejected'})==sum(e['decision']=='rejected' for e,report in cases)
for e,report in cases:
 if e['decision']!='rejected':continue
 key=e['source_sha256'];r=rows[key];boundary=None;assert priority[key]['high_priority'] and r['review']=='rejected' and r['generated_fullsize_sha256']==e['generated_fullsize_sha256']
 opaque_reason=canvas_reviews.get(key,{}).get('opaque_canvas_reason')
 prompt=('Use case: precise-object-edit. Image1 is the actual raw-HD mascot edit target. Image2 is the exact original game portrait/card and sole authority for visible features. Image3 is the user mascot identity reference.\nActual observed correction: '+e['reason']+'\n'
 'Keep all unrelated source-visible hairstyle and hair colour, eyebrows and exact fine facial-hair state, glasses, headgear when actually present, clothes/neckwear, badges/buttons/straps, expression, gaze, pose, crop and lighting. Source-visible eyebrows remain distinct independent brows; never erase them to copy the identity reference smooth forehead or merge them into head hair. Smooth golden-yellow compact round mascot head with green-ringed black eyes and exactly ONE small mouth at the actual original mouth position. If a moustache is present, that one mouth is below it: never add a second grey slit, beak, nose or default mascot lip above the moustache. No human skin/nose/ears, broad invented facial-hair band or hat replacing real hair.\n'
 'Only when the original actually has a photograph frame/note, retain that entire tilted frame and overlapping paper, opaque photographic backing and true exterior alpha outside the complete original card. Copy the actual original note markings as required visual shapes: preserve their original number of row/groups, compact footprint, placement and dark contrast. Keep original blank paper blank outside that footprint. Do not erase original marks, replace them with random stains or dots, spread writing over the page or invent extra rows. These existing indistinct marks are required original image content, not a request for newly readable words. A standalone full portrait retains its entire original painted backdrop and must not acquire a new photo frame or note. Preserve genuine original transparency only where it really exists. Dark cloth stays fully opaque. Short broad fitted neck with rounded chin immediately meeting actual garment, preserve its open/closed state and do not add a neck column, separate roll, cream bib or floating collar. The exact original controls mouth opening, smile shape and source-visible tooth edge; do not import the mascot reference closed grey lip over an open source mouth. Keep full raw-HD detail, resolution and original aspect ratio; no newly invented readable text, extra note writing beyond the actual original footprint, watermark, new symbols, people or panels.')
 supporting_crops=[]
 if key in custom_prompts:
  custom=custom_prompts[key]
  if isinstance(custom,str):prompt=custom
  else:
   assert set(custom)=={'prompt','supporting_crops'} and isinstance(custom['prompt'],str)
   prompt=custom['prompt'];supporting_crops=custom['supporting_crops']
 journalpath=f'mod_nailong/data/generation-requests/{key}.json';history=read_json(ROOT/journalpath)['attempts'];latest=history[-1];inherited_canvas_attempt=None
 if opaque_reason is None:
  for previous in reversed(history):
   if previous.get('alpha_prompt_policy')!='source-manually-verified-opaque-canvas-v1':continue
   source_input=next(i for i in previous['inputs'] if i['role']=='original source portrait')
   assert source_input['converted_png_sha256']==file_sha256(ROOT/'runtime/references'/f'{key}.png')
   opaque_reason=previous['opaque_canvas_reason'];assert opaque_reason.strip()
   inherited_canvas_attempt=previous['number'];break
 if latest['status']=='prepared':
  asset=next(a for a in read_json(ROOT/'mod_nailong/data/catalog.json')['assets'] if a['source_sha256']==key)
  expected_prompt=prompt+(alpha_instruction(asset) if latest['transparent_background'] else near_opaque_backdrop_instruction() if latest['alpha_prompt_policy']=='source-near-opaque-backdrop-v1' else '')
  if latest['alpha_prompt_policy']=='source-manually-verified-opaque-canvas-v1':
   assert opaque_reason==latest['opaque_canvas_reason'];expected_prompt=prompt+verified_opaque_canvas_instruction()
  assert latest['prompt']==expected_prompt and file_sha256(ROOT/latest['prompt_file'])==latest['prompt_sha256']
  assert latest['edit_existing'] and latest['inputs'][0]['sha256']==r['generated_fullsize_sha256']
  assert not (ROOT/f'runtime/production-queue/dispatch/{key}-{latest["number"]:03}.json').exists()
  source=ROOT/'runtime/references'/f'{key}.png';refs=[str(ROOT/latest['inputs'][0]['path']),str(source),str(ROOT/'mod_nailong/assets/reference/naiwa.png')]
  assert file_sha256(Path(refs[0]))==latest['inputs'][0]['sha256'] and file_sha256(source)==latest['inputs'][1]['converted_png_sha256'] and file_sha256(Path(refs[2]))==latest['inputs'][2]['sha256']
  extra=supporting_crop_inputs(r,supporting_crops,True)
  assert latest['inputs'][3:]==extra
  refs.extend(str(ROOT/i['path']) for i in extra)
  j={'key':key,'source':asset['path'],'references':refs,'original':str(source),'size':asset['size'],'transparent':latest['transparent_background'],'prompt':latest['prompt'],'journal':journalpath}
 else:
  families={f['source_sha256'] for previous in history for f in previous.get('deferred_service_families',[])}
  family_histories={other:read_json(ROOT/f'mod_nailong/data/generation-requests/{other}.json')['attempts'] for other in families}
  boundary=validate_art_boundary(history,key,r['generated_fullsize_sha256'],ROOT/'runtime/production-queue/dispatch',read_json(ROOT/'mod_nailong/data/generation-failures.json')['attempts'],family_histories)
  j=prepare(key,prompt,True,opaque_canvas_reason=opaque_reason,supporting_crops=supporting_crops)
 jobs.append(j);a=read_json(ROOT/j['journal'])['attempts'][-1];proof.append({'source_sha256':key,'rejected_fullsize_sha256':e['generated_fullsize_sha256'],'manual_review_report':report,'prepared_attempt':a['number'],'prompt_sha256':a['prompt_sha256'],'individual_canvas_reason_inherited_from_attempt':inherited_canvas_attempt,'preparation_boundary':boundary})
assert len(jobs)==expected;out=ROOT/f'runtime/production-{batch}-jobs.json';assert not out.exists();write_json(out,jobs)
p=ROOT/'runtime/after128-continuous-plan.json';plan=read_json(p);assert len(plan['batches'])==plan_index
plan['batches'].append({'batch':batch,'jobs':out.relative_to(ROOT).as_posix().replace('/','\\')});write_json(p,plan)
receipt=ROOT/f'mod_nailong/data/{batch.replace("resume-","resumed-",1)}-prepared.json';assert not receipt.exists()
write_json(receipt,{'machine_id':machine_id(),'prepared_at_utc':utc_now(),'scope':'Independently observed HIGH corrections. Only exact original/current raw master/user reference inputs; auxiliary larger preview is not a request input.','followups':proof});print('Prepared',expected,'repairs at plan',plan_index)
