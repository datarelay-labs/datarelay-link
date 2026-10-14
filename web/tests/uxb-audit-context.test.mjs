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
  {originType:Object.create(null),originId:"host-1"},
  {originType:{toString(){throw new Error("untrusted context must not run code")}},originId:"host-1"},
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
 assert.match(main,/import \{auditInvestigation,matchObservedAuditReturn,matchObservedPolicyReturn,recentAuditInvestigation,observedAuditEventDetails,observedAuditAppliedFilters/);
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

test("UX-5 selected entity carries a strictly observed UTC-bounded Audit time window",()=>{
 const ctx=context.auditInvestigation({
  originType:"remote-service",originId:"svc-12",auditActor:"operator-3",
  auditCategory:"ACCESS_DECISION",auditResult:"deny",
  auditStart:"2026-10-10T00:00:00Z",auditEnd:"2026-10-11T00:00:00Z"
 });
 assert.equal(ctx.resource,"svc-12");
 assert.equal(ctx.start,"2026-10-10T00:00:00Z");
 assert.equal(ctx.end,"2026-10-11T00:00:00Z");
 assert.equal(ctx.actor,"operator-3");
 assert.deepEqual(ctx.returnTarget?.context,{savedFilter:"id:svc-12",inspectResourceId:"svc-12"});
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const audit=source.split("function AuditExplorer(",2)[1]?.split("function AgentRolloutPreviewPanel(",1)[0]||"";
 assert.match(audit,/\[start,setStart\]=useState\(investigation\.start\)/);
 assert.match(audit,/\[end,setEnd\]=useState\(investigation\.end\)/);
 assert.match(audit,/setStart\(investigation\.start\);setEnd\(investigation\.end\)/);
});
test("UX-5 malformed, spoofed or reversed Core Audit times cannot become investigation filters",()=>{
 const base={originType:"managed-host",originId:"host-a",
   auditStart:"2026-10-10T00:00:00Z",auditEnd:"2026-10-11T00:00:00Z"};
 for(const extra of [
  {auditStart:"2026-02-30T00:00:00Z"},
  {auditStart:"last week"},
  {auditStart:"2026-10-10T00:00:00Z\nsecret"},
  {auditEnd:"2026-10-11T00:00:00Z\u202e"},
  {auditStart:3},
  {auditStart:"2026-10-13T00:00:00Z"}
 ]){
  const row=context.auditInvestigation({...base,...extra});
  assert.equal(row.start,"",JSON.stringify(extra));
  assert.equal(row.end,"",JSON.stringify(extra));
  assert.equal(row.returnTarget?.id,"hosts");
 }
 const open=context.auditInvestigation({originType:"managed-host",originId:"host-a",
  auditStart:"2026-10-10T00:00:00Z"});
 assert.equal(open.start,"2026-10-10T00:00:00Z");
 assert.equal(open.end,"");
 const noEntity=context.auditInvestigation({auditStart:base.auditStart,auditEnd:base.auditEnd});
 assert.equal(noEntity.start,"");
 assert.equal(noEntity.end,"");
});

test("UX-5 selected Recent Activity event navigates to an exact Core Audit entity/time investigation",()=>{
 const event={
  event_id:"evt-44",resource_type:"remote-service",resource_id:"svc-22",
  actor_id:"operator-7",occurred_at:"2026-10-11T11:21:37.123456Z",
  category:"ACCESS_DECISION",result:"deny"
 };
 const carried=context.recentAuditInvestigation(event);
 assert.deepEqual(carried,{
  originType:"remote-service",originId:"svc-22",auditActor:"operator-7",
  auditCategory:"ACCESS_DECISION",auditResult:"deny",
  auditStart:"2026-10-11T11:21:37.123456Z",
  auditEnd:"2026-10-11T11:21:37.123456Z"
 });
 const parsed=context.auditInvestigation(carried);
 assert.equal(parsed.resource,"svc-22");
 assert.equal(parsed.actor,"operator-7");
 assert.equal(parsed.start,event.occurred_at);
 assert.equal(parsed.end,event.occurred_at);
 assert.deepEqual(parsed.returnTarget?.context,{
  savedFilter:"id:svc-22",inspectResourceId:"svc-22"});
 const source=readFileSync(join(root,"src","main.tsx"),"utf8");
 const command=source.split("function CommandCenter(",2)[1]?.split("function AccessHygienePanel(",1)[0]||"";
 assert.match(command,/onNavigate\?\.\("audit","activity",recentAuditInvestigation\(item\)\|\|undefined\)/);
 // The separate "Open audit" header action deliberately remains an unfiltered
 // generic Audit route; only observed event rows carry exact Core context.
});
test("UX-5 Recent Activity never guesses a Host/Service link from malformed Core event evidence",()=>{
 const original={resource_type:"managed-host",resource_id:"host-a",
  occurred_at:"2026-10-11T11:21:37Z",actor_id:"actor-a"};
 assert.equal(context.recentAuditInvestigation(original)?.originId,"host-a");
 for(const wrong of [
  {...original,resource_type:"unknown"},
  {...original,resource_id:"host\nsecret"},
  {...original,resource_id:"../host-a"},
  {...original,resource_id:{secret:"PRIVATE"}},
  {...original,occurred_at:"yesterday"},
  {...original,occurred_at:"2026-02-30T00:00:00Z"},
  {...original,occurred_at:null},
  {...original,occurred_at:"2026-10-11T11:21:37Z\u202e"}
 ])assert.equal(context.recentAuditInvestigation(wrong),null);
 const partial=context.recentAuditInvestigation({
  ...original,actor_id:"actor\nunsafe",category:"NOT_A_CORE_CATEGORY",result:"ALLOW"
 });
 assert.equal(partial.auditActor,"");
 assert.equal(partial.auditCategory,"");
 assert.equal(partial.auditResult,"");
 assert.doesNotMatch(JSON.stringify(partial),/PRIVATE|unsafe/);
});

test("CUI-007 StrongDM-inspired Audit detail is exact, bounded Core event evidence only",()=>{
 const raw={event_id:"evt-08",row_id:8,occurred_at:"2030-01-02T03:04:05Z",
   category:"ACCESS_DECISION",event_type:"remote.access.decision",
   actor_id:"web:operator-a",resource_type:"managed-host",resource_id:"host-11",
   result:"DENY",reason_code:"POLICY_DENY",correlation_id:"corr-11",
   revision_before:12,revision_after:13,
   matched_policy:[{secret:"POLICY_SECRET"}],
   source_meta:{secret:"SOURCE_SECRET"},session_id:"session-private",
   before_summary:"UNSAFE",raw_bytes:"DO_NOT_LEAK"};
 const evidence=context.observedAuditEventDetails(raw);
 assert.deepEqual(evidence,{
  eventId:"evt-08",occurredAt:"2030-01-02T03:04:05Z",
  category:"ACCESS_DECISION",eventType:"remote.access.decision",
  actor:"web:operator-a",resourceType:"managed-host",resourceId:"host-11",
  result:"DENY",reason:"POLICY_DENY",correlation:"corr-11",
  revisionBefore:"12",revisionAfter:"13"
 });
 assert.doesNotMatch(JSON.stringify(evidence),/POLICY_SECRET|SOURCE_SECRET|session-private|UNSAFE|DO_NOT_LEAK/);
 const legacy=context.observedAuditEventDetails({...raw,event_id:null,row_id:17});
 assert.equal(legacy?.eventId,"legacy:17");
 for(const invalid of [null,{},[],{...raw,occurred_at:"2030-02-30T00:00:00Z"},
   {...raw,event_id:{secret:"x"}},{...raw,actor_id:{secret:"x"}},
   {...raw,reason_code:"x\u202e"},{...raw,category:"UNKNOWN_CATEGORY"},
   {...raw,resource_id:"../../../etc/secret"},{...raw,result:["ALLOW"]},
   {...raw,revision_before:-1}])
   assert.equal(context.observedAuditEventDetails(invalid),null,JSON.stringify(invalid));
 assert.equal(context.observedAuditEventDetails({...raw,actor_id:null})?.actor,"UNKNOWN");
 assert.equal(context.observedAuditEventDetails({...raw,resource_id:null})?.resourceId,"UNKNOWN");
});
test("CUI-007 current Audit query scope is explicit and rejects mutated/duplicate filter evidence",()=>{
 const input="limit=50&start=2030-01-01T00%3A00%3A00Z&actor=admin-a&result=deny";
 assert.deepEqual(context.observedAuditAppliedFilters(input),[
   {label:"Start UTC",value:"2030-01-01T00:00:00Z"},
   {label:"Actor",value:"admin-a"},{label:"Result",value:"deny"}
 ]);
 assert.deepEqual(context.observedAuditAppliedFilters("limit=50"),[]);
 for(const invalid of [null,{},"","limit=100","limit=50&actor=x&actor=y",
   "limit=50&token=secret","limit=50&start=bogus","limit=50&actor=x\u202e"])
   assert.equal(context.observedAuditAppliedFilters(invalid),null,JSON.stringify(invalid));
});
test("CUI-007 Audit row Inspect links to exactly selected loaded Core record and queried scope",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const table=main.split("function Table(")[1]?.split("function Metric(",1)[0]||"";
 const audit=main.split("function AuditExplorer(")[1]?.split("function AgentRolloutPreviewPanel(",1)[0]||"";
 assert.match(table,/onInspect\?:\(item:any,index:number\)=>void/);
 assert.match(table,/onClick=\{\(\)=>onInspect\(item,i\)\}/);
 assert.match(audit,/const \[selectedAuditEvent,setSelectedAuditEvent\]=useState</);
 assert.match(audit,/setSelectedAuditEvent\(null\);setError\(""\);setData\(null\)/);
 assert.match(audit,/observedAuditEventDetails\(data\?\.items\?\.\[index\]\)/);
 assert.match(audit,/observedAuditAppliedFilters\(auditFilterKey\)/);
 assert.match(audit,/aria-label="Observed Core Audit event detail"/);
 assert.match(audit,/Audit event detail belongs to the loaded Core page and applied filters only/);
 assert.match(audit,/auditFiltersEdited\?null:/);
});

test("UXR-4.4 Activity log uses six human columns and opens only the selected bounded Core event",()=>{
 const main=readFileSync(join(root,"src","main.tsx"),"utf8");
 const list=main.split("function AuditEventList(",2)[1]?.split("function AuditExplorer(",1)[0]||"";
 const audit=main.split("function AuditExplorer(",2)[1]?.split("function AgentRolloutPreviewPanel(",1)[0]||"";
 for(const label of ["When","What","Who","Resource","Result","Action"])assert.match(list,new RegExp('>'+label+'<'));
 assert.match(list,/View details →/);assert.match(list,/disabled=\{!canInspect\(item,index\)\}/);
 assert.match(audit,/<AuditEventList items=\{rows\}/);
 assert.match(audit,/observedAuditEventDetails\(data\?\.items\?\.\[index\]\)/);
 assert.match(audit,/aria-label="Observed Core Audit event detail"/);
 assert.match(audit,/Activity log/);
 assert.doesNotMatch(list,/JSON\.stringify|metadata|payload|session_id|private_key/);
});
