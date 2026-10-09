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
 assert.match(src,/RemoteServiceEditor api=\{api\}/);
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

test("no browser-local credentials or unapproved backend policy engine",()=>{
 const src=["uxb-navigation.ts","uxb-home.tsx","uxb-setup.tsx","uxb-remote-service.tsx"].map(
  x=>readFileSync(join(root,"src",x),"utf8")).join("\n");
 for(const forbidden of ["localStorage.","sessionStorage.","document.cookie=","/api/v1/policy/direct-apply"]){
  assert.equal(src.includes(forbidden),false,forbidden);
 }
});
