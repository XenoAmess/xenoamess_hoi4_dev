from pathlib import Path
import sys
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,machine_id,utc_now
from tools.portrait_dispatch_guard import same_service_family
from mod_nailong.tools.generation_requests import prepare
from tools.production_priority_gate import tier_allowed
selected=ROOT/sys.argv[1];config=read_json(selected)
assert config['machine_id']==machine_id() and config['actually_observed'] is True
special_authorization=None
if config.get('special_source_authorization'):
 binding=config['special_source_authorization'];path=(ROOT/binding['path']).resolve()
 assert path.parent==(ROOT/'mod_nailong/data/production-special-source-directions').resolve()
 assert file_sha256(path)==binding['sha256']
 special_authorization=read_json(path);assert special_authorization['machine_id']==machine_id()
tag=config['tag'];batch=config['batch'];sources=config['sources'];details={str(n):s['description'] for n,s in enumerate(sources,1)}
assert batch.replace('-','').isalnum() and tag.replace('-','').isalnum()
for evidence in config['evidence']:
 path=(ROOT/evidence['path']).resolve();assert path.is_relative_to(ROOT.resolve()) and file_sha256(path)==evidence['sha256']
mod=ROOT/'mod_nailong';rows=read_json(mod/'data/generated.json')['portraits'];priority=read_json(mod/'data/production-priority.json')['sources'];blocked={f['source_sha256'] for f in read_json(mod/'data/generation-failures.json')['attempts'] if f.get('status')=='blocked' and not f.get('resolved_by_retry')}
assert 1<=len(sources)==len(details)<=8
assert not any(read_json(p).get('status')=='calling' for p in (ROOT/'runtime/production-queue/dispatch').glob('*.json'))
nonperson=set(read_json(mod/'data/nonperson-source-observations.json')['observations'])
failures=read_json(mod/'data/generation-failures.json');assets=read_json(mod/'data/catalog.json')['assets']
resolved={a['path'].lower() for a in assets for f in failures['attempts'] if a['source_sha256']==f['source_sha256'] and f.get('resolved_by_retry')}
held=(set(p.lower() for p in failures.get('held_source_paths',[]))-resolved)|{a['path'].lower() for a in assets if a['source_sha256'] in blocked}
assert len({s['key'] for s in sources})==len(sources)
for s in sources:
 key=s['key'];assert key not in rows and key not in nonperson and s['source'].lower() not in held and tier_allowed(ROOT,priority[key])
 assert isinstance(s['description'],str) and s['description'].strip()
 journal=mod/f'data/generation-requests/{key}.json'
 if s.get('cancelled_request_history'):
  history=s['cancelled_request_history'];assert file_sha256(journal)==history['journal_sha256']
  assert all(a['status']=='cancelled_before_generation' for a in read_json(journal)['attempts']) and not list((ROOT/'runtime/production-queue/dispatch').glob(key+'-*.json'))
 else:assert not journal.exists()
 assert not any(same_service_family(key,b,priority[key],priority[b]) for b in blocked)
 assert file_sha256(Path(s['original']))==s['original_png_sha256']
planpath=ROOT/'runtime/after128-continuous-plan.json';plan=read_json(planpath);index=len(plan['batches'])
out=ROOT/f'runtime/production-{batch}-jobs.json';assert not out.exists();jobs=[];proof=[]
for n,s in enumerate(sources,1):
 key=s['key'];desc=details[str(n)];reason=None
 if desc.startswith('Standalone full painted rectangle.'):
  with Image.open(s['original']) as im:extrema=list(im.convert('RGBA').getchannel('A').getextrema())
  assert extrema[0]>0
  reason=f"Actually viewed complete exact original {s['source']} on SHA-bound fresh HIGH {tag} input pages, including full painted background in all four corners. Converted PNG SHA256 {s['original_png_sha256']}, original alpha extrema {extrema}. This individual original is a complete opaque painted rectangular canvas; retain it with fully opaque subject/clothing. No figure-cutout exterior exists. Not a global alpha threshold or frozen retry change."
 prompt=('Use case: compositing. Image1 is the exact original game character portrait/card and sole source authority. Image2 is the user yellow mascot identity reference. Produce one independent full-resolution yellow mascot fusion preserving original composition and aspect ratio.\n'
 'Actually viewed source-specific features: '+desc+'\n'
 'Convert the visible character anatomy to a smooth golden-yellow compact round mascot with green-ringed black eyes, retaining original hair/fur contour, brows and only actual source facial hair with exact extent, density and colour. Preserve all real accessories, headgear, clothing details, source head direction, gaze, pose, lighting and crop. Do not infer appearance from filename or biography. No human skin/nose/ears, new beard, hat, people, symbols or decorations.\n'
 'Match the actual source mouth and expression: a somber downturned mouth remains visibly downturned, a small lip parting remains slightly open, and an open toothy or happy mouth remains open. Do not replace every mouth with the neutral grey reference wedge or an upward smile. Retain subtle asymmetry and brow mood.\n'
 'Use one simple mascot mouth opening with the actual source curve and openness. Do not retain or add separately projecting human upper and lower lips, a cupid bow, fleshy lip rolls or lipstick-like outer rims. Visible teeth, tongue or mouth interior may remain when required by the source expression; those alone are not lip defects.\n'
 'Use a compact round head with curved chin resting immediately at the source neckline through a VERY SHORT BROAD transition. Fit existing garment collar and shoulder lines to the mascot, preserving original open/closed fastening. No long yellow stalk, neck roll, pinched ring, floating collar, clipping or cream neck bib. Preserve actual bare/animal clothing state; do not invent a human garment where absent.\n'
 'Standalone source retains its COMPLETE original painted rectangular backdrop and all original subject/clothing through every edge, fully opaque. Only an original framed card retains that exact tilted frame, wholly opaque backing, cream overlapping note and genuine alpha outside the complete card silhouette. Keep original upper-note multirow markings in their actual position/footprint/contrast as indistinct dark strokes; never erase them into blank parchment, add extra writing or invent readable words/numbers. All original solid surfaces stay fully opaque. Keep full painterly detail and tool output resolution. One asset, no comparison board, new label, text or watermark.')
 if special_authorization is not None:
  from tools.special_source_prompt import special_source_prompt
  prompt=special_source_prompt(s,special_authorization)
 j=prepare(key,prompt,False,opaque_canvas_reason=reason);jobs.append(j);a=read_json(ROOT/j['journal'])['attempts'][-1]
 proof.append({'source_sha256':key,'source':s['source'],'original_png_sha256':s['original_png_sha256'],'actual_source_features':desc,'source_canvas_manual_reason':reason,'cancelled_request_history':s.get('cancelled_request_history'),'prepared_attempt':a['number'],'prompt_sha256':a['prompt_sha256'],'transparent_background':a['transparent_background']})
from tools.production_priority_gate import append_prepared_windows
append_prepared_windows(ROOT,plan,batch,jobs,out);write_json(planpath,plan)
write_json(mod/f'data/{batch.replace("resume-","resumed-",1)}-prepared.json',{'machine_id':machine_id(),'prepared_at_utc':utc_now(),'scope':f'{len(sources)} actually viewed uncalled HIGH exact originals. No unresolved same-person service family at preparation. Sources either have no prior journal or explicit SHA-bound all-cancelled history with zero dispatch ledgers; prior unsubmitted records remain unchanged. Known four static nonperson sources excluded without removing their denominator. Actual animal characters, if present, remain characters; no imaginary human occupant.','source_selection_sha256':file_sha256(selected),'sources':proof})
print('Prepared',len(sources),'fresh HIGH original requests at plan',index)
