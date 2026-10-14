// M1-B G-22: policy expiry triage → read-only exact Core Audit investigation.
// No genuine browser, installed Agent/Server or two-person release E2E represented.
import assert from "node:assert/strict";
import {test} from "node:test";
import {build} from "esbuild";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
const root=dirname(dirname(fileURLToPath(import.meta.url)));
const scratch=mkdtempSync(join(root,"node_modules",".drlink-g22-audit-link-"));
let helper,audit;
try{
 for(const [label,entry] of [["context","uxb-policy-audit-action.ts"],["audit","uxb-audit-context.ts"]]){
  await build({entryPoints:[join(root,"src",entry)],outfile:join(scratch,label+".mjs"),
   bundle:true,platform:"node",format:"esm",logLevel:"silent"});
 }
 helper=await import(pathToFileURL(join(scratch,"context.mjs")).href);
 audit=await import(pathToFileURL(join(scratch,"audit.mjs")).href);
}finally{rmSync(scratch,{recursive:true,force:true})}

test("G-22 exact loaded Core policy ID + plane only, independent of action/status/expiry",()=>{
 for(const plane of ["remote","internet","ai"]){
  const row={id:"rule-100",name:"Ops policy",plane,enabled:0,
   expires_at:"2026-10-11T22:00:00Z",approval_status:"REQUESTED",
   secret:"DO_NOT_INCLUDE",metadata:{token:"DO_NOT_INCLUDE"}};
  const context=helper.policyAuditInvestigationTarget(row);
  assert.deepEqual(context,{originType:"access-rule",originId:"rule-100",plane});
  assert.doesNotMatch(JSON.stringify(context),/DO_NOT_INCLUDE|Ops policy|REQUESTED/);
  const parsed=audit.auditInvestigation(context);
  assert.equal(parsed.originType,"access-rule");
  assert.equal(parsed.resource,"rule-100");
  assert.equal(parsed.start,"");
  assert.equal(parsed.end,"");
  assert.deepEqual(parsed.returnTarget,{
    id:"policies",group:"access",context:{plane,inspectPolicyId:"rule-100"}
  });
 }
});
test("G-22 missing, malformed, unsafe and conflicting Core policy fields do not create Audit navigation authority",()=>{
 for(const row of [null,undefined,[],{},1,{id:"rule-1"},
  {id:"rule-1",plane:"all"},{id:"rule-1",plane:"REMOTE"},
  {id:"rule-1",plane:{hidden:"private"}},
  {id:"../outside",plane:"remote"},
  {id:"safe\nTOKEN",plane:"ai"},
  {id:"safe\u202eBAD",plane:"ai"},
  {id:"X".repeat(161),plane:"internet"},
  {id:{value:"SECRET"},plane:"remote"}]){
  assert.equal(helper.policyAuditInvestigationTarget(row),null,JSON.stringify(row));
 }
 assert.equal(audit.auditInvestigation({originType:"access-rule",originId:"bad\nx"}).resource,"");
});
test("G-22 Table/Card buttons navigate without opening policy detail; existing drawer remains safety-held",()=>{
 const src=readFileSync(join(root,"src","main.tsx"),"utf8");
 const page=src.split("function PolicyWorkspace(",2)[1]?.split("function ServiceUseActions(",1)[0]||"";
 assert.match(src,/import \{policyAuditInvestigationTarget\} from "\.\/uxb-policy-audit-action"/);
 assert.match(page,/function reviewPolicyAudit\(row:unknown\)\{/);
 assert.match(page,/const target=policyAuditInvestigationTarget\(row\)/);
 assert.match(page,/if\(!target\)return/);
 assert.match(page,/onNavigate\?\.\("audit","activity",target\)/);
 assert.match(page,/Review related Audit/);
 assert.match(page,/<th>Investigation<\/th>/);
 assert.match(page,/onClick=\{event=>\{event\.stopPropagation\(\);reviewPolicyAudit\(item\)\}\}/);
 assert.match(page,/onKeyDown=\{event=>event\.stopPropagation\(\)\}/);
 assert.match(page,/disabled=\{!policyAuditInvestigationTarget\(item\)\}/);
 // The pre-existing detail drawer remains unchanged: its alteration was platform safety-denied.
 // This runnable work qualifies the separate Table/Card actions without rerouting that effect.
 assert.match(page,/Recent activity<\/button>/);
 assert.match(page,/aria-label=\{"Review related Audit for "/);
 assert.match(page,/matchObservedPolicyReturn/);
 assert.match(page,/Core policy list may be incomplete/);
 assert.match(page,/policyView==="cards"/);
 assert.match(page,/policyExpiryLabel\(item\)/);
 const pure=readFileSync(join(root,"src","uxb-policy-audit-action.ts"),"utf8");
 assert.doesNotMatch(pure,/\b(?:fetch|api|localStorage|sessionStorage|eval|Date\.now)\s*\(/);
});
