// P0 User-flow UI fixtures: offline React SSR and fail-closed state invariants.
// Does not run the previous platform-denied browser installer or live logins.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync} from "node:fs";
import {dirname,join} from "node:path";
import {fileURLToPath,pathToFileURL} from "node:url";
import {build} from "esbuild";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";

const webRoot=dirname(dirname(fileURLToPath(import.meta.url)));
let scratch,access,enroll;
before(async()=>{
  scratch=mkdtempSync(join(webRoot,"node_modules",".p0-ux-"));
  for(const [name,entry] of [
    ["access","p0-access-policy.tsx"],["enroll","p0-enrollment.tsx"],
  ]){
    const outfile=join(scratch,name+".mjs");
    await build({entryPoints:[join(webRoot,"src",entry)],outfile,bundle:true,
      platform:"node",format:"esm",jsx:"automatic",external:["react","react/jsx-runtime"],logLevel:"silent"});
  }
  access=await import(pathToFileURL(join(scratch,"access.mjs")).href);
  enroll=await import(pathToFileURL(join(scratch,"enroll.mjs")).href);
});
after(()=>{if(scratch)rmSync(scratch,{recursive:true,force:true})});

test("Policy decisions are fail-closed for missing and unrecognized Core values",()=>{
  for(const input of [null,undefined,"","PERMIT","MAYBE","healthy","ALLOW?"]){
    assert.equal(access.reliableDecision(input),"UNKNOWN");
  }
  assert.equal(access.reliableDecision("ALLOW"),"ALLOW");
  assert.equal(access.reliableDecision("deny"),"DENY");
  const real=access.explainTrace({
    final:{result:"ALLOW",reason:"Rule matched"},
    policy:{matched_rules:["allow-dev"],mode:"WHITELIST"},
  });
  assert.deepEqual(real,{decision:"ALLOW",reason:"Rule matched",rules:["allow-dev"]});
  assert.equal(access.explainTrace(null).decision,"UNKNOWN");
});

test("NetBird/Twingate-inspired focus only uses complete same-plane Core modeled flows",()=>{
 const row={plane:"remote",input:{plane:"remote",source:" corp ",destination:" app ",service:"ssh"},
   decision:"ALLOW",rules:["ssh-allow","ssh-allow","other"]};
 const focus=access.modeledPathEvidence(row,"remote");
 assert.equal(focus.decision,"ALLOW");
 assert.deepEqual(focus.flow,{source:"corp",destination:"app",selector:"ssh",path:""});
 assert.equal(focus.key,access.coreFlowKey("remote","corp","app","ssh"));
 assert.deepEqual(focus.ruleReferences,["ssh-allow","other"]);
 assert.equal(focus.ruleReferencesLimited,false);
 assert.equal(access.modeledPathEvidence({...row,rules:Array.from({length:9},(_,i)=>"rule-"+i)},"remote").ruleReferencesLimited,true);
 assert.equal(access.modeledPathEvidence(row,"internet"),null);
 assert.equal(access.modeledPathEvidence({...row,input:{...row.input,source:""}},"remote"),null);
 assert.equal(access.modeledPathEvidence({...row,input:{...row.input,service:null}},"remote"),null);
 assert.equal(access.modeledPathEvidence({...row,input:{...row.input,source:"X".repeat(161)}},"remote"),null);
 assert.equal(access.modeledPathEvidence({...row,decision:"Maybe",rules:["allow-ssh"]},"remote").decision,"UNKNOWN");
 assert.deepEqual(access.modeledPathEvidence({plane:"ai",input:{
   plane:"ai",source:"bot",destination:"file",permission:"read",path:"/doc"},rules:[]},"ai").flow,
   {source:"bot",destination:"file",selector:"read",path:"/doc"});
 assert.equal(access.modeledPathEvidence({input:{source:"bot",destination:"file",permission:"read",path:"a".repeat(513)}},"ai"),null);
 assert.equal(access.modeledPathEvidence(null,"remote"),null);
 assert.equal(access.modeledPathEvidence({input:null},"remote"),null);
});

test("Matched rule name never becomes an exact-policy ID unless a complete unique Core page proves it",()=>{
 const rows=[
   {plane:"remote",name:"allow-ssh",id:"policy-123"},
   {plane:"internet",name:"allow-ssh",id:"policy-999"},
   {plane:"remote",name:"allow-web",id:"policy-456"},
 ];
 assert.equal(access.resolveCompletePolicyMatch(rows,"remote","allow-ssh",true)?.id,"policy-123");
 assert.equal(access.resolveCompletePolicyMatch(rows,"internet","allow-ssh",true)?.id,"policy-999");
 assert.equal(access.resolveCompletePolicyMatch(rows,"remote","allow-ssh",false),null);
 assert.equal(access.resolveCompletePolicyMatch([...rows,{plane:"remote",name:"allow-ssh",id:"another"}],
   "remote","allow-ssh",true),null);
 assert.equal(access.resolveCompletePolicyMatch(rows,"remote","ALLOW-SSH",true),null);
 assert.equal(access.resolveCompletePolicyMatch(rows,"ai","allow-ssh",true),null);
 assert.equal(access.resolveCompletePolicyMatch([{plane:"remote",name:"allow-ssh",id:""}],
   "remote","allow-ssh",true),null);
 assert.equal(access.resolveCompletePolicyMatch(null,"remote","allow-ssh",true),null);
 assert.equal(access.resolveCompletePolicyMatch(rows,"remote","",true),null);
});

test("Core decision evidence can only be shown for the exact current flow and AI path",()=>{
 const old=access.coreFlowKey("remote","source-a","app-b","ssh-tcp22");
 assert.equal(old,access.coreFlowKey("remote"," source-a "," app-b "," ssh-tcp22 "));
 const record={key:old,value:{final:{result:"ALLOW",reason:"Matched old rule"}}};
 assert.deepEqual(access.visibleCoreEvidence(record,old),record.value);
 assert.equal(access.visibleCoreEvidence(record,access.coreFlowKey("remote","source-b","app-b","ssh-tcp22")),null);
 assert.equal(access.visibleCoreEvidence(record,access.coreFlowKey("remote","source-a","app-b","https-tcp443")),null);
 assert.equal(access.visibleCoreEvidence(record,access.coreFlowKey("internet","source-a","app-b","ssh-tcp22")),null);
 assert.equal(access.visibleCoreEvidence(null,old),null);
 const aiA=access.coreFlowKey("ai","bot-a","app-b","permission-read","/api/a");
 const aiB=access.coreFlowKey("ai","bot-a","app-b","permission-read","/api/b");
 assert.notEqual(aiA,aiB);
 assert.equal(access.coreFlowKey("remote","s","d","svc","/ignored"),access.coreFlowKey("remote","s","d","svc"));
});
test("Emergency cutoff review scope cannot be reused for another plane, selector or action",()=>{
 const current=access.coreCutoffKey("remote","remote-service","ssh-prod","apply","incident-a");
 assert.equal(current,access.coreCutoffKey("remote","remote-service"," ssh-prod ","apply"," incident-a "));
 for(const altered of [
   ["ai","remote-service","ssh-prod","apply","incident-a"],
   ["remote","plane","ssh-prod","apply","incident-a"],
   ["remote","remote-service","other-host","apply","incident-a"],
   ["remote","remote-service","ssh-prod","clear","incident-a"],
   ["remote","remote-service","ssh-prod","apply","incident-b"],
 ]){
   assert.notEqual(current,access.coreCutoffKey(...altered));
 }
 assert.equal(access.visibleCoreEvidence({key:current,value:{change_plan_id:"cp-old"}},
    access.coreCutoffKey("ai","plane","","apply","")),null);
});
test("Guided Apply remains locked without exact plan and independent required-test PASS",()=>{
  const preview={change_plan_id:"cp_123",no_change:false,blast_radius:{limits:{truncated:false},unknowns:[]}};
  const ok={ok:true,required_failed:0,count:1,passed:1};
  assert.equal(access.canApplyGuidedRule(null,ok,true),false);
  assert.equal(access.canApplyGuidedRule(preview,null,true),false);
  assert.equal(access.canApplyGuidedRule(preview,{ok:false,required_failed:1},true),false);
  assert.equal(access.canApplyGuidedRule(preview,{ok:true,required_failed:1},true),false);
  assert.equal(access.canApplyGuidedRule({...preview,no_change:true},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,change_plan_id:""},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,blast_radius:{limits:{truncated:true}}},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,policy_regression:{ok:false,required_failed:1}},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,blast_radius:{unknowns:["unmodeled"]}},ok,false),false);
  assert.equal(access.canApplyGuidedRule({...preview,blast_radius:{unknowns:["unmodeled"]}},ok,true),true);
  assert.equal(access.canApplyGuidedRule(preview,ok,false),true);
});

test("Access explorer initial rendering explicitly says UNKNOWN and exposes Core query",()=>{
  const html=renderToStaticMarkup(React.createElement(access.AccessEvidenceExplorer,{
    api:async()=>{throw new Error("SSR did not invoke server APIs")},
    plane:"remote",source:"host-a",destination:"host-b",selector:"ssh",
    onSelect:()=>{},
  }));
  assert.match(html,/data-testid="p0-access-explain"/);
  assert.match(html,/Decision: UNKNOWN until a fresh Core decision trace succeeds/);
  assert.match(html,/Load modeled paths/);
  assert.match(html,/Explain selected access/);
  assert.match(html,/Core evidence/);
  assert.doesNotMatch(html,/class="dr-p0-result allow"/);
});

test("Guided policy screen shows four stages and hides Apply without Core plan",()=>{
  const html=renderToStaticMarkup(React.createElement(access.GuidedPolicyJourney,{
    api:async()=>{throw new Error("SSR did not invoke server APIs")},
  }));
  for(const stage of ["Define rule","Review impact","Verify required tests","Confirm apply"]){
    assert.ok(html.includes(stage),stage);
  }
  assert.match(html,/data-testid="p0-guided-policy"/);
  assert.match(html,/<button[^>]*disabled=""[^>]*>1\. Preview Core impact<\/button>/);
  assert.doesNotMatch(html,/Apply through Core/);
});

test("Enrollment history distinguishes unavailable Core state from an observed empty list",()=>{
 const render=data=>renderToStaticMarkup(React.createElement(enroll.EnrollmentOnboarding,{
  api:async()=>{throw new Error("SSR must not call Core API")},data,refresh:()=>{},
  operator:{role:"Read Only"},
 }));
 assert.match(render(null),/Enrollment history: UNKNOWN/);
 assert.doesNotMatch(render(null),/No enrollment history reported/);
 assert.match(render({items:[]}),/No enrollment history reported/);
});

test("Host readiness preserves admission, trust, connection and policy as separate concepts",()=>{
  assert.equal(enroll.hostReadinessLabel(null),"NO CONNECTION EVIDENCE");
  assert.equal(enroll.hostReadiness(null).policy,"NOT VERIFIED");
  assert.equal(enroll.hostReadinessLabel({admission_state:"PENDING_APPROVAL",connected:true,trust_status:"trusted"}),"WAITING FOR APPROVAL");
  assert.equal(enroll.hostReadinessLabel({admission_state:"QUARANTINED",connected:true,trust_status:"trusted"}),"QUARANTINED");
  assert.equal(enroll.hostReadinessLabel({admission_state:"APPROVED",connected:true,trust_status:"untrusted"}),"CONNECTED · TRUST NOT VERIFIED");
  assert.equal(enroll.hostReadinessLabel({admission_state:"APPROVED",connected:true,trust_status:"trusted"}),"CONNECTED · APPROVED · TRUSTED");
  assert.equal(enroll.hostReadiness({admission_state:"APPROVED",connected:true,trust_status:"trusted"}).policy,"NOT VERIFIED");
});

for(const [role,allowed] of [["Admin",true],["Operator",false],["Read Only",false]]){
  test(role+" onboarding shows four stages; only Admin can issue",()=>{
    const html=renderToStaticMarkup(React.createElement(enroll.EnrollmentOnboarding,{
      api:async()=>{throw new Error("SSR did not call API")},
      data:{items:[]},refresh:()=>{},operator:{role},
    }));
    for(const stage of enroll.enrollmentSteps)assert.ok(html.includes(stage.replaceAll("&","&amp;")),stage);
    assert.match(html,/data-testid="p0-enrollment-journey"/);
    assert.match(html,/Pending Approval is the default/);
    assert.equal(html.includes("Pre-approve first Host"),allowed);
    if(allowed)assert.match(html,/<button[^>]*>Issue enrollment →<\/button>/);
    else assert.match(html,/<button[^>]*disabled=""[^>]*>Issue enrollment →<\/button>/);
  });
}
