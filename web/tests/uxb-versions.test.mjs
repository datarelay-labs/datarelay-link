// UXB-06F version truth: dynamic read-only SSR / Core projection, not live E2E.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,AgentVersionDrift,observedVersionState,validatedVersionInventory;
before(async()=>{
 scratch=mkdtempSync(join(root,"node_modules",".uxb-version-truth-"));
 const outfile=join(scratch,"versions.mjs");
 await build({entryPoints:[join(root,"src","uxb-versions.tsx")],outfile,
   bundle:true,platform:"node",format:"esm",jsx:"automatic",
   external:["react","react/jsx-runtime"],logLevel:"silent"});
 ({AgentVersionDrift,observedVersionState,validatedVersionInventory}
   =await import(pathToFileURL(outfile).href));
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});
const page=(server_version,hosts,limit=200)=>({
 server_version,hosts,limit,
 drift_count:hosts.filter(row=>row.drift).length,
 unknown_count:hosts.filter(row=>row.unknown).length
});
const a=(id,version,other={})=>({id,name:id,platform:"linux",
 version,lifecycle:"connected",heartbeat:"2026-10-09T07:00:00Z",...other});
const render=data=>renderToStaticMarkup(React.createElement(AgentVersionDrift,{data}));
test("Core missing Server version is UNKNOWN even when Agent versions look identical",()=>{
 assert.equal(observedVersionState("unknown","3.0.0"),"UNKNOWN");
 assert.equal(observedVersionState("3.0.0","unknown"),"UNKNOWN");
 assert.equal(observedVersionState("3.0.0","3.0.0"),"SAME");
 assert.equal(observedVersionState("3.0.0","2.4.0"),"DIFFERENT");
 const h=render(page("unknown",[a("agent-a","3.0.0"),a("agent-b","unknown")]));
 assert.match(h,/Installed Server version was not observed/);
 assert.match(h,/do not interpret the Core drift count as zero problems/);
 assert.match(h,/Different versions<\/strong><p>UNKNOWN/);
 assert.match(h,/Matching versions<\/strong><p>UNKNOWN/);
 assert.match(h,/Unknown comparisons<\/strong><p>2/);
 assert.match(h,/<option value="DIFFERENT" disabled="">Different<\/option>/);
});
test("Known Server distinguishes matching, different and unknown without claiming upgrades",()=>{
 const h=render(page("3.0.0",[
   a("agent-new","3.0.0"),a("agent-old","2.4.0",{drift:true}),
   a("agent-unreported","unknown",{unknown:true}),
 ]));
 assert.match(h,/Agent version drift/);
 assert.match(h,/View Servers &amp; Agents/);
 assert.match(h,/Different versions<\/strong><p>1/);
 assert.match(h,/Unknown comparisons<\/strong><p>1/);
 assert.match(h,/Matching versions<\/strong><p>1/);
 assert.match(h,/agent-old/);
 assert.match(h,/Different/);
 assert.match(h,/Not observed|2026-10-09T07:00:00Z/);
 assert.doesNotMatch(h,/Installed Server version was not observed/);
});
test("A full bounded Core page is possibly truncated, not complete fleet evidence",()=>{
 const h=render(page("3.0.0",[a("agent-one","3.0.0")],1));
 assert.match(h,/Partial Core version snapshot possible/);
 assert.match(h,/not the total managed fleet/);
 assert.doesNotMatch(h,/No managed Agents/);
});
test("Malformed version inventory cannot masquerade as healthy empty",()=>{
 for(const bad of [null,[],{}, {hosts:[],server_version:"3.0.0",limit:200},
   {...page("3.0.0",[]),hosts:[null]},page("3.0.0",[a("one","3.0.0")],0),
   {...page("3.0.0",[a("one","3.0.0")]),drift_count:-1},
   {...page("3.0.0",[a("one","3.0.0")]),hosts:[a("", "3.0.0")]}
 ])assert.throws(()=>validatedVersionInventory(bad),/Core|UNKNOWN/);
});

test("Malformed optional Core Agent labels cannot crash or leak into version-drift UI",()=>{
 const data=page("3.0.0",[a("host-1","3.0.0",{
   name:{secret:"SENSITIVE-NAME"},platform:{secret:"SENSITIVE-PLATFORM"},
   lifecycle:["SENSITIVE-STATUS"],heartbeat:{private_key:"SENSITIVE-HEARTBEAT"}
 })]);
 const html=render(data);
 assert.match(html,/host-1/);
 assert.match(html,/UNKNOWN/);
 assert.doesNotMatch(html,/SENSITIVE/);
});
test("Unsafe Unicode and unbounded optional version-inventory labels are UNKNOWN",()=>{
 const data=page("3.0.0",[a("host-2","3.0.0",{
   name:"label\u202eoverride",platform:"A".repeat(500),
   lifecycle:"bad\nstatus",heartbeat:null
 })]);
 const html=render(data);
 assert.doesNotMatch(html,/\u202e|bad\nstatus/);
 assert.doesNotMatch(html,/A{100}/);
 assert.match(html,/UNKNOWN/);
});

test("Core version summary cannot contradict the bounded observed Host rows",()=>{
 const valid=page("3.0.0",[
  a("host-a","3.0.0"),a("host-b","2.4.0",{drift:true}),
  a("host-c","unknown",{unknown:true})
 ]);
 assert.equal(validatedVersionInventory(valid).hosts.length,3);
 for(const broken of [
  {...valid,drift_count:4},
  {...valid,unknown_count:4},
  {...valid,drift_count:2,unknown_count:2},
  {...page("3.0.0",[]),drift_count:1},
  {...page("3.0.0",[]),unknown_count:1},
  {...page("unknown",[a("host-a","3.0.0")]),drift_count:1},
  page("3.0.0",[a("same","3.0.0"),a("same","2.4.0")])
 ])assert.throws(()=>validatedVersionInventory(broken),/Core|UNKNOWN/);
});

test("Malformed Core version snapshots render a nonfatal UNKNOWN workspace instead of crashing the shell",()=>{
 const known=page("3.0.0",[a("host-1","3.0.0")]);
 for(const bad of [
  null,
  {server_version:"3.0.0",hosts:[],limit:200},
  {...known,drift_count:3},
  page("3.0.0",[a("dup","3.0.0"),a("dup","2.4.0")]),
  {...known,hosts:[{id:"host-1",version:{credential:"SECRET_KEY"}}]},
 ]){
  const html=render(bad);
  assert.match(html,/Agent version drift/);
  assert.match(html,/UNKNOWN/);
  assert.match(html,/Core Agent version inventory could not be validated/);
  assert.match(html,/View Servers &amp; Agents/);
  assert.doesNotMatch(html,/No managed Agents|0 observed Agent records|SECRET_KEY/);
 }
 // Explicitly malformed data must continue failing as an authoritative
 // projection: only the read-only component catches it for display.
 assert.throws(()=>validatedVersionInventory(null),/UNKNOWN/);
});

test("Direct version comparison never treats bidi/control or unbounded labels as evidence",()=>{
 for(const invalid of [
   ["3.0.0\u202e","3.0.0"],
   ["3.0.0","3.0.0\n"],
   ["3.0.0","3.0.0\u2066"],
   ["3.0.0".repeat(34),"3.0.0".repeat(34)],
 ]){
   assert.equal(observedVersionState(...invalid),"UNKNOWN",invalid.join(" vs "));
 }
 assert.equal(observedVersionState("3.0.0","3.0.0"),"SAME");
 assert.equal(observedVersionState("3.0.0","2.4.0"),"DIFFERENT");
});
