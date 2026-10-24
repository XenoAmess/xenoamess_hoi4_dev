"""Validate actual requests, preserving the boundary of post-hoc legacy recovery."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from tools.common import read_json,file_sha256,machine_id

# These two retained dispatchers were manually read in full. Both parse the
# actual command stdout and forward job.prompt, job.references, job.transparent
# directly to the builtin tool, without mutating those arguments.
LEGACY_DIRECT_FORWARDERS={
 '94b0bc89a54012c31211d5f792b796eb46a71e3e7bae3ed814eb0cd1ea0cb8ac',
 '6a63a7af0950b5a4796745a2370737c372771910e962d71f4d6eecc065fc076c',
}

def digest_text(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def event_time(event):return datetime.fromisoformat(event['timestamp'].replace('Z','+00:00'))

def validate_legacy_archive(root,key,attempt,archive):
 assert archive['schema']=='naiwa-recovered-actual-request-v1'
 assert archive['machine_id']==attempt['machine_id']==machine_id()
 assert archive['source_sha256']==key and archive['failed_attempt']==attempt['number']
 assert archive['actual_recorded_before_call'] is False,'Recovery must not impersonate pre-call recording'
 assert archive['validated_from_retained_historical_tool_events'] is True
 events={}
 for name in ('dispatch','pre_call_job','failed_extension','refusal_receipt'):
  record=archive['events'][name];raw=record['raw_utf8']
  assert digest_text(raw)==record['raw_line_sha256'],'Retained tool event bytes changed'
  events[name]=json.loads(raw)
 dispatch=events['dispatch'];caller=dispatch['payload']
 assert dispatch['type']=='response_item' and caller['type']=='custom_tool_call' and caller['name']=='exec'
 assert digest_text(caller['input']) in LEGACY_DIRECT_FORWARDERS,'Unreviewed dispatcher contract'
 exported=events['pre_call_job'];item=exported['payload']['item']
 assert exported['payload']['type']=='item_completed' and item['type']=='CommandExecution' and item['status']=='completed'
 assert item['exit_code']==0 and item['command'][-1]=='type runtime\\cooldown-retry-job.json'
 job=json.loads(item['stdout']);assert job['key']==key and isinstance(job['transparent'],bool)
 assert job['journal']==f'mod_nailong/data/generation-requests/{key}.json'
 ext_event=events['failed_extension'];ext=ext_event['payload']['item']
 assert ext['type']=='Extension' and ext['kind']=='image_gen.generation' and ext['status']=='failed'
 assert ext['revisedPrompt']==job['prompt']==attempt['prompt']
 assert digest_text(job['prompt'])==attempt['prompt_sha256']==file_sha256(root/attempt['prompt_file'])
 assert (root/attempt['prompt_file']).read_text(encoding='utf-8')==job['prompt']
 refusal_event=events['refusal_receipt'];refusal=refusal_event['payload']['item']
 assert refusal['type']=='FileChange' and refusal['status']=='completed'
 errors=[v['content'] for path,v in refusal['changes'].items() if key in path and v['type']=='add']
 assert len(errors)==1 and 'moderation_blocked' in errors[0]
 request_ids=re.findall(r'request ID ([0-9a-f-]{36})',attempt['error'])
 assert len(request_ids)==1 and request_ids[0] in errors[0],'Refusal receipt belongs to another call'
 assert event_time(dispatch)<event_time(exported)<event_time(ext_event)<=event_time(refusal_event)
 assert event_time(refusal_event)<=datetime.fromisoformat(attempt['observed_at_utc'].replace('Z','+00:00'))
 expected=[];references=[]
 for source in attempt['inputs']:
  if source.get('path'):
   references.append(str(root/source['path']));expected.append(source['sha256'])
  else:
   assert source['role']=='original source portrait' and source['raw_sha256']==key
   references.append(str(root/'runtime/references'/(key+'.png')));expected.append(source['converted_png_sha256'])
 assert job['references']==references,'Retained input order/path differs from the frozen journal'
 assert [file_sha256(Path(p)) for p in references]==expected==archive['input_sha256']
 return job,{'machine_id':archive['machine_id'],'actual_recorded_before_call':False,
  'validated_from_retained_historical_tool_events':True,'recovered_at_utc':archive['recovered_at_utc'],
  'transparent_background':job['transparent'],'input_sha256':expected}

def load_actual_request(root,key,attempt,candidate=None):
 """Modern pre-call protocol remains strict; legacy evidence is explicitly separate."""
 root=Path(root);assert attempt['machine_id']==machine_id()
 verification=attempt.get('actual_request_verification')
 if verification:
  assert verification['actual_recorded_before_call'] is True and verification['machine_id']==machine_id()
  dispatch=read_json(root/f'runtime/production-queue/dispatch/{key}-{attempt["number"]:03}.json')
  snapshot=Path(dispatch['actual_request_snapshot_file'])
  assert file_sha256(snapshot)==verification['actual_request_snapshot_sha256']==dispatch['actual_request_snapshot_sha256']
  assert verification['input_sha256']==dispatch['input_sha256']
  return read_json(snapshot),verification
 assert candidate and candidate.get('historical_actual_evidence'),'Missing verified actual request; remain held'
 binding=candidate['historical_actual_evidence'];path=root/binding['path']
 assert path.resolve().parent==(root/'mod_nailong/data/legacy-request-recoveries').resolve()
 assert path.name==f'{key}-{attempt["number"]:03}.json'
 assert file_sha256(path)==binding['sha256'],'Historical archive changed after review'
 job,proof=validate_legacy_archive(root,key,attempt,read_json(path))
 proof['actual_request_snapshot_sha256']=binding['sha256']
 proof['snapshot_provenance']='post_hoc_retained_tool_events; not a pre-call snapshot'
 return job,proof
