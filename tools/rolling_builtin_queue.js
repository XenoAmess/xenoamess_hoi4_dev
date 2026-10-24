async function runLogicalQueue(spec,options={}) {
 const root="C:\\workspace\\xenoamess_hoi4_dev";
 if(!/^[A-Za-z0-9_-]+$/.test(spec.runId||""))throw Error("Safe run identity required");
 const maxCalls=spec.maxCalls??192,maxBytes=spec.maxPreviewBytes??(16*1024*1024);
 if(!Number.isInteger(maxCalls)||maxCalls<1||maxCalls>192||maxBytes<8*65536||maxBytes>16*1024*1024)throw Error("Invalid logical transport bounds");
 const run=options.run||(async(cmd,budget=2500)=>{
  let r=await tools.exec_command({cmd,shell:"cmd.exe",login:false,workdir:root,max_output_tokens:budget});
  let output=r.output||"";
  while(r.session_id){r=await tools.write_stdin({session_id:r.session_id,chars:"",yield_time_ms:1000,max_output_tokens:budget});output+=r.output||"";}
  r={...r,output};store(spec.runId+"_last_local_result",{command:cmd,result:r,observed_at_utc:new Date().toISOString()});
  if(r.exit_code!==0)throw Error(JSON.stringify(r));return r;
 });
 const sleep=options.sleep||(ms=>new Promise(resolve=>setTimeout(resolve,ms)));
 const produceWindow=options.producer||eval("("+load("bounded_window_source")+")");
 const started=Date.now();let requests=0,displayBytes=0,windows=0,wasIdle=false;
 let lastCheckpoint=started-(spec.checkpointIntervalSeconds??1800)*1000;
 await run("python tools\\rolling_production_queue.py claim "+spec.runId+" --index "+spec.startIndex+" --after "+spec.afterWindow);
 const renderResult=async({path,key,batch})=>{
  if(!/^C:\\[A-Za-z0-9_\\.\/-]+\.png$/i.test(path))throw Error("Unsafe actual PNG path; preserve result for reconciliation");
  const preview=JSON.parse((await run('python tools\\production_transport_preview.py --image '+path,40000)).output);
  if(preview.preview_bytes>65536||!preview.image_url.startsWith("data:image/png;base64,"))throw Error("Display transport budget violated");
  displayBytes+=preview.preview_bytes;
  generatedImage({image_url:preview.image_url,output_hint:preview.output_hint});
 };
 try{
  while(requests+8<=maxCalls&&displayBytes+8*65536<=maxBytes&&Date.now()-started<(spec.maxRunSeconds??21600)*1000){
   const next=JSON.parse((await run("python tools\\rolling_production_queue.py next "+spec.runId)).output);
   if(next.stop_requested)break;
   if(!next.ready){
    if(!wasIdle)notify(spec.runId+": logical queue waiting for allowed prepared/manual-reviewed HIGH work; owner retained, automatic wake, no image replay");
    wasIdle=true;await sleep(5000);continue;
   }
   wasIdle=false;
   if(!options.producer&&Date.now()-lastCheckpoint>=(spec.checkpointIntervalSeconds??1800)*1000
      &&(next.requests>=4||Date.now()-lastCheckpoint>=3600000)){
    next.plan[0].checkpointCommand="python tools\\production_checkpoint.py "+next.plan[0].batch;
    lastCheckpoint=Date.now();
   }
   await produceWindow(next.plan,{windowId:next.window_id,renderResult});
   requests+=next.requests;windows++;
   await run("python tools\\rolling_production_queue.py complete "+spec.runId);
   notify(spec.runId+": logical queue advanced automatically through window "+windows+", requests "+requests+", bounded display bytes "+displayBytes);
   await yield_control();
  }
  await run("python tools\\rolling_production_queue.py stop "+spec.runId+" --reason bounded_transport_or_run_duration");
  return {run_id:spec.runId,windows,requests,display_bytes:displayBytes,status:"safe_boundary"};
 }catch(error){
  notify(spec.runId+": logical owner retained after failure; reconcile actual ledger/prepared jobs before resuming; "+String(error));
  throw error;
 }
}
