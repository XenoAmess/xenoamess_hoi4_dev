import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json
from mod_nailong.tools.image_retries import claim
from PIL import Image
batch=sys.argv[1];candidates=read_json(ROOT/sys.argv[2] if len(sys.argv)>2 else ROOT/f'runtime/cooldown-{batch}-original-transport-proof.json');jobs=[]
for c in candidates:
 assert c['original_actual_prompt_verified']
 if c.get('requires_manual_policy_review'):assert c.get('policy_reviewed') is True,'Actual original inputs and prompt need manual policy review before any quota claim'
 q=read_json(ROOT/'mod_nailong/data/image-retry-queue.json')['sources'][c['key']]
 assert q['retries_used']==c.get('next_retry_number',1)-1 and q['not_before_utc']==c['not_before_utc'],'Counter or latest refusal deadline changed; reconcile selection before consuming a call'
 expected_alpha=c['original_tool_transparent_background']
 if expected_alpha is None:
  assert all(ord(ch)<128 for ch in c['prompt'])
  with Image.open(c['original']) as source:expected_alpha=source.convert('RGBA').getchannel('A').getextrema()[0]<255
  assert expected_alpha and 'Output alpha: keep a genuine fully transparent RGBA background' in c['prompt']
 claim(c['key']);j=read_json(ROOT/'runtime/cooldown-retry-job.json')
 assert j['prompt']==c['prompt'] and j['references']==c['references'] and j['transparent']==expected_alpha
 j.update(source=c['source'],original=c['original']);jobs.append(j)
 write_json(ROOT/f'runtime/cooldown-{batch}-jobs.json',jobs)
write_json(ROOT/f'runtime/cooldown-{batch}-keys.json',[j['key'] for j in jobs])
print(len(jobs),'exact permitted retries claimed before their single calls')
