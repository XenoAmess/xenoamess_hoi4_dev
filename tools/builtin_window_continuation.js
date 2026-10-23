async function continueWindow(spec) {
 const root="C:\\workspace\\xenoamess_hoi4_dev";
 for(const value of [spec.afterWindow,spec.windowId])if(!/^[a-zA-Z0-9_-]+$/.test(value||""))throw Error("Explicit safe window identities required");
 const events=[],emit=(phase,extra={})=>events.push({phase,observed_at_utc:new Date().toISOString(),...extra});
 const run=async cmd=>{
  emit("command_started",{command:cmd});
  let r=await tools.exec_command({cmd,shell:"cmd.exe",login:false,workdir:root,max_output_tokens:2200});
  while(r.session_id)r=await tools.write_stdin({session_id:r.session_id,chars:"",yield_time_ms:1000,max_output_tokens:2200});
  emit("command_finished",{command:cmd,exit_code:r.exit_code});
  if(r.exit_code!==0)throw Error(JSON.stringify(r));return r;
 };
 const receipt={machine_id:"bf-202609141645-5434332d4d",window_id:spec.windowId,after_window:spec.afterWindow,created_at_utc:new Date().toISOString(),prepare_commands:spec.prepareCommands||[],events,scope:"Disk receipt gates the next sole executor; cross-exec in-memory store values are not used to release a handover. Preparation occurs only after the exact preceding window has completed imports."};
 const persist=async suffix=>await tools.apply_patch("*** Begin Patch\n*** Add File: "+root+"\\mod_nailong\\data\\production-window-timings\\"+spec.windowId+"-continuation-"+suffix+".json\n+"+JSON.stringify(receipt,null,2).replaceAll("\n","\n+")+"\n*** End Patch");
 await persist("started");
 try{
  const gate=JSON.parse((await run("python tools\\production_window_gate.py "+spec.afterWindow+" --wait-seconds 900")).output);
  if(!gate.ready||gate.window_id!==spec.afterWindow)throw Error("No exact durable handover");
  emit("durable_gate_released",gate);
  await run("python mod_nailong\\tools\\production_queue.py apply-reviews");
  for(const command of spec.prepareCommands||[])await run(command);
  receipt.status="prepared_for_next_window";receipt.prepared_at_utc=new Date().toISOString();
  await persist("prepared");
  const window=spec.producer||eval("("+load("bounded_window_source")+")");
  await window(spec.plan,{windowId:spec.windowId});
  receipt.status="completed";receipt.completed_at_utc=new Date().toISOString();
  await persist("completed");
 }catch(error){
  receipt.status="stopped_requires_reconciliation";receipt.error=String(error);
  await persist("stopped");throw error;
 }
}
