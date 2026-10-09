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
