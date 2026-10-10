// UXB-06F: supplementary contract evidence only; not a logged-in browser/User E2E.
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {mkdtempSync,rmSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {build} from 'esbuild';
const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,menu;
before(async()=>{
  scratch=mkdtempSync(join(root,'node_modules','.uxb-menu-evidence-'));
  const outfile=join(scratch,'evidence.mjs');
  await build({entryPoints:[join(root,'src','uxb-menu-evidence.ts')],outfile,
    bundle:true,platform:'node',format:'esm',logLevel:'silent'});
  menu=await import(pathToFileURL(outfile).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

test('each Core collection menu recognizes real observed emptiness, not a broken response',()=>{
  for(const route of ['hosts','services','policies','enrollments','hygiene','jobs','audit','revisions','views','users','service-accounts','webhooks']){
    const empty={items:[]};
    assert.equal(menu.requireObservedMenuPayload(route,empty),empty,route);
    const populated={items:[{id:'observed'}]};
    assert.equal(menu.requireObservedMenuPayload(route,populated),populated,route);
    for(const bad of [null,undefined,{}, {items:null},{items:{}},{items:''},{items:false},
      {items:0},{items:[null]},{items:['invalid']},{items:[[]]},{items:[],next_cursor:42},
      {error:'Core unavailable'},[]]){
      assert.throws(()=>menu.requireObservedMenuPayload(route,bad),/Core|UNKNOWN/,route);
    }
  }
});
test('structurally required non-item Core pages remain UNKNOWN without evidence',()=>{
  for(const [route,valid,broken] of [
    ['doctor',{checks:[]},{checks:null}],
    ['versions',{hosts:[]},{hosts:'unknown'}],
    ['overview',{overview:{managed_hosts:{total:0}}},{overview:null}],
  ]){
    assert.equal(menu.requireObservedMenuPayload(route,valid),valid);
    assert.throws(()=>menu.requireObservedMenuPayload(route,broken),/Core|UNKNOWN/);
  }
});
test('Core pagination is visible and local filters never imply a complete list',()=>{
  for(const response of [null,undefined,{items:[]},{items:[],next_cursor:null},
    {items:[],next_cursor:''},{items:[],next_cursor:7}]){
    assert.equal(menu.isPartialCorePage(response),false);
  }
  const paged={items:[{id:'loaded'}],next_cursor:'opaque-core-cursor'};
  assert.equal(menu.isPartialCorePage(paged),true);
  assert.equal(menu.requireObservedMenuPayload('hosts',paged),paged);
  assert.equal(menu.requireObservedMenuPayload('policies',paged),paged);
});
test('Managed Host and Remote Service pagination accepts only matching observed Core pages',()=>{
  const cursor='observed-opaque-core-page';
  for(const [route,resource_type] of [
    ['hosts','managed-host'],['services','remote-service']
  ]){
    const page={resource_type,limit:100,items:[{id:'item-101',name:'Observed'}],next_cursor:null};
    assert.equal(menu.requireObservedInventoryContinuation(route,page,cursor,100),page);
    for(const wrong of [
      {...page,resource_type:route==='hosts'?'remote-service':'managed-host'},
      {...page,limit:50},
      {...page,items:[{id:''}]},
      {...page,items:[{id:17}]},
      {...page,items:Array.from({length:101},(_,i)=>({id:String(i)}))},
      {...page,items:[],next_cursor:'unearned-next-page'},
      {...page,next_cursor:cursor},
      {...page,items:null},
      {error:'Core unreachable'},
    ]){
      assert.throws(()=>menu.requireObservedInventoryContinuation(route,wrong,cursor,100),
        /Core|UNKNOWN/,route);
    }
  }
});

test('each Objects & Groups family consumes only its authorized Core inventory cursor',()=>{
  const cursor='opaque-object-list-cursor';
  for(const type of ['network-object','network-group','service-object','service-group',
    'permission-object','permission-group','ai-identity']){
    const page={resource_type:type,limit:50,items:[{id:'object-51',name:'Observed'}],next_cursor:null};
    assert.equal(menu.requireObservedObjectContinuation(type,page,cursor,50),page);
    for(const bad of [
      {...page,resource_type:'managed-host'}, {...page,limit:100},
      {...page,items:[null]}, {...page,items:[{id:''}]},
      {...page,items:Array.from({length:51},(_,i)=>({id:String(i)}))},
      {...page,next_cursor:cursor}, {items:null}, null,
    ]){
      assert.throws(()=>menu.requireObservedObjectContinuation(type,bad,cursor,50),
        /Core|UNKNOWN/,type);
    }
  }
  assert.throws(()=>menu.requireObservedObjectContinuation(
    'invalid-object-type',{resource_type:'invalid-object-type',limit:50,items:[]},cursor,50),
    /Core|UNKNOWN/);
});
test('Audit keyset backward and forward pagination uses opaque observed Core cursors only',()=>{
  const start={cursor:'',history:[]};
  assert.deepEqual(menu.selectMenuPage(start,'cursor-page-2','older'),
    {cursor:'cursor-page-2',history:['']});
  const page2=menu.selectMenuPage(start,'cursor-page-2','older');
  assert.deepEqual(menu.selectMenuPage(page2,'cursor-page-3','older'),
    {cursor:'cursor-page-3',history:['','cursor-page-2']});
  const page3=menu.selectMenuPage(page2,'cursor-page-3','older');
  assert.deepEqual(menu.selectMenuPage(page3,null,'newer'),page2);
  assert.deepEqual(menu.selectMenuPage(page2,null,'newer'),start);
  assert.deepEqual(menu.selectMenuPage(page3,null,'reset'),start);
  assert.equal(menu.selectMenuPage(start,null,'newer'),null);
  for(const invalid of [null,undefined,{},'',false,'cursor-page-2']){
    assert.equal(menu.selectMenuPage(page2,invalid,'older'),null);
  }
});
test('large Remote policy family cannot hide observed Internet or AI rules',()=>{
  const corePage=(plane,ids,limit=2)=>({plane,limit,
    items:ids.map(id=>({id,plane,name:id}))});
  const pages=[
    corePage('remote',['r-1','r-2']),
    corePage('internet',['i-1']),
    corePage('ai',['a-1'])
  ];
  const observed=menu.combineObservedPolicyPlanes(pages,2);
  assert.deepEqual(observed.items.map(row=>row.id),['r-1','r-2','i-1','a-1']);
  assert.deepEqual(observed.possibly_truncated_planes,['remote']);
  assert.deepEqual(observed.next_cursor_by_plane,{remote:null,internet:null,ai:null});
  assert.deepEqual(menu.combineObservedPolicyPlanes(pages.map(page=>({...page,items:[]})),2),
    {items:[],possibly_truncated_planes:[],next_cursor_by_plane:{remote:null,internet:null,ai:null}});
  const withCursors=menu.combineObservedPolicyPlanes(
    pages.map((page,i)=>({...page,next_cursor:i===0?'opaque-next-page':null})),2);
  assert.equal(withCursors.next_cursor_by_plane.remote,'opaque-next-page');
  assert.deepEqual(withCursors.possibly_truncated_planes,['remote']);
  const lastPage=menu.combineObservedPolicyPlanes(
    pages.map(page=>({...page,next_cursor:null})),2);
  assert.deepEqual(lastPage.possibly_truncated_planes,[]);
  for(const bad of [
    pages.slice(0,2),null,[],[pages[1],pages[0],pages[2]],
    [pages[0],{plane:'internet',limit:2,items:null},pages[2]],
    [pages[0],{...pages[1],items:[{id:'wrong',plane:'remote'}]},pages[2]],
    [pages[0],{...pages[1],limit:1},pages[2]],
    [pages[0],{...pages[1],items:[{plane:'internet'},{plane:'internet'},{plane:'internet'}]},pages[2]],
  ]){
    assert.throws(()=>menu.combineObservedPolicyPlanes(bad,2),/Core|UNKNOWN/);
  }
});
test('Audit retention status is never fabricated as Normal or zero from missing Core evidence',()=>{
  const full={config:{control_days:365,access_days:90,max_events:500000},
    total_events:0,db_size_bytes:0,capacity_exceeded:false,
    capacity_policy:"Core separates control and access retention"};
  assert.deepEqual(menu.requireObservedAuditRetention(full),full);
  assert.equal(menu.requireObservedAuditRetention({...full,total_events:17,db_size_bytes:943,
    capacity_exceeded:true}).capacity_exceeded,true);
  for(const broken of [null,undefined,{},[],{error:"offline"},
    {...full,total_events:undefined},{...full,total_events:-1},
    {...full,total_events:"0"},{...full,db_size_bytes:null},
    {...full,capacity_exceeded:undefined},{...full,capacity_exceeded:"false"},
    {...full,config:null},{...full,config:{control_days:365,access_days:90}},
    {...full,config:{control_days:365,access_days:0,max_events:500000}},
    {...full,capacity_policy:12}]){
    assert.throws(()=>menu.requireObservedAuditRetention(broken),/UNKNOWN/);
  }
});
test('Irreversible audit retention cannot run without exact typed review of observed saved policy',()=>{
  const core={config:{control_days:365,access_days:90,max_events:500000},
    total_events:4,db_size_bytes:1024,capacity_exceeded:false,
    capacity_policy:"Age and capacity"};
  const form={control_days:"365",access_days:"90",max_events:"500000"};
  assert.equal(menu.auditRetentionRunPermitted(core,form,"ready",false,"RUN RETENTION"),true);
  for(const [snapshot,input,status,busy,confirm] of [
    [core,form,"loading",false,"RUN RETENTION"],
    [core,form,"unknown",false,"RUN RETENTION"],
    [core,form,"ready",true,"RUN RETENTION"],
    [core,form,"ready",false,"RUN"],
    [core,form,"ready",false,"run retention"],
    [core,{...form,control_days:"7"},"ready",false,"RUN RETENTION"],
    [core,{...form,max_events:"200"},"ready",false,"RUN RETENTION"],
    [core,{...form,access_days:""},"ready",false,"RUN RETENTION"],
    [{...core,capacity_exceeded:"false"},form,"ready",false,"RUN RETENTION"],
    [null,form,"ready",false,"RUN RETENTION"]
  ]){
    assert.equal(menu.auditRetentionRunPermitted(snapshot,input,status,busy,confirm),false);
  }
});
test('Access Hygiene requires Core read-only evidence and truthful total/unknown counts',()=>{
  const sample={items:[],count:0,summary:{action_required:0,unknown_evidence:0},
    authoritative:false,read_only:true,auto_mutation:false,
    generated_at:"2026-10-09T00:00:00Z"};
  assert.equal(menu.requireObservedAccessHygiene(sample),sample);
  const partial={...sample,items:[{resource_type:'managed-host',resource_id:'host-1'}],count:2,
    summary:{action_required:1,unknown_evidence:1}};
  assert.equal(menu.requireObservedAccessHygiene(partial),partial);
  for(const bad of [null,{}, {items:[]},
    {...sample,count:undefined},{...sample,count:-1},{...sample,count:'0'},
    {...sample,count:0,items:[{resource_type:'object'}]},
    {...sample,summary:{}},{...sample,summary:{action_required:0,unknown_evidence:'0'}},
    {...sample,summary:{action_required:1,unknown_evidence:0}},
    {...sample,read_only:false},{...sample,authoritative:true},
    {...sample,auto_mutation:true},{...sample,generated_at:undefined},
    {...sample,items:Array.from({length:201},()=>({}))}]){
    assert.throws(()=>menu.requireObservedAccessHygiene(bad),/UNKNOWN/);
  }
});
test('Access Hygiene inspect has only meaningful authorized destinations',()=>{
  assert.deepEqual(menu.hygieneInspectTarget('managed-host','Read Only'),{route:'hosts',group:'connections'});
  assert.deepEqual(menu.hygieneInspectTarget('object','Operator'),{route:'objects',group:'access'});
  assert.deepEqual(menu.hygieneInspectTarget('access-rule','Read Only'),{route:'policies',group:'access'});
  assert.deepEqual(menu.hygieneInspectTarget('service-account','Admin'),{route:'integrations',group:'administration'});
  assert.equal(menu.hygieneInspectTarget('service-account','Operator'),null);
  assert.equal(menu.hygieneInspectTarget('service-account','Read Only'),null);
  assert.equal(menu.hygieneInspectTarget('unsupported','Admin'),null);
  assert.equal(menu.hygieneInspectTarget(null,'Admin'),null);
});
test('A diagnostic Job response cannot fabricate an accepted zero-target Queue from incomplete Core data',()=>{
  const valid={job:{id:'mjob_123',job_type:'doctor',status:'QUEUED',target_count:2},
    selection:{target_count:2,resource_type:'managed-host'}};
  assert.equal(menu.requireObservedJobStart(valid,'doctor'),valid);
  for(const invalid of [null,{}, {job:null,selection:null}, {...valid,job:{...valid.job,id:''}},
    {...valid,job:{...valid.job,job_type:'refresh'}},
    {...valid,job:{...valid.job,status:'SUCCEEDED'}},
    {...valid,job:{...valid.job,target_count:undefined}},
    {...valid,job:{...valid.job,target_count:0}},
    {...valid,selection:{target_count:0,resource_type:'managed-host'}},
    {...valid,selection:{target_count:2,resource_type:'remote-service'}},
    {...valid,job:{...valid.job,target_count:101}}
  ]){
    assert.throws(()=>menu.requireObservedJobStart(invalid,'doctor'),/UNKNOWN/);
  }
});
test('Fleet apply reports completion only when Core confirms APPLIED revision and targets',()=>{
  const valid={status:'APPLIED',revision:17,result:{target_count:2}};
  assert.equal(menu.requireObservedFleetApply(valid),valid);
  for(const invalid of [null,{}, {...valid,status:'QUEUED'},
    {...valid,revision:undefined},{...valid,revision:'17'},
    {...valid,result:null},{...valid,result:{target_count:0}},
    {...valid,result:{target_count:101}},{...valid,result:{target_count:'2'}}
  ]){
    assert.throws(()=>menu.requireObservedFleetApply(invalid),/UNKNOWN/);
  }
});
test('Audit Export reports CREATED only for the actual Core artifact and requested filters',()=>{
  const requested={category:'CONTROL',actor:'alice'};
  const verified={
    status:'CREATED',path:'/var/lib/drlink/audit-exports/drlink-audit-20261009T135012Z-1234abcd.ndjson',
    sha256:'a'.repeat(64),schema_version:1,size_bytes:500,event_count:0,
    sanitized:true,download_exposed:false,authoritative_mutation:false,
    filters:{actor:'alice',category:'CONTROL'}
  };
  assert.equal(menu.requireObservedAuditExport(verified,requested),verified);
  assert.equal(menu.requireObservedAuditExport({...verified,filters:{}},{}).event_count,0);
  for(const bad of [null,{},[],{error:'Core unavailable'},
    {...verified,status:'QUEUED'},{...verified,path:'/tmp/preview.ndjson'},
    {...verified,path:'/var/lib/drlink/audit-exports/../../secret.ndjson'},
    {...verified,sha256:''},{...verified,sha256:'0'.repeat(63)},
    {...verified,schema_version:0},{...verified,size_bytes:0},
    {...verified,size_bytes:67108865},{...verified,event_count:-1},
    {...verified,event_count:50001},{...verified,event_count:'0'},
    {...verified,sanitized:false},{...verified,download_exposed:true},
    {...verified,authoritative_mutation:true},
    {...verified,filters:{category:'CONTROL'}},
    {...verified,filters:{...requested,extra:'data'}},
    {...verified,filters:{...requested,actor:'bob'}},
  ]){
    assert.throws(()=>menu.requireObservedAuditExport(bad,requested),/UNKNOWN/);
  }
  assert.throws(()=>menu.requireObservedAuditExport(verified,{category:'CONTROL',actor:12}),/UNKNOWN/);
});
test('Agent rollout preview is advisory for exactly the Core-observed requested targets',()=>{
  const request={targets:['host-b','host-a','host-b'],canary_targets:[],
    artifact:{version:'3.0.0-rc.1',source_ref:'a'.repeat(40),sha256:'b'.repeat(64)},
    wave_size:1,failure_threshold_percent:20};
  const row=(id)=>({target_id:id,current_version:'unknown',target_version:'3.0.0-rc.1',
    platform:'unknown',version_relation:'UNKNOWN',last_heartbeat:null,
    provenance:'NOT_VERIFIED',update_available:'UNKNOWN'});
  const valid={read_only:true,eligible:false,ready_to_apply:false,creates_job:false,
    requires_fresh_validation_on_apply:true,artifact_qualification:'NOT_VERIFIED',
    qualification_note:'Artifact identity only; signed delivery not qualified',
    targets:['host-b','host-a'],target_count:2,blocked_targets:['host-a'],
    canary_targets:['host-b'],wave_size:1,failure_threshold_percent:20,
    artifact:request.artifact,target_observations:[row('host-b'),row('host-a')]};
  assert.equal(menu.requireObservedRolloutPreview(valid,request),valid);
  assert.equal(menu.requireObservedRolloutPreview({...valid,eligible:true,blocked_targets:[]},request).eligible,true);
  for(const bad of [
    null,{}, {error:'Core unavailable'},
    {...valid,read_only:false},{...valid,ready_to_apply:true},
    {...valid,creates_job:true},{...valid,requires_fresh_validation_on_apply:false},
    {...valid,artifact_qualification:'PASS'},{...valid,eligible:true},
    {...valid,targets:['host-a','host-b']},{...valid,target_count:0},
    {...valid,blocked_targets:['outsider']},{...valid,canary_targets:['host-a']},
    {...valid,wave_size:2},{...valid,failure_threshold_percent:21},
    {...valid,artifact:{...request.artifact,sha256:'c'.repeat(64)}},
    {...valid,target_observations:[row('host-a')]},
    {...valid,target_observations:[{...row('host-b'),provenance:'VERIFIED'},row('host-a')]},
    {...valid,target_observations:[{...row('host-b'),update_available:'YES'},row('host-a')]},
    {...valid,target_observations:[{...row('host-b'),target_version:'2.0.0'},row('host-a')]},
  ]){
    assert.throws(()=>menu.requireObservedRolloutPreview(bad,request),/UNKNOWN/);
  }
});
test('Inventory Export cannot claim CREATED without a real bounded Core artifact',()=>{
  const counts={managed_hosts:2,remote_services:1,managed_host_groups:1,managed_host_tags:3};
  const limits={managed_hosts:100,remote_services:1000,managed_host_groups:200,managed_host_tags:1000};
  const good={status:'CREATED',path:'/var/lib/drlink/exports/drlink-inventory-20261009T132300Z-deadbeef.ndjson',
    sha256:'a'.repeat(64),size_bytes:700,record_count:7,counts,limits,
    sanitized:true,download_exposed:false,authoritative_mutation:false};
  assert.equal(menu.requireObservedInventoryExport(good),good);
  const empty={...good,record_count:0,counts:{managed_hosts:0,remote_services:0,managed_host_groups:0,managed_host_tags:0}};
  assert.equal(menu.requireObservedInventoryExport(empty),empty);
  for(const bad of [null,{},[],{error:'connection lost'},
    {...good,status:'QUEUED'},{...good,path:'/tmp/inventory.ndjson'},
    {...good,path:'/var/lib/drlink/exports/../private.ndjson'},
    {...good,sha256:'x'.repeat(64)},{...good,sha256:undefined},
    {...good,size_bytes:0},{...good,record_count:0},
    {...good,record_count:'7'},{...good,counts:{...counts,managed_hosts:120}},
    {...good,counts:{...counts,managed_host_tags:undefined}},
    {...good,limits:{...limits,managed_hosts:101}},
    {...good,limits:{...limits,remote_services:null}},
    {...good,sanitized:false},{...good,download_exposed:true},
    {...good,authoritative_mutation:true}]){
    assert.throws(()=>menu.requireObservedInventoryExport(bad),/UNKNOWN/);
  }
});
test('Fleet metadata preview is bound to the actual Core selection, changes and impact',()=>{
  const request={resource_type:'managed-host',resource:'',changes:{
    description:'Fleet A',tags:{site:'lab'},add_groups:['ops','ops']
  }};
  const ok={change_plan_id:'cp_1234567890abcdefghijABCDEFGHIJ',operation_class:'CHANGE',
    operation:'fleet-metadata.apply',resource_type:'managed-host-fleet',
    resource_ref:'all',confirmation_class:'APPLY',expected_revision:18,
    selection:{resource_type:'managed-host',resource_ref:'all',resource_display:'All hosts',target_count:2},
    changes:{description:'Fleet A',tags:{site:'lab'},add_groups:['ops']},
    preview:{target_count:2,operation_count:6,targets:[
      {managed_host_id:'a',operation_count:3},{managed_host_id:'b',operation_count:3}]},
    impact:{target_count:2,operation_count:6,requires_confirmation:true,
      destructive:false,access_broadened:false,access_narrowed:false}
  };
  assert.equal(menu.requireObservedFleetPreview(ok,request),ok);
  for(const invalid of [null,{},[],
    {...ok,change_plan_id:''},{...ok,expected_revision:'18'},
    {...ok,selection:{...ok.selection,resource_type:'managed-host-group'}},
    {...ok,selection:{...ok.selection,resource_ref:''}},
    {...ok,selection:{...ok.selection,target_count:0}},
    {...ok,changes:{...ok.changes,description:'Other fleet'}},
    {...ok,changes:{...ok.changes,tags:{site:'remote'}}},
    {...ok,preview:{...ok.preview,target_count:3}},
    {...ok,preview:{...ok.preview,targets:[ok.preview.targets[0],ok.preview.targets[0]]}},
    {...ok,preview:{...ok.preview,operation_count:5}},
    {...ok,impact:{...ok.impact,operation_count:0}},
    {...ok,impact:{...ok.impact,access_broadened:true}},
    {...ok,impact:{...ok.impact,requires_confirmation:false}},
    {...ok,impact:{...ok.impact,target_count:101}},
  ])assert.throws(()=>menu.requireObservedFleetPreview(invalid,request),/UNKNOWN/);
  assert.throws(()=>menu.requireObservedFleetPreview(ok,
    {...request,resource_type:'managed-host-group'}),/UNKNOWN/);
  assert.throws(()=>menu.requireObservedFleetPreview(ok,
    {...request,changes:{description:'Changed'}}),/UNKNOWN/);
});
test('Fleet Apply response matches the exact reviewed Core plan, revision and targets',()=>{
  const reviewed={
    expected_revision:41,
    selection:{resource_type:'managed-host',resource_ref:'all',resource_display:'All hosts',target_count:2},
    changes:{description:'Ops fleet',tags:{site:'west'}},
    preview:{target_count:2,operation_count:4,targets:[
      {managed_host_id:'a',operation_count:2},{managed_host_id:'b',operation_count:2}]}
  };
  const applied={status:'APPLIED',revision:42,selection:reviewed.selection,
    changes:reviewed.changes,
    result:{target_count:2,operation_count:4,targets:reviewed.preview.targets}};
  assert.equal(menu.requireObservedFleetApplyForPreview(applied,reviewed),applied);
  for(const altered of [null,{}, {...applied,status:'QUEUED'},
    {...applied,revision:41},{...applied,revision:43},
    {...applied,selection:{...applied.selection,resource_ref:'other'}},
    {...applied,changes:{description:'Other fleet',tags:{site:'west'}}},
    {...applied,result:{...applied.result,target_count:1}},
    {...applied,result:{...applied.result,operation_count:3}},
    {...applied,result:{...applied.result,targets:[]}},
    {...applied,result:{...applied.result,targets:[
      {...applied.result.targets[0],managed_host_id:'wrong'},applied.result.targets[1]]}},
  ])assert.throws(()=>menu.requireObservedFleetApplyForPreview(altered,reviewed),/UNKNOWN/);
  assert.throws(()=>menu.requireObservedFleetApplyForPreview(applied,null),/UNKNOWN/);
});
test('Management Job Detail belongs to requested Core Job and never borrows stale status',()=>{
  const item=(id,status='QUEUED')=>({target_id:id,status,attempt:0});
  const base={id:'mjob_001',job_type:'doctor',status:'QUEUED',target_count:2,
    cancel_requested:0,targets:[item('host-a'),item('host-b')]};
  assert.equal(menu.requireObservedJobDetail(base,'mjob_001'),base);
  for(const bad of [null,{}, {error:'unavailable'},
    {...base,id:'mjob_002'}, {...base,id:''},{...base,status:'unknown'},
    {...base,job_type:null},{...base,target_count:0},
    {...base,target_count:3},{...base,cancel_requested:null},
    {...base,targets:[]},{...base,targets:[item('host-a'),item('host-a')]},
    {...base,targets:[item('host-a'),item('host-b','UNKNOWN')]},
    {...base,targets:[null,item('host-b')]}]){
    assert.throws(()=>menu.requireObservedJobDetail(bad,'mjob_001'),/UNKNOWN/);
  }
});
test('Job Cancel accepts Core acknowledgement or honest already-terminal result, never an invented cancellation',()=>{
  const job={id:'mjob_123',job_type:'doctor',status:'RUNNING',target_count:2,
    cancel_requested:1,targets:[
      {target_id:'host-a',status:'RUNNING'},
      {target_id:'host-b',status:'CANCELLED'}]};
  assert.deepEqual(menu.requireObservedJobCancellation(job,'mjob_123'),{job,outcome:'REQUESTED'});
  const finished={...job,status:'SUCCEEDED',cancel_requested:0,
    targets:job.targets.map(x=>({...x,status:'SUCCEEDED'}))};
  assert.deepEqual(menu.requireObservedJobCancellation(finished,'mjob_123'),{job:finished,outcome:'ALREADY_TERMINAL'});
  const failedAfterPriorCancel={...job,status:'FAILED'};
  assert.deepEqual(menu.requireObservedJobCancellation(failedAfterPriorCancel,'mjob_123'),
    {job:failedAfterPriorCancel,outcome:'ALREADY_TERMINAL'});
  for(const invalid of [null,{}, {...job,id:'mjob_wrong'}, {...job,cancel_requested:0},
    {...job,status:'QUEUED'}, {...job,status:'CANCELLED',cancel_requested:2},
    {...job,targets:[]}]){
    assert.throws(()=>menu.requireObservedJobCancellation(invalid,'mjob_123'),/UNKNOWN/);
  }
});
test('partial Objects inventory remains available for its existing explicit UNKNOWN warning',()=>{
  // ObjectsWorkspace itself distinguishes incomplete resources from a valid empty list.
  for(const response of [{resources:{}},{resources:{'network-object':{items:[]}}}]){
    assert.equal(menu.requireObservedMenuPayload('objects',response),response);
  }
});
