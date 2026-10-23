async function produce(jobFile,batch,checkpointCommand="",options={}) {
 const emit=(phase,detail={})=>options.onEvent?.({phase,batch,observed_at_utc:new Date().toISOString(),...detail});
 emit("batch_started",{jobs_file:jobFile});
 const root="C:\\workspace\\xenoamess_hoi4_dev";
 const run=async(cmd,budget=1600)=>{const start=Date.now();emit("local_command_started",{command:cmd});let r=await tools.exec_command({cmd,shell:"cmd.exe",login:false,workdir:root,max_output_tokens:budget});while(r.session_id)r=await tools.write_stdin({session_id:r.session_id,chars:"",max_output_tokens:budget,yield_time_ms:1000});emit("local_command_finished",{command:cmd,elapsed_ms:Date.now()-start,exit_code:r.exit_code});if(r.exit_code!==0)throw Error(JSON.stringify(r));return r;};
 const keys=JSON.parse((await run("python runtime\\batch-keys.py "+jobFile,3000)).output),todo=[...keys];
 if(keys.length>8)throw Error("Bounded cell accepts at most8 actual requests");
 let checkpoint=null,checkpointResult=null,checkpointStarted=false,checkpointFailureRecorded=false;const pending=[];
 const flush=async()=>{
  if(checkpoint && !checkpointResult)return false;
  while(pending.length){const item=pending[0];
   if(item.errorFile)await run("python mod_nailong\\tools\\generation_requests.py fail --key "+item.key+" --message-file "+item.errorFile);
   else await run("python mod_nailong\\tools\\generation_requests.py finish --key "+item.key+" --image "+item.path);
   pending.shift();
  }
  await run("python mod_nailong\\tools\\production_queue.py apply-reviews");
  // Only this executor mutates canonical requests, after checkpoint/import barriers.
  const preparation=JSON.parse((await run("python tools\\production_prepare_boundary.py",1600)).output);
  if(preparation.status==="preparation_requires_reconciliation")notify(batch+": future preparation stopped for reconciliation; current prepared originals continue");
  if(checkpointResult?.error&&!checkpointFailureRecorded){
   const failure={machine_id:"bf-202609141645-5434332d4d",observed_at_utc:new Date().toISOString(),batch,jobs_file:jobFile,error:String(checkpointResult.error),status:"checkpoint_requires_reconciliation_unrelated_generation_continues",scope:"Checkpoint subprocess has exited. Actual returns/errors imported by the sole executor. No successful validation,commit,push or readback claimed for the failed checkpoint. Future checkpoint must reconcile and validate preserved task files;no image request replay or retry."};
   await tools.apply_patch("*** Begin Patch\n*** Add File: "+root+"\\mod_nailong\\data\\checkpoint-validation-failures\\"+batch+"-"+Date.now()+".json\n+"+JSON.stringify(failure,null,2).replaceAll("\n","\n+")+"\n*** End Patch");
   checkpointFailureRecorded=true;notify(batch+": checkpoint failed and recorded separately; actual results preserved; unrelated prepared originals continue");
  }
  return true;
 };
 let deferredWithoutDispatch=0;
 while(todo.length){
  await flush();
  const key=todo.shift();
  if(pending.some(p=>p.errorFile)){
   const held=pending.filter(p=>p.errorFile).map(p=>p.key).join(',');
   const check=JSON.parse((await run("python runtime\\deferred-service-family-20261020.py "+key+" "+held,1000)).output);
   if(check.defer){todo.push(key);deferredWithoutDispatch++;notify(batch+": same-person pending service error deferred; unrelated prepared sources continue");
    if(deferredWithoutDispatch>=todo.length){await checkpoint;await flush();deferredWithoutDispatch=0;}continue;}
  }
  deferredWithoutDispatch=0;
  const j=JSON.parse((await run("python mod_nailong\\tools\\production_queue.py export-job --jobs-file "+jobFile+" --key "+key,8000)).output);
  const eligibility=JSON.parse((await run("python runtime\\guard-dispatch-family.py "+key,1600)).output);
  if(!eligibility.eligible){notify(batch+": same-person service hold preserved; no alternate request dispatched");continue;}
  const actual="runtime\\dispatch-actual\\"+batch+"-"+key+".json";
  await tools.apply_patch("*** Begin Patch\n*** Add File: "+root+"\\"+actual+"\n+"+JSON.stringify(j,null,2).replaceAll("\n","\n+")+"\n*** End Patch");
  await run("python mod_nailong\\tools\\production_queue.py begin --actual-job-file "+actual+" --key "+key);
  notify(batch+" "+(keys.indexOf(key)+1)+"/"+keys.length+": "+j.source+"; exact payload frozen; one builtin lane");await yield_control();
  // Exact original and current raw edit target already actually viewed on SHA-bound immutable comparison pages before preparation; do not re-display duplicate inputs here.
  emit("image_invoked",{key});const imageStarted=Date.now();
  const promise=tools.image_gen__imagegen({prompt:j.prompt,referenced_image_paths:j.references,transparent_background:j.transparent}).then(r=>({r}),e=>({error:String(e)}));
  if(checkpointCommand&&!checkpointStarted){checkpointStarted=true;checkpoint=run(checkpointCommand,2500).then(r=>{checkpointResult={r};return checkpointResult;},e=>{checkpointResult={error:String(e)};return checkpointResult;});}
  const outcome=await promise;
  emit("image_resolved",{key,elapsed_ms:Date.now()-imageStarted,error:outcome.error??null});
  if(outcome.error){
   const file="runtime\\"+batch+"-error-"+key+".txt";
   await tools.apply_patch("*** Begin Patch\n*** Add File: "+root+"\\"+file+"\n+"+outcome.error.replaceAll("\n","\n+")+"\n*** End Patch");
   await run("python mod_nailong\\tools\\production_queue.py returned --key "+key+" --error-file "+file);
   pending.push({key,errorFile:file});
   notify(batch+": actual error durably recorded; no immediate retry");
   if(!outcome.error.includes("moderation_blocked")){if(checkpoint)await checkpoint;await flush();throw Error(outcome.error);}
  }else{
   const path=outcome.r.output_hint?.match(/ as (C:\\[^\n]+?\.png) by default\./)?.[1];
   if(!path){store(batch+"_unparsed_"+key,outcome.r);throw Error("Actual result retained; inspect without another call");}
   await tools.apply_patch("*** Begin Patch\n*** Add File: "+root+"\\runtime\\"+batch+"-result-"+key+".json\n+"+JSON.stringify({path,output_hint:outcome.r.output_hint},null,2).replaceAll("\n","\n+")+"\n*** End Patch");
   await run("python mod_nailong\\tools\\production_queue.py returned --key "+key+" --image "+path);
   pending.push({key,path});generatedImage(outcome.r);
  }
  await flush();
 }
 if(checkpoint)await checkpoint;
 await flush();
 if(checkpointCommand&&!checkpointStarted)await run(checkpointCommand,2500);
 emit("batch_completed");
 notify(batch+" actual distinct requests finished; all returns/errors imported; no image call replayed");
}
