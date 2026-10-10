// Pure cross-page audit context evidence; no browser, Core, or live actor mutation.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drl3-audit-context-"));
let context;
try{
 const output=join(scratch,"helper.mjs");
 await build({entryPoints:[join(root,"src","uxb-audit-context.ts")],
   outfile:output,platform:"node",format:"esm",bundle:true,logLevel:"silent"});
 context=await import(pathToFileURL(output).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("Selected Host/Service/Policy have bounded read-only audit filter and safe return route",()=>{
 for(const [originType,route,group,filter] of [
   ["managed-host","hosts","connections","id:host-12"],
   ["remote-service","services","connections","id:svc-22"],
   ["access-rule","policies","access",null]
 ]){
   const originId=originType==="managed-host"?"host-12":originType==="remote-service"?"svc-22":"rule-3";
   const audit=context.auditInvestigation({originType,originId,plane:"remote"});
   assert.equal(audit.resource,originId);
   assert.equal(audit.originType,originType);
   assert.equal(audit.returnTarget?.id,route);
   assert.equal(audit.returnTarget?.group,group);
   if(filter)assert.equal(audit.returnTarget?.context?.savedFilter,filter);
   else assert.equal(audit.returnTarget?.context?.plane,"remote");
   assert.equal(audit.category,"");
   assert.equal(audit.actor,"");
   assert.equal(audit.result,"");
 }
});

test("Return to a selected Host/Service is a loaded-only detail match, never an implicit Core fetch",()=>{
 const audit=context.auditInvestigation({originType:"managed-host",originId:"host-7"});
 assert.equal(audit.returnTarget.context.inspectResourceId,"host-7");
 const service=context.auditInvestigation({originType:"remote-service",originId:"svc-7"});
 assert.equal(service.returnTarget.context.inspectResourceId,"svc-7");
 const rows=[{id:"host-7",name:"Observed"},{id:"host-8",name:"Other"}];
 assert.equal(context.matchObservedAuditReturn(rows,"host-7")?.name,"Observed");
 for(const [loaded,id] of [
   [[], "host-7"],[rows,"host-other"],[rows,"host\nhack"],
   [[{id:"host-7"},{id:"host-7"}],"host-7"],
   [null,"host-7"],
 ]){
   assert.equal(context.matchObservedAuditReturn(loaded,id),null);
 }
});
test("An exact identified policy returns to its same-plane loaded Core rule detail only",()=>{
 const ctx=context.auditInvestigation({
   originType:"access-rule",originId:"rule-9",plane:"internet"
 });
 assert.deepEqual(ctx.returnTarget,{
   id:"policies",group:"access",
   context:{plane:"internet",inspectPolicyId:"rule-9"}
 });
 const policies=[
  {id:"rule-9",plane:"remote",name:"not internet"},
  {id:"rule-9",plane:"internet",name:"intended"},
  {id:"rule-17",plane:"internet",name:"other"}
 ];
 assert.equal(context.matchObservedPolicyReturn(policies,"rule-9","internet")?.name,"intended");
 for(const [items,id,plane] of [
   [policies,"rule-9","ai"],[policies,"rule-9",null],
   [policies,"rule-9","ALL"],
   [policies,"../rule-9","internet"],
   [null,"rule-9","internet"],
   [[policies[1],policies[1]],"rule-9","internet"]
 ]){
   assert.equal(context.matchObservedPolicyReturn(items,id,plane),null);
 }
});

test("Policy audit shortcut carries exact selected Core policy ID/plane and return honors pagination",()=>{
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const policy=source.split("function PolicyWorkspace(",2)[1]?.split("function ResourceWorkspace(",1)[0]||"";
 assert.match(policy,/originType:"access-rule",plane:selected.plane/);
 assert.match(policy,/matchObservedPolicyReturn\(\[\.\.\.\(data.items\|\|\[\]\),\.\.\.additional\],inspectPolicyId,carriedPlane\)/);
 assert.match(policy,/setSelected\(matchObservedPolicyReturn/);
 assert.match(policy,/Core policy inventory/);
 assert.match(policy,/Load more/);
});
test("Invalid context never pre-filters or pretends exact matching evidence",()=>{
 for(const v of [
  null,{},[],{originType:"managed-host",originId:""},
  {originType:"managed-host",originId:"a\nf"},
  {originType:"remote-service",originId:"x".repeat(180)},
  {originType:"access-rule",originId:"../../etc/passwd"},
  {originType:"web-user",originId:"admin"},
  {originType:"managed-host",originId:{secret:"hidden"}},
  {originType:"managed-host",originId:"host🟩"},
 ]){
   const a=context.auditInvestigation(v);
   assert.equal(a.resource,"");
   assert.equal(a.returnTarget,null);
   assert.equal(a.originType,null);
 }
});

test("Audit extra filters use bounded allowlisted values without carrying secret/free-form context",()=>{
 const value=context.auditInvestigation({
   originId:"host-1",originType:"managed-host",auditActor:"operator-17",
   auditCategory:"ACCESS_DECISION",auditResult:"deny",
   secret:"NEVER_COPY",token:"NEVER_COPY",password:"NEVER_COPY",
   next_cursor:"untrusted",
 });
 assert.equal(value.resource,"host-1");
 assert.equal(value.actor,"operator-17");
 assert.equal(value.category,"ACCESS_DECISION");
 assert.equal(value.result,"deny");
 assert.ok(!JSON.stringify(value).includes("NEVER_COPY"));
 const invalid=context.auditInvestigation({
   originId:"host-1",originType:"managed-host",auditActor:"actor\ninjected",
   auditCategory:"everything",auditResult:"maybe"
 });
 assert.equal(invalid.actor,"");
 assert.equal(invalid.category,"");
 assert.equal(invalid.result,"");
});

test("Returning to resource uses existing authorized loaded row, not server-side discovery",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const resource=src.split("function ResourceWorkspace(",2)[1]?.split("function UsersPanel(",1)[0]||"";
 const view=src.split("function View(",2)[1]?.split("function WorkspaceIcon(",1)[0]||"";
 assert.match(resource,/initialInspectId/);
 assert.match(resource,/matchObservedAuditReturn\(loaded,initialInspectId\)/);
 assert.match(view,/initialInspectId=\{context\?\.inspectResourceId\}/);
 assert.match(resource,/requireObservedInventoryContinuation/);
 assert.match(resource,/useEscapeClose\(!!selected,.*setSelected\(null\)/);
});
test("Audit context is source-only, Core audit resource filter and pagination remain intact",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const audit=main.split("function AuditExplorer(",2)[1]?.split("function AgentRolloutPreviewPanel(",1)[0]||"";
 assert.match(main,/import \{auditInvestigation,matchObservedAuditReturn,matchObservedPolicyReturn\} from "\.\/uxb-audit-context"/);
 assert.match(main,/if\(active==="audit"\)return <AuditExplorer operator=\{operator\} context=\{context\} onNavigate=\{onNavigate\}\/>/);
 assert.match(audit,/auditInvestigation\(context\)/);
 assert.match(audit,/setResource\(.*\.resource\)/);
 assert.match(audit,/onNavigate\?\.\(investigation\.returnTarget\.id,investigation\.returnTarget\.group,investigation\.returnTarget\.context\)/);
 assert.match(audit,/Core audit resource ID filter/);
 assert.match(audit,/Audit filters are applied to observed Core events; an empty page/);
 assert.match(audit,/const \[auditPage,setAuditPage\]/);
 assert.match(audit,/function filterParams\(\)/);
 assert.match(audit,/function exportFilters\(\)/);
 assert.match(audit,/\/api\/v1\/audit\?/);
 assert.match(audit,/auditFiltersEdited/);
 assert.match(audit,/Retry with Search audit/);
});
