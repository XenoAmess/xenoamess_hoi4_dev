"""Defer known same-person variants after a service refusal, retaining distinct people."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,utc_now,machine_id

def surname(path):
 stem=Path(path).stem.lower()
 if 'generic' in stem:return None
 parts=stem.split('_')
 while parts and (parts[-1] in {'small','large'} or parts[-1].isdigit()):parts.pop()
 if not parts:return None
 if parts[-1] in {'jr','sr','ii','iii','iv','vi','vii','viii','ix','x','pasha'}:return '_'.join(parts[-2:])
 return 'doenitz' if parts[-1]=='donitz' else parts[-1]

def known_distinct_people(first,second):
 markers={'frederic_joliot_curie','irene_joliot_curie'}
 left={name for name in markers if any(name in path.lower() for path in first['paths'])}
 right={name for name in markers if any(name in path.lower() for path in second['paths'])}
 return len(left)==len(right)==1 and left!=right

def same_service_family(key,other_key,entry,other):
 if key==other_key or set(entry['characters'])&set(other['characters']):return True
 names={surname(path) for path in entry['paths']}-{None}
 other_names={surname(path) for path in other['paths']}-{None}
 return bool(names&other_names) and not known_distinct_people(entry,other)

def main():
 mod=ROOT/'mod_nailong';key=sys.argv[1];path=mod/f'data/generation-requests/{key}.json'
 history=read_json(path);latest=history['attempts'][-1]
 assert latest['status']=='prepared','Already dispatched/resolved; do not regenerate'
 queue=read_json(mod/'data/image-retry-queue.json')['sources']
 if latest.get('retry_of_attempt'):
  from mod_nailong.tools.image_retries import policy
  used=queue[key]['retries_used'];assert 1<=used<=policy()['max_cooldown_retries_per_source'] and queue[key]['state']=='claimed_before_call'
  assert latest.get('cooldown_retry_number',1)==used
  print(json.dumps({'eligible':True,'reason':'Exact unchanged cooldown retry already claimed','retry_number':used}));return
 priority=read_json(mod/'data/production-priority.json')['sources'];entry=priority[key]
 assert entry['high_priority'],'New non-HIGH sources remain locked'
 conflicts=[]
 for failure in read_json(mod/'data/generation-failures.json')['attempts']:
  if failure.get('status')!='blocked' or failure.get('resolved_by_retry'):continue
  other=failure['source_sha256']
  if same_service_family(key,other,entry,priority[other]):conflicts.append({'source_sha256':other,'source':failure['source_path']})
 if conflicts:
  latest.update(status='cancelled_before_generation',reason='Deferred: same person has an unresolved service refusal; no alternate image/prompt request',observed_at_utc=utc_now(),deferred_service_families=conflicts,machine_id=machine_id())
  write_json(path,history)
  print(json.dumps({'eligible':False,'reason':'Unresolved service-held family','source_sha256':key,'conflicts':conflicts},ensure_ascii=True))
 else:print(json.dumps({'eligible':True,'reason':'Fresh HIGH source or ordinary accepted-image art correction'}))

if __name__=='__main__':main()
