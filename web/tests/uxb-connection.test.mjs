// UXB-03 offline render/security contract; NOT a live browser or Client E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,setup,service,policy,impact,enrollment;
before(async()=>{
 scratch=mkdtempSync(join(root,"node_modules",".uxb-connection-"));
 for(const [name,entry] of [
  ["setup","uxb-setup.tsx"],["service","uxb-remote-service.tsx"],["policy","p0-access-policy.tsx"],
  ["impact","uxb-impact-evidence.ts"],["enrollment","p0-enrollment.tsx"],
 ]){
  const out=join(scratch,name+".mjs");
  await build({entryPoints:[join(root,"src",entry)],outfile:out,
   platform:"node",format:"esm",bundle:true,jsx:"automatic",
   external:["react","react/jsx-runtime"],logLevel:"silent"});
 }
 setup=await import(pathToFileURL(join(scratch,"setup.mjs")).href);
 service=await import(pathToFileURL(join(scratch,"service.mjs")).href);
 policy=await import(pathToFileURL(join(scratch,"policy.mjs")).href);
 impact=await import(pathToFileURL(join(scratch,"impact.mjs")).href);
 enrollment=await import(pathToFileURL(join(scratch,"enrollment.mjs")).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

test("Policy Preview, required tests and Apply lock parent setup navigation without claiming completion",()=>{
 assert.equal(setup.isWizardBusy(false,false,false),false);
 assert.equal(setup.isWizardBusy(true,false,false),true);
 assert.equal(setup.isWizardBusy(false,true,false),true);
 assert.equal(setup.isWizardBusy(false,false,true),true);
 assert.equal(setup.isWizardBusy(true,true,true),true);
});
test("separate Remote, Internet and AI first-use journeys preserve security semantics",()=>{
 assert.deepEqual(setup.firstUseStages.remote,[
  "Add & approve Agent","Publish one Remote Service","Define a narrow access rule","Verify the decision"]);
 assert.deepEqual(setup.firstUseStages.internet,[
  "Select managed source","Choose outside destination","Define an Internet Access rule","Verify the decision"]);
 assert.deepEqual(setup.firstUseStages.ai,[
  "Select AI Identity","Choose a Permission Object","Define an AI Access rule","Verify the permission"]);
 assert.equal(setup.firstUseStages.internet.some(x=>x.includes("Remote Service")),false);
 assert.equal(setup.firstUseStages.ai.some(x=>x.includes("Remote Service")),false);
});

test("Guided Policy to Access Workspace preserves only complete bounded non-secret flow intent",()=>{
 const full=setup.connectionReviewContext("internet"," office "," archive "," https-443 ");
 assert.deepEqual(full,{plane:"internet",source:"office",destination:"archive",selector:"https-443"});
 assert.deepEqual(setup.connectionReviewContext("ai"," bot "," repo "," read "),{
   plane:"ai",source:"bot",destination:"repo",selector:"read"});
 for(const fields of [["","dst","svc"],["src","","svc"],["src","dst",""],
   ["src\nsecret","dst","svc"],["src","dst","a".repeat(161)],[null,"dst","svc"]]){
   assert.deepEqual(setup.connectionReviewContext("remote",...fields),{plane:"remote"});
 }
 assert.deepEqual(setup.connectionReviewContext("remote","one","two","three"),{
   plane:"remote",source:"one",destination:"two",selector:"three"});
});
test("Guided policy exposes contextual Core explanation without automatic Apply or saved credentials",()=>{
 for(const role of ["Admin","Operator","Read Only"]){
   const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
     api:async()=>{throw new Error("SSR cannot contact Core")},operator:{role},
     initialDraft:{plane:"internet",step:3,source:"source-a",destination:"target-b",selector:"https-443"},
   }));
   assert.match(html,/Test &amp; explain selected access/);
   assert.match(html,/navigation only/);
   assert.doesNotMatch(html,/Core applied rule change at revision/);
   assert.match(html,/source-a/);
   if(role==="Read Only")assert.match(html,/Your role is read-only/);
 }
 const incomplete=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
   api:async()=>{throw new Error("SSR cannot contact Core")},operator:{role:"Operator"},
   initialDraft:{plane:"ai",step:3,source:"bot-a",destination:"",selector:"read"},
 }));
 assert.match(incomplete,/incomplete/);
 const review=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
   api:async()=>{throw new Error("SSR cannot contact Core")},operator:{role:"Admin"},
   initialDraft:{plane:"ai",step:4,source:"bot-a",destination:"resource-b",selector:"read"},
 }));
 assert.match(review,/Review selected flow in Guided Policy/);
 assert.match(review,/Returning to rule definition starts a fresh Core Preview/);
 const source=readFileSync(join(root,"src","uxb-setup.tsx"),"utf8");
 assert.match(source,/onNavigate=\{navigateFromSetup\}/);
 assert.match(source,/id==="access"\?reviewContext:context/);
});
test("Policy impact controls render UNKNOWN for missing flags, counts and references",()=>{
 for(const [value,want] of [[true,"YES"],[false,"NO"],[null,"UNKNOWN"],
   [0,"UNKNOWN"],["false","UNKNOWN"],[undefined,"UNKNOWN"]]){
   assert.equal(impact.observedCoreFlag(value),want);
 }
 assert.equal(impact.observedCoreCount(0),0);
 assert.equal(impact.observedCoreCount(3),3);
 for(const invalid of [undefined,null,-1,NaN,"0",Infinity,1.2]){
   assert.equal(impact.observedCoreCount(invalid),"UNKNOWN");
 }
 assert.equal(impact.observedCoreNames(null),"UNKNOWN");
 assert.equal(impact.observedCoreNames(""),"UNKNOWN");
 assert.equal(impact.observedCoreNames([]),"none reported");
 assert.equal(impact.observedCoreNames(["rule-1","rule-2"]),"rule-1, rule-2");
 assert.equal(impact.observedCoreNames(["",123]),"UNKNOWN");
 assert.match(impact.observedCoreNames(Array.from({length:11},(_,i)=>"rule-"+i)),/first 8 of 11/);
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 assert.match(main,/observedCoreFlag\(blast.access_broadened\)/);
 assert.match(main,/observedCoreFlag\(limits.truncated\)/);
 assert.match(main,/observedCoreCount\(limits.newly_blocked_total\)/);
 assert.match(main,/observedCoreNames\(blast.affected_rules\)/);
 assert.match(main,/Missing impact fields are UNKNOWN/);
});
test("Access → Draft → Guided Policy navigation keeps bounded intent as read-only reference",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const access=src.split("function AccessOperations(",2)[1]?.split("function AuditExplorer(",1)[0]||"";
 const draftRef=src.split("function DraftWorkflowReference(",2)[1]?.split("function DraftWorkspace(){",1)[0]||"";
 const policy=src.split("function PolicyWorkspace(",2)[1]?.split("function ResourceWorkspace(",1)[0]||"";
 const view=src.split("function View(",2)[1]?.split("function WorkspaceIcon(",1)[0]||"";
 assert.match(access,/const flowContext=connectionReviewContext\(plane as AccessPlane,source,destination,selector\)/);
 assert.match(access,/onNavigate\?\.\("drafts","access",flowContext\)/);
 assert.match(access,/onNavigate\?\.\("policies","access",flowContext\)/);
 assert.match(draftRef,/connectionReviewContext\(plane,context\?\.source,context\?\.destination,context\?\.selector\)/);
 assert.match(draftRef,/reference only/);
 assert.match(draftRef,/not added to ConfigurationBundle/);
 assert.match(draftRef,/not carry a Change Plan or approval/);
 assert.match(draftRef,/onNavigate\?\.\("policies","access",selected\)/);
 assert.match(draftRef,/onNavigate\?\.\("access","access",selected\)/);
 assert.match(policy,/onNavigate\?\.\("drafts","access",carriedFlow\|\|undefined\)/);
 assert.match(policy,/not an approved rule/);
 assert.match(view,/DraftWorkflowReference context=\{context\} onNavigate=\{onNavigate\}/);
 assert.match(view,/initialPlane=\{selectedPlane\} initialFlow=\{"source" in initialFlow\?initialFlow:undefined\}/);
 const coreDraft=src.split("function DraftWorkspace(){",2)[1]?.split("function BlastRadiusView(",1)[0]||"";
 assert.match(coreDraft,/if\(!draftId\|\|!preview\?\.change_plan_id\|\|confirmation!=="APPLY"\)return;/);
 assert.match(coreDraft,/onChange=\{e=>changeBundle\(e.target.value\)\}/);
 for(const unsafe of ["connectionReviewContext","setBundle(context","autoApply","/api/v1/policy/direct-apply"])
   assert.ok(!coreDraft.includes(unsafe),unsafe);
});
test("Only an explicit, complete recognized-plane selection can be reused for navigation",()=>{
 const s=setup.connectionReviewContext("remote","  net-a  "," server-b ","ssh");
 assert.deepEqual(s,{plane:"remote",source:"net-a",destination:"server-b",selector:"ssh"});
 assert.deepEqual(setup.connectionReviewContext("ai","identity","object",""),{plane:"ai"});
 assert.deepEqual(setup.connectionReviewContext("internet","id","target","service\ninvalid"),{plane:"internet"});
});
test("Explicitly switching owning Agent invalidates prior service and policy choices",()=>{
 const saved={
  plane:"remote",step:2,selectedHost:"host-a",serviceName:"ssh-on-a",
  source:"source-on-a",destination:"destination-on-a",selector:"ssh-a",
  service:{owner:"host-a",name:"ssh-on-a",service:"ssh-a",destination:"this-host"}
 };
 const changed=setup.retargetRemoteHost(saved,"host-b");
 assert.deepEqual(changed,{
  ...saved,selectedHost:"host-b",serviceName:"",source:"",destination:"",selector:"",
  service:{owner:"host-b",name:"",service:"",destination:"this-host"}
 });
 assert.deepEqual(saved.service,{owner:"host-a",name:"ssh-on-a",service:"ssh-a",destination:"this-host"});
 const gone=setup.retargetRemoteHost(changed,"");
 assert.equal(gone.service.owner,"");
 assert.equal(gone.selector,"");
 assert.equal(gone.serviceName,"");
});
test("Restored first-use draft never retains another Agent's service or access choices",()=>{
 const mismatched={plane:"remote",step:2,selectedHost:"host-a",serviceName:"ssh-on-b",
  source:"source-for-b",destination:"target-for-b",selector:"ssh-b",
  service:{owner:"host-b",name:"ssh-on-b",service:"ssh-b",destination:"this-host"}};
 const safe=setup.reconcileHostBoundDraft(mismatched);
 assert.equal(safe.selectedHost,"host-a");
 assert.equal(safe.service.owner,"host-a");
 assert.equal(safe.service.name,"");
 assert.equal(safe.serviceName,"");
 assert.equal(safe.source,"");
 assert.equal(safe.destination,"");
 assert.equal(safe.selector,"");
 assert.deepEqual(mismatched.service,{owner:"host-b",name:"ssh-on-b",service:"ssh-b",destination:"this-host"});
 const matching={...mismatched,service:{...mismatched.service,owner:"host-a"}};
 assert.deepEqual(setup.reconcileHostBoundDraft(matching),matching);
 const ai={...mismatched,plane:"ai"};
 assert.deepEqual(setup.reconcileHostBoundDraft(ai),ai);
 const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
   api:async()=>{throw new Error("SSR must not call Core")},
   operator:{role:"Admin"},initialDraft:{...mismatched,step:3}
 }));
 for(const oldName of ["source-for-b","target-for-b","ssh-b"]){
   assert.doesNotMatch(html,new RegExp('value="'+oldName+'"'));
 }
});
test("Next action is specific and never claims a verified connection",()=>{
 const basis={hosts:[],selectedHost:"",source:"",destination:"",selector:"",serviceName:""};
 assert.match(setup.firstConnectionGuidance("remote",1,basis),/Add an Agent|Select an observed Agent/);
 assert.match(setup.firstConnectionGuidance("remote",1,{...basis,hosts:null}),/UNKNOWN/);
 assert.match(setup.firstConnectionGuidance("remote",1,{...basis,hosts:[{id:"host-a",admission_state:"PENDING_APPROVAL"}],selectedHost:"host-a"}),/approval/);
 assert.match(setup.firstConnectionGuidance("remote",2,basis),/Agent/);
 assert.match(setup.firstConnectionGuidance("remote",2,{...basis,selectedHost:"host-a",serviceName:"ssh"}),/job|verified/i);
 assert.match(setup.firstConnectionGuidance("internet",1,basis),/managed source/i);
 assert.match(setup.firstConnectionGuidance("internet",2,basis),/destination.*service/i);
 assert.match(setup.firstConnectionGuidance("ai",1,basis),/AI Identity/);
 assert.match(setup.firstConnectionGuidance("ai",2,basis),/permission.*destination/i);
 assert.match(setup.firstConnectionGuidance("remote",3,basis),/source|destination|service/);
 assert.match(setup.firstConnectionGuidance("ai",4,basis),/NOT VERIFIED/);
});
test("first-use setup serves one continuous four-stage workflow and shows no fabricated success",()=>{
 const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
  api:async()=>{throw new Error("SSR must not call Core API")},
  operator:{role:"Admin"},
 }));
 assert.match(html,/data-testid="uxb-connection-setup"/);
 for(const stage of setup.firstUseStages.remote)assert.ok(
  html.includes(stage.replaceAll("&","&amp;")),stage);
 assert.match(html,/Core-authoritative connection setup/);
 assert.match(html,/Core policy reachability: NOT VERIFIED/);
 assert.match(html,/NO HOST SELECTED|UNKNOWN/);
 assert.match(html,/Connect an Agent in four steps/);
 assert.doesNotMatch(html,/connection successful/i);
});
test("non-admin never sees enabled enrollment issue during setup",()=>{
 const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
  api:async()=>{throw new Error("SSR must not call Core API")},
  operator:{role:"Read Only"},
 }));
 assert.match(html,/<button[^>]*disabled=""[^>]*>Issue enrollment →<\/button>/);
});

test("First-time Admin picks an understandable purpose, sees glossary, and does not skip Core evidence",()=>{
 const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
   api:async()=>{throw new Error("SSR cannot contact Core")},operator:{role:"Admin"}
 }));
 for(const purpose of ["Connect to an internal server","Let a server reach the Internet","Allow an AI integration"]){
   assert.ok(html.includes(purpose),purpose);
 }
 assert.match(html,/aria-pressed="true"/);
 assert.match(html,/What do Agent, Remote Service and Access Rule mean/);
 assert.match(html,/Current stage 1 of 4/);
 assert.match(html,/changing stages does not modify access/i);
 assert.match(html,/NOT VERIFIED/);
});
test("Internet and AI setup explain separate prerequisites and offer Core selectors without approval",()=>{
 for(const [plane,stageLabel,field] of [
   ["internet","Select the intended outside destination","Service Object / Group"],
   ["ai","Select a named Permission Object","Permission Object / Group"],
 ]){
   const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
     api:async()=>{throw new Error("SSR cannot contact Core")},
     operator:{role:"Operator"},initialDraft:{plane,step:2}
   }));
   assert.match(html,/Core inventory UNKNOWN/);
   assert.match(html,new RegExp(field.replace("/","\\/")));
   assert.match(html,/Manage Objects &amp; Groups/);
   assert.doesNotMatch(html,/Queue authenticated Agent job/);
   assert.doesNotMatch(html,/Applied at revision/);
 }
});
test("Core-backed policy suggestions are optional; no implicit change is queued",()=>{
 const catalog={resources:{
   "network-object":{items:[{name:"source-office"},{name:"destination-app"}]},
   "network-group":{items:[]},
   "service-object":{items:[{name:"ssh-tcp22"}]},
   "service-group":{items:[]},
 }};
 const html=renderToStaticMarkup(React.createElement(policy.GuidedPolicyJourney,{
   api:async()=>{throw new Error("SSR cannot contact Core")},
   resourceCatalog:catalog,initialPlane:"remote",
   initialFlow:{source:"source-office",destination:"destination-app",selector:"ssh-tcp22"}
 }));
 assert.match(html,/Choose who, where and what/);
 assert.match(html,/Prepared SET/);
 assert.match(html,/Advanced · review or enter exact Core names manually/);
 assert.match(html,/Not submitted to Core until a fresh Preview, required tests and explicit Apply/);
 assert.match(html,/source-office/);
 assert.match(html,/ssh-tcp22/);
 assert.match(html,/Core validates the change/);
 assert.doesNotMatch(html,/Apply through Core/);
});
test("Guided setup cannot publish to a Host other than the observed explicit selection",()=>{
 assert.equal(service.remoteServiceOwner("host-a","host-b",true),"host-b");
 assert.equal(service.remoteServiceOwner("host-a","host-b",false),"host-a");
 assert.equal(service.remoteServiceOwner("host-a","",true),"");
 const guided=renderToStaticMarkup(React.createElement(service.RemoteServiceEditor,{
  api:async()=>{throw new Error("SSR must not call Core")},
  ownerHint:"host-b",lockOwner:true,
  initialSelection:{owner:"host-a",name:"ssh-admin",service:"ssh-tcp22",destination:"this-host"}
 }));
 assert.match(guided,/Owning Agent \/ Managed Host/);
 assert.match(guided,/value="host-b"/);
 assert.match(guided,/readOnly=""/);
 assert.doesNotMatch(guided,/value="host-a"/);
 const unset=renderToStaticMarkup(React.createElement(service.RemoteServiceEditor,{
  api:async()=>{throw new Error("SSR must not call Core")},
  ownerHint:"",lockOwner:true,
  initialSelection:{owner:"host-a",name:"ssh-admin",service:"ssh-tcp22",destination:"this-host"}
 }));
 assert.match(unset,/readOnly=""/);
 assert.match(unset,/value=""/);
 assert.match(unset,/<button[^>]*disabled=""[^>]*>Preview service impact<\/button>/);
 const raw=renderToStaticMarkup(React.createElement(service.RemoteServiceEditor,{
  api:async()=>{throw new Error("SSR must not call Core")},
  ownerHint:"host-b",
  initialSelection:{owner:"host-a",name:"ssh-admin",service:"ssh-tcp22",destination:"this-host"}
 }));
 assert.match(raw,/value="host-a"/);
 assert.doesNotMatch(raw,/readOnly=""/);
});
test("Setup does not mount a Host-bound editor until selected Host is observed",()=>{
 const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
  api:async()=>{throw new Error("SSR must not call Core")},
  operator:{role:"Admin"},
  initialDraft:{plane:"remote",step:2,selectedHost:"host-a",
   service:{owner:"host-a",name:"ssh-admin",service:"ssh-tcp22",destination:"this-host"}},
 }));
 assert.match(html,/Selected Agent must be observed/);
 assert.match(html,/Go to Agent selection/);
 assert.doesNotMatch(html,/data-testid="uxb-remote-service"/);
});
test("service publication is preview/typed/queued and cannot imply deployed",()=>{
 const html=renderToStaticMarkup(React.createElement(service.RemoteServiceEditor,{
  api:async()=>{throw new Error("SSR must not call Core API")},
  ownerHint:"host-a",
 }));
 assert.match(html,/data-testid="uxb-remote-service"/);
 assert.match(html,/Host name or ID|Owning Agent/);
 assert.match(html,/Preview service impact/);
 assert.match(html,/<button[^>]*disabled=""[^>]*>Preview service impact<\/button>/);
 assert.doesNotMatch(html,/Queue authenticated Agent job/);
 const source=readFileSync(join(root,"src","uxb-remote-service.tsx"),"utf8");
 for(const endpoint of ["/api/v1/remote-services/preview","/api/v1/remote-services/apply","/api/v1/jobs/"]){
  assert.ok(source.includes(endpoint),endpoint);
 }
 assert.match(source,/setPreview\(null\)/);
 assert.match(source,/preview\.change_plan_id/);
 assert.match(source,/confirmation!==required/);
 assert.match(source,/does not instantly prove success|queued Agent job is NOT|queued Agent job is not/i);
});

test("Remote Service queued job stays refreshable after Core job-detail response",()=>{
 const queued={job_id:"job-42",status:"QUEUED"};
 const running=service.mergeRemoteServiceJob(queued,{id:"job-42",status:"RUNNING",targets:[]});
 assert.equal(running.job_id,"job-42");
 assert.equal(running.status,"RUNNING");
 assert.equal(running.id,"job-42");
 const done=service.mergeRemoteServiceJob(running,{id:"job-42",status:"SUCCEEDED"});
 assert.equal(done.job_id,"job-42");
 assert.equal(done.status,"SUCCEEDED");
 assert.throws(()=>service.mergeRemoteServiceJob(queued,{id:"different",status:"RUNNING"}),/different Agent job identity/);
});

test("setup fixes selected plane for the Core-backed guided policy editor",()=>{
 const html=renderToStaticMarkup(React.createElement(policy.GuidedPolicyJourney,{
  api:async()=>{throw new Error("SSR must not call Core API")},
  initialPlane:"ai",lockedPlane:true,initialFlow:{selector:"permission-read"},
 }));
 assert.match(html,/<select[^>]*disabled=""[^>]*>/);
 assert.match(html,/Permission/);
 assert.match(html,/permission-read/);
 assert.doesNotMatch(html,/Apply through Core/);
 const src=readFileSync(join(root,"src","uxb-setup.tsx"),"utf8");
 assert.match(src,/initialPlane=\{plane\} lockedPlane/);
 assert.match(src,/onFlowChange=\{f=>/);
 assert.match(src,/canEdit&&selected\?<RemoteServiceEditor key=\{selectedHost\} api=\{api\} ownerHint=\{selectedHost\} lockOwner/);
 assert.match(src,/AccessEvidenceExplorer api=\{api\}/);
});

test("Returning to the setup guide restores non-secret stage and choices",()=>{
 const initialDraft={plane:"ai",step:4,source:"identity-a",destination:"object-b",selector:"permission-read",selectedHost:""};
 const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
  api:async()=>{throw new Error("SSR must not request Core API")},operator:{role:"Read Only"},initialDraft,
 }));
 assert.match(html,/Verify the permission/);
 assert.match(html,/value="identity-a"/);
 assert.match(html,/value="object-b"/);
 assert.match(html,/value="permission-read"/);
 assert.doesNotMatch(html,/Issue enrollment →/);
 const svc=renderToStaticMarkup(React.createElement(service.RemoteServiceEditor,{
   api:async()=>{throw new Error("SSR must not request Core API")},
   ownerHint:"host-b", // A prior manual owner selection must survive remount.
   initialSelection:{owner:"host-a",name:"ssh-admin",service:"ssh-tcp22",destination:"this-host"},
 }));
 assert.match(svc,/value="host-a"/);
 assert.match(svc,/value="ssh-admin"/);
 assert.match(svc,/value="ssh-tcp22"/);
 assert.doesNotMatch(svc,/Queue authenticated Agent job/); // no resumed mutation plan
});

test("Host approval needs explicit selection and missing enrollment evidence is UNKNOWN",()=>{
 const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
  api:async()=>{throw new Error("SSR must not call Core API")},operator:{role:"Admin"},
 }));
 assert.match(html,/Enrollment history: UNKNOWN/);
 assert.doesNotMatch(html,/No enrollment history reported\./);
 const setupSource=readFileSync(join(root,"src","uxb-setup.tsx"),"utf8");
 const enrollSource=readFileSync(join(root,"src","p0-enrollment.tsx"),"utf8");
 assert.match(setupSource,/const currentHost=selectedHostRef\.current/);
 assert.match(setupSource,/if\(currentHost&&\!list\.some/);
 assert.match(setupSource,/chooseRemoteHost\(e\.target\.value\)/);
 assert.match(setupSource,/setServiceDraft\(prev=>\(\{\.\.\.prev,owner:""\}\)\)/);
 assert.match(enrollSource,/setSelectedHost\(value=>value&&observed\.items\.some/);
 assert.match(enrollSource,/Select an observed Managed Host/);
});

test("no browser-local credentials or unapproved backend policy engine",()=>{
 const src=["uxb-navigation.ts","uxb-home.tsx","uxb-setup.tsx","uxb-remote-service.tsx"].map(
  x=>readFileSync(join(root,"src",x),"utf8")).join("\n");
 for(const forbidden of ["localStorage.","sessionStorage.","document.cookie=","/api/v1/policy/direct-apply"]){
  assert.equal(src.includes(forbidden),false,forbidden);
 }
});

test("Core impact lists reject direction-changing or control text instead of reporting spoofed affected rules",()=>{
 for(const unsafe of ["allow\u202eDeny","rule-1\nALLOW","\u2066private\u2069","\u0000hidden"]){
  assert.equal(impact.observedCoreNames(["trusted",unsafe]),"UNKNOWN",unsafe);
 }
 assert.equal(impact.observedCoreNames(["rule-1","rule-2"]),"rule-1, rule-2");
});

test("UX-8 cross-page context rejects bidi/C1 spoofing while retaining legitimate Unicode names",()=>{
 for(const bad of ["ssh\u202e","policy\u2066name","src\u0085spoof","dst\u007fhidden","\u202aprefix","\u2069tail"]){
  assert.deepEqual(setup.connectionReviewContext("remote",bad,"destination","ssh"),{plane:"remote"});
  assert.deepEqual(setup.connectionReviewContext("internet","source",bad,"https"),{plane:"internet"});
  assert.deepEqual(setup.connectionReviewContext("ai","bot","object",bad),{plane:"ai"});
 }
 assert.deepEqual(setup.connectionReviewContext("remote"," 서울-지점 "," DB서비스 "," SSH-22 "),{
  plane:"remote",source:"서울-지점",destination:"DB서비스",selector:"SSH-22"});
 const input=["src","dest","ssh"];
 assert.deepEqual(setup.connectionReviewContext("remote",...input),{
  plane:"remote",source:"src",destination:"dest",selector:"ssh"});
});

test("UX-3/Core wizard refuses malformed or cross-type first-page Host and Service inventory",()=>{
 const validHosts={resource_type:"managed-host",limit:100,next_cursor:null,
  items:[{id:"host-a",name:"서울 서버",admission_state:"APPROVED",connected:1}]};
 const validServices={resource_type:"remote-service",limit:100,next_cursor:null,
  items:[{id:"service-a",name:"관리 SSH",managed_host_id:"host-a",enabled:1}]};
 assert.deepEqual(setup.observedSetupInventory(validHosts,"managed-host"),validHosts.items);
 assert.deepEqual(setup.observedSetupInventory(validServices,"remote-service"),validServices.items);
 assert.deepEqual(setup.observedSetupInventory({items:[]},"managed-host"),[]);
 for(const bad of [
  null,{}, {items:"not-an-array"}, {items:[null]},{items:[42]},
  {items:[{id:null}]},{items:[{id:{secret:"DO_NOT_RENDER"}}]},
  {items:[{id:"host-a"},{id:"host-a"}]},
  {items:[{id:"host\u202e-a"}]},
  {items:[{id:"host-a",name:{secret:"DO_NOT_RENDER"}}]},
  {items:Array.from({length:101},(_,i)=>({id:"host-"+i}))},
  {resource_type:"remote-service",items:[{id:"host-a"}]},
  {items:[{id:"host-a"}],next_cursor:""},
  {items:[{id:"host-a"}],next_cursor:42},
 ]){
  assert.equal(setup.observedSetupInventory(bad,"managed-host"),null,JSON.stringify(bad)?.slice(0,100));
 }
 assert.equal(setup.observedSetupInventory(validServices,"managed-host"),null);
 assert.equal(setup.observedSetupInventory(validHosts,"remote-service"),null);
 const source=readFileSync(join(root,"src","uxb-setup.tsx"),"utf8");
 assert.match(source,/observedSetupInventory\(r\[0\]\.value,"managed-host"\)/);
 assert.match(source,/observedSetupInventory\(r\[1\]\.value,"remote-service"\)/);
});

test("UX-8 Service readiness must not confuse string false, null or partial Core data with enabled",()=>{
 for(const [v,want] of [
  [true,"CONFIGURED · VERIFY JOB"],[1,"CONFIGURED · VERIFY JOB"],
  [false,"DISABLED · VERIFY JOB"],[0,"DISABLED · VERIFY JOB"],
  ["false","UNKNOWN"],["0","UNKNOWN"],[null,"UNKNOWN"],
  [undefined,"UNKNOWN"],[-1,"UNKNOWN"],[{},"UNKNOWN"]
 ])assert.equal(setup.observedRemoteServiceReadiness(v),want);
 const source=readFileSync(join(root,"src","uxb-setup.tsx"),"utf8");
 assert.match(source,/observedRemoteServiceReadiness\(service\.enabled\)/);
 assert.doesNotMatch(source,/String\(service\.enabled\?/);
});

test("UX-3 invalid resumed setup draft must not crash UI or revive unsafe intent",()=>{
 for(const initialDraft of [
  {plane:"unknown-plane",step:"not-a-step",selectedHost:7,source:{secret:"PRIVATE_TOKEN"},
   service:{owner:{secret:"PRIVATE_OWNER"},name:42}},
  {plane:"remote",step:Infinity,source:"origin\u202e",destination:"DB서비스",selector:"ssh"},
  {plane:"ai",step:-1,source:"bot",destination:"object",selector:"read"},
  {plane:"internet",step:99,source:"source-a",destination:"target-b",selector:"service-a"},
  {plane:{toString(){throw Error("must not stringify untrusted plane")}},step:3},
 ]){
  const html=renderToStaticMarkup(React.createElement(setup.FirstConnectionSetup,{
   api:async()=>{throw Error("SSR must not fetch Core")},operator:{id:"viewer-a",role:"Read Only"},
   initialDraft,
  }));
  assert.match(html,/data-testid="uxb-connection-setup"/);
  assert.match(html,/Current stage [1-4] of 4/);
  assert.doesNotMatch(html,/PRIVATE_TOKEN|PRIVATE_OWNER|origin\u202e|\[object Object\]|undefined/);
 }
 const defaults=setup.safeResumedSetupDraft({plane:"wrong",step:"4",
   selectedHost:{id:"host-a"},source:"ssh\u2066"});
 assert.equal(defaults.plane,"remote");
 assert.equal(defaults.step,1);
 assert.equal(defaults.selectedHost,"");
 assert.equal(defaults.source,"");
});
test("UX-3 valid non-secret in-session user draft is restored exactly with owning Host guard",()=>{
 const original={plane:"remote",step:3,selectedHost:"host-a",serviceName:"admin-ssh",
  source:" 서울지점 ",destination:"database-a",selector:"ssh-22",
  service:{owner:"host-a",name:"admin-ssh",service:"ssh-22",destination:"this-host"}};
 const safe=setup.safeResumedSetupDraft(original);
 assert.equal(safe.plane,"remote");
 assert.equal(safe.step,3);
 assert.equal(safe.selectedHost,"host-a");
 assert.equal(safe.source,"서울지점");
 assert.deepEqual(safe.service,original.service);
 assert.deepEqual(setup.safeResumedSetupDraft({...original,service:{...original.service,owner:"other-host"}}).service,
   {owner:"host-a",name:"",service:"",destination:"this-host"});
 assert.equal(setup.safeResumedSetupDraft(null).step,1);
 const source=readFileSync(join(root,"src","uxb-setup.tsx"),"utf8");
 assert.match(source,/const restoredDraft=safeResumedSetupDraft\(initialDraft\)/);
});

test("UX-8 Remote Service Job detail shows only bounded safe status evidence, never Core arbitrary payload",()=>{
 const raw={id:"job-42",status:"RUNNING",target_count:3,
  updated_at:"2026-10-11T04:12:00Z",last_error:"none",
  access_token:"PRIVATE_TOKEN",credential:{private_key:"PRIVATE_KEY"},
  payload:{secret:"PRIVATE_PAYLOAD"},targets:[{result:{secret:"PRIVATE_RESULT"}}]};
 const safe=service.remoteServiceJobEvidence(raw);
 assert.deepEqual(safe,{job_id:"job-42",status:"RUNNING",target_count:3,
  updated_at:"2026-10-11T04:12:00Z",last_error:"none"});
 assert.doesNotMatch(JSON.stringify(safe),/PRIVATE_/);
 const source=readFileSync(join(root,"src","uxb-remote-service.tsx"),"utf8");
 assert.match(source,/const visibleJob=remoteServiceJobEvidence\(job\)/);
 assert.match(source,/JSON\.stringify\(visibleJob,null,2\)/);
 assert.doesNotMatch(source,/JSON\.stringify\(job,null,2\)/);
});
test("UX-8 malformed or control-tainted Core Job status/ID is UNKNOWN, not success",()=>{
 for(const bad of [
  null,[],{}, {job_id:{secret:"PRIVATE_ID"},status:"SUCCEEDED"},
  {job_id:"job\u202eSUCCESS",status:"SUCCEEDED"},
  {job_id:"job-42",status:{secret:"PRIVATE_STATUS"},target_count:"0"},
  {job_id:"job-42",status:"DONE",target_count:-1,updated_at:"yesterday"}
 ]){
  const view=service.remoteServiceJobEvidence(bad);
  assert.ok(["UNKNOWN","job-42"].includes(view.job_id));
  assert.equal(view.status,"UNKNOWN",JSON.stringify(bad));
  assert.doesNotMatch(JSON.stringify(view),/PRIVATE_|yesterday|\u202e/);
 }
 assert.equal(service.remoteServiceJobEvidence({job_id:"job-42",status:"SUCCEEDED",target_count:0}).status,"SUCCEEDED");
});

test("UX-3 enrollment history shows UNKNOWN for malformed Core pages, not falsely empty",()=>{
 const render=data=>renderToStaticMarkup(React.createElement(enrollment.EnrollmentOnboarding,{
  api:async()=>{throw Error("SSR cannot read Core")},data,refresh:()=>{},
  operator:{id:"reader-1",role:"Read Only"}
 }));
 const empty=render({items:[],total:0});
 assert.match(empty,/No enrollment history reported/);
 assert.doesNotMatch(empty,/Enrollment history: UNKNOWN/);
 for(const invalid of [
  null,undefined,{}, {items:null},{items:"not-an-array"},
  {items:[null]}, {items:[12]}, {items:[{id:""}]},
  {items:[{id:{secret:"PRIVATE_TICKET"}}]},
  {items:[{id:"ticket-1"}],total:0},
  {items:Array.from({length:51},(_,i)=>({id:"ticket-"+i}))}
 ]){
  const out=render(invalid);
  assert.match(out,/Enrollment history: UNKNOWN/);
  assert.doesNotMatch(out,/No enrollment history reported|PRIVATE_TICKET/);
 }
});
test("UX-3 enrollment history redacts malformed nested labels and bounded time evidence",()=>{
 const payload={total:3,items:[
  {id:"ticket-1",type:"zero-touch",state:"ACTIVE",label:" 서울지점 ",
   first_host_admission:"PENDING_APPROVAL",remaining_seconds:120,
   credential:{private_key:"PRIVATE_KEY"}},
  {id:"ticket-2",type:"manual",state:"PENDING",label:{secret:"PRIVATE_LABEL"},
   first_host_admission:{secret:"PRIVATE_APPROVAL"},remaining_seconds:"0"},
 ]};
 const projected=enrollment.observedEnrollmentHistory(payload);
 assert.equal(projected.status,"ready");
 assert.equal(projected.total,3);
 assert.equal(projected.partial,true);
 assert.equal(projected.items.length,2);
 assert.equal(projected.items[0].label,"서울지점");
 assert.equal(projected.items[0].remaining,"120 seconds");
 assert.equal(projected.items[1].label,"UNKNOWN");
 assert.equal(projected.items[1].admission,"UNKNOWN");
 assert.equal(projected.items[1].remaining,"UNKNOWN");
 assert.doesNotMatch(JSON.stringify(projected),/PRIVATE_/);
 const html=renderToStaticMarkup(React.createElement(enrollment.EnrollmentOnboarding,{
  api:async()=>{throw Error("SSR cannot fetch")},data:payload,refresh:()=>{},
  operator:{role:"Operator"}
 }));
 assert.match(html,/Showing first 2 of 3 observed enrollments/);
 assert.match(html,/120 seconds/);
 assert.match(html,/UNKNOWN/);
 assert.doesNotMatch(html,/PRIVATE_KEY|PRIVATE_LABEL|PRIVATE_APPROVAL|UNKNOWN seconds/);
});
test("UX-3 ticket identity and status reject control/bidi without echoing unsafe Core detail",()=>{
 const base={items:[{id:"ticket-1",label:"alias",type:"manual",state:"ACTIVE",
  first_host_admission:"PENDING_APPROVAL",remaining_seconds:0}],total:1};
 assert.equal(enrollment.observedEnrollmentHistory(base).items[0].remaining,"0 seconds");
 for(const bad of ["ticket\u202e", "ticket\u0085","t\nsecret","A".repeat(161)]){
  const input={...base,items:[{...base.items[0],id:bad}]};
  assert.equal(enrollment.observedEnrollmentHistory(input).status,"UNKNOWN");
 }
 for(const bad of ["ACTIVE\u2066", {secret:"PRIVATE_STATUS"}, "B".repeat(161)]){
  const input={...base,items:[{...base.items[0],state:bad}]};
  const safe=enrollment.observedEnrollmentHistory(input);
  assert.equal(safe.items[0].state,"UNKNOWN");
  assert.doesNotMatch(JSON.stringify(safe),/PRIVATE_|\u2066/);
 }
 const source=readFileSync(join(root,"src","p0-enrollment.tsx"),"utf8");
 assert.match(source,/const history=observedEnrollmentHistory\(data\)/);
 assert.doesNotMatch(source,/\(data\?\.items\|\|\[\]\)\.map/);
});

test("UX-3 Host readiness refuses nested or spoofed Core admission/trust as verified",()=>{
 for(const bad of [
  {admission_state:{toString(){throw Error("MUST_NOT_COERCE")}},
   trust_status:{secret:"PRIVATE_TRUST"},connected:"true",
   agent_heartbeat_at:{secret:"PRIVATE_TIME"}},
  {admission_state:"APPROVED\u202e",trust_status:"trusted",connected:true},
  {admission_state:"APPROVED",trust_status:"trusted\u2066",connected:true},
  {admission_state:"APPROVED",trust_status:"trusted",connected:"true"},
  {admission_state:"APPROVED",trust_status:"trusted",connected:2},
  []
 ]){
  const view=enrollment.hostReadiness(bad);
  assert.ok(view);
  assert.equal(view.policy,"NOT VERIFIED");
  assert.doesNotMatch(JSON.stringify(view),/PRIVATE_|\u202e|\u2066|\[object Object\]/);
  assert.notEqual(enrollment.hostReadinessLabel(bad),"CONNECTED · APPROVED · TRUSTED");
 }
 assert.equal(enrollment.hostReadiness({admission_state:"APPROVED",connected:true,
  trust_status:{toString(){throw Error("PRIVATE_MUST_NOT_COERCE")}}}).trust,"UNKNOWN");
});
test("UX-4 Agent last observation uses only verifiable absolute Core times",()=>{
 const valid={admission_state:"APPROVED",trust_status:"trusted",connected:1,
  agent_heartbeat_at:"2026-10-11T03:10:11Z",last_seen:"2026-09-18T10:10:00Z"};
 const fresh=enrollment.hostReadiness(valid);
 assert.equal(fresh.admission,"APPROVED");
 assert.equal(fresh.trust,"TRUSTED");
 assert.equal(fresh.connection,"CONNECTED");
 assert.equal(fresh.observedAt,"2026-10-11T03:10:11Z");
 for(const invalid of [{secret:"PRIVATE_TIMESTAMP"},"2026-02-30T00:00:00Z",
   "2026-10-11\u202eT03:10:11Z","yesterday",false]){
  const result=enrollment.hostReadiness({...valid,agent_heartbeat_at:invalid,last_seen:null});
  assert.equal(result.observedAt,"UNKNOWN");
  assert.doesNotMatch(JSON.stringify(result),/PRIVATE_|yesterday|\u202e|\[object Object\]/);
 }
 assert.equal(enrollment.hostReadiness({...valid,agent_heartbeat_at:null}).observedAt,
  "2026-09-18T10:10:00Z");
});

test("UX-3 onboarding chooses only unique bounded Host inventory, not arbitrary Core data",()=>{
 const host={id:"machine-a",name:" 서울-1 ",admission_state:"PENDING_APPROVAL",
  trust_status:"untrusted",connected:0,last_seen:"2026-10-11T03:10:11Z",
  private_token:"PRIVATE_TOKEN",credential:{secret:"PRIVATE_CREDENTIAL"}};
 const page={resource_type:"managed-host",items:[host],limit:100,next_cursor:null};
 const valid=enrollment.observedEnrollmentHostPage(page);
 assert.equal(valid?.complete,true);
 assert.deepEqual(valid?.items,[{id:"machine-a",name:"서울-1",
  admission_state:"PENDING_APPROVAL",trust_status:"untrusted",
  connected:0,last_seen:"2026-10-11T03:10:11Z"}]);
 assert.doesNotMatch(JSON.stringify(valid),/PRIVATE_/);
 assert.equal(enrollment.observedEnrollmentHostPage({...page,next_cursor:"opaque-2"})?.complete,false);
 // Missing Core page completeness is now unknown and cannot admit a Host selection.
 assert.equal(enrollment.observedEnrollmentHostPage({...page,next_cursor:undefined}),null);
 for(const invalid of [
  null,{},{items:null},{items:"text"},{...page,resource_type:"remote-service"},
  {...page,items:[null]},{...page,items:[{...host,id:{secret:"PRIVATE"}}]},
  {...page,items:[{...host,id:"machine\u202e-a"}]},
  {...page,items:[host,host]},{...page,items:[{...host,admission_state:"INVALID"}]},
  {...page,items:Array.from({length:101},(_,i)=>({...host,id:"machine-"+i}))},
  {...page,limit:101},{...page,next_cursor:{secret:"PRIVATE_CURSOR"}},
 ]){
  const observed=enrollment.observedEnrollmentHostPage(invalid);
  assert.equal(observed,null,JSON.stringify(invalid)?.slice(0,70));
 }
});
test("UX-3 enrollment Host options tolerate malformed display labels without leaking Core fields",()=>{
 const page={resource_type:"managed-host",limit:100,next_cursor:"continued",
  items:[{id:"host-a",name:{secret:"PRIVATE_HOSTNAME"},label:"oops\u2066",
   admission_state:"APPROVED",trust_status:{secret:"PRIVATE_TRUST"},
   connected:"true",agent_heartbeat_at:{secret:"PRIVATE_TIME"}}]};
 const observed=enrollment.observedEnrollmentHostPage(page);
 assert.equal(observed?.items[0]?.name,"host-a");
 assert.equal(observed?.items[0]?.connected,null);
 assert.equal(observed?.items[0]?.trust_status,"UNKNOWN");
 assert.equal(observed?.items[0]?.agent_heartbeat_at,undefined);
 assert.doesNotMatch(JSON.stringify(observed),/PRIVATE_|\u2066/);
 const src=readFileSync(join(root,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const observed=observedEnrollmentHostPage\(result\)/);
 assert.match(src,/setHosts\(observed\.items\)/);
 assert.match(src,/setHostsComplete\(observed\.complete\)/);
 assert.doesNotMatch(src,/setHosts\(result\.items\)/);
 assert.match(src,/Other Hosts may exist beyond this Core page/);
});

test("UX-3 issued Agent instructions require authentic display-once Core evidence",()=>{
 const valid={mode:"zero-touch",platform:"linux",state:"pending",
  expires_at:"2026-10-11T06:00:00Z",ttl_seconds:3600,
  command:"curl -f https://installer.example.invalid/agent | sh",
  display_once:true,management_only:true,pre_approved:false,
  next_step:"Run the command once on the selected Agent."};
 const parsed=enrollment.observedIssuedEnrollment(valid,"zero-touch","linux");
 assert.deepEqual(parsed,{
  mode:"zero-touch",platform:"linux",expires_at:"2026-10-11T06:00:00Z",
  command:valid.command,enrollment_code:"",pre_approved:false,
  next_step:valid.next_step
 });
 assert.equal(enrollment.observedIssuedEnrollment({...valid,pre_approved:true},"zero-touch","linux")?.pre_approved,true);
 const manual={...valid,mode:"manual",platform:"macos",ttl_seconds:600,
  enrollment_code:"a".repeat(16)+"."+"b".repeat(64)};
 const manualParsed=enrollment.observedIssuedEnrollment(manual,"manual","macos");
 assert.equal(manualParsed?.enrollment_code,manual.enrollment_code);
 assert.equal(manualParsed?.pre_approved,false);
 for(const bad of [
  null,{}, {...valid,mode:"manual"},{...valid,platform:"windows"},
  {...valid,command:{secret:"PRIVATE_CMD"}},
  {...valid,command:"curl -X GET\u202e hidden"},
  {...valid,display_once:false},{...valid,management_only:false},
  {...valid,pre_approved:"false"},{...valid,expires_at:"yesterday"},
  {...valid,ttl_seconds:"3600"},{...valid,command:"x".repeat(70000)},
  {...valid,state:"approved"},
 ]){
  assert.equal(enrollment.observedIssuedEnrollment(bad,"zero-touch","linux"),null);
 }
 assert.equal(enrollment.observedIssuedEnrollment({...manual,enrollment_code:"INVALID"},"manual","macos"),null);
 const hostile={toString(){throw Error("PRIVATE_MODE_MUST_NOT_COERCE")}};
 assert.equal(enrollment.observedIssuedEnrollment(valid,hostile,"linux"),null);
 assert.equal(enrollment.observedIssuedEnrollment(valid,"zero-touch",hostile),null);
});
test("UX-3 issuing malformed Core credential evidence never advances onboarding to copy UI",()=>{
 const source=readFileSync(join(root,"src","p0-enrollment.tsx"),"utf8");
 assert.match(source,/const observed=observedIssuedEnrollment\(result,mode,platform\)/);
 assert.match(source,/if\(!observed\)throw new Error\("Core returned invalid enrollment evidence/);
 assert.match(source,/if\(currentIssueIntent\.current!==requestedIntent\)/);
 assert.match(source,/setIssued\(\{intent:requestedIntent,evidence:observed\}\);refresh\(\);setStep\(2\)/);
 assert.doesNotMatch(source,/setIssued\(result\);refresh\(\);setStep\(2\)/);
 const parsed=enrollment.observedIssuedEnrollment({
  mode:"zero-touch",platform:"windows",state:"pending",display_once:true,
  management_only:true,pre_approved:false,expires_at:"2026-10-11T06:00:00Z",
  ttl_seconds:3600,command:"pwsh -Command example",next_step:{secret:"PRIVATE_NEXT"}
 },"zero-touch","windows");
 assert.equal(parsed?.next_step,"Inspect Managed Hosts after installing the Agent.");
 assert.doesNotMatch(JSON.stringify(parsed),/PRIVATE_/);
});

test("M2/R6 Remote Service Preview requires exact Core owner, operation, impact and expiring Change Plan",()=>{
 const request={owner:"host-a",name:"ssh-admin",operation:"set",destination:"this-host",
   service:"ssh-tcp22",enabled:true};
 const plan={change_plan_id:"cp_"+"a".repeat(32),operation_class:"CHANGE",
   operation:"remote-service.set",resource_type:"remote-service",
   resource_ref:"host-a:ssh-admin",expected_revision:13,
   confirmation_class:"APPLY",valid_until:"2032-01-01T00:00:00Z",
   remote_service:"ssh-admin",
   owner:{id:"host-a",name:"Ops Host",connectivity:"connected",private_key:"SENSITIVE"},
   impact:{requires_confirmation:true,destructive:false,
     owner_managed_host_id:"host-a",owner_connectivity:"connected",
     runtime_authority:"agent-rpc",secret:"SENSITIVE"},
   private_credentials:{token:"SENSITIVE"}
 };
 const preview=service.observedRemoteServicePreview(plan,request,Date.parse("2030-01-01T00:00:00Z"));
 assert.deepEqual(preview,{
   change_plan_id:plan.change_plan_id,operation_class:"CHANGE",
   operation:"remote-service.set",resource_type:"remote-service",
   resource_ref:"host-a:ssh-admin",expected_revision:13,
   confirmation_class:"APPLY",valid_until:plan.valid_until,
   remote_service:"ssh-admin",
   owner:{id:"host-a",name:"Ops Host",connectivity:"connected"},
   impact:{requires_confirmation:true,destructive:false,
     owner_managed_host_id:"host-a",owner_connectivity:"connected",
     runtime_authority:"agent-rpc"}
 });
 assert.doesNotMatch(JSON.stringify(preview),/SENSITIVE|private_key|private_credentials/);
 for(const invalid of [null,{},[],{...plan,resource_ref:"host-z:ssh-admin"},
   {...plan,resource_type:"host"}, {...plan,operation:"remote-service.delete"},
   {...plan,remote_service:"other"}, {...plan,confirmation_class:"DELETE"},
   {...plan,change_plan_id:"not_plan"},{...plan,expected_revision:"13"},
   {...plan,valid_until:"2020-01-01T00:00:00Z"},
   {...plan,owner:{...plan.owner,id:"host-z"}},
   {...plan,impact:{...plan.impact,destructive:true}},
   {...plan,impact:{...plan.impact,owner_connectivity:"disconnected"}},
   {...plan,impact:{...plan.impact,runtime_authority:"web-local"}},
 ])assert.equal(service.observedRemoteServicePreview(invalid,request,Date.parse("2030-01-01T00:00:00Z")),null);
});

test("M2/R6 Remote Service Apply must match exact immutable reviewed Core Plan and one queued Agent job",()=>{
 const plan={change_plan_id:"cp_"+"a".repeat(32),resource_ref:"host-a:ssh-admin",
   remote_service:"ssh-admin",operation:"remote-service.set",expected_revision:13,
   owner:{id:"host-a"}};
 const ack={status:"QUEUED",job_id:"mjob_"+"b".repeat(24),job_status:"QUEUED",
   target_managed_host_id:"host-a",remote_service:"ssh-admin",
   operation:"set",authoritative_revision_at_enqueue:13,
   payload:{token:"DONT_EXPOSE"},agent_private_key:"DONT_EXPOSE"};
 const result=service.observedRemoteServiceApplyReceipt(ack,plan);
 assert.deepEqual(result,{status:"QUEUED",job_id:ack.job_id,job_status:"QUEUED",
   target_managed_host_id:"host-a",remote_service:"ssh-admin",operation:"set",
   authoritative_revision_at_enqueue:13});
 assert.doesNotMatch(JSON.stringify(result),/DONT_EXPOSE|agent_private_key/);
 for(const bad of [null,{}, {...ack,status:"APPLIED"},
   {...ack,job_id:"unsafe"}, {...ack,job_status:"RUNNING"},
   {...ack,target_managed_host_id:"host-b"},
   {...ack,remote_service:"other"},
   {...ack,operation:"delete"},
   {...ack,authoritative_revision_at_enqueue:14},
   {...ack,authoritative_revision_at_enqueue:"13"},
 ])assert.equal(service.observedRemoteServiceApplyReceipt(bad,plan),null);
});
test("M2/R6 Remote Service non-idempotent Apply uses ref lock, strict Core receipts and discards ambiguous plans",()=>{
 const src=readFileSync(join(root,"src","uxb-remote-service.tsx"),"utf8");
 const apply=src.split("  async function doApply(){",2)[1]?.split("  async function refreshJob(){",1)[0]||"";
 const preview=src.split("  async function doPreview(){",2)[1]?.split("  async function doApply(){",1)[0]||"";
 assert.match(src,/const applyInFlight=useRef\(false\)/);
 assert.match(preview,/const observed=observedRemoteServicePreview\(result,body\)/);
 assert.match(preview,/if\(!observed\)throw new Error\(/);
 assert.match(preview,/setPreview\(observed\)/);
 assert.match(apply,/if\(applyInFlight\.current\)return;/);
 assert.match(apply,/applyInFlight\.current=true;/);
 assert.match(apply,/const reviewed=preview;/);
 assert.match(apply,/const receipt=observedRemoteServiceApplyReceipt\(result,reviewed\)/);
 assert.match(apply,/if\(!receipt\)throw new Error\(/);
 assert.match(apply,/setJob\(receipt\)/);
 assert.match(apply,/finally\{applyInFlight\.current=false;/);
 assert.match(apply,/UNKNOWN.*Agent Job may already be queued/);
 assert.match(apply,/setPreview\(null\);setConfirmation\(""\)/);
 assert.doesNotMatch(apply,/setJob\(result\)/);
});
