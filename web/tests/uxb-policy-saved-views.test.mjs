// M1-B G-28: operator-private named policy search + plane Saved View.
// Source/SSR checks only: not a real logged-in Browser or Core User E2E.
import assert from "node:assert/strict";
import {test} from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g28-policy-views-"));
let view;
try{
 const outfile=join(scratch,"views.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views.tsx")],outfile,
  platform:"node",format:"esm",bundle:true,jsx:"automatic",
  external:["react","react/jsx-runtime"],logLevel:"silent"});
 view=await import(pathToFileURL(outfile).href);
}finally{rmSync(scratch,{recursive:true,force:true})}
const render=(items=[],initialDraft=null)=>renderToStaticMarkup(
 React.createElement(view.SavedViewsWorkspace,{data:{items},initialDraft,
  api:()=>{throw Error("SSR must never call backend")},
  onNavigate:()=>{},refresh:()=>{}})
);
const saved={id:"v-policy",name:"Vendor AI",payload:{
 resource_type:"access-rule",filter:"provider-4",plane:"ai"
}};

test("G-28 strictly bounded personal Policy Saved View supports only text and explicit plane",()=>{
 assert.deepEqual(view.saveDraftForResource("policy"," provider-4 ","ai"),{
  resource_type:"access-rule",filter:"provider-4",plane:"ai"});
 assert.deepEqual(view.saveDraftForResource("policy","","remote"),{
  resource_type:"access-rule",filter:"",plane:"remote"});
 assert.deepEqual(view.saveDraftForResource("policy","ai-ref","all"),{
  resource_type:"access-rule",filter:"ai-ref",plane:"all"});
 assert.deepEqual(view.readSavedView(saved),{
  route:"policies",filter:"provider-4",plane:"ai"});
 assert.deepEqual(view.readSavedView({payload:{
  resource_type:"access-rule",filter:"",plane:"remote"
 }}),{route:"policies",filter:"",plane:"remote"});
 assert.deepEqual(view.saveDraftForResource("host"," pending " ),
  {resource_type:"managed-host",filter:"pending"});
 assert.deepEqual(view.readSavedView({payload:{resource_type:"remote-service",filter:"ssh"}}),
  {route:"services",filter:"ssh"});
});

test("G-28 malformed saved policy source/plane/extra status or admission fails closed",()=>{
 for(const bad of [null,undefined,"","other","REMOTE",{},[],"ai ","__proto__",0]){
  assert.equal(view.saveDraftForResource("policy","provider-4",bad),null);
  assert.equal(view.readSavedView({payload:{
   resource_type:"access-rule",filter:"provider-4",plane:bad
  }}),null);
 }
 for(const bad of ["","  ","x".repeat(121),"token\u202e","spoof\nfilter"]){
  assert.equal(view.saveDraftForResource("policy",bad,"all"),null);
 }
 for(const obj of [
  {resource_type:"access-rule",filter:"provider-4"},
  {resource_type:"access-rule",filter:"",plane:"all"},
  {resource_type:"access-rule",filter:"provider-4",plane:"ai",admission:"APPROVED"},
  {resource_type:"access-rule",filter:"provider-4",plane:"ai",sort:"enabled"},
  {resource_type:"access-rule",filter:23,plane:"ai"},
  {resource_type:"access-rule",filter:{token:"PRIVATE"},plane:"ai"}
 ])assert.equal(view.readSavedView({payload:obj}),null);
 assert.equal(view.saveDraftForResource("policy",null,"ai"),null);
 assert.equal(view.saveDraftForResource("policy","q\nspoof","ai"),null);
});

test("G-28 Saved Views UI supports explicit Policy target, plane and private reopen route",()=>{
 const html=render([saved],saved.payload);
 assert.match(html,/Save a resource filter/);
 assert.match(html,/<option value="access-rule"(?: selected="")?>Policies<\/option>/);
 assert.match(html,/Policy plane/);
 for(const plane of ["all","remote","internet","ai"])
  assert.match(html,new RegExp('<option value="'+plane+'"(?: selected="")?>'));
 assert.match(html,/Pre-filled from Policies/);
 assert.match(html,/value="provider-4"/);
 assert.match(html,/My saved filters/);
 assert.match(html,/Vendor AI/);
 assert.match(html,/Open saved filter/);
 const src=readFileSync(join(root,"src","uxb-saved-views.tsx"),"utf8");
 assert.match(src,/onNavigate\?\.\("policies","access",\{savedFilter:parsed\.filter,savedPolicyPlane:parsed\.plane\}\)/);
 assert.match(src,/\/api\/v1\/saved-views/);
 assert.doesNotMatch(src,/\/api\/v1\/(?:policy-grant|permissions\/grant)/);
 assert.doesNotMatch(html,/PRIVATE|\[object Object\]/);
});

test("G-28 PolicyWorkspace reopens verified private view, saves only local text/plane; Core untouched",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=main.split("function PolicyWorkspace(",2)[1]?.split("function ServiceSshConnectHint(",1)[0]||"";
 assert.match(policy,/const savedPolicyDraft=saveDraftForResource\("policy",context\?\.savedFilter,context\?\.savedPolicyPlane\|\|"all"\)/);
 assert.match(policy,/focusPlane\|\|carriedPlane\|\|savedPolicyDraft\?\.plane\|\|"all"/);
 assert.match(policy,/focusName\|\|inspectPolicyId\|\|savedPolicyDraft\?\.filter\|\|""/);
 assert.match(policy,/const currentSaveDraft=saveDraftForResource\("policy",filter,plane\)/);
 assert.match(policy,/onNavigate\?\.\("views","activity",\{savedViewDraft:currentSaveDraft\}\)/);
 assert.match(policy,/Save this Policy filter/);
 assert.match(policy,/Saved filter includes only local text and plane/);
 assert.match(policy,/Core policy list may be incomplete/);
 assert.match(policy,/Read-only presentation of the currently loaded Core policies/);
 assert.match(policy,/Review related Audit/);
 assert.match(policy,/Recent activity/);
 assert.doesNotMatch(policy,/\/api\/v1\/saved-views/);
});
