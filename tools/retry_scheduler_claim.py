import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json
from mod_nailong.tools.image_retries import claim
from PIL import Image

def expected_transparency(candidate,attempt):
 flag=candidate.get('original_tool_transparent_background')
 verification=attempt.get('actual_request_verification',{})
 actual=verification.get('transparent_background')
 bound=verification.get('actual_recorded_before_call') and isinstance(actual,bool)
 if flag is None and bound:
  assert candidate['verified_actual_snapshot_sha256']==verification['actual_request_snapshot_sha256']
  assert candidate['prompt']==attempt['prompt'] and candidate['input_sha256']==verification['input_sha256']
  return actual
 if flag is not None:
  assert isinstance(flag,bool)
  if bound:assert flag==actual,'Proof flag conflicts with actual tool call'
  return flag
 assert all(ord(ch)<128 for ch in candidate['prompt'])
 with Image.open(candidate['original']) as source:flag=source.convert('RGBA').getchannel('A').getextrema()[0]<255
 assert flag and 'Output alpha: keep a genuine fully transparent RGBA background' in candidate['prompt']
 return flag

def claim_candidates(batch,proof):
 candidates=read_json(proof);jobs=[];preflight=[]
 # Resolve all transport fields before consuming the first source allowance.
 for c in candidates:
  assert c['original_actual_prompt_verified']
  if c.get('requires_manual_policy_review'):assert c.get('policy_reviewed') is True,'Actual original inputs and prompt need manual policy review before any quota claim'
  q=read_json(ROOT/'mod_nailong/data/image-retry-queue.json')['sources'][c['key']]
  assert q['retries_used']==c.get('next_retry_number',1)-1 and q['not_before_utc']==c['not_before_utc'],'Counter or latest refusal deadline changed; reconcile before consuming a call'
  a=read_json(ROOT/f'mod_nailong/data/generation-requests/{c["key"]}.json')['attempts'][-1]
  assert a['status']=='failed' and q['state']=='cooling_down'
  preflight.append((c,expected_transparency(c,a)))
 for c,expected_alpha in preflight:
  claim(c['key']);j=read_json(ROOT/'runtime/cooldown-retry-job.json')
  assert j['prompt']==c['prompt'] and j['references']==c['references'] and j['transparent']==expected_alpha
  j.update(source=c['source'],original=c['original']);jobs.append(j)
  write_json(ROOT/f'runtime/cooldown-{batch}-jobs.json',jobs)
 write_json(ROOT/f'runtime/cooldown-{batch}-keys.json',[j['key'] for j in jobs])
 print(len(jobs),'exact permitted retries claimed before their single calls')

if __name__=='__main__':
 batch=sys.argv[1]
 claim_candidates(batch,ROOT/sys.argv[2] if len(sys.argv)>2 else ROOT/f'runtime/cooldown-{batch}-original-transport-proof.json')
