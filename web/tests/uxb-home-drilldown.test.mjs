// G-37: independently authored Home Core evidence and trustworthy task drilldowns.
// Pure + source qualification; NOT an authenticated 3-role browser walkthrough.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const dir=mkdtempSync(join(root,"node_modules",".drlink-g37-home-evidence-"));
let home;
try{
 const outfile=join(dir,"home.mjs");
 await build({entryPoints:[join(root,"src","uxb-home.tsx")],outfile,
  platform:"node",format:"esm",bundle:true,logLevel:"silent",
  external:["react","react/jsx-runtime"]});
 home=await import(pathToFileURL(outfile).href);
}finally{rmSync(dir,{recursive:true,force:true})}
const main=readFileSync(join(root,"src","main.tsx"),"utf8");
const command=main.split("function CommandCenter(",2)[1]?.split("function HealthWorkspace(",1)[0]||"";
const rawAttention=(kind,label="Attention",count=2)=>({
 attention:{count:1,authoritative:false,generated_at:"2026-10-12T00:10:00Z",
  items:[{kind,label,count,severity:"warning"}]}
});

test("G37 Home Attention drilling is based ONLY on validated Core fixed destination and actor role",()=>{
 assert.deepEqual(home.observedHomeAttention(rawAttention("pending-host-approval"),"Read Only")?.items[0],{
   kind:"pending-host-approval",label:"Attention",count:2,severity:"warning",
   route:"hosts",group:"connections",action:"Inspect Hosts"
 });
 assert.deepEqual(home.observedHomeAttention(rawAttention("failed-jobs"),"Operator")?.items[0],
  {kind:"failed-jobs",label:"Attention",count:2,severity:"warning",
   route:"jobs",group:"activity",action:"Inspect Jobs"});
 assert.equal(home.observedHomeAttention(rawAttention("webhook-backlog"),"Admin")?.items[0]?.route,"integrations");
 assert.equal(home.observedHomeAttention(rawAttention("webhook-backlog"),"Read Only")?.items[0]?.route,"health");
 assert.equal(home.observedHomeAttention(rawAttention("new-unknown-kind"),"Read Only")?.items[0]?.route,"doctor");
 for(const value of [null,undefined,{},{attention:{...rawAttention("failed-jobs").attention,generated_at:"yesterday"}},
   {attention:{...rawAttention("failed-jobs").attention,items:[{kind:"bad\u202e",label:"X",count:1,severity:"warning"}]}}]){
  assert.equal(home.observedHomeAttention(value,"Read Only"),null);
 }
});

test("G37 derived fleet timestamp/scope is strict UNKNOWN, never an invented live connection fact",()=>{
 const overview={schema_version:1,state_class:"DERIVED",authoritative:false,rebuildable:true,
  generated_at:"2026-10-12T00:10:00Z",
  managed_hosts:{total:2,connected:1},remote_services:{total:1,enabled:1},
  policies:{remote:{total:1,enabled:1},ai:{total:0,enabled:0}}};
 assert.deepEqual(home.observedCoreOverviewEvidence({overview}),{
  status:"observed",scope:"Fleet-wide derived Core counts",observedAt:"2026-10-12T00:10:00Z"
 });
 for(const bad of [null,{}, {overview:{...overview,generated_at:"2026-02-30T00:10:00Z"}},
  {overview:{...overview,state_class:"ACTUAL"}},{overview:{...overview,authoritative:true}}]){
  assert.equal(home.observedCoreOverviewEvidence(bad).status,"UNKNOWN");
 }
 assert.match(command,/const overviewEvidence=observedCoreOverviewEvidence\(data\)/);
 assert.match(command,/Fleet-wide derived Core counts/);
 assert.match(command,/Core observation: \{overviewEvidence\.observedAt\}/);
 assert.match(command,/overviewEvidence\.status==="observed"/);
 assert.match(command,/UNKNOWN/);
 assert.match(command,/not proof of current live access/);
});

test("G37 Home attention entries are native keyboard buttons linking only through Core-validated route metadata",()=>{
 assert.match(command,/const attentionState=observedHomeAttention\(data,operator\.role\)/);
 assert.match(command,/attention\.slice\(0,8\)\.map\(\(x:any\)=><button/);
 assert.match(command,/className="dr-attention-row dr-attention-link"/);
 assert.match(command,/type="button"/);
 assert.match(command,/onClick=\{\(\)=>onNavigate\?\.\(x\.route,x\.group\)\}/);
 assert.match(command,/\{x\.action\} →/);
 assert.match(command,/\{x\.count\} affected/);
 assert.match(command,/Core evidence at \{attentionState\?\.observedAt/);
 assert.doesNotMatch(command,/onNavigate\?\.\(x\.resource_id/);
 assert.doesNotMatch(command,/onNavigate\?\.\(x\.label/);
 assert.doesNotMatch(command,/\b(?:window|localStorage|sessionStorage)\.(?:fetch|location|setItem|href)/);
});

test("G37 fleet KPI read-only actions and plane-specific Policy Coverage link to existing Core pages only",()=>{
 for(const [label,route,group] of [
  ["Inspect Hosts","hosts","connections"],
  ["Inspect Services","services","connections"],
  ["Inspect Jobs","jobs","activity"]
 ]){
  assert.ok(command.includes(label),label);
  assert.ok(command.includes('onNavigate?.("'+route+'","'+group+'")'),route);
 }
 assert.match(command,/onNavigate\?\.\("policies","access",\{plane:row\.key\}\)/);
 assert.match(command,/\{label:"Remote Access",key:"remote"/);
 assert.match(command,/\{label:"Internet Access",key:"internet"/);
 assert.match(command,/\{label:"AI Access",key:"ai"/);
 assert.match(command,/Policy Coverage/);
 assert.match(command,/\{hostCounts\.subset\} connected/);
 assert.match(command,/\{serviceCounts\.subset\} enabled/);
 assert.match(command,/\{row\.value\.subset\} enabled of \{row\.value\.total\}/);
 assert.doesNotMatch(command,/onNavigate\?\.\("policy\/apply"/);
});

test("G37 accessible attention CTAs use native button focus and mobile-safe 44px click target",()=>{
 const css=readFileSync(join(root,"dist","styles.css"),"utf8");
 assert.match(css,/\.dr-attention-link\{[^}]*width:100%[^}]*min-height:44px/);
 assert.match(css,/\.dr-attention-link:focus-visible\{[^}]*outline:2px solid var\(--dr-focus-ring\)/);
 assert.match(css,/\.dr-attention-link:hover/);
 assert.match(css,/@media\(max-width:560px\)/);
 const region=command.split('dr-attention-list',2)[1]?.split("</section>",1)[0]||"";
 assert.match(region,/dr-severity-dot/);
 assert.match(region,/\{x\.severity\}/);
 assert.match(region,/\{x\.label\}/);
});

test("UXR-4.1 configured Home keeps next tasks dominant and moves fleet counts into secondary evidence disclosure",()=>{
 assert.match(command,/<FirstUseHome data=\{data\}/);
 assert.match(command,/<details className="card dr-home-evidence-details">/);
 assert.match(command,/Core inventory evidence/);
 assert.doesNotMatch(command,/<section className="dr-kpi-strip">/);
 assert.match(command,/These are configuration\/observation summaries, not proof of current live access/);
});

test("UXR-4.3 Home exposes enabled loaded services as actions without calling them reachable",()=>{
 assert.match(command,/resource_type=remote-service&limit=100/);
 assert.match(command,/requireObservedBoundedCorePage\("services",serviceResult\.value,"",100\)/);
 assert.match(command,/serviceStateLabel\(row\)==="Enabled"/);
 assert.match(command,/Enabled configuration only; access policy and transport success remain unverified/);
 assert.match(command,/inspectResourceId:item\.id/);
 assert.doesNotMatch(command,/popular|most used|reachable service|connection successful/i);
});
