// UXB-06F: supplementary contract evidence only; not a logged-in browser/User E2E.
import assert from 'node:assert/strict';
import {before,after,test} from 'node:test';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
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
test('Policy list and details never mislabel missing Core status or expiry as Disabled/Never',()=>{
  for(const value of [true,1])assert.equal(menu.policyStateLabel(value),"Enabled");
  for(const value of [false,0])assert.equal(menu.policyStateLabel(value),"Disabled");
  for(const value of [null,undefined,"false",2,-1,[],{}])
    assert.equal(menu.policyStateLabel(value),"UNKNOWN");
  assert.equal(menu.policyExpiryLabel({expires_at:null}),"Never");
  assert.equal(menu.policyExpiryLabel({expires_at:"2030-01-01T00:00:00Z"}),"2030-01-01T00:00:00Z");
  for(const item of [{},{expires_at:undefined},{expires_at:""},{expires_at:0},
    {expires_at:"X".repeat(300)},null])
    assert.equal(menu.policyExpiryLabel(item),"UNKNOWN");
  const source=readFileSync(join(root,"src","main.tsx"),"utf8");
  assert.match(source,/policyStateLabel\(item.enabled\)/);
  assert.match(source,/policyStateLabel\(selected.enabled\)/);
  assert.match(source,/policyExpiryLabel\(item\)/);
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
  // Navigation hints must fail closed when the Web session role is missing or unrecognized.
  for(const role of [null,undefined,'Guest','admin','UNKNOWN',{},'']){
    for(const type of ['managed-host','object','access-rule','service-account'])
      assert.equal(menu.hygieneInspectTarget(type,role),null,`${type}/${String(role)}`);
  }
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

test("P0 Temporary Access UI never claims applied from HTTP 200 without exact Core Change Plan receipt",()=>{
 const plan={change_plan_id:"cp_"+"a".repeat(24),operation:"temporary-access.set",
  resource_type:"remote-access-rule",resource_ref:"ssh-prod",expected_revision:12,
  valid_until:"2035-01-01T00:00:00Z",confirmation_class:"APPLY",
  desired_expires_at:"2034-01-01T00:00:00Z",no_change:false};
 const good={status:"APPLIED",operation:plan.operation,resource_type:plan.resource_type,
  resource_ref:plan.resource_ref,expires_at:plan.desired_expires_at,revision:13};
 assert.deepEqual(menu.requireObservedTemporaryAccessApplyForPlan(good,plan),{revision:13});
 for(const wrong of [
  null,{},[],{...good,status:"NO_CHANGE"},{...good,status:"PENDING"},
  {...good,revision:12},{...good,revision:"13"},{...good,revision:13.5},
  {...good,operation:"temporary-access.clear"},
  {...good,resource_type:"ai-access-rule"},
  {...good,resource_ref:"other-rule"},
  {...good,expires_at:null}
 ])assert.throws(()=>menu.requireObservedTemporaryAccessApplyForPlan(wrong,plan),
   /UNKNOWN|Core|unverified/,JSON.stringify(wrong));
 for(const bad of [
  {...plan,no_change:true},
  {...plan,confirmation_class:"DELETE"},
  {...plan,valid_until:"2020-01-01T00:00:00Z"},
  {...plan,expected_revision:undefined},
  {...plan,resource_type:"managed-host"},
  {...plan,change_plan_id:"untrusted"}
 ])assert.throws(()=>menu.requireObservedTemporaryAccessApplyForPlan(good,bad),
   /UNKNOWN|Core|unverified/,JSON.stringify(bad));
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=source.split("function TemporaryAccessPanel(){")[1]?.split("function PolicySafetyPanel(",1)[0]||"";
 assert.match(panel,/requireObservedTemporaryAccessApplyForPlan\(result,reviewedPlan\)/);
 assert.match(panel,/setPreview\(null\);setConfirmation\(""\);/);
 assert.match(panel,/not a requester\/reviewer approval/);
});

test("UX-8 Emergency Cutoff Apply requires exact Core plan and verified status, not HTTP 200",()=>{
 const preview={change_plan_id:"cp_"+"a".repeat(32),operation_class:"INCIDENT_CHANGE",
   resource_type:"emergency-cutoff",operation:"emergency-cutoff.apply",
   resource_ref:"remote-service:service-1",scope_kind:"remote-service",
   scope_ref:"service-1",desired_active:true,confirmation_class:"CONFIRM CUTOFF",
   no_change:false,expected_revision:12,valid_until:"2032-01-01T00:00:00Z"};
 const ack={status:"APPLIED",revision:13,operation:"emergency-cutoff.apply",
   plane:"remote",scope_kind:"remote-service",scope_ref:"service-1",
   active:true,active_sessions_terminated:false};
 assert.deepEqual(menu.requireObservedEmergencyCutoffApplyForPlan(ack,preview,"remote","apply"),
   {revision:13,active_sessions_terminated:false});
 for(const [plane,kind,ref] of [["remote","plane",""],
   ["internet","managed-host","host-1"],["ai","ai-identity","bot-1"]]){
   const resource=kind==="plane"?plane:kind+":"+ref;
   const p={...preview,resource_ref:resource,scope_kind:kind,scope_ref:ref};
   const a={...ack,plane,scope_kind:kind,scope_ref:ref};
   assert.deepEqual(menu.requireObservedEmergencyCutoffApplyForPlan(a,p,plane,"apply"),
     {revision:13,active_sessions_terminated:false});
 }
 const clearPreview={...preview,operation:"emergency-cutoff.clear",desired_active:false};
 const clearReceipt={...ack,operation:"emergency-cutoff.clear",active:false};
 assert.deepEqual(menu.requireObservedEmergencyCutoffApplyForPlan(clearReceipt,
   clearPreview,"remote","clear"),{revision:13,active_sessions_terminated:false});
 for(const bad of [null,{},[],{...ack,status:"NO_CHANGE"},
   {...ack,revision:12},{...ack,revision:"13"},{...ack,plane:"ai"},
   {...ack,scope_ref:"service-2"},{...ack,scope_kind:"plane"},
   {...ack,active:false},{...ack,active_sessions_terminated:true},
   {...ack,operation:"emergency-cutoff.clear"}])
   assert.throws(()=>menu.requireObservedEmergencyCutoffApplyForPlan(bad,preview,"remote","apply"),
     /UNKNOWN|Core/,JSON.stringify(bad));
 for(const bad of [{...preview,no_change:true},{...preview,expected_revision:"12"},
   {...preview,confirmation_class:"APPLY"},{...preview,change_plan_id:""},
   {...preview,operation_class:"CHANGE"},{...preview,resource_ref:"remote-service:other"},
   {...preview,scope_kind:"managed-host"},{...preview,valid_until:"invalid"}])
   assert.throws(()=>menu.requireObservedEmergencyCutoffApplyForPlan(ack,bad,"remote","apply"),/UNKNOWN|Core/);
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 assert.match(src,/requireObservedEmergencyCutoffApplyForPlan\(result,currentCutoffPreview,plane,cutoffOperation\)/);
 assert.match(src,/setCutoffMessage\(\(cutoffOperation==="clear"\?"Cutoff cleared":"Cutoff applied"\)\+" at revision "\+confirmed\.revision/);
 assert.match(src,/setCutoffPreview\(null\);setCutoffConfirm\(""\)/);
 assert.match(src,/Inspect Core cutoff inventory and Change History before any retry/);
});

test("UX-8 Live Access never presents malformed Core counts or unauthorized session metadata",()=>{
 const core={plane:"ai",resource:null,resource_type:null,fidelity:"EXACT_PER_CONNECTION",
   active_count:2,limit:50,next_cursor:null,reason:"",
   observations:[{observation_kind:"AI_JOB",observation_id:"job-a",
     job_id:"job-a",status:"RUNNING",ai_identity:"bot-a",
     started_at:"2026-10-11T01:00:00Z",private_token:"SECRET_LIVE_TOKEN"}]};
 const safe=menu.requireObservedLiveAccessView(core,"ai","");
 assert.equal(safe.fidelity,"EXACT_PER_CONNECTION");
 assert.equal(safe.active_count,2);
 assert.equal(safe.observations.length,1);
 assert.equal(safe.partial,false);
 assert.equal(menu.requireObservedLiveAccessView({...core,next_cursor:"cursor-1"},
   "ai","").partial,true);
 assert.doesNotMatch(JSON.stringify(safe),/SECRET_LIVE_TOKEN/);
 const unknown=menu.requireObservedLiveAccessView({plane:"remote",resource:null,
   resource_type:null,fidelity:"UNKNOWN",active_count:null,limit:50,
   next_cursor:null,reason:"official FRP cannot prove active lifecycle",observations:[]},
   "remote","");
 assert.equal(unknown.fidelity,"UNKNOWN");
 assert.equal(unknown.active_count,null);
 assert.deepEqual(unknown.observations,[]);
 for(const invalid of [null,[],{},
   {...core,plane:"remote"},{...core,fidelity:"UNKNOWN"},
   {...core,active_count:undefined},{...core,active_count:"2"},
   {...core,active_count:0},{...core,limit:500},
   {...core,observations:[null]},{...core,observations:{secret:"hidden"}},
   {...core,observations:[{observation_kind:"AI_JOB",observation_id:"job-a\u202e"}]},
   {...core,observations:[{observation_kind:"NETWORK_SESSION",observation_id:"job-a"}]},
   {...core,next_cursor:{key:"cursor"}}
 ])assert.throws(()=>menu.requireObservedLiveAccessView(invalid,"ai",""),
    /UNKNOWN|Core/,JSON.stringify(invalid));
 assert.throws(()=>menu.requireObservedLiveAccessView(core,"internet",""),/UNKNOWN|Core/);
 assert.throws(()=>menu.requireObservedLiveAccessView({...core,resource:"old"},
   "ai","current"),/UNKNOWN|Core/);
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 assert.match(src,/const valid=requireObservedLiveAccessView\(result,plane,liveResource\.trim\(\)\)/);
 assert.match(src,/setLiveEvidence\(\{key:requestKey,value:valid\}\)/);
 assert.match(src,/matchingLive\.partial&&<p className="dr-uxb-catalog-page-notice"/);
});

test("UX-8 Connection Diagnosis only displays consistent same-flow Core layer evidence",()=>{
 const core={plane:"remote",input:{source:"src",destination:"dst",service:"ssh",
    permission:"",path:""},side_effect_free:true,network_probe_performed:false,
   overall:"UNKNOWN",next_action:"Collect evidence",
   policy_trace:{private_secret:"DO_NOT_EXPOSE"},
   layers:[{layer:"policy",status:"HEALTHY",summary:"Core ALLOW",evidence:{private:"PRIVATE"}},
     {layer:"runtime",status:"UNKNOWN",summary:"No runtime observation"}]};
 const safe=menu.requireObservedDiagnosisView(core,"remote","src","dst","ssh");
 assert.equal(safe.overall,"UNKNOWN");
 assert.equal(safe.layers.length,2);
 assert.deepEqual(safe.layers[0],{layer:"policy",status:"HEALTHY",summary:"Core ALLOW"});
 assert.doesNotMatch(JSON.stringify(safe),/DO_NOT_EXPOSE|PRIVATE/);
 for(const invalid of [null,{},[],
   {...core,plane:"ai"},{...core,network_probe_performed:true},
   {...core,side_effect_free:"true"},{...core,overall:"HEALTHY"},
   {...core,layers:[]},{...core,layers:[null]},
   {...core,layers:[...core.layers,core.layers[0]]},
   {...core,layers:[{layer:"policy",status:["HEALTHY"],summary:"Core ALLOW"}]},
   {...core,layers:[{layer:"policy",status:"HEALTHY",summary:{secret:"bad"}}]},
   {...core,layers:[{layer:"policy",status:"HEALTHY",summary:"spoof\u202e"}]},
   {...core,next_action:{private_key:"secret"}},
   {...core,input:{...core.input,service:"other"}}
 ])assert.throws(()=>menu.requireObservedDiagnosisView(invalid,"remote","src","dst","ssh"),
   /UNKNOWN|Core/,JSON.stringify(invalid));
 assert.throws(()=>menu.requireObservedDiagnosisView(core,"remote","src","dst","other"),/UNKNOWN|Core/);
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 assert.match(src,/const valid=requireObservedDiagnosisView\(result,plane,source\.trim\(\),destination\.trim\(\),selector\.trim\(\)\)/);
 assert.match(src,/setDiagnosisEvidence\(\{key:requestKey,value:valid\}\)/);
});

test("UX-8 Emergency Cutoff Preview must match selected Core scope and expire before Apply",()=>{
 const now=Date.parse("2031-01-01T00:00:00Z");
 const preview={change_plan_id:"cp_"+"a".repeat(32),operation_class:"INCIDENT_CHANGE",
   operation:"emergency-cutoff.apply",resource_type:"emergency-cutoff",
   resource_ref:"remote-service:service-1",expected_revision:12,
   valid_until:"2032-01-01T00:00:00Z",confirmation_class:"CONFIRM CUTOFF",
   scope_kind:"remote-service",scope_ref:"service-1",scope_display:"My Service",
   currently_active:false,desired_active:true,active_sessions_terminated:false,
   no_change:false,impact:{requires_confirmation:true,access_broadened:false,
     access_narrowed:true,warning:"This will block new sessions",
     private_context:{secret:"LEAKED_CONTEXT"}}};
 const expected={...preview,impact:{requires_confirmation:true,
   access_broadened:false,access_narrowed:true,
   warning:"This will block new sessions"}};
 assert.deepEqual(menu.observedEmergencyCutoffPreviewForIntent(
   preview,"remote","remote-service","My Service","apply",now),expected);
 assert.deepEqual(menu.observedEmergencyCutoffPreviewForIntent(
   preview,"remote","remote-service","service-1","apply",now),expected);
 assert.doesNotMatch(JSON.stringify(expected),/LEAKED_CONTEXT/);
 for(const bad of [null,{},[],{...preview,operation:"emergency-cutoff.clear"},
   {...preview,operation_class:"CHANGE"},{...preview,resource_ref:"remote-service:other"},
   {...preview,scope_ref:"other"},{...preview,scope_kind:"plane"},
   {...preview,scope_display:"other"},{...preview,desired_active:false},
   {...preview,active_sessions_terminated:true},{...preview,no_change:true},
   {...preview,valid_until:"invalid"},{...preview,expected_revision:"12"},
   {...preview,impact:{...preview.impact,requires_confirmation:"true"}},
   {...preview,impact:{...preview.impact,access_narrowed:"true"}},
   {...preview,change_plan_id:"invalid"},{...preview,confirmation_class:"APPLY"}
 ])assert.equal(menu.observedEmergencyCutoffPreviewForIntent(
   bad,"remote","remote-service","My Service","apply",now),null,JSON.stringify(bad));
 assert.equal(menu.observedEmergencyCutoffPreviewForIntent(
   preview,"remote","remote-service","My Service","apply",
   Date.parse(preview.valid_until)),null);
 assert.equal(menu.observedEmergencyCutoffPreviewForIntent(
   preview,"ai","ai-identity","My Service","apply",now),null);
 const rootPath=readFileSync(join(root,"src","main.tsx"),"utf8");
 assert.match(rootPath,/const verified=observedEmergencyCutoffPreviewForIntent\(result,plane,scopeKind,scopeRef,cutoffOperation\)/);
 assert.match(rootPath,/setCutoffPreview\(\{key:requestKey,value:verified\}\)/);
 assert.match(rootPath,/const currentCutoffActionable=observedEmergencyCutoffPreviewForIntent\(/);
 assert.match(rootPath,/Cutoff Preview expired or unverified/);
});

test("UX-8 Active Emergency Cutoffs require exact Core plane, counts and bounded observations",()=>{
 const item={id:"cut_"+ "a".repeat(20),plane:"remote",
   scope_kind:"remote-service",scope_ref:"service-a",
   reason:"emergency control",row_version:2,updated_at:"2030-06-01T12:00:00Z",
   nested_secret:{value:"DO_NOT_EXPOSE"}};
 const response={items:[item],count:1,returned:1,plane:"remote",active:true,
   limit:200,truncated:false};
 const got=menu.requireObservedCutoffInventory(response,"remote");
 assert.deepEqual(got,{...response,items:[{
   id:item.id,plane:item.plane,scope_kind:item.scope_kind,
   scope_ref:item.scope_ref,reason:item.reason,row_version:2,updated_at:item.updated_at}]});
 assert.doesNotMatch(JSON.stringify(got),/DO_NOT_EXPOSE/);
 const empty={items:[],count:0,returned:0,plane:"ai",active:false,
   limit:200,truncated:false};
 assert.deepEqual(menu.requireObservedCutoffInventory(empty,"ai"),empty);
 const partial={...response,items:[item],count:201,truncated:true};
 assert.equal(menu.requireObservedCutoffInventory(partial,"remote").truncated,true);
 for(const invalid of [null,{},[],{...response,plane:"ai"},
   {...response,count:0},{...response,returned:0},{...response,returned:"1"},
   {...response,limit:201},{...response,truncated:true},
   {...response,active:false},{...response,count:-1},
   {...response,items:[item,item]},
   {...response,items:[{...item,plane:"internet"}]},
   {...response,items:[{...item,scope_kind:"managed-host"}]},
   {...response,items:[{...item,scope_ref:"other\u202ehost"}]},
   {...response,items:[{...item,reason:"bad\u202esequence"}]},
   {...response,items:[{...item,updated_at:"invalid"}]},
   {...response,items:[{...item,row_version:"2"}]},
   {...response,items:[{...item,id:{secret:"DO_NOT_EXPOSE"}}]}
 ])assert.throws(()=>menu.requireObservedCutoffInventory(invalid,"remote"),
    /UNKNOWN|Core/,JSON.stringify(invalid));
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 assert.match(src,/const verified=requireObservedCutoffInventory\(result,plane\)/);
 assert.match(src,/setCutoffEvidence\(\{key:plane,value:verified\}\)/);
});

test("UX-8 Policy expiry does not display impossible calendar timestamps as observed",()=>{
 const valid=["2030-01-01T00:00:00Z","2028-02-29T23:59:59+09:00",
   "2019-01-01T12:30:00-05:00"];
 for(const date of valid)assert.equal(menu.policyExpiryLabel({expires_at:date}),date);
 const invalid=["2030-02-30T00:00:00Z","2030-13-01T00:00:00Z",
   "2030-01-01T25:00:00Z","2030-01-01T00:00:00+14:01",
   "2030-01-01T00:00:00+15:00","2030-01-01",
   "2030-01-01T00:00:00Z\u202e","not-a-time","12345"];
 for(const date of invalid)assert.equal(menu.policyExpiryLabel({expires_at:date}),
   "UNKNOWN",date);
 assert.equal(menu.policyExpiryLabel({expires_at:null}),"Never");
 assert.equal(menu.policyExpiryLabel({}),"UNKNOWN");
 const src=readFileSync(join(root,"src","uxb-menu-evidence.ts"),"utf8");
 assert.match(src,/if\(!isObservedAbsoluteTime\(row\.expires_at\)\)return "UNKNOWN"/);
});

test("UX-2 generic Guided Change applies only a current exact Core Change Plan and matching receipt",()=>{
 const req={change_type:"service-object",payload:{operation:"set",name:"https",type:"tcp",port:443}};
 const preview={change_plan_id:"cp_"+"a".repeat(24),operation_class:"CHANGE",
   operation:"guided.service-object.set",resource_type:"service-object",
   resource_ref:"https",change_type:"service-object",expected_revision:15,
   confirmation_class:"APPLY",valid_until:"2035-01-01T00:00:00Z",no_change:false};
 const now=Date.parse("2034-01-01T00:00:00Z");
 assert.equal(menu.guidedChangePreviewMatchesIntent(preview,req,now),true);
 const receipt={status:"APPLIED",change_type:"service-object",
   resource_type:"service-object",resource_ref:"https",revision:16};
 assert.deepEqual(menu.requireObservedGuidedChangeApplyReceipt(receipt,preview,req),
   {revision:16});
 for(const wrong of [null,{},[],{...preview,no_change:true},
   {...preview,change_plan_id:"wrong"},{...preview,resource_ref:"ssh"},
   {...preview,change_type:"network-object"},{...preview,operation:"guided.service-object.delete"},
   {...preview,operation_class:"INCIDENT_CHANGE"},
   {...preview,confirmation_class:"CONFIRM CUTOFF"},
   {...preview,expected_revision:"15"},{...preview,valid_until:"bogus"},
   {...preview,policy_regression:{ok:true,required_failed:1}},
   {...preview,blast_radius:{limits:{truncated:true}}}
 ])assert.equal(menu.guidedChangePreviewMatchesIntent(wrong,req,now),false,
   JSON.stringify(wrong));
 assert.equal(menu.guidedChangePreviewMatchesIntent(preview,req,
   Date.parse(preview.valid_until)),false);
 assert.equal(menu.guidedChangePreviewMatchesIntent(preview,
   {...req,payload:{...req.payload,name:"other"}},now),false);
 for(const bad of [null,{},[],{...receipt,status:"NO_CHANGE"},
   {...receipt,revision:15},{...receipt,revision:"16"},
   {...receipt,change_type:"network-object"},{...receipt,resource_ref:"ssh"},
   {...receipt,resource_type:"network-object"}])
  assert.throws(()=>menu.requireObservedGuidedChangeApplyReceipt(bad,preview,req),
    /UNKNOWN|Core|unverified/,JSON.stringify(bad));
});
test("UX-2 generic Guided Change supports the existing Host and policy scopes, never a false Apply",()=>{
 const at=Date.parse("2034-01-01T00:00:00Z");
 const base={change_plan_id:"cp_"+"a".repeat(24),operation_class:"CHANGE",
   expected_revision:13,confirmation_class:"APPLY",
   valid_until:"2035-01-01T00:00:00Z",no_change:false};
 const hostReq={change_type:"managed-host-metadata",
   payload:{operation:"set",host:"host-a",description:"office"}};
 assert.equal(menu.guidedChangePreviewMatchesIntent({...base,change_type:"managed-host-metadata",
   resource_type:"managed-host-metadata",resource_ref:"host-a",
   operation:"guided.managed-host-metadata.set"},hostReq,at),true);
 const policyReq={change_type:"remote-access-policy",
   payload:{operation:"set-enforcement",enabled:false}};
 for(const ref of ["", "remote"])assert.equal(menu.guidedChangePreviewMatchesIntent(
   {...base,change_type:"remote-access-policy",resource_type:"remote-access-policy",
     resource_ref:ref,operation:"guided.remote-access-policy.set-enforcement"},
   policyReq,at),true);
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=src.split("function GuidedApplyPanel(")[1]?.split("function ManagedHostMetadataPanel(",1)[0]||"";
 assert.match(panel,/guidedChangePreviewMatchesIntent\(result,req\)/);
 assert.match(panel,/requireObservedGuidedChangeApplyReceipt\(result,reviewedPlan,reviewedRequest\)/);
 assert.match(panel,/Apply outcome UNKNOWN/);
 assert.match(panel,/setPreview\(null\);setConfirmation\(""\)/);
 assert.match(panel,/disabled=\{busy\|\|confirmation!=="APPLY"/);
});

test("UI-06 adjacent Temporary Access Preview is scoped to exact rule, action and canonical expiry",()=>{
 const now=Date.parse("2033-01-01T00:00:00Z");
 const req={plane:"remote",rule:" ssh-prod ",operation:"set",
   expires_at:"2034-01-01T09:00:00+09:00"};
 const plan={change_plan_id:"cp_"+"a".repeat(24),operation_class:"CHANGE",
   operation:"temporary-access.set",resource_type:"remote-access-rule",
   resource_ref:"ssh-prod",expected_revision:18,confirmation_class:"APPLY",
   valid_until:"2035-01-01T00:00:00Z",desired_expires_at:"2034-01-01T00:00:00Z",
   current_expires_at:null,no_change:false,
   policy_regression:{ok:true,required_failed:0},
   blast_radius:{limits:{truncated:false},unknowns:[]}};
 assert.equal(menu.temporaryAccessPreviewMatchesIntent(plan,req,now),true);
 assert.equal(menu.temporaryAccessPreviewMatchesIntent({...plan,operation:"temporary-access.clear"},
   {...req,operation:"clear",expires_at:""},now),false);
 const cleared={...plan,operation:"temporary-access.clear",desired_expires_at:null};
 assert.equal(menu.temporaryAccessPreviewMatchesIntent(cleared,
   {...req,operation:"clear",expires_at:""},now),true);
 for(const invalid of [null,{},[],{...plan,resource_ref:"other"},
   {...plan,resource_type:"ai-access-rule"},
   {...plan,operation:"temporary-access.clear"},
   {...plan,desired_expires_at:"2034-01-02T00:00:00Z"},
   {...plan,desired_expires_at:null},{...plan,no_change:true},
   {...plan,change_plan_id:"invalid"},
   {...plan,confirmation_class:"APPROVE"},
   {...plan,expected_revision:"18"},
   {...plan,valid_until:"expired"},
   {...plan,policy_regression:{ok:false,required_failed:1}},
   {...plan,blast_radius:{limits:{truncated:true}}}
 ])assert.equal(menu.temporaryAccessPreviewMatchesIntent(invalid,req,now),false,JSON.stringify(invalid));
 assert.equal(menu.temporaryAccessPreviewMatchesIntent(plan,req,
   Date.parse(plan.valid_until)),false);
 assert.equal(menu.temporaryAccessPreviewMatchesIntent(plan,{...req,rule:"other"},now),false);
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=src.split("function TemporaryAccessPanel(){")[1]?.split("function PolicySafetyPanel(",1)[0]||"";
 assert.match(panel,/const token=\+\+previewGeneration\.current/);
 assert.match(panel,/temporaryAccessPreviewMatchesIntent\(result,request\)/);
 assert.match(panel,/if\(token!==previewGeneration\.current\)return;/);
 assert.match(panel,/resetChangePlan\(\);setExpiresAt\(e\.target\.value\)/);
 assert.match(panel,/const actionable=temporaryAccessPreviewMatchesIntent\(preview,currentRequest\.current\)/);
 assert.match(panel,/Apply outcome UNKNOWN/);
});

test("UI-03 Managed Host admission must verify exact Core Host, action, impact and Apply receipt",()=>{
 const current=Date.parse("2034-01-01T00:00:00Z");
 const base={change_plan_id:"cp_"+"a".repeat(24),operation_class:"CHANGE",
   operation:"managed-host-admission.quarantine",admission_operation:"quarantine",
   resource_type:"managed-host",resource_ref:"host-a",expected_revision:17,
   confirmation_class:"QUARANTINE",no_change:false,
   valid_until:"2035-01-01T00:00:00Z",
   preview:{id:"host-a",before:"APPROVED",after:"QUARANTINED"},
   impact:{kind:"managed-host-admission",before:"APPROVED",after:"QUARANTINED",
     destructive:false,requires_confirmation:true,access_broadened:false,
     access_narrowed:true,warning:"Quarantine prevents new access.",
     kept:["Host identity"],internal:{secret:"DO_NOT_EXPOSE"}}};
 const plan=menu.observedHostAdmissionPlanForAction(base,"host-a","quarantine",current);
 assert.equal(plan?.change_plan_id,base.change_plan_id);
 assert.equal(plan?.preview.id,"host-a");
 assert.doesNotMatch(JSON.stringify(plan),/DO_NOT_EXPOSE/);
 const receipt={status:"APPLIED",admission_operation:"quarantine",revision:18};
 assert.deepEqual(menu.requireObservedHostAdmissionReceipt(receipt,plan,"quarantine"),{revision:18});
 const approve={...base,operation:"managed-host-admission.approve",
   admission_operation:"approve",confirmation_class:"APPROVE",
   preview:{...base.preview,after:"APPROVED",before:"QUARANTINED"},
   impact:{...base.impact,before:"QUARANTINED",after:"APPROVED",
     access_broadened:true,access_narrowed:false}};
 assert.equal(menu.observedHostAdmissionPlanForAction(approve,"host-a","approve",current)?.confirmation_class,"APPROVE");
 for(const bad of [null,{},[],{...base,resource_ref:"host-b"},
   {...base,operation:"managed-host-admission.approve"},
   {...base,confirmation_class:"APPROVE"},
   {...base,preview:{...base.preview,id:"host-b"}},
   {...base,impact:{...base.impact,destructive:true}},
   {...base,impact:{...base.impact,access_narrowed:false}},
   {...base,impact:{...base.impact,warning:"bad\u202e"}},
   {...base,no_change:true},{...base,valid_until:"invalid"},
   {...base,expected_revision:"17"}])
  assert.equal(menu.observedHostAdmissionPlanForAction(bad,"host-a","quarantine",current),null,JSON.stringify(bad));
 assert.equal(menu.observedHostAdmissionPlanForAction(base,"host-b","quarantine",current),null);
 for(const wrong of [null,{},[],{...receipt,status:"NO_CHANGE"},
   {...receipt,admission_operation:"approve"},{...receipt,revision:17},
   {...receipt,revision:"18"}])
  assert.throws(()=>menu.requireObservedHostAdmissionReceipt(wrong,plan,"quarantine"),/UNKNOWN|Core/);
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const panel=main.split("function ManagedHostAdmissionPanel(){")[1]?.split("function ManagedHostLifecyclePanel(",1)[0]||"";
 assert.match(panel,/observedHostAdmissionPlanForAction\(result,requestHost,requestOperation\)/);
 assert.match(panel,/requireObservedHostAdmissionReceipt\(result,reviewedPlan,operation\)/);
 assert.match(panel,/Core Admission Apply outcome UNKNOWN/);
 assert.match(panel,/previewGeneration\.current/);
});

test('R2.2 M2: initial Host/Service inventory observes Core family, 100-row bound and terminal cursor',()=>{
  for(const [route,resource_type] of [['hosts','managed-host'],['services','remote-service']]){
    const valid={resource_type,limit:100,items:[{id:'host-01'}],next_cursor:null};
    assert.equal(menu.requireObservedBoundedCorePage(route,valid,'',100),valid);
    const next={...valid,next_cursor:'next-Core-page'};
    assert.equal(menu.requireObservedBoundedCorePage(route,next,'',100),next);
    for(const broken of [
      {items:[]}, {...valid,resource_type:'audit-event'},
      {...valid,limit:50}, {...valid,limit:'100'},
      {...valid,next_cursor:undefined},{...valid,next_cursor:''},
      {...valid,next_cursor:'bad cursor'}, {...valid,next_cursor:42},
      {...valid,items:Array.from({length:101},(_,i)=>({id:'h-'+i}))},
      {...valid,items:[{id:'host-01'},{id:'host-01'}]},
      {...valid,items:[{id:'bad\nidentifier'}]},
      {...valid,items:[],next_cursor:'phantom'},
    ])assert.throws(()=>menu.requireObservedBoundedCorePage(route,broken,'',100),/Core|UNKNOWN/);
    assert.throws(()=>menu.requireObservedBoundedCorePage(route,next,'next-Core-page',100),/Core|UNKNOWN/);
  }
  const source=readFileSync(join(root,'src','main.tsx'),'utf8');
  assert.match(source,/active==="hosts"\|\|active==="services".*requireObservedBoundedCorePage/s);
  assert.match(source,/requireObservedInventoryContinuation\(route,await api\(path\),requestedCursor,100\)/);
});

test('R2.2 M2: Audit first-50 and keyset pages refuse mismatched/overlong/duplicated Core evidence',()=>{
  const item={row_id:101,event_id:null,occurred_at:'2026-10-12T00:00:00Z'};
  const valid={resource_type:'audit-event',limit:50,items:[item],next_cursor:null};
  assert.equal(menu.requireObservedBoundedCorePage('audit',valid,'',50),valid);
  const next={...valid,next_cursor:'opaque-Audit-2026'};
  assert.equal(menu.requireObservedBoundedCorePage('audit',next,'',50),next);
  for(const broken of [
    {items:[]},{...valid,resource_type:'managed-host'},
    {...valid,limit:100},{...valid,limit:'50'},
    {...valid,next_cursor:undefined},{...valid,next_cursor:''},
    {...valid,items:Array.from({length:51},(_,i)=>({...item,row_id:i+1}))},
    {...valid,items:[item,item]},
    {...valid,items:[{...item,row_id:'101'}]},
    {...valid,items:[{...item,row_id:0}]},
    {...valid,items:[{...item,event_id:123}]},
    {...valid,items:[],next_cursor:'phantom'},
    {...valid,next_cursor:'unsafe%20cursor'},
  ])assert.throws(()=>menu.requireObservedBoundedCorePage('audit',broken,'',50),/Core|UNKNOWN/);
  assert.throws(()=>menu.requireObservedBoundedCorePage('audit',next,'opaque-Audit-2026',50),/Core|UNKNOWN/);
  const source=readFileSync(join(root,'src','main.tsx'),'utf8');
  assert.ok(source.includes('requireObservedBoundedCorePage("audit",await api("/api/v1/audit?"'))
});
