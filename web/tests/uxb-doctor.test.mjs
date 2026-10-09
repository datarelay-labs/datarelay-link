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
