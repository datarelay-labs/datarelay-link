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
let scratch,setup,service,policy;
before(async()=>{
 scratch=mkdtempSync(join(root,"node_modules",".uxb-connection-"));
 for(const [name,entry] of [
  ["setup","uxb-setup.tsx"],["service","uxb-remote-service.tsx"],["policy","p0-access-policy.tsx"],
 ]){
  const out=join(scratch,name+".mjs");
  await build({entryPoints:[join(root,"src",entry)],outfile:out,
   platform:"node",format:"esm",bundle:true,jsx:"automatic",
   external:["react","react/jsx-runtime"],logLevel:"silent"});
 }
 setup=await import(pathToFileURL(join(scratch,"setup.mjs")).href);
 service=await import(pathToFileURL(join(scratch,"service.mjs")).href);
 policy=await import(pathToFileURL(join(scratch,"policy.mjs")).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

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
 assert.match(html,/Rule you are preparing/);
 assert.match(html,/Advanced · review or enter exact Core names manually/);
 assert.match(html,/This is an unverified draft/);
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
 assert.match(enrollSource,/setSelectedHost\(value=>value&&items\.some/);
 assert.match(enrollSource,/Select an observed Managed Host/);
});

test("no browser-local credentials or unapproved backend policy engine",()=>{
 const src=["uxb-navigation.ts","uxb-home.tsx","uxb-setup.tsx","uxb-remote-service.tsx"].map(
  x=>readFileSync(join(root,"src",x),"utf8")).join("\n");
 for(const forbidden of ["localStorage.","sessionStorage.","document.cookie=","/api/v1/policy/direct-apply"]){
  assert.equal(src.includes(forbidden),false,forbidden);
 }
});
