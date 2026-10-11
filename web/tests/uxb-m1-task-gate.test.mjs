// M1 cross-screen source gate. SSR/source only: NO Browser, Core or 2-user E2E PASS.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {readFileSync,mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
let temp,nav,doctor,views;
before(async()=>{
 temp=mkdtempSync(join(root,"node_modules",".drlink-m1-task-gate-"));
 for(const [id,file] of [
  ["nav","uxb-navigation.ts"],["doctor","uxb-doctor.tsx"],["views","uxb-saved-views.tsx"]
 ]){
  const outfile=join(temp,id+".mjs");
  await build({entryPoints:[join(root,"src",file)],outfile,
   bundle:true,platform:"node",format:"esm",jsx:"automatic",
   external:["react","react/jsx-runtime"],logLevel:"silent"});
 }
 nav=await import(pathToFileURL(join(temp,"nav.mjs")).href);
 doctor=await import(pathToFileURL(join(temp,"doctor.mjs")).href);
 views=await import(pathToFileURL(join(temp,"views.mjs")).href);
});
after(()=>{if(temp)rmSync(temp,{recursive:true,force:true})});

test("M1 Activity & Health task routes remain discoverable for all three declared roles",()=>{
 assert.deepEqual(nav.navGroups.map(g=>g.id),
  ["connections","access","activity","administration"]);
 for(const role of ["Admin","Operator","Read Only"]){
  assert.ok(nav.navMatches("troubleshoot",role).some(x=>x.id==="doctor"),role);
  assert.ok(nav.navMatches("saved views",role).some(x=>x.id==="views"),role);
  assert.ok(nav.navMatches("agent version drift",role).some(x=>x.id==="versions"),role);
  assert.ok(nav.navMatches("audit",role).some(x=>x.id==="audit"),role);
  assert.equal(nav.visibleRoute("users",role),role==="Admin",role);
  assert.equal(nav.visibleRoute("integrations",role),role==="Admin",role);
  assert.equal(nav.visibleRoute("drafts",role),role!=="Read Only",role);
 }
});
test("M1 Doctor to Health/Jobs and private Saved View workflows retain truthful empty and populated Core facts",()=>{
 const data={read_only:true,side_effect_free:true,health:{db_healthy:true},
  attention:{count:0},checks:[{id:"runtime.remote",plane:"remote",status:"ATTENTION",
  message:"Runtime generation status: failed",db_revision:2,generation:4}]};
 const doctorHtml=renderToStaticMarkup(React.createElement(doctor.CoreDoctorWorkspace,{data}));
 for(const marker of ["Core Doctor","Runtime generation status: failed","System Health","Management Jobs","ATTENTION checks","Filter Core Doctor state"]){
  assert.ok(doctorHtml.includes(marker),marker);
 }
 assert.doesNotMatch(doctorHtml,/All Agents reachable|All policies applied/);
 const privateData={items:[{id:"view-1",name:"Offline hosts",updated_at:"2026-10-11T00:00:00Z",
  payload:{resource_type:"managed-host",filter:"offline"}}]};
 const viewsHtml=renderToStaticMarkup(React.createElement(views.SavedViewsWorkspace,{
  data:privateData,api:async()=>{throw Error("SSR must not access Core")},refresh:()=>{}
 }));
 for(const marker of ["Save a resource filter","My saved filters","Offline hosts","Open saved filter","private display preferences"]){
  assert.ok(viewsHtml.includes(marker),marker);
 }
 assert.doesNotMatch(viewsHtml,/Connection granted|Policy authorized/);
});
test("M1 optional Web wiring and narrow-screen table scrolling are source evidence, not Browser acceptance",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(source,/if\(active==="doctor"&&data\)return <CoreDoctorWorkspace data=\{data\}/);
 assert.match(source,/if\(active==="views"&&data\)return <SavedViewsWorkspace data=\{data\}/);
 assert.match(css,/\.dr-table-scroll\{overflow:auto\}/);
 assert.match(css,/\.dr-resource-table\{min-width:760px\}/);
 assert.match(css,/\.dr-uxb-context\{min-width:0;overflow-wrap:anywhere;/);
});
