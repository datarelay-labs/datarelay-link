// DRL3-7B UXB-01/02 offline deterministic contract, not browser/user E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,nav,home;
before(async()=>{
 scratch=mkdtempSync(join(root,"node_modules",".uxb-"));
 for(const [name,entry] of [["nav","uxb-navigation.ts"],["home","uxb-home.tsx"]]){
  const outfile=join(scratch,name+".mjs");
  await build({entryPoints:[join(root,"src",entry)],outfile,
   bundle:true,format:"esm",platform:"node",jsx:"automatic",
   external:["react","react/jsx-runtime"],logLevel:"silent"});
 }
 nav=await import(pathToFileURL(join(scratch,"nav.mjs")).href);
 home=await import(pathToFileURL(join(scratch,"home.mjs")).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});
test("exactly Home and four task-first sidebar groups; canonical routes survive",()=>{
 assert.deepEqual(nav.navGroups.map(g=>g.label),["Connections","Access","Activity & Health","Administration"]);
 assert.equal(nav.labelFor("overview"),"Home");
 assert.equal(nav.labelFor("hosts"),"Servers & Agents");
 assert.equal(nav.labelFor("access"),"Test & explain access");
 assert.equal(nav.groupFor("audit"),"activity");
 assert.equal(nav.groupFor("enrollments"),"connections");
 assert.equal(nav.groupFor("setup"),"connections");
 const ids=nav.navGroups.flatMap(g=>g.items.map(x=>x[0]));
 assert.deepEqual(new Set(ids).size,ids.length);
 assert.equal(ids.includes("enrollments"),false);
 assert.equal(ids.includes("setup"),false);
 for(const id of ["hosts","services","access","policies","objects","health","hygiene","audit","jobs","revisions","versions","system","users","integrations"]){
  assert.ok(ids.includes(id),id);
 }
});
test("Saved Views stays discoverable once in Activity & Health for all Web roles",()=>{
 const activity=nav.navGroups.find(group=>group.id==="activity");
 assert.deepEqual(activity.items.filter(row=>row[0]==="views"),[["views","Saved Views"]]);
 assert.equal(nav.contextualRoutes.some(route=>route.id==="views"),false);
 assert.equal(nav.groupFor("views"),"activity");
 assert.equal(nav.labelFor("views"),"Saved Views");
 for(const role of ["Admin","Operator","Read Only"]){
  assert.equal(nav.visibleRoute("views",role),true);
  assert.equal(nav.navMatches("saved views",role).filter(row=>row.id==="views").length,1);
  assert.equal(nav.navMatches("saved filters",role).filter(row=>row.id==="views").length,1);
 }
});
test("Objects-family search returns only an unambiguous setup context",()=>{
 assert.deepEqual(nav.setupContextForObjectFamily("ai"),{plane:"ai"});
 assert.deepEqual(nav.setupContextForObjectFamily("permission"),{plane:"ai"});
 for(const ambiguous of ["network","service","all","unexpected"]){
  assert.equal(nav.setupContextForObjectFamily(ambiguous),null,ambiguous);
 }
});
test("old menu names, user tasks, and canonical public nouns all searchable",()=>{
 for(const [query,id] of [
  ["managed hosts","hosts"],["remote services","services"],["access operations","access"],
  ["access hygiene","hygiene"],["version drift","versions"],["audit","audit"],
  ["test connection","access"],["connect agent","enrollments"],["new connection","setup"],
  ["permission objects","objects"],["configurATION bundle","drafts"],
 ]){
  assert.ok(nav.navMatches(query,"Admin").some(row=>row.id===id),query);
 }
 assert.equal(nav.navMatches("","Admin").length,0);
});
test("search never offers unauthorized admin tasks to non-admin roles",()=>{
 for(const role of ["Operator","Read Only"]){
  for(const id of ["users","integrations","enrollments"]){
   assert.equal(nav.visibleRoute(id,role),false);
   assert.ok(!nav.navMatches(id,role).some(row=>row.id===id),role+" "+id);
  }
 }
 assert.equal(nav.visibleRoute("drafts","Read Only"),false);
 assert.equal(nav.visibleRoute("drafts","Operator"),true);
 assert.equal(nav.visibleRoute("enrollments","Admin"),true);
});
test("Fresh installations see first-use guide, populated or UNKNOWN Core stays in operator dashboard",()=>{
 const empty={overview:{managed_hosts:{total:0},remote_services:{total:0,enabled:0},
   policies:{ai:{total:0,enabled:0}}}};
 assert.equal(home.isFreshInstallation(empty),true);
 assert.equal(home.isFreshInstallation(null),false);
 assert.equal(home.isFreshInstallation({overview:{managed_hosts:{total:0},remote_services:{total:0},policies:{}}}),false);
 assert.equal(home.isFreshInstallation({overview:{managed_hosts:{total:0},remote_services:{total:0},policies:{ai:{enabled:0}}}}),false);
 assert.equal(home.isFreshInstallation({overview:{managed_hosts:{total:1},remote_services:{total:0},policies:{ai:{total:0}}}}),false);
 assert.equal(home.isFreshInstallation({overview:{managed_hosts:{total:0},remote_services:{total:0},policies:{ai:{total:1}}}}),false);
});
test("Home welcome requires confirmed empty Core across Hosts, Services and every policy plane",()=>{
 const empty={overview:{managed_hosts:{total:0},remote_services:{total:0,enabled:0},
  policies:{ai:{total:0,enabled:0}}}};
 assert.equal(home.showFreshHomeWelcome(empty,"loading"),false);
 assert.equal(home.showFreshHomeWelcome(empty,"error"),false);
 assert.equal(home.showFreshHomeWelcome(empty,"ready"),true);
 assert.equal(home.showFreshHomeWelcome({...empty,overview:{...empty.overview,managed_hosts:{total:1}}},"ready"),false);
 assert.equal(home.showFreshHomeWelcome({...empty,overview:{...empty.overview,remote_services:{total:1}}},"ready"),false);
 assert.equal(home.showFreshHomeWelcome({...empty,overview:{...empty.overview,
  policies:{ai:{total:0},remote:{total:1}}}},"ready"),false);
 assert.equal(home.showFreshHomeWelcome({...empty,overview:{...empty.overview,
  policies:{ai:{total:0},internet:{total:1}}}},"ready"),false);
 assert.equal(home.showFreshHomeWelcome({...empty,overview:{...empty.overview,
  policies:{ai:{total:0},remote:{enabled:0}}}},"ready"),false);
 assert.equal(home.showFreshHomeWelcome(null,"ready"),false);
});
test("Pending Host attention links to the existing admission-filtered Host inventory without approval",()=>{
 const data={overview:{managed_hosts:{total:10,pending_approval:3},
    remote_services:{total:0,enabled:0},policies:{ai:{total:0,enabled:0}}}};
 for(const role of ["Admin","Operator","Read Only"]){
   const html=renderToStaticMarkup(React.createElement(home.FirstUseHome,{
     data,operator:{role},api:async()=>{throw new Error("SSR must not call Core")}}));
   assert.match(html,/3 Host\(s\) await Admin approval/);
   assert.match(html,/Review pending Hosts/);
   assert.match(html,/more pages may be needed/);
   assert.doesNotMatch(html,/Click here to approve|Approvals completed/);
 }
 const source=readFileSync(join(root,"src","uxb-home.tsx"),"utf8");
 assert.match(source,/onNavigate\?\.\("hosts","connections",\{savedAdmission:"PENDING_APPROVAL"\}\)/);
});
test("Home next action never skips UNKNOWN or unapproved Agent prerequisites",()=>{
 const ready="Configured · verify",unknown="Unknown",todo="Not started",verify="Needs verification";
 assert.equal(home.nextFirstConnectionAction([ready,unknown,todo,todo,verify],"Admin").route,"hosts");
 assert.equal(home.nextFirstConnectionAction([ready,unknown,todo,todo,verify],"Read Only").route,"hosts");
 assert.equal(home.nextFirstConnectionAction([ready,"Needs approval",todo,todo,verify],"Admin").route,"hosts");
 assert.equal(home.nextFirstConnectionAction([ready,todo,todo,todo,verify],"Admin").route,"enrollments");
 assert.equal(home.nextFirstConnectionAction([ready,todo,todo,todo,verify],"Operator").route,"hosts");
 assert.equal(home.nextFirstConnectionAction([ready,verify,todo,todo,verify],"Admin").route,"hosts");
 assert.equal(home.nextFirstConnectionAction([ready,ready,todo,todo,verify],"Admin").route,"services");
 const readOnlySvc=home.nextFirstConnectionAction([ready,ready,todo,todo,verify],"Read Only");
 assert.equal(readOnlySvc.route,"services");
 assert.match(readOnlySvc.action,/Review|Inspect/);
 assert.equal(home.nextFirstConnectionAction([ready,ready,ready,todo,verify],"Read Only").route,"policies");
 assert.equal(home.nextFirstConnectionAction([ready,ready,ready,ready,verify],"Admin").route,"access");
});
test("Approval queue prioritizes the complete Core overview over an incomplete 100-Host page",()=>{
 const data={overview:{managed_hosts:{total:130,pending_approval:7,approved:120},
   remote_services:{total:2,enabled:1},policies:{ai:{total:0,enabled:0}}}};
 const loaded=Array.from({length:100},(_,i)=>({id:"host-"+i,
   admission_state:"APPROVED",trust_status:"untrusted",connected:false}));
 assert.equal(home.observedApprovalQueueCount(data,loaded,false),7);
 assert.equal(home.firstConnectionStates(data,loaded,false)[1],"Needs approval");
 assert.equal(home.observedApprovalQueueCount({overview:{managed_hosts:{pending_approval:0}}},loaded,false),0);
 assert.equal(home.observedApprovalQueueCount(null,loaded,false),"UNKNOWN");
 assert.equal(home.observedApprovalQueueCount(null,loaded,true),0);
 assert.equal(home.observedApprovalQueueCount({overview:{managed_hosts:{total:130}}},loaded,true),"UNKNOWN");
 assert.equal(home.observedApprovalQueueCount({overview:{managed_hosts:{total:100}}},loaded,true),0);
 assert.equal(home.observedApprovalQueueCount({overview:{managed_hosts:{pending_approval:-1}}},loaded,false),"UNKNOWN");
 assert.equal(home.observedApprovalQueueCount({overview:{managed_hosts:{pending_approval:"7"}}},loaded,false),"UNKNOWN");
 assert.equal(home.firstConnectionStates({overview:{managed_hosts:{total:130},
   remote_services:{total:0,enabled:0},policies:{ai:{total:0,enabled:0}}}},loaded,false)[1],"Unknown");
 assert.equal(home.observedApprovalQueueCount(null,null,true),"UNKNOWN");
 assert.equal(home.hostInventoryPageComplete({items:[],next_cursor:null}),true);
 assert.equal(home.hostInventoryPageComplete({items:loaded,next_cursor:"cursor-101"}),false);
 assert.equal(home.hostInventoryPageComplete({items:loaded}),null);
 assert.equal(home.hostInventoryPageComplete({items:null,next_cursor:null}),null);
});
test("first-use states are fail-closed without trustworthy evidence",()=>{
 assert.deepEqual(home.firstConnectionStates(null,null),[
  "Unknown","Unknown","Unknown","Unknown","Needs verification"]);
 const blank={overview:{managed_hosts:{total:0},remote_services:{total:0,enabled:0},policies:{remote:{total:0,enabled:0}}}};
 assert.deepEqual(home.firstConnectionStates(blank,[]),[
  "Configured · verify","Not started","Not started","Not started","Needs verification"]);
 const partial={overview:{managed_hosts:{total:1},remote_services:{total:1,enabled:1},policies:{remote:{total:2,enabled:2}}}};
 const waiting=home.firstConnectionStates(partial,[{admission_state:"PENDING_APPROVAL",connected:true,trust_status:"trusted"}]);
 assert.equal(waiting[1],"Needs approval");
 assert.equal(waiting[2],"Configured · verify");
 assert.equal(waiting[3],"Configured · verify");
 assert.equal(waiting[4],"Needs verification");
 assert.equal(home.firstConnectionStates(partial,[{admission_state:"APPROVED",connected:true,trust_status:"trusted"}])[1],"Configured · verify");
 const noRemoteRules={overview:{managed_hosts:{total:0},remote_services:{total:0,enabled:0},policies:{ai:{enabled:0,total:0}}}};
 assert.equal(home.firstConnectionStates(noRemoteRules,[])[3],"Not started");
});
test("Partial Core overview remains UNKNOWN and must not be announced as system readiness",()=>{
 for(const partial of [
  {overview:{}},
  {overview:{managed_hosts:{total:0},remote_services:{total:0},policies:{ai:{enabled:0}}}},
 ]){
  assert.equal(home.firstConnectionStates(partial,[])[0],"Unknown");
  const html=renderToStaticMarkup(React.createElement(home.FirstUseHome,{
   data:partial,operator:{role:"Read Only"},api:async()=>{throw new Error("SSR must not fetch")},
  }));
  assert.doesNotMatch(html,/Core overview received/);
  assert.match(html,/Unknown/);
 }
 const complete={overview:{managed_hosts:{total:0},remote_services:{total:0},policies:{ai:{total:0}}}};
 assert.equal(home.firstConnectionStates(complete,[])[0],"Configured · verify");
});
test("Audit and revision responses distinguish empty records from failed or malformed Core reads",()=>{
 const observed=home.observedRecentFeed({status:"fulfilled",value:{items:[]}});
 assert.deepEqual(observed,{status:"ready",items:[]});
 assert.deepEqual(home.observedRecentFeed({status:"fulfilled",value:{items:[{id:"audit-1"}]}}),
  {status:"ready",items:[{id:"audit-1"}]});
 for(const result of [
  {status:"rejected",reason:new Error("Core unreachable")},
  {status:"fulfilled",value:{error:"Internal failure"}},
  {status:"fulfilled",value:{items:null}},
 ]){
  assert.deepEqual(home.observedRecentFeed(result),{status:"unknown",items:[]});
 }
});
test("Health summary shows UNKNOWN, not an invented zero or all-plane status",()=>{
 assert.equal(home.observedNumber(undefined),"UNKNOWN");
 assert.equal(home.observedNumber(0),0);
 assert.equal(home.observedNumber(7),7);
 assert.equal(home.accessPlaneCount({generations:{}}),null);
 assert.equal(home.accessPlaneCount({generations:{ai:{status:"active"}}}),null);
 assert.equal(home.accessPlaneCount({generations:{
  remote:{status:"active"},internet:{status:"not_configured"},ai:{status:"failed"}}}),1);
 assert.equal(home.coreHealthState({db_healthy:true}),"UNKNOWN");
 assert.equal(home.coreHealthState({db_healthy:true,mismatch:false}),"Healthy");
 assert.equal(home.coreHealthState({db_healthy:false,mismatch:false}),"Attention");
 assert.equal(home.coreHealthState({db_healthy:true,mismatch:true}),"Attention");
});
test("Home SSR has useful actions, no fake connection claims or credential URLs",()=>{
 const empty={overview:{managed_hosts:{total:0},remote_services:{total:0,enabled:0},policies:{remote:{enabled:0}}}};
 for(const role of ["Admin","Read Only"]){
  const html=renderToStaticMarkup(React.createElement(home.FirstUseHome,{
   data:empty,operator:{role},api:async()=>{throw new Error("SSR must not fetch")},
  }));
  assert.match(html,/data-testid="uxb-first-connection"/);
  for(const phrase of ["Add and approve a server","Publish a specific service","Create narrow access rules","Test and explain the connection"]){
   assert.ok(html.includes(phrase),phrase);
  }
  assert.ok(html.includes("Needs verification"));
  for(const purpose of ["Connect to a server","Allow approved outbound access","Grant an AI integration permission"]){
    assert.ok(html.includes(purpose),purpose);
  }
  for(const action of ["Set up Remote Access","Set up Internet Access","Set up AI Access"]){
    assert.ok(html.includes(action),action);
  }
  assert.ok(!html.includes("Secret="));
  // Read Only can view the setup guide, but role-bound changes stay disabled.
  assert.match(html,/>Open guided setup →<\/button>/);
  assert.doesNotMatch(html,/<button[^>]*disabled=""[^>]*>Open guided setup →<\/button>/);
 }
});

test("M1 Home rejects impossible Core counts and inconsistent step completion",()=>{
 for(const bad of [-1,1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,"0",null]){
  assert.equal(home.observedNumber(bad),"UNKNOWN",String(bad));
 }
 const good={overview:{managed_hosts:{total:2},remote_services:{total:1,enabled:1},
  policies:{ai:{total:0,enabled:0},remote:{total:1,enabled:1}}}};
 assert.equal(home.hasObservedCoreOverview(good),true);
 for(const invalid of [
  {...good,overview:{...good.overview,managed_hosts:{total:-1}}},
  {...good,overview:{...good.overview,managed_hosts:{total:2,pending_approval:-1}}},
  {...good,overview:{...good.overview,managed_hosts:{total:2,pending_approval:3}}},
  {...good,overview:{...good.overview,remote_services:{total:1,enabled:2}}},
  {...good,overview:{...good.overview,policies:{ai:{total:0,enabled:-1}}}},
  {...good,overview:{...good.overview,policies:{remote:{total:0,enabled:5}}}},
 ]){
  assert.equal(home.hasObservedCoreOverview(invalid),false);
  assert.equal(home.firstConnectionStates(invalid,[])[0],"Unknown");
 }
 const partial={overview:{...good.overview,policies:{remote:{enabled:1},ai:{total:0,enabled:0}}}};
 assert.equal(home.firstConnectionStates(partial,[])[3],"Unknown");
});
test("Home Host page cannot claim complete approval queue from invalid/unknown admission",()=>{
 for(const bad of [
  {items:[null],next_cursor:null},
  {items:[{id:"host-1"}],next_cursor:null},
  {items:[{admission_state:"INVALID"}],next_cursor:null},
  {items:Array.from({length:101},(_,i)=>({id:"h"+i,admission_state:"APPROVED"})),next_cursor:null},
  {items:[],next_cursor:""}
 ]){
  assert.equal(home.hostInventoryPageComplete(bad),null);
 }
 assert.equal(home.observedApprovalQueueCount(null,[{admission_state:"UNKNOWN"}],true),"UNKNOWN");
 assert.equal(home.observedApprovalQueueCount(null,[{admission_state:"APPROVED"}],true),0);
});
test("Recent Core Home feed cannot present malformed events as empty or render nested secrets",()=>{
 for(const rows of [[null],[{}],[{event_id:"evt\u202e"}],Array.from({length:7},(_,i)=>({event_id:"evt-"+i}))]){
  assert.deepEqual(home.observedRecentFeed({status:"fulfilled",value:{items:rows}}),
   {status:"unknown",items:[]});
 }
 const result=home.observedRecentFeed({status:"fulfilled",value:{items:[
  {event_id:"evt-1",event_type:"read",result:"allow",
   actor_id:{secret:"PRIVATE_ACTOR"},category:"ACCESS",
   unused:{key:"PRIVATE_KEY"}}
 ]}});
 assert.equal(result.status,"ready");
 assert.equal(result.items[0].event_id,"evt-1");
 assert.equal(result.items[0].actor_id,"UNKNOWN");
 assert.doesNotMatch(JSON.stringify(result),/PRIVATE_/);
 const revision=home.observedRecentFeed({status:"fulfilled",value:{items:[
  {revision:12,actor:"operator-a",summary:"Narrow SSH access",
   created_at:"2026-10-11T00:11:00Z"}
 ]}});
 assert.equal(revision.status,"ready");
 assert.equal(revision.items[0].revision,12);
});

test("FirstUseHome must fail closed before accepting malformed role-scoped Host inventory",()=>{
 const valid={items:[{id:"host-a",admission_state:"APPROVED",trust_status:"trusted",connected:true}],next_cursor:null};
 assert.deepEqual(home.observedHomeHostPage(valid),{items:valid.items,complete:true});
 assert.deepEqual(home.observedHomeHostPage({...valid,next_cursor:"opaque"}),{items:valid.items,complete:false});
 for(const invalid of [
  null,{items:null},{items:[null],next_cursor:null},
  {items:[{id:"host-a"}],next_cursor:null},
  {items:[{id:"host-a",admission_state:"INVALID"}],next_cursor:null},
  {items:[{id:{secret:"private"},admission_state:"APPROVED"}],next_cursor:null},
  {items:Array.from({length:101},(_,i)=>({id:"host-"+i,admission_state:"APPROVED"})),next_cursor:null}
 ]){
  assert.equal(home.observedHomeHostPage(invalid),null);
 }
 const source=readFileSync(join(root,"src","uxb-home.tsx"),"utf8");
 assert.match(source,/const observed=observedHomeHostPage\(payload\)/);
 assert.match(source,/if\(!observed\)throw new Error\("Core inventory response missing or malformed items"\)/);
 assert.match(source,/\},\[api,operator\?\.id,operator\?\.role\]\)/);
 assert.match(source,/setInventory\(null\);setInventoryComplete\(null\);setLoadState\("loading"\)/);
});

test("Host inventory evidence must remain private to its exact current Web operator and role",()=>{
 const actor={id:"web-operator-a",role:"Admin"};
 const scope={id:"web-operator-a",role:"Admin"};
 assert.equal(home.homeInventoryMatchesActor(scope,actor),true);
 for(const other of [
  {id:"web-operator-b",role:"Admin"},
  {id:"web-operator-a",role:"Operator"},
  {id:"web-operator-a",role:"Read Only"},
  {id:"",role:"Admin"},
  {id:"web-operator-a",role:"Unknown"}
 ])assert.equal(home.homeInventoryMatchesActor(scope,other),false,JSON.stringify(other));
 assert.equal(home.homeInventoryMatchesActor(null,actor),false);
 assert.equal(home.homeInventoryMatchesActor({id:"web-operator-a",role:"Admin"},null),false);
 const src=readFileSync(join(root,"src","uxb-home.tsx"),"utf8");
 assert.match(src,/const matchingActor=homeInventoryMatchesActor\(loadedFor,operator\)/);
 assert.match(src,/const scopedInventory=matchingActor\?inventory:null/);
 assert.match(src,/\},\[api,operator\?\.id,operator\?\.role\]\)/);
});

test("Competitor UX-4 Home evidence shows Core derived scope and observed time, not invented freshness",()=>{
 const overview={schema_version:1,state_class:"DERIVED",authoritative:false,rebuildable:true,
  generated_at:"2026-10-11T03:10:11Z",
  managed_hosts:{total:3,pending_approval:1},remote_services:{total:1,enabled:1},
  policies:{ai:{total:0,enabled:0},remote:{total:1,enabled:1}}};
 assert.deepEqual(home.observedCoreOverviewEvidence({overview}),{
  status:"observed",scope:"Fleet-wide derived Core counts",
  observedAt:"2026-10-11T03:10:11Z"});
 const html=renderToStaticMarkup(React.createElement(home.FirstUseHome,{
  data:{overview},operator:{id:"reader-a",role:"Read Only"},
  api:async()=>{throw new Error("SSR must not call Core")}}));
 assert.match(html,/Core overview evidence/);
 assert.match(html,/Fleet-wide derived Core counts/);
 assert.match(html,/2026-10-11T03:10:11Z/);
 assert.match(html,/Not proof of live connectivity/);
 assert.match(html,/Inspect System Health/);
 assert.doesNotMatch(html,/All systems healthy|Live access verified/);
});
test("UX-4 invalid or missing Core provenance/timestamps are UNKNOWN, never a healthy-looking timestamp",()=>{
 const base={schema_version:1,state_class:"DERIVED",authoritative:false,rebuildable:true,
  generated_at:"2026-10-11T03:10:11Z",
  managed_hosts:{total:0},remote_services:{total:0,enabled:0},
  policies:{ai:{total:0,enabled:0}}};
 for(const partial of [
  null,{overview:{}},
  {overview:{...base,state_class:"AUTHORITATIVE"}},
  {overview:{...base,authoritative:true}},
  {overview:{...base,rebuildable:false}},
  {overview:{...base,managed_hosts:{total:-1}}},
 ]){
  assert.deepEqual(home.observedCoreOverviewEvidence(partial),{
   status:"UNKNOWN",scope:"UNKNOWN",observedAt:"UNKNOWN"});
 }
 for(const bad of [null,{}, "yesterday","2026-02-30T00:00:00Z","2026-10-11\nspoof",
   "2026-10-11T03:10:11Z\u202e",42]){
  const evidence=home.observedCoreOverviewEvidence({overview:{...base,generated_at:bad}});
  assert.equal(evidence.scope,"Fleet-wide derived Core counts");
  assert.equal(evidence.observedAt,"UNKNOWN");
  assert.equal(evidence.status,"UNKNOWN");
  const html=renderToStaticMarkup(React.createElement(home.FirstUseHome,{
   data:{overview:{...base,generated_at:bad}},
   operator:{id:"admin-a",role:"Admin"},api:async()=>Promise.resolve({items:[]})}));
  assert.match(html,/Core overview UNKNOWN/);
  assert.match(html,/Observation timestamp unavailable/);
  assert.doesNotMatch(html,/spoof|\[object Object\]/);
 }
});

test("UX-4 Core attention items provide bounded task-specific read-only inspection routes",()=>{
 const page={attention:{authoritative:false,count:4,generated_at:"2026-10-11T03:19:00Z",items:[
  {kind:"pending-host-approval",label:"Managed Hosts Pending Approval",count:2,severity:"warning"},
  {kind:"degraded-remote-services",label:"DEGRADED Remote Services",count:1,severity:"warning"},
  {kind:"failed-jobs",label:"Failed Management Jobs",count:4,severity:"warning"},
  {kind:"webhook-delivery",label:"Signed Webhook Delivery Degraded",count:1,severity:"warning"}
 ]}};
 const admin=home.observedHomeAttention(page,"Admin");
 assert.equal(admin?.items.length,4);
 assert.deepEqual(admin?.items.map(item=>[item.route,item.group]),[
  ["hosts","connections"],["services","connections"],["jobs","activity"],["integrations","administration"]]);
 assert.equal(admin?.observedAt,"2026-10-11T03:19:00Z");
 const readonly=home.observedHomeAttention(page,"Read Only");
 assert.equal(readonly.items[3].route,"health");
 assert.equal(readonly.items[3].group,"activity");
 const html=renderToStaticMarkup(React.createElement(home.FirstUseHome,{
  data:{...page,overview:{managed_hosts:{total:2},remote_services:{total:1,enabled:1},policies:{ai:{total:0,enabled:0}}}},
  operator:{id:"reader-a",role:"Read Only"},api:async()=>{throw Error("SSR may not read Core")}}));
 assert.match(html,/Investigate Core attention/);
 assert.match(html,/DEGRADED Remote Services/);
 assert.match(html,/Failed Management Jobs/);
 assert.match(html,/Inspect Services/);
 assert.match(html,/Inspect Jobs/);
 assert.match(html,/Core attention observed at/);
 assert.doesNotMatch(html,/Inspect integrations|No current attention items/);
});
test("UX-4 malformed or stale-looking attention cannot claim zero problems or expose nested Core payloads",()=>{
 const valid={attention:{authoritative:false,count:1,generated_at:"2026-10-11T00:00:00Z",
  items:[{kind:"version-drift",label:"Agent Version Drift",count:1,severity:"warning"}]}};
 for(const bad of [
  null,{}, {attention:{items:[]}}, {attention:{...valid.attention,count:0}},
  {attention:{...valid.attention,authoritative:true}},
  {attention:{...valid.attention,generated_at:"yesterday"}},
  {attention:{...valid.attention,items:[null]}},
  {attention:{...valid.attention,items:[{kind:"version-drift",label:{secret:"PRIVATE"},count:1,severity:"warning"}]}},
  {attention:{...valid.attention,items:[{kind:"version-drift",label:"Agent\u202e Drift",count:1,severity:"warning"}]}},
  {attention:{...valid.attention,items:[{kind:"version-drift",label:"Agent Version Drift",count:-1,severity:"warning"}]}},
  {attention:{...valid.attention,items:[{kind:"version-drift",label:"Agent Version Drift",count:1,severity:"unsafe"}]}}
 ])assert.equal(home.observedHomeAttention(bad,"Read Only"),null);
 const unexpected=home.observedHomeAttention({attention:{...valid.attention,
  items:[{kind:"constructor",label:"New Core signal",count:1,severity:"info"}]}},"Read Only");
 assert.equal(unexpected?.items[0].route,"doctor");
 assert.equal(unexpected?.items[0].action,"Troubleshoot");
 assert.equal(home.observedHomeAttention({attention:{authoritative:false,count:0,
  generated_at:"2026-10-11T00:00:00Z",items:[]}},"Read Only")?.items.length,0);
 const none=renderToStaticMarkup(React.createElement(home.FirstUseHome,{
  data:null,operator:{id:"reader-a",role:"Read Only"},
  api:async()=>{throw Error("SSR may not read Core")}}));
 assert.match(none,/Core attention UNKNOWN/);
 assert.doesNotMatch(none,/No current attention items|PRIVATE/);
});
