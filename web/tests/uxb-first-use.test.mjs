// DRL3-7B UXB-01/02 offline deterministic contract, not browser/user E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync} from "node:fs";
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
test("first-use states are fail-closed without trustworthy evidence",()=>{
 assert.deepEqual(home.firstConnectionStates(null,null),[
  "Unknown","Unknown","Unknown","Unknown","Needs verification"]);
 const blank={overview:{managed_hosts:{total:0},remote_services:{total:0,enabled:0},policies:{remote:{enabled:0}}}};
 assert.deepEqual(home.firstConnectionStates(blank,[]),[
  "Configured · verify","Not started","Not started","Not started","Needs verification"]);
 const partial={overview:{managed_hosts:{total:1},remote_services:{total:1,enabled:1},policies:{remote:{enabled:2}}}};
 const waiting=home.firstConnectionStates(partial,[{admission_state:"PENDING_APPROVAL",connected:true,trust_status:"trusted"}]);
 assert.equal(waiting[1],"Needs approval");
 assert.equal(waiting[2],"Configured · verify");
 assert.equal(waiting[3],"Configured · verify");
 assert.equal(waiting[4],"Needs verification");
 assert.equal(home.firstConnectionStates(partial,[{admission_state:"APPROVED",connected:true,trust_status:"trusted"}])[1],"Configured · verify");
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
  assert.ok(!html.includes("Secret="));
  if(role==="Admin")assert.match(html,/>Open guided setup →<\/button>/);
  else assert.match(html,/<button[^>]*disabled=""[^>]*>Open guided setup →<\/button>/);
 }
});
