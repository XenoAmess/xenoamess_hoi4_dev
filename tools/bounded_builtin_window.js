async function produceWindow(plan, options={}) {
 const root="C:\\workspace\\xenoamess_hoi4_dev";
 const windowId=options.windowId;
 if(!/^[a-zA-Z0-9_-]+$/.test(windowId||""))throw Error("An explicit safe windowId is required");
 if(!Array.isArray(plan)||!plan.length)throw Error("A nonempty prepared plan is required");
 const events=[],seen=new Set();let total=0;
 const emit=(phase,detail={})=>events.push({phase,observed_at_utc:new Date().toISOString(),...detail});
 const run=async cmd=>{
  let r=await tools.exec_command({cmd,shell:"cmd.exe",login:false,workdir:root,max_output_tokens:4000});
  while(r.session_id)r=await tools.write_stdin({session_id:r.session_id,chars:"",yield_time_ms:1000,max_output_tokens:4000});
  if(r.exit_code!==0)throw Error(JSON.stringify(r));return r;
 };
 // Inspect the entire bounded plan before the first irreversible image dispatch.
 for(const item of plan){
  if(!/^[a-zA-Z0-9_-]+$/.test(item.batch||"")||!/^runtime[\\/][a-zA-Z0-9_\\/.-]+\.json$/.test(item.jobs||"")||item.jobs.split(/[\\/]/).includes(".."))throw Error("Unsafe batch or jobs path");
  const keys=JSON.parse((await run("python runtime\\batch-keys.py "+item.jobs)).output);
  if(!Array.isArray(keys)||!keys.length)throw Error("Empty or invalid prepared batch");
  for(const key of keys){
   if(!/^[0-9a-f]{64}$/.test(key)||seen.has(key))throw Error("Invalid or duplicate source across prepared batches");
   seen.add(key);
  }
  total+=keys.length;
  if(total>8)throw Error("Window accepts at most 8 requests in total; preserve the IPC bound");
 }
 const report={schema_version:1,machine_id:"bf-202609141645-5434332d4d",window_id:windowId,started_at_utc:new Date().toISOString(),planned_requests:total,batches:plan.map(x=>({batch:x.batch,jobs:x.jobs})),events};
 const persist=async suffix=>{
  const path=root+"\\mod_nailong\\data\\production-window-timings\\"+windowId+"-"+suffix+".json";
  await tools.apply_patch("*** Begin Patch\n*** Add File: "+path+"\n+"+JSON.stringify(report,null,2).replaceAll("\n","\n+")+"\n*** End Patch");
 };
 await persist("started");
 try{
  const produce=options.producer||eval("("+load("bounded_produce_source")+")");
  for(const item of plan){
   emit("batch_dispatch_started",{batch:item.batch});
   await produce(item.jobs,item.batch,item.checkpointCommand||"",{onEvent:e=>events.push(e),renderResult:options.renderResult});
   emit("batch_imports_completed",{batch:item.batch});
   // The same executor advances immediately; no model/review/documentation turn here.
  }
  report.status="completed";report.completed_at_utc=new Date().toISOString();
  await persist("completed");
  notify(windowId+": bounded prepared plan completed; "+total+" requests maximum, one builtin lane");
 }catch(error){
  report.status="stopped_requires_reconciliation";report.error=String(error);report.stopped_at_utc=new Date().toISOString();
  await persist("stopped");throw error;
 }
 return report;
}
