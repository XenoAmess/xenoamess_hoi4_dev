const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),test=require('node:test');
const source=fs.readFileSync('tools/rolling_builtin_queue.js','utf8');
function harness(count=3,fail=false,idle=false){
 let index=0,active=0,maxActive=0,sleeps=0;const commands=[],rendered=[],windows=[];
 const context={Date,JSON,Error,Number,notify:()=>{},yield_control:async()=>{},generatedImage:r=>rendered.push(r)};
 const run=async cmd=>{commands.push(cmd);let body={};
  if(cmd.includes(' next ')){
   if(idle&&sleeps===0)body={ready:false};
   else body={ready:true,requests:8,window_id:'run-window'+index,plan:[{batch:'b'+index,jobs:'runtime/b'+index+'.json'}]};
  }
  if(cmd.includes(' complete '))index++;
  if(cmd.includes('production_transport_preview.py'))body={preview_bytes:100,image_url:'data:image/png;base64,fixture',output_hint:'display-only fixture'};
  return {output:JSON.stringify(body)};
 };
 const producer=async(plan,{windowId,renderResult})=>{active++;maxActive=Math.max(maxActive,active);windows.push(windowId);
  if(fail)throw Error('ambiguous actual output');
  for(let i=0;i<8;i++)await renderResult({path:'C:\\fixture\\actual.png',key:String(i),batch:plan[0].batch});active--;
 };
 return {runQueue:vm.runInNewContext('('+source+')',context),options:{run,producer,sleep:async()=>{sleeps++;}},commands,rendered,windows,maxActive:()=>maxActive,sleeps:()=>sleeps};
}
test('large queue crosses three eight-request windows in one executor without model handover',async()=>{
 const h=harness();const result=await h.runQueue({runId:'run',startIndex:0,afterWindow:'prior',maxCalls:24},h.options);
 assert.equal(result.windows,3);assert.equal(result.requests,24);assert.equal(result.display_bytes,2400);
 assert.equal(h.rendered.length,24);assert.equal(h.maxActive(),1);assert.equal(h.commands.filter(c=>c.includes(' claim ')).length,1);
 assert.equal(h.commands.filter(c=>c.includes(' complete ')).length,3);assert.equal(h.commands.filter(c=>c.includes(' stop ')).length,1);
});
test('idle logical queue automatically wakes for background prepared work',async()=>{
 const h=harness(1,false,true);const result=await h.runQueue({runId:'run',startIndex:0,afterWindow:'prior',maxCalls:8},h.options);
 assert.equal(h.sleeps(),1);assert.equal(result.requests,8);assert.equal(h.commands.filter(c=>c.includes(' claim ')).length,1);
});
test('uncertain output retains owner and never marks completed or repeats request',async()=>{
 const h=harness(1,true);await assert.rejects(h.runQueue({runId:'run',startIndex:0,afterWindow:'prior',maxCalls:8},h.options),/ambiguous/);
 assert.equal(h.windows.length,1);assert.equal(h.commands.some(c=>c.includes(' complete ')),false);assert.equal(h.commands.some(c=>c.includes(' stop ')),false);
});
test('transport budget stops at a completed window instead of accumulating raw PNGs',async()=>{
 const h=harness();const result=await h.runQueue({runId:'run',startIndex:0,afterWindow:'prior',maxCalls:192,maxPreviewBytes:8*65536},h.options);
 assert.equal(result.windows,1);assert.equal(result.requests,8);assert.equal(h.commands.filter(c=>c.includes(' stop ')).length,1);
});
for(const mode of ['complete_stdout_before_final_empty_poll','json_split_across_polls'])test('default runner preserves '+mode,async()=>{
 let produced=0,polls=0;const commands=[];
 const next=JSON.stringify({ready:true,requests:8,window_id:'run-window0',plan:[{batch:'b0',jobs:'runtime/b0.json'}]});
 const prefix=mode==='complete_stdout_before_final_empty_poll'?next:next.slice(0,17),tail=mode==='complete_stdout_before_final_empty_poll'?'':next.slice(17);
 const context={Date,JSON,Error,Number,notify:()=>{},yield_control:async()=>{},generatedImage:()=>{},store:()=>{},tools:{
  exec_command:async({cmd})=>{commands.push(cmd);return cmd.includes(' next ')?{session_id:77,output:prefix}:{exit_code:0,output:''};},
  write_stdin:async({session_id})=>{assert.equal(session_id,77);polls++;return {exit_code:0,output:tail};}
 }};
 const runQueue=vm.runInNewContext('('+source+')',context);
 const result=await runQueue({runId:'run',startIndex:0,afterWindow:'prior',maxCalls:8},{producer:async()=>{produced++;}});
 assert.equal(produced,1);assert.equal(polls,1);assert.equal(result.windows,1);assert.equal(commands.filter(c=>c.includes(' complete ')).length,1);
});
