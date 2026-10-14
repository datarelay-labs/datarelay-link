// WU1: user-visible workflow contracts. SSR is not real browser/User E2E.
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
let ui,scratch;
const admin={id:'operator-admin',username:'admin',role:'Admin'};
const page=(items=[],next_cursor=null)=>({resource_type:'managed-host',limit:100,items,next_cursor});
const host=(id='host-a',extra={})=>({id,name:'Server A',hostname:'server-a',admission_state:'APPROVED',connected:1,trust_status:'trusted',agent_platform:'linux',agent_version:'3.0.0',...extra});
const render=(data,extra={})=>renderToStaticMarkup(React.createElement(ui.ServerWorkspace,{data,operator:admin,api:async()=>{throw new Error('SSR must not call API')},...extra}));
before(async()=>{
  scratch=mkdtempSync(join(root,'node_modules','.workflow-servers-'));
  const out=join(scratch,'servers.mjs');
  await build({entryPoints:[join(root,'src','workflow-servers.tsx')],outfile:out,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react/jsx-runtime'],logLevel:'silent'});
  ui=await import(pathToFileURL(out).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

test('only a validated complete empty page opens first-server onboarding',()=>{
  assert.equal(ui.serverPageState(page()),'empty');
  assert.equal(ui.serverPageState(page([host()])),'populated');
  for(const bad of [null,{},[],{items:[]},page([],'cursor-a'),page([host(),host()]),{...page(),resource_type:'remote-service'},page([{name:'missing-id'}])]){
    assert.equal(ui.serverPageState(bad),'unavailable');
  }
});
test('empty viewport is a connection diagram and one Add server primary action, not a form wall',()=>{
  const html=render(page());
  assert.match(html,/Connect your first server/);
  assert.match(html,/aria-label="How remote access works"/);
  assert.match(html,/Your device/);
  assert.match(html,/DataRelay Link/);
  assert.match(html,/Internal server/);
  assert.equal((html.match(/>Add server</g)||[]).length,1);
  assert.match(html,/Already installed an Agent/);
  assert.doesNotMatch(html,/<table|Search servers|Guided Managed Host|Quarantine|Lifecycle|Sort loaded|Clear Host filters/);
});
test('read-only and unrecognized actors are never offered enrollment or mutation',()=>{
  for(const operator of [{...admin,role:'Read Only'},{...admin,role:'Operator'},{...admin,role:'ROOT'},{role:'Admin'},null]){
    const html=render(page(),{operator});
    assert.doesNotMatch(html,/>Add server</);
    assert.match(html,/Ask an Admin/);
  }
});
test('invalid inventory is unavailable, not an empty or healthy system',()=>{
  const html=render({items:[]});
  assert.match(html,/Server inventory unavailable/);
  assert.match(html,/Retry/);
  assert.doesNotMatch(html,/Connect your first server|Healthy/);
});
test('populated page puts six concise columns and status tabs before optional details',()=>{
  const html=render(page([host(),host('host-b',{name:'Pending node',admission_state:'PENDING_APPROVAL',connected:0})]));
  assert.match(html,/aria-label="Server status filters"/);
  assert.match(html,/All servers/);
  assert.match(html,/Pending approval/);
  assert.match(html,/Connection needs review/);
  assert.match(html,/placeholder="Search servers/);
  assert.equal((html.match(/<th\b/g)||[]).length,6);
  assert.match(html,/>Filters</);
  assert.match(html,/>Technical details</);
  assert.doesNotMatch(html,/Guided Managed Host Metadata|Managed Host Change Plan|Managed Host Lifecycle/);
});
test('no search match retains filters and never shows first-install onboarding',()=>{
  const html=render(page([host()]),{initialFilter:'name:missing'});
  assert.match(html,/No matching servers/);
  assert.match(html,/Clear filters/);
  assert.doesNotMatch(html,/Connect your first server/);
});
test('incomplete inventory and unknown connection remain explicitly qualified',()=>{
  const html=render(page([host('host-a',{connected:'true'})],'cursor-next'));
  assert.match(html,/loaded servers/);
  assert.match(html,/Load more/);
  assert.match(html,/Not reported/);
  assert.doesNotMatch(html,/All connections healthy|Connection verified/);
});
test('next action is contextual and does not assert a successful service connection',()=>{
  assert.equal(ui.serverNextAction(host('a',{admission_state:'PENDING_APPROVAL'}),admin),'approval');
  assert.equal(ui.serverNextAction(host('a',{connected:0}),admin),'diagnose');
  assert.equal(ui.serverNextAction(host('a',{connected:'true'}),admin),'diagnose');
  assert.equal(ui.serverNextAction(host(),admin),'services');
  assert.equal(ui.serverNextAction(host('a',{admission_state:'QUARANTINED'}),{...admin,role:'Read Only'}),'details');
  assert.equal(ui.serverNextAction(host(),{role:'Admin'}),'details');
});
test('only an exactly selected authorized server receives its management renderer',()=>{
  let called=0;
  const management=(row,action)=>{called++;return React.createElement('p',null,`Bound ${action}: ${row.id}`)};
  const html=render(page([host()]),{initialInspectId:'host-a',renderManagement:management});
  assert.match(html,/aria-label="Server details"/);
  assert.match(html,/Overview/);assert.match(html,/Services/);assert.match(html,/Activity/);assert.match(html,/Settings/);
  assert.equal(called,0,'Opening details must not immediately expose sensitive forms');
  const missing=render(page([host()]),{initialInspectId:'missing',renderManagement:management});
  assert.doesNotMatch(missing,/aria-label="Server details"/);
});
test('server detail allowlists facts and escapes untrusted visible text',()=>{
  const html=render(page([host('host-a',{name:'<script>alert(1)</script>',password:'SECRET_PW',api_key:'SECRET_KEY',payload:{secret:'SECRET_NESTED'}})]),{initialInspectId:'host-a'});
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script|SECRET_/);
});
test('real host route uses workflow surface and target-bound panels, not extra page-bottom forms',()=>{
  const main=readFileSync(join(root,'src','main.tsx'),'utf8');
  const line=main.split('\n').find(x=>x.includes('if(active==="hosts"&&data)'))||'';
  assert.match(line,/<ServerWorkspace/);
  assert.doesNotMatch(line,/<ManagedHostMetadataPanel\/>|<ManagedHostAdmissionPanel\/>|<ManagedHostLifecyclePanel\/>/);
  assert.match(main,/function SelectedServerManagement/);
  assert.match(main,/selectedHostId/);
});
test('detail uses focus containment, Escape dismissal and return-to-trigger; mobile CSS is scoped',()=>{
  const source=readFileSync(join(root,'src','workflow-servers.tsx'),'utf8');
  assert.match(source,/aria-modal="true"/);
  assert.match(source,/event.key==="Tab"/);
  assert.match(source,/event.key==="Escape"/);
  assert.match(source,/previous\?\.focus/);
  const css=readFileSync(join(root,'dist','styles.css'),'utf8');
  assert.match(css,/\.dr-workflow-servers/);
  assert.match(css,/\.dr-server-sheet/);
  assert.match(css,/min-height:44px/);
  assert.match(css,/@media\s*\(max-width:700px\)/);
});

test('explicit partial or stale empty evidence is never first-use setup',()=>{
  for(const flag of [{partial:true},{truncated:true},{complete:false},{stale:true}])assert.equal(ui.serverPageState({...page(),...flag}),'unavailable');
  for(const readState of ['refreshing','stale'])assert.doesNotMatch(render(page(),{readState}),/Connect your first server|>Add server</);
  assert.doesNotMatch(render(page(),{initialFilter:'id:missing'}),/Connect your first server/);
});
test('lifecycle plan must match immutable selected identity, action, confirmation, revision and expiry',()=>{
  const at=Date.now();
  const plan={change_plan_id:'cp_'+ 'x'.repeat(24),operation_class:'CHANGE',operation:'managed-host-lifecycle.revoke-trust',resource_type:'managed-host',resource_ref:'host-a',expected_revision:5,confirmation_class:'REVOKE',valid_until:new Date(at+300000).toISOString(),lifecycle_operation:'revoke-trust',no_change:false,preview:{entity:{type:'managed-host',id:'host-a',name:'Server A'},operation:'revoke-trust'},impact:{requires_confirmation:true,destructive:false,warning:'Re-enrollment required',kept:['published services','public port reservations']}};
  assert.ok(ui.observedServerLifecyclePlan(plan,'host-a','revoke-trust',at));
  for(const bad of [{...plan,resource_ref:'host-b'},{...plan,confirmation_class:'RETIRE'},{...plan,expected_revision:'5'},{...plan,valid_until:new Date(at-1).toISOString()},{...plan,preview:{...plan.preview,entity:{type:'managed-host',id:'host-b'}}},{...plan,no_change:'false'}])assert.equal(ui.observedServerLifecyclePlan(bad,'host-a','revoke-trust',at),null);
  const receipt={status:'APPLIED',revision:6,lifecycle_operation:'revoke-trust'};
  assert.equal(ui.requireServerLifecycleReceipt(receipt,plan).revision,6);
  for(const bad of [{revision:6},{...receipt,revision:5},{...receipt,lifecycle_operation:'retire'}])assert.throws(()=>ui.requireServerLifecycleReceipt(bad,plan));
});
