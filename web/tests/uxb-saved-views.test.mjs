// Saved Views are Web-only private read preferences. Not authenticated browser E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,SavedViewsWorkspace,readSavedView,saveDraftForResource,conflictingSavedViewName;
before(async()=>{
 scratch=mkdtempSync(join(root,"node_modules",".uxb-saved-views-"));
 const outfile=join(scratch,"views.mjs");
 await build({entryPoints:[join(root,"src","uxb-saved-views.tsx")],outfile,
  bundle:true,platform:"node",format:"esm",jsx:"automatic",
  external:["react","react/jsx-runtime"],logLevel:"silent"});
 ({SavedViewsWorkspace,readSavedView,saveDraftForResource,conflictingSavedViewName}=await import(pathToFileURL(outfile).href));
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});
const render=(items,initialDraft=null)=>renderToStaticMarkup(React.createElement(SavedViewsWorkspace,{
 data:{items},initialDraft,api:async()=>{throw Error("No SSR API request permitted")},
 onNavigate:()=>{},refresh:()=>{}
}));
test("Saved filters open only explicit canonical Core-backed resource types",()=>{
 const hosts={id:"v1",name:"Offline hosts",payload:{resource_type:"managed-host",filter:"offline"}};
 const services={id:"v2",name:"SSH services",payload:{resource_type:"remote-service",filter:"ssh"}};
 assert.deepEqual(readSavedView(hosts),{route:"hosts",filter:"offline"});
 assert.deepEqual(readSavedView(services),{route:"services",filter:"ssh"});
 const html=render([hosts,services]);
 assert.match(html,/Saved Views/);
 assert.match(html,/Offline hosts/);
 assert.match(html,/SSH services/);
 assert.match(html,/Open saved filter →/);
 assert.match(html,/private display preferences, never access policies/);
 assert.match(html,/never access policies/);
});
test("Old or unsupported saved view never silently guesses target or grants a policy",()=>{
 for(const legacy of [null,{}, {payload:{}},{payload:{filter:"offline"}},
   {payload:{resource_type:"access-rule",filter:"deny"}},
   {payload:{resource_type:"managed-host",filter:14}},
   {payload:{resource_type:"managed-host",filter:"x".repeat(121)}}]){
   assert.equal(readSavedView(legacy),null);
 }
 const html=render([{id:"old",name:"Old filter",payload:{filter:"offline"}}]);
 assert.match(html,/Legacy\/unsupported view/);
 assert.match(html,/Target unspecified/);
 assert.doesNotMatch(html,/Open saved filter →/);
});
test("Saved Views render confirmed no views without pretending an API result",()=>{
 assert.match(render([]),/No saved views yet/);
 assert.match(render([]),/does not fetch missing inventory pages/);
});
test("Current Hosts/Services filter produces a bounded, explicit private preference draft",()=>{
 assert.deepEqual(saveDraftForResource("host"," pending "),{resource_type:"managed-host",filter:"pending"});
 assert.deepEqual(saveDraftForResource("service"," ssh "),{resource_type:"remote-service",filter:"ssh"});
 for(const invalid of ["", "  ", "x".repeat(121)])assert.equal(saveDraftForResource("host",invalid),null);
 assert.equal(saveDraftForResource("policy","allow"),null);
 assert.equal(saveDraftForResource("host",null),null);
});
test("Case-insensitive observed Saved View names require explicit replacement intent",()=>{
 const rows=[
  {id:"one",name:"Offline hosts",payload:{resource_type:"managed-host",filter:"offline"}},
  {id:"two",name:"SSH",payload:{resource_type:"remote-service",filter:"ssh"}}
 ];
 assert.equal(conflictingSavedViewName(rows," offline HOSTS "),"Offline hosts");
 assert.equal(conflictingSavedViewName(rows,"ssh"),"SSH");
 assert.equal(conflictingSavedViewName(rows,"new view"),null);
 assert.equal(conflictingSavedViewName(rows,""),null);
 assert.equal(conflictingSavedViewName(null,"SSH"),null);
 assert.equal(conflictingSavedViewName(rows,{name:"SSH"}),null);
 assert.equal(conflictingSavedViewName([{name:3},...rows],"ssh"),"SSH");
 assert.equal(conflictingSavedViewName(rows,"ＳＳＨ"),null);
});
test("Blank or whitespace-only saved filters cannot masquerade as an explicit filter",()=>{
 assert.equal(readSavedView({payload:{resource_type:"managed-host",filter:"  "}}),null);
 assert.equal(readSavedView({payload:{resource_type:"remote-service",filter:""}}),null);
});
test("Saved Views prefill only an explicit canonical resource-filter draft; name requires intent",()=>{
 const html=render([],{resource_type:"remote-service",filter:" ssh "});
 assert.match(html,/Pre-filled from Published Services/);
 assert.match(html,/value="ssh"/);
 assert.match(html,/Save filter/);
 assert.match(html,/disabled=""/);
 assert.doesNotMatch(render([],{resource_type:"access-rule",filter:"allow"}),/Pre-filled from/);
});

test("Host Saved Views may intentionally preserve an admission filter even with no text",()=>{
 const saved={payload:{resource_type:"managed-host",filter:"",admission:"PENDING_APPROVAL"}};
 assert.deepEqual(readSavedView(saved),{route:"hosts",filter:"",admission:"PENDING_APPROVAL"});
 assert.deepEqual(saveDraftForResource("host","","PENDING_APPROVAL"),{
  resource_type:"managed-host",filter:"",admission:"PENDING_APPROVAL"
 });
 assert.deepEqual(saveDraftForResource("host"," node ","QUARANTINED"),{
  resource_type:"managed-host",filter:"node",admission:"QUARANTINED"
 });
 assert.deepEqual(saveDraftForResource("host"," node ","all"),{
  resource_type:"managed-host",filter:"node"
 });
 const html=render([saved],saved.payload);
 assert.match(html,/Pre-filled from.*Servers &amp; Agents/);
 assert.match(html,/Filter Managed Host admission/);
 assert.match(html,/Pending approval/);
 assert.match(html,/Saved admission state/);
});
test("Fail closed for unknown admission and misplaced service admission",()=>{
 for(const invalid of ["", "NONE", "pending", "PENDING", "PENDING_APPROVAL ", null, 5, {}, true]){
  assert.equal(readSavedView({payload:{
   resource_type:"managed-host",filter:"offline",admission:invalid
  }}),null);
  assert.equal(saveDraftForResource("host","offline",invalid),null);
 }
 assert.equal(readSavedView({payload:{
  resource_type:"remote-service",filter:"ssh",admission:"QUARANTINED"
 }}),null);
 assert.equal(saveDraftForResource("service","ssh","QUARANTINED"),null);
 assert.deepEqual(readSavedView({payload:{
  resource_type:"managed-host",filter:"offline"
 }}),{route:"hosts",filter:"offline"});
 assert.equal(readSavedView({payload:{
  resource_type:"managed-host",filter:"",admission:"all"
 }}),null);
});
