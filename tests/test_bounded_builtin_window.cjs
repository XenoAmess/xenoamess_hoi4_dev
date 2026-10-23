const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const source=fs.readFileSync('tools/bounded_builtin_window.js','utf8');
const producerSource=fs.readFileSync('tools/continuous_builtin_producer.js','utf8');
const key=n=>n.toString(16).padStart(64,'0');
function harness(batches,failAt=null){
 const calls=[],patches=[];let active=0,maxActive=0;
 const context={Date,Set,JSON,Error,notify:()=>{},load:()=>producerSource,tools:{
  exec_command:async({cmd,shell,login})=>{assert.equal(shell,'cmd.exe');assert.equal(login,false);return {exit_code:0,output:JSON.stringify(batches[cmd.split(' ').at(-1)])};},
  apply_patch:async p=>patches.push(p)
 }};
 const produce=async(jobs,batch,checkpoint,{onEvent})=>{
  active++;maxActive=Math.max(maxActive,active);calls.push(batch);onEvent({phase:'test_image_invoked',batch});
  await Promise.resolve();active--;
  if(batch===failAt)throw Error('ambiguous result; reconcile before resuming');
 };
 return {run:vm.runInNewContext('('+source+')',context),calls,patches,produce,maxActive:()=>maxActive};
}
test('small prepared batches advance in order through the same single executor',async()=>{
 const h=harness({'runtime/a.json':[key(1),key(2)],'runtime/b.json':[key(3)]});
 const r=await h.run([{jobs:'runtime/a.json',batch:'a'},{jobs:'runtime/b.json',batch:'b'}],{windowId:'test',producer:h.produce});
 assert.deepEqual(h.calls,['a','b']);assert.equal(h.maxActive(),1);assert.equal(r.status,'completed');
 assert.equal(r.planned_requests,3);assert.equal(h.patches.length,2);
 assert.deepEqual(Array.from(r.events.filter(e=>e.phase==='batch_imports_completed'),e=>e.batch),['a','b']);
});
test('the 8 request limit covers all batches and is checked before any call',async()=>{
 const h=harness({'runtime/a.json':Array.from({length:8},(_,i)=>key(i+1)),'runtime/b.json':[key(9)]});
 await assert.rejects(h.run([{jobs:'runtime/a.json',batch:'a'},{jobs:'runtime/b.json',batch:'b'}],{windowId:'test',producer:h.produce}),/at most 8/);
 assert.deepEqual(h.calls,[]);assert.equal(h.patches.length,0);
});
test('duplicate sources across batches cannot trigger a repeated image request',async()=>{
 const h=harness({'runtime/a.json':[key(1)],'runtime/b.json':[key(1)]});
 await assert.rejects(h.run([{jobs:'runtime/a.json',batch:'a'},{jobs:'runtime/b.json',batch:'b'}],{windowId:'test',producer:h.produce}),/duplicate/);
 assert.deepEqual(h.calls,[]);
});
test('an uncertain result stops the window without dispatching or replaying other batches',async()=>{
 const h=harness({'runtime/a.json':[key(1)],'runtime/b.json':[key(2)]},'a');
 await assert.rejects(h.run([{jobs:'runtime/a.json',batch:'a'},{jobs:'runtime/b.json',batch:'b'}],{windowId:'test',producer:h.produce}),/ambiguous/);
 assert.deepEqual(h.calls,['a']);assert.equal(h.patches.length,2);assert.match(h.patches[1],/stopped_requires_reconciliation/);
});
test('unsafe paths are rejected before invoking a shell',async()=>{
 const h=harness({});
 await assert.rejects(h.run([{jobs:'runtime/../a.json',batch:'a'}],{windowId:'test',producer:h.produce}),/Unsafe/);
 assert.deepEqual(h.calls,[]);
});
test('direct producer entry also rejects an oversized batch before image calls',async()=>{
 const events=[];let images=0;
 const context={Date,JSON,Error,tools:{exec_command:async()=>({exit_code:0,output:JSON.stringify(Array.from({length:9},(_,i)=>key(i+1)))}),image_gen__imagegen:async()=>{images++;}}};
 const produce=vm.runInNewContext('('+producerSource+')',context);
 await assert.rejects(produce('runtime/a.json','a','',{onEvent:e=>events.push(e)}),/at most8/);
 assert.equal(images,0);assert.equal(events[0].phase,'batch_started');
 assert.equal(events[1].phase,'local_command_started');assert.equal(events[2].phase,'local_command_finished');
});
