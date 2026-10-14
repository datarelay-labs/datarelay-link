// Supplemental Core Doctor source/SSR evidence only, not authenticated browser E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,CoreDoctorWorkspace,validatedDoctorEvidence;
before(async()=>{
  scratch=mkdtempSync(join(root,"node_modules",".uxb-doctor-truth-"));
  const outfile=join(scratch,"doctor.mjs");
  await build({entryPoints:[join(root,"src","uxb-doctor.tsx")],outfile,
    bundle:true,platform:"node",format:"esm",jsx:"automatic",
    external:["react","react/jsx-runtime"],logLevel:"silent"});
  ({CoreDoctorWorkspace,validatedDoctorEvidence}
    =await import(pathToFileURL(outfile).href));
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});
const data=(checks=[],count=0)=>({
  read_only:true,side_effect_free:true,health:{db_healthy:true},
  attention:{count},checks
});
const render=d=>renderToStaticMarkup(React.createElement(CoreDoctorWorkspace,{data:d}));
test("No runtime checks is UNKNOWN, not evidence of a healthy Core",()=>{
 const result=render(data());
 assert.match(result,/No runtime generation checks were observed/);
 assert.match(result,/not proof of healthy access or policy deployment/);
 assert.match(result,/System Health/);
 assert.match(result,/Management Jobs/);
 assert.match(result,/Other Core attention<\/strong><p>0/);
});
test("Observed PASS and ATTENTION checks are distinguishable and detailed",()=>{
 const html=render(data([
   {id:"runtime.remote",plane:"remote",status:"PASS",message:"Runtime generation status: active",generation:17,db_revision:14},
   {id:"runtime.ai",plane:"ai",status:"ATTENTION",message:"Runtime generation status: failed",error:"Observed runtime mismatch",generation:4},
   {id:"runtime.internet",plane:"internet",status:"other"}
 ],2));
 assert.match(html,/PASS checks<\/strong><p>1/);
 assert.match(html,/ATTENTION checks<\/strong><p>1/);
 assert.match(html,/UNKNOWN checks<\/strong><p>1/);
 assert.match(html,/Other Core attention<\/strong><p>2/);
 assert.match(html,/Observed runtime mismatch/);
 assert.match(html,/runtime.remote/);
 assert.match(html,/runtime.internet/);
 assert.match(html,/Inspect details and System Health/);
});
test("Malformed or not certified read-only Doctor evidence never displays a valid summary",()=>{
 for(const bad of [null,[],{}, {...data(),read_only:false},
   {...data(),side_effect_free:false},{...data(),checks:null},
   {...data(),checks:[null]}, {...data(),health:null},
   {...data(),checks:[{id:""}]}]){
   assert.throws(()=>validatedDoctorEvidence(bad),/Core|UNKNOWN/);
 }
});
test("Unknown attention count remains UNKNOWN instead of an invented zero",()=>{
 const html=render({...data(),attention:{}});
 assert.match(html,/Other Core attention<\/strong><p>UNKNOWN/);
});

test("Malformed optional Doctor facts stay UNKNOWN without React crashes or nested-data disclosure",()=>{
 const raw=data([{
  id:"runtime.remote",plane:{internal:"PRIVATE_PLANE"},status:"PASS",
  message:{credential:"PRIVATE_MESSAGE"},error:{secret:"PRIVATE_ERROR"},
  db_revision:{internal:"PRIVATE_REVISION"},generation:[42],
  activated_at:{token:"PRIVATE_DATE"},unused_metadata:"PRIVATE_UNUSED"
 }]);
 const html=render(raw);
 assert.match(html,/UNKNOWN checks<\/strong><p>1/);
 assert.match(html,/UNKNOWN · Core reason unavailable/);
 assert.match(html,/UNKNOWN/);
 assert.doesNotMatch(html,/PRIVATE_|\[object Object\]/);
});
test("Invalid duplicate or unbounded Doctor identifiers cannot fabricate distinct checks",()=>{
 for(const bad of [
  data([{id:"runtime.remote",status:"PASS"},{id:"runtime.remote",status:"PASS"}]),
  data([{id:"runtime.\u202e",status:"PASS"}]),
  data([{id:"a".repeat(170),status:"PASS"}]),
  data(Array.from({length:33},(_,i)=>({id:"runtime."+i,status:"PASS"})))
 ]){
  assert.throws(()=>validatedDoctorEvidence(bad),/Core|UNKNOWN/);
 }
});

test("Unverifiable Doctor evidence renders a nonfatal UNKNOWN fallback and Health navigation",()=>{
 for(const bad of [
   null,
   {...data(),read_only:false},
   {...data(),checks:[null]},
   {...data(),checks:[{id:"runtime.remote",status:"PASS"},{id:"runtime.remote",status:"PASS"}]},
 ]){
  const html=render(bad);
  assert.match(html,/Core Doctor/);
  assert.match(html,/UNKNOWN/);
  assert.match(html,/Core Doctor evidence could not be validated/);
  assert.match(html,/System Health/);
  assert.doesNotMatch(html,/PASS checks|No runtime generation checks were observed|SECRET_DOCTOR/);
 }
 // Malformed optional row evidence is allowed only as explicitly UNKNOWN,
 // while a structurally invalid response uses the whole-page fallback.
 const optional=render(data([{id:"runtime.remote",status:"PASS",
  message:{credential:"SECRET_DOCTOR"}}]));
 assert.match(optional,/UNKNOWN checks<\/strong><p>1/);
 assert.match(optional,/UNKNOWN · Core reason unavailable/);
 assert.doesNotMatch(optional,/SECRET_DOCTOR/);
 assert.throws(()=>validatedDoctorEvidence(null),/Core|UNKNOWN/);
});

test("UX-4 Doctor last activation is a real Core absolute timestamp or UNKNOWN",()=>{
 const present=data([{id:"runtime.remote",status:"PASS",
  message:"Runtime generation status: active",
  activated_at:"2026-10-11T03:10:11Z"}]);
 assert.equal(validatedDoctorEvidence(present).checks[0].activated_at,"2026-10-11T03:10:11Z");
 for(const bad of [
  "yesterday","2026-02-30T00:00:00Z","2026-10-11\u202eT03:10:11Z",
  1234,{secret:"PRIVATE_ACTIVATION"}
 ]){
  const payload=data([{id:"runtime.remote",status:"PASS",
   message:"Runtime generation status: active",activated_at:bad}]);
  const safe=validatedDoctorEvidence(payload);
  assert.equal(safe.checks[0].activated_at,"UNKNOWN");
  const html=render(payload);
  assert.match(html,/UNKNOWN/);
  assert.doesNotMatch(html,/yesterday|PRIVATE_ACTIVATION|\u202e|\[object Object\]/);
 }
 assert.equal(validatedDoctorEvidence(data([{id:"runtime.ai",status:"PASS",
  message:"Not configured",activated_at:null}])).checks[0].activated_at,"Not observed");
});

test("Core Doctor runtime severity cannot contradict its observed canonical state",()=>{
 const cases=[
  ["PASS","Runtime generation status: failed"],
  ["PASS","Runtime generation status: unknown"],
  ["ATTENTION","Runtime generation status: active"],
  ["ATTENTION","Runtime generation status: not_configured"],
  ["PASS","Everything looks healthy"],
 ];
 for(const [status,message] of cases){
  const input=data([{id:"runtime.remote",plane:"remote",status,message}]);
  const observed=validatedDoctorEvidence(input);
  assert.equal(observed.passCount,0,message);
  assert.equal(observed.attentionCount,0,message);
  assert.equal(observed.unknownCount,1,message);
  assert.match(render(input),/UNKNOWN checks<\/strong><p>1/);
 }
 const pass=validatedDoctorEvidence(data([{id:"runtime.remote",plane:"remote",status:"PASS",
  message:"Runtime generation status: active"}]));
 const attention=validatedDoctorEvidence(data([{id:"runtime.remote",plane:"remote",status:"ATTENTION",
  message:"Runtime generation status: failed"}]));
 assert.equal(pass.passCount,1);
 assert.equal(attention.attentionCount,1);
});

test("R2.2 M2 Core Doctor observed runtime PASS requires canonical plane/identity match",()=>{
 for(const check of [
   {id:"runtime.remote",plane:"internet",status:"PASS",message:"Runtime generation status: active"},
   {id:"runtime.ai",plane:"remote",status:"PASS",message:"Runtime generation status: active"},
   {id:"runtime.unrecognized",plane:"unrecognized",status:"PASS",message:"Runtime generation status: active"},
   {id:"runtime.remote",status:"PASS",message:"Runtime generation status: active"},
   {id:"runtime.remote",plane:{secret:"PRIVATE"},status:"PASS",message:"Runtime generation status: active"},
 ]){
   const report=validatedDoctorEvidence(data([check]));
   assert.equal(report.passCount,0,JSON.stringify(check));
   assert.equal(report.unknownCount,1,JSON.stringify(check));
   assert.match(render(data([check])),/UNKNOWN checks<\/strong><p>1/);
 }
 const healthy=data([{id:"runtime.remote",plane:"remote",status:"PASS",message:"Runtime generation status: active"}]);
 assert.equal(validatedDoctorEvidence(healthy).passCount,1);
});
