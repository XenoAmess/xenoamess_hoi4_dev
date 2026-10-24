"""Four explicitly recovered legacy cache contracts; never infer unknown caches."""
import hashlib,json
from datetime import datetime

# Each complete loader and dispatcher was read before freezing these contracts.
# The complete intervening byte range was scanned: only the loader and caller
# mention this exact cache. These are historical observations, not new pre-call
# snapshots. A different source, cache, command or code stays held.
CONTRACTS={
 'production_003_jobs':{
  'key':'3966e41889a5080a68e3166dd7c560b23bbd5e2709412596f70b803446c91072',
  'loader':'666fd85b2ad054aad18fd922c72ae5099260a4458d6eb90e4e216993c378e7ed',
  'dispatch':'fb0d9e0a92372c5c0ce7631c18693d9c08e2230fd29149eb9b0b5da1dbd75015',
  'command':'type runtime\\cooldown-001-art-repair-jobs.json','index':2,'list_length':3,
  'interval_sha256':'ae50aa05f1b3277d59bfd804794dd052e28567cf7ef7eb364f8f56b065c03b8b','interval_bytes':469261},
 'production_004_jobs':{
  'key':'1b735cd1a32794c23be04dcdca90385d4ef3e1fb971a3f6bfca7985cd142430a',
  'loader':'4c252f6d42f6ebea5b71aec87bfe913055a19d37ab7ef68cb892c681ea9498b8',
  'dispatch':'f921f8667e52fe5159b3df001f4480cf1775c46b21f7b7ccca3c03c940b7b6e4',
  'command':'type runtime\\cooldown-002-art-repair-jobs.json','index':0,'list_length':1,
  'interval_sha256':'8fad2bf125b7ff439019623deee4848036c2b1634bba0eb9f82649d943cf161b','interval_bytes':325924},
 'cooldown_003_jobs':{
  'key':'b3ba713347dc9620fee391ab93275dc036d6d6067ee25b73564497926f8fbac8',
  'loader':'b037ecaec3373e1c4604209e9418d2f5f4bc4cc95f081e6542383b2c8c251889',
  'dispatch':'d3632409889d9a5e6a1a77c19b582488d447dad537f967e4a24687f8678af173',
  'command':'type runtime\\cooldown-retry-job.json','index':None,
  'interval_sha256':'9bfb447e3b99b8a3b581d26970b577402ebc3e78e8cf28193be57969b61a47d9','interval_bytes':327331},
 'cooldown_003_kesselring_edit':{
  'key':'ab1facab79ba1f5b2fb213c96466410c6452cb27cc5228cd8144a4ff653f248b',
  'loader':'d05f05fb5226e493fb30dd40728e643bcf4fdc4d77d0ba09ae40f00023ef952d',
  'dispatch':'b79d4799b64aeea98a9c77fa926505f92f68b52c1eeb5e009a3e54d015e9bb68',
  'command':'type runtime\\prepared-image-job.json','index':None,
  'interval_sha256':'308c2dc666ea0cb3ee0301c51cd361eeee080216d0db7c4607909eda81a364b8','interval_bytes':105978},
}

def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def moment(event):return datetime.fromisoformat(event['timestamp'].replace('Z','+00:00'))

def validate_cached_job(key,archive,events):
 assert archive['schema']=='naiwa-recovered-cached-actual-request-v1'
 contract=CONTRACTS[archive['cache_name']]
 assert contract['key']==key,'Cache contract belongs to another source'
 loader,dispatch=events['cache_loader'],events['dispatch']
 for event,expected in ((loader,contract['loader']),(dispatch,contract['dispatch'])):
  caller=event['payload']
  assert event['type']=='response_item' and caller['type']=='custom_tool_call' and caller['name']=='exec'
  assert digest(caller['input'])==expected,'Unreviewed cache loader or dispatcher'
 interval=archive['cache_interval_proof'];records=archive['events']
 assert interval['interval_sha256']==contract['interval_sha256'] and interval['interval_bytes']==contract['interval_bytes']
 assert interval['matching_tool_call_line_sha256']==[records['cache_loader']['raw_line_sha256'],records['dispatch']['raw_line_sha256']],'Unknown cache access requires investigation'
 assert interval['start_byte_offset']==records['cache_loader']['source_byte_offset']
 assert interval['end_byte_offset']==records['dispatch']['source_byte_offset']+len(records['dispatch']['raw_utf8'].encode('utf-8'))
 assert interval['end_byte_offset']-interval['start_byte_offset']==interval['interval_bytes']
 exported=events['pre_call_job'];item=exported['payload']['item']
 assert exported['payload']['type']=='item_completed' and item['type']=='CommandExecution'
 assert item['status']=='completed' and item['exit_code']==0 and item['command'][-1]==contract['command']
 value=json.loads(item['stdout']);index=contract['index']
 if index is None:
  assert isinstance(value,dict);job=value
 else:
  assert isinstance(value,list) and len(value)==contract['list_length'];job=value[index]
 assert job['key']==key and isinstance(job['transparent'],bool)
 assert moment(loader)<moment(exported)<moment(dispatch)<moment(events['failed_extension']),'Cached stdout must precede the actual dispatcher'
 return job
