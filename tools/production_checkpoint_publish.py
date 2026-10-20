"""Publish one immutable checkpoint after the producer resumes image imports."""
import sys,os,subprocess,traceback,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,machine_id,utc_now
from tools.isolated_production_sync import rebase_validated_commit
commit,batch=sys.argv[1:3]
assert len(commit)==40 and all(c in '0123456789abcdef' for c in commit)
out=ROOT/f'runtime/checkpoint-{batch}.json'
receipt=read_json(out)
assert receipt['commit']==commit and receipt['machine_id']==machine_id()
receipt.update(network_publish_process_id=os.getpid(),push_started_at_utc=utc_now(),status='committed_push_pending')
write_json(out,receipt)
lock=ROOT/'runtime/production-publish.lock';acquired=False
def run(*args,timeout=900):
 p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
 return p.stdout.strip()
try:
 deadline=time.monotonic()+180
 while True:
  try:
   fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
  except FileExistsError:
   if time.monotonic()>=deadline:raise TimeoutError('Publish lock remained occupied for 180 seconds; inspect owner, do not delete an unverified lock')
   if receipt['status']!='waiting_for_publish_lock':
    receipt.update(status='waiting_for_publish_lock',lock_wait_started_at_utc=utc_now());write_json(out,receipt)
   time.sleep(1)
  else:
   os.write(fd,json.dumps({'machine_id':machine_id(),'process_id':os.getpid(),'acquired_at_utc':utc_now(),'commit':commit,'batch':batch}).encode('utf-8'));os.close(fd);acquired=True
   receipt['status']='committed_push_pending';break
 synchronization=receipt.get('isolated_git_synchronization',{})
 if synchronization.get('status')!='validated_commit_rebased_unchanged_fast_forward_eligible':
  for sync_attempt in range(1,3):
   history=receipt.setdefault('isolated_synchronization_attempt_history',[])
   label=batch+'-network-'+str(len(history)+1)
   item={'started_at_utc':utc_now(),'batch':label,'commit':commit};history.append(item)
   try:
    synchronization=rebase_validated_commit(commit,label)
    item.update(status='succeeded',completed_at_utc=utc_now());receipt['isolated_git_synchronization']=synchronization;write_json(out,receipt);break
   except Exception as error:
    item.update(status='failed',completed_at_utc=utc_now(),error=str(error));write_json(out,receipt)
    if sync_attempt==2 or not any(t in str(error) for t in ['Connection was reset','Recv failure','RPC failed','SSL_ERROR_SYSCALL']):raise
    time.sleep(2)
 def remote_head():return run('git','ls-remote','origin','refs/heads/master',timeout=120).split()[0]
 def contains_fixed(observed):
  if observed==commit:return True
  return subprocess.run(['git','merge-base','--is-ancestor',commit,observed],cwd=ROOT,capture_output=True,timeout=30).returncode==0
 observed=remote_head()
 if contains_fixed(observed):
  receipt.update(push_stdout='Remote already contains this fixed commit; no older-head push attempted.',remote_presence_verified_at_utc=utc_now())
 else:
  for attempt in range(1,3):
   item={'machine_id':machine_id(),'started_at_utc':utc_now(),'transport':'ordinary fast-forward push with HTTP/1.1; TLS verification unchanged'}
   receipt.setdefault('publish_attempt_history',[]).append(item)
   try:
    receipt['push_stdout']=run('git','-c','gc.auto=0','-c','maintenance.auto=false','-c','http.version=HTTP/1.1','push','origin',commit+':refs/heads/master')
    item.update(completed_at_utc=utc_now(),status='command_succeeded');break
   except RuntimeError as error:
    item.update(completed_at_utc=utc_now(),status='command_failed',error=str(error))
    observed=remote_head();item['remote_master_after_error']=observed
    if contains_fixed(observed):
     receipt.update(push_stdout='Transport command failed but fresh remote read proves the fixed commit is present.',remote_presence_verified_at_utc=utc_now());break
    write_json(out,receipt)
    if attempt==2 or not any(term in str(error) for term in ['curl 55','RPC failed','Connection was reset','SSL_ERROR_SYSCALL']):raise
    time.sleep(2)
 observed=run('git','ls-remote','origin','refs/heads/master',timeout=120).split()[0]
 if observed!=commit:run('git','merge-base','--is-ancestor',commit,observed,timeout=30)
 receipt.update(status='committed_and_pushed',pushed_at_utc=utc_now(),remote_master_observed=observed)
 write_json(out,receipt)
 lock.unlink();acquired=False
 run(sys.executable,str(ROOT/'runtime/verify-production-commit.py'),commit,batch,timeout=1200)
 proof=read_json(ROOT/f'runtime/master-readback-{batch}.json');assert proof['status']=='verified' and proof['commit']==commit
 receipt.update(status='committed_pushed_and_originals_verified',completed_at_utc=utc_now(),remote_original_readback=f'runtime/master-readback-{batch}.json')
except BaseException:
 receipt.update(status='pushed_verification_pending' if receipt.get('pushed_at_utc') else 'push_pending_inspection_required',error=traceback.format_exc(),observed_at_utc=utc_now())
 raise
finally:
 write_json(out,receipt)
 if acquired:lock.unlink()
