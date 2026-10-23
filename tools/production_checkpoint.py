"""Checkpoint while the producer's one image call is awaiting its result.

The producer records returned paths but defers imports/failures until this exits.
Only this checkpoint writes canonical metadata during that interval.
"""
import sys,subprocess,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,utc_now,machine_id
from mod_nailong.tools.master_files import sync_git
from mod_nailong.tools.portraits import coverage
from mod_nailong.tools.production_priority import build
from mod_nailong.tools.art_contract import portrait_ready
from mod_nailong.tools.production_queue import attempt_for_snapshot

def execute(*args,timeout=180):
 p=subprocess.run(list(args),cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
 return p.stdout.strip()

batch=sys.argv[1];completed=sys.argv[2:]
receipt={'machine_id':machine_id(),'started_at_utc':utc_now(),'inflight_batch':batch,'imports_deferred_by_producer':True,'completed_batches':completed}
print('Checkpoint '+batch+': preserving originals and completed batch metadata while one builtin call runs',flush=True)
for name in completed:
 file=ROOT/('runtime/'+name+'-jobs.json') if name.startswith('cooldown-') else ROOT/('runtime/production-'+name.removeprefix('important-')+'-jobs.json')
 if name=='resume-20261020-repairs':file=ROOT/'runtime/production-resume-20261020-all-repairs-jobs.json'
 jobs=read_json(file);requests=[]
 rows=read_json(ROOT/'mod_nailong/data/generated.json')['portraits']
 for job in jobs:
  actual=ROOT/f'runtime/dispatch-actual/{name}-{job["key"]}.json'
  if not actual.exists():
   latest=read_json(ROOT/f'mod_nailong/data/generation-requests/{job["key"]}.json')['attempts'][-1]
   assert latest['status']=='cancelled_before_generation'
   requests.append({'source_sha256':job['key'],'source':job['source'],'attempt_number':latest['number'],'status':latest['status'],'call_dispatched':False,'prompt_sha256':latest['prompt_sha256'],'fullsize_sha256':None,'output_sha256':None,'this_output_qualified':False,'current_source_ready':False,'reason':latest['reason']})
   continue
  proof=file_sha256(actual)
  a=attempt_for_snapshot(job['key'],actual);row=rows.get(job['key'],{})
  requests.append({'source_sha256':job['key'],'source':job['source'],'attempt_number':a['number'],'status':a['status'],'call_dispatched':True,'prompt_sha256':a['prompt_sha256'],'fullsize_sha256':a.get('fullsize_sha256'),'output_sha256':a.get('output_sha256'),'this_output_qualified':bool(a.get('output_sha256')==row.get('image_sha256') and portrait_ready(row)),'current_source_ready':portrait_ready(row) if row else False,'actual_request_verification':a['actual_request_verification']})
 write_json(ROOT/f'mod_nailong/data/production-batches/{name}.json',{'machine_id':machine_id(),'observed_at_utc':utc_now(),'actual_calls':sum(a['call_dispatched'] for a in requests),'deferred_without_call':sum(not a['call_dispatched'] for a in requests),'returned_images':sum(bool(a['fullsize_sha256']) for a in requests),'failed_calls':sum(a['status']=='failed' for a in requests),'qualified_outputs_from_this_batch':sum(a['this_output_qualified'] for a in requests),'requests':requests,'retry_policy_path':'mod_nailong/data/image-retry-policy.json','retry_policy_sha256':file_sha256(ROOT/'mod_nailong/data/image-retry-policy.json'),'scope':'Exact actual-payload proof binds each batch attempt. Failed/refused/rejected outputs do not count as qualified. New sources remain HIGH-first. Each eligible retry retains exact prompt/input bytes and order, uses one builtin lane, observes at least eight hours after the latest refusal and consumes the cumulative source quota in the bound policy without resetting previous use.'})
sync_git();coverage(True);build()
print(execute(sys.executable,'mod_nailong/tools/audit_art.py',timeout=900),flush=True)
print(execute(sys.executable,'mod_nailong/tools/build_release.py','--preview','--check','--validation-sample','4'),flush=True)
git=['git','-c','gc.auto=0','-c','maintenance.auto=false']
assert execute('git','branch','--show-current')=='master'
execute(*git,'add','--','AGENTS.md','mod_nailong','tests/test_master_files.py','tests/test_generation_requests.py','tests/test_retry_scheduler_merge.py','tests/test_image_retries.py','tests/test_portrait_pipeline.py','tests/test_fullsize_game_textures.py','tests/test_production_queue.py','tools/retry_scheduler_next.py','tools/retry_scheduler_merge.py','tools/retry_transport_proof.py','tools/retry_scheduler_complete.py','tools/retry_scheduler_claim.py','tools/portrait_dispatch_guard.py','tools/retry_statistics.py','tools/desktop.py','tools/keyboard_scan_codes.py','tools/desktop_verified_click.py','docs/maintenance/hd-display-probe-restoration-2026-10-19.json','docs/maintenance/portrait-production-capacity-2026-10-19.json')
execute(*git,'add','--','tools/common.py','tests/test_json_read_sharing.py')
execute(*git,'add','--','tests/test_fullsize_review.py')
execute(*git,'add','--','tests/test_portrait_dispatch_guard.py')
execute(*git,'add','--','docs/maintenance/hd-adviser-probe-restoration-2026-10-19.json')
execute(*git,'add','--','docs/maintenance/desktop-gbk-observation-2026-10-19.json')
execute(*git,'add','--','tests/test_hd_masking.py')
execute(*git,'add','--','tools/isolated_production_sync.py','tests/test_isolated_production_sync.py')
execute(*git,'add','--','README.md','tools/production_checkpoint.py','tools/production_checkpoint_publish.py')
execute(*git,'add','--','workshop/products.json')
execute(*git,'add','--','tools/production_plan_state.py','tests/test_production_plan_state.py')
execute(*git,'add','--','tests/test_master_remote_api.py')
execute(*git,'add','--','tools/continuous_builtin_producer.js')
execute(*git,'add','--','tools/bounded_builtin_window.js','tools/production_gap_audit.py','tests/test_bounded_builtin_window.cjs')
execute(*git,'add','--','tools/production_window_gate.py','tests/test_production_window_gate.py')
execute(*git,'add','--','tools/builtin_window_continuation.js')
execute(*git,'add','--','tools/production_benchmark.py')
execute(*git,'add','--','tests/test_production_benchmark.py')
execute(*git,'add','--','tools/prepare_reviewed_art_repairs.py','tools/production_prepare_boundary.py','tests/test_production_prepare_boundary.py')
message=ROOT/'runtime/production-checkpoint-message.txt'
message.write_text('Preserve reviewed HIGH portraits and original fullsize PNGs\n\nContinue the full portrait task across storage and validation checkpoints.\nKeep remote original verification bound to immutable Git metadata.\n',encoding='utf-8',newline='\n')
if execute('git','diff','--cached','--name-only'):
 execute(*git,'commit','--file',str(message))
commit=execute('git','rev-parse','HEAD')
receipt.update(local_commit_completed_at_utc=utc_now(),commit=commit,status='committed_push_pending',imports_may_resume_after_local_commit=True,isolated_git_synchronization={'status':'pending_in_separate_network_publisher','primary_worktree_untouched':True})
write_json(ROOT/f'runtime/checkpoint-{batch}.json',receipt)
log=ROOT/f'runtime/publish-{batch}.log'
with log.open('wb') as stream:
 child=subprocess.Popen([sys.executable,str(ROOT/'tools/production_checkpoint_publish.py'),commit,batch],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
print('Local checkpoint committed '+commit+'; imports resume while finite pinned-commit push and PNG readback run in process '+str(child.pid)+'. Remote success remains pending actual receipts.',flush=True)
