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
