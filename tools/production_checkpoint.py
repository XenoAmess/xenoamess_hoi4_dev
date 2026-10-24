"""Checkpoint while the producer's one image call is awaiting its result.

The producer records returned paths but defers imports/failures until this exits.
Only this checkpoint writes canonical metadata during that interval.
"""
import sys,subprocess,json,time
from contextlib import contextmanager
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.common import ROOT,read_json,write_json,file_sha256,utc_now,machine_id
from mod_nailong.tools.master_files import sync_git
from mod_nailong.tools.portraits import coverage
from mod_nailong.tools.production_priority import build
from mod_nailong.tools.art_contract import portrait_ready
from mod_nailong.tools.production_queue import attempt_for_snapshot
from tools.checkpoint_schedule import automatic_checkpoint_deferral
from tools.invocation_file_verifier import InvocationFileVerifier

def trace(phase,**details):
 event={'machine_id':machine_id(),'observed_at_utc':utc_now(),'batch':batch,'phase':phase,**details}
 with (ROOT/f'runtime/checkpoint-phases-{batch}.jsonl').open('a',encoding='utf-8',newline='\n') as stream:stream.write(json.dumps(event,ensure_ascii=True)+'\n')

@contextmanager
def timed(phase,**details):
 started=time.perf_counter();trace(phase+'_started',**details)
 try:yield
 except BaseException as error:
  trace(phase+'_failed',elapsed_seconds=round(time.perf_counter()-started,3),error=str(error),**details);raise
 else:trace(phase+'_completed',elapsed_seconds=round(time.perf_counter()-started,3),**details)

def execute(*args,timeout=180):
 with timed('command',command=list(args)):
  p=subprocess.run(list(args),cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
  if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
  return p.stdout.strip()

batch=sys.argv[1];force='--force' in sys.argv[2:];completed=[arg for arg in sys.argv[2:] if arg!='--force']
deferred=automatic_checkpoint_deferral(ROOT,force)
if deferred:
 path=ROOT/f'runtime/checkpoint-{batch}.json';assert not path.exists(),'Existing checkpoint receipt requires reconciliation'
 write_json(path,dict(deferred,machine_id=machine_id(),requested_at_utc=utc_now(),inflight_batch=batch,imports_deferred_by_producer=False))
 print(json.dumps(deferred,ensure_ascii=True),flush=True);raise SystemExit(0)
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
byte_verifier=InvocationFileVerifier()
with timed('archive_sync'):sync_git(hasher=byte_verifier)
with timed('coverage'):coverage(True)
with timed('priority'):build()
with timed('art_audit'):
 from mod_nailong.tools.audit_art import audit
 audit(hasher=byte_verifier)
receipt['invocation_byte_verification']=byte_verifier.summary()
trace('invocation_byte_verification',**receipt['invocation_byte_verification'])
print(execute(sys.executable,'mod_nailong/tools/build_release.py','--preview','--check','--validation-sample','4'),flush=True)
git=['git','-c','gc.auto=0','-c','maintenance.auto=false']
assert execute('git','branch','--show-current')=='master'
execute(*git,'add','--','AGENTS.md','mod_nailong','tests/test_master_files.py','tests/test_generation_requests.py','tests/test_retry_scheduler_merge.py','tests/test_image_retries.py','tests/test_portrait_pipeline.py','tests/test_fullsize_game_textures.py','tests/test_production_queue.py','tools/retry_scheduler_next.py','tools/retry_scheduler_merge.py','tools/retry_transport_proof.py','tools/retry_scheduler_complete.py','tools/retry_scheduler_claim.py','tools/portrait_dispatch_guard.py','tools/retry_statistics.py','tools/desktop.py','tools/keyboard_scan_codes.py','tools/desktop_verified_click.py','docs/maintenance/hd-display-probe-restoration-2026-10-19.json','docs/maintenance/portrait-production-capacity-2026-10-19.json')
execute(*git,'add','--','tools/common.py','tests/test_json_read_sharing.py')
execute(*git,'add','--','tests/test_fullsize_review.py')
execute(*git,'add','--','tests/test_audit_art.py')
execute(*git,'add','--','tests/test_ready_art_reports.py')
execute(*git,'add','--','tests/test_ready_art_service_holds.py')
execute(*git,'add','--','tests/test_rolling_builtin_queue.cjs','tests/test_production_transport_preview.py','tests/test_rolling_production_queue.py')
execute(*git,'add','--','tests/test_portrait_review_queue.py')
execute(*git,'add','--','tools/retry_actual_proof.py','tests/test_retry_actual_proof.py')
execute(*git,'add','--','tools/legacy_cached_request.py','tests/test_legacy_cached_request.py')
execute(*git,'add','--','tools/rolling_builtin_queue.js','tools/rolling_production_queue.py','tools/production_transport_preview.py','tools/portrait_review_queue.py','tools/portrait_review_worker.md')
execute(*git,'add','--','tests/test_portrait_dispatch_guard.py')
execute(*git,'add','--','docs/maintenance/hd-adviser-probe-restoration-2026-10-19.json')
execute(*git,'add','--','docs/maintenance/desktop-gbk-observation-2026-10-19.json')
execute(*git,'add','--','tests/test_hd_masking.py')
execute(*git,'add','--','tools/isolated_production_sync.py','tests/test_isolated_production_sync.py')
execute(*git,'add','--','README.md','tools/production_checkpoint.py','tools/production_checkpoint_publish.py')
execute(*git,'add','--','workshop/products.json')
execute(*git,'add','--','tools/production_plan_state.py','tests/test_production_plan_state.py')
execute(*git,'add','--','tests/test_master_remote_api.py')
execute(*git,'add','--','tests/test_master_remote_reuse.py')
execute(*git,'add','--','tools/continuous_builtin_producer.js')
execute(*git,'add','--','tools/bounded_builtin_window.js','tools/production_gap_audit.py','tests/test_bounded_builtin_window.cjs')
execute(*git,'add','--','tools/production_window_gate.py','tests/test_production_window_gate.py')
execute(*git,'add','--','tools/builtin_window_continuation.js')
execute(*git,'add','--','tools/production_benchmark.py')
execute(*git,'add','--','tools/production_benchmark_observer.py')
execute(*git,'add','--','tests/test_production_benchmark.py')
execute(*git,'add','--','tools/prepare_reviewed_art_repairs.py','tools/production_prepare_boundary.py','tests/test_production_prepare_boundary.py')
execute(*git,'add','--','tools/prepare_reviewed_original_replacements.py','tests/test_original_replacement_preparation.py')
execute(*git,'add','--','tools/prepare_reviewed_fresh_sources.py')
execute(*git,'add','--','tools/fresh_source_observation_queue.py','tests/test_fresh_source_observation_queue.py')
execute(*git,'add','--','tools/checkpoint_schedule.py','tests/test_checkpoint_schedule.py')
execute(*git,'add','--','tools/accepted_retry_art.py','tests/test_accepted_retry_art.py')
execute(*git,'add','--','tests/test_exact_art_review_selection.py')
execute(*git,'add','--','tools/prepare_reviewed_transport_retry.py','tests/test_reviewed_transport_retry.py','docs/handoffs/2026-10-24-resume-preflight.json','docs/handoffs/2026-10-24-resume-activation.json')
execute(*git,'add','--','tools/invocation_file_verifier.py','tests/test_invocation_file_verifier.py')
execute(*git,'add','--','tests/test_supporting_target_crops.py')
execute(*git,'add','--','tests/test_matched_original_context.py')
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
