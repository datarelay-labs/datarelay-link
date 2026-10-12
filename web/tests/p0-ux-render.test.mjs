// P0 User-flow UI fixtures: offline React SSR and fail-closed state invariants.
// Does not run the previous platform-denied browser installer or live logins.
import assert from "node:assert/strict";
import {before,after,test} from "node:test";
import {mkdtempSync,rmSync,readFileSync} from "node:fs";
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
  assert.deepEqual(real,{decision:"ALLOW",reason:"Rule matched",rules:["allow-dev"],rulesQualified:true});
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
  const preview={change_plan_id:"cp_"+"a".repeat(32),operation_class:"CHANGE",
    operation:"guided.remote-access-rule.set",change_type:"remote-access-rule",
    resource_type:"remote-access-rule",resource_ref:"allow-ssh",
    confirmation_class:"APPLY",expected_revision:5,no_change:false,
    valid_until:"2032-01-01T00:00:00Z",
    policy_regression:{ok:true,required_failed:0},
    blast_radius:{limits:{truncated:false},unknowns:[]}};
  const ok={ok:true,required_failed:0,count:1,passed:1};
  assert.equal(access.canApplyGuidedRule(null,ok,true),false);
  assert.equal(access.canApplyGuidedRule(preview,null,true),false);
  assert.equal(access.canApplyGuidedRule(preview,{ok:false,required_failed:1},true),false);
  assert.equal(access.canApplyGuidedRule(preview,{ok:true,required_failed:1},true),false);
  assert.equal(access.canApplyGuidedRule({...preview,no_change:true},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,change_plan_id:""},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,blast_radius:{limits:{truncated:true}}},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,policy_regression:{ok:false,required_failed:1}},ok,true),false);
  assert.equal(access.canApplyGuidedRule({...preview,blast_radius:{limits:{truncated:false},unknowns:["unmodeled"]}},ok,false),false);
  assert.equal(access.canApplyGuidedRule({...preview,blast_radius:{limits:{truncated:false},unknowns:["unmodeled"]}},ok,true),true);
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
 assert.match(render({items:[],total:0}),/No enrollment history reported/);
 assert.match(render({items:[]}),/Enrollment history: UNKNOWN/);
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

test("UX-3 display-once enrollment ticket is scoped to exact operator and unchanged issuance intent",()=>{
 const intent={
  operatorId:"admin-a",role:"Admin",mode:"zero-touch",platform:"linux",
  ttl:"3600",label:"branch-a",note:"onboarding",preApproved:false
 };
 const original=enroll.enrollmentIssuanceIntent(intent);
 const evidence={mode:"zero-touch",platform:"linux",command:"safe test command",
  expires_at:"2026-10-11T09:00:00Z",pre_approved:false,
  enrollment_code:"",next_step:"install"};
 assert.deepEqual(enroll.issuedEnrollmentForCurrentIntent({
  intent:original,evidence},original),evidence);
 for(const changes of [
  {operatorId:"admin-b"},{role:"Read Only"},{role:"Operator"},
  {mode:"manual"},{platform:"macos"},{ttl:"1200"},{label:"branch-b"},
  {note:"another ticket"},{preApproved:true}
 ]){
  assert.equal(enroll.issuedEnrollmentForCurrentIntent({
   intent:original,evidence},enroll.enrollmentIssuanceIntent({...intent,...changes})),null,
   JSON.stringify(changes));
 }
 for(const invalid of [null,{},[],{intent:original,evidence:null},
  {intent:"another",evidence},{intent:original,evidence:{token:"DO_NOT_SHOW"}}]){
  assert.equal(enroll.issuedEnrollmentForCurrentIntent(invalid,original),null);
 }
});
test("UX-3 onboarding source does not retain or display old ticket when issue inputs/actor change",()=>{
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const visibleIssued=issuedEnrollmentForCurrentIntent\(issued,issuedIntent\)/);
 assert.match(src,/setIssued\(\{intent:requestedIntent,evidence:observed\}\)/);
 assert.match(src,/if\(currentIssueIntent\.current!==requestedIntent\)/);
 assert.match(src,/setIssued\(null\).*setMode/);
 assert.match(src,/setIssued\(null\).*setPlatform/);
 assert.match(src,/disabled=\{busy\}[^>]*onChange=\{e=>\{setIssued\(null\);setCopyStatus\(""\);setTtl/);
 assert.match(src,/disabled=\{busy\}[^>]*onChange=\{e=>\{setIssued\(null\);setCopyStatus\(""\);setLabel/);
 assert.match(src,/disabled=\{busy\}[^>]*onChange=\{e=>\{setIssued\(null\);setCopyStatus\(""\);setNote/);
 assert.match(src,/disabled=\{busy\}[^>]*onChange=\{e=>\{setIssued\(null\);setCopyStatus\(""\);setPreApproved/);
 assert.match(src,/\{shownIssued\?<div className="warning-box">/);
});

test("UX-3 Host admission evidence is private to the exact current operator ID and Web role",()=>{
 const scope={id:"admin-a",role:"Admin"};
 assert.equal(enroll.onboardingHostSnapshotMatchesActor(scope,{id:"admin-a",role:"Admin"}),true);
 for(const changed of [
  {id:"admin-b",role:"Admin"},{id:"admin-a",role:"Operator"},
  {id:"admin-a",role:"Read Only"},null,{},[],{id:"",role:"Admin"},
  {id:"admin-a",role:"admin"},{id:"admin-a",role:"UNKNOWN"}
 ]){
  assert.equal(enroll.onboardingHostSnapshotMatchesActor(scope,changed),false,
   JSON.stringify(changed));
 }
 assert.equal(enroll.onboardingHostSnapshotMatchesActor(null,scope),false);
 assert.equal(enroll.onboardingHostSnapshotMatchesActor({id:"admin-a",role:"Admin"},null),false);
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const matchingHostScope=onboardingHostSnapshotMatchesActor\(hostsScope,operator\)/);
 assert.match(src,/const visibleHosts=matchingHostScope\?hosts:null/);
 assert.match(src,/const scopedPreview=matchingHostScope\?preview:null/);
 assert.match(src,/setHostsScope\(\{id:operator\?\.id,role:operator\?\.role\}\)/);
 assert.match(src,/\[step,operator\?\.id,operator\?\.role\]/);
 assert.match(src,/if\(!admin\|\|!matchingHostScope\|\|!selectedHost/);
 assert.match(src,/if\(!admin\|\|!matchingHostScope\|\|!selectedHost\|\|!scopedPreview\?\.change_plan_id/);
});

test("UX-3 Admin approval requires one exact Core Host/operation/revision Change Plan",()=>{
 const impact={kind:"managed-host-admission",before:"PENDING_APPROVAL",after:"APPROVED",
  requires_confirmation:true,destructive:false,access_broadened:true,access_narrowed:false,
  kept:["Host identity","policy references"],warning:"Approval enables normal policies"};
 const plan={change_plan_id:"cp_"+"a".repeat(32),operation_class:"CHANGE",
  operation:"managed-host-admission.approve",admission_operation:"approve",
  resource_type:"managed-host",resource_ref:"host-a",expected_revision:12,
  confirmation_class:"APPROVE",valid_until:"2032-05-22T12:00:00Z",
  no_change:false,preview:{id:"host-a",before:"PENDING_APPROVAL",after:"APPROVED"},
  impact};
 const good=enroll.observedHostAdmissionApprovalPlan(plan,"host-a");
 assert.equal(good?.change_plan_id,plan.change_plan_id);
 assert.equal(good?.confirmation_class,"APPROVE");
 assert.equal(good?.expected_revision,12);
 assert.equal(good?.preview.id,"host-a");
 assert.equal(good?.impact.after,"APPROVED");
 assert.doesNotMatch(JSON.stringify(good),/PRIVATE_TOKEN/);
 for(const bad of [
  null,{},[],{...plan,change_plan_id:"evil"},
  {...plan,resource_ref:"host-b"},{...plan,resource_type:"remote-service"},
  {...plan,operation:"managed-host-admission.quarantine"},
  {...plan,admission_operation:"quarantine"},
  {...plan,confirmation_class:"DELETE"},
  {...plan,expected_revision:-1},{...plan,no_change:true},
  {...plan,valid_until:"2020-01-01T00:00:00Z"},
  {...plan,preview:{...plan.preview,id:"host-b"}},
  {...plan,preview:{...plan.preview,after:"QUARANTINED"}},
  {...plan,impact:{...impact,destructive:true}},
  {...plan,impact:{...impact,access_broadened:false}},
  {...plan,impact:{...impact,warning:{secret:"PRIVATE_TOKEN"}}}
 ])assert.equal(enroll.observedHostAdmissionApprovalPlan(bad,"host-a"),null);
});
test("UX-3 API 200 is not proof of applied Host approval without exact Core acknowledgement",()=>{
 assert.deepEqual(enroll.observedHostAdmissionApplyResult({
  status:"APPLIED",admission_operation:"approve",revision:13,
  result:{private:{secret:"PRIVATE_TOKEN"}}},12),{revision:13});
 for(const bad of [
  null,{},[],{status:"APPLIED",admission_operation:"approve"},
  {status:"APPLIED",admission_operation:"quarantine",revision:13},
  {status:"NO_CHANGE",admission_operation:"approve",revision:12},
  {status:"APPLIED",admission_operation:"approve",revision:12},
  {status:"APPLIED",admission_operation:"approve",revision:"13"},
  {status:"APPLIED",admission_operation:"approve",revision:1.5}
 ])assert.equal(enroll.observedHostAdmissionApplyResult(bad,12),null);
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const observed=observedHostAdmissionApprovalPlan\(result,selectedHost\)/);
 assert.match(src,/const applied=observedHostAdmissionApplyResult\(result,scopedPreview.expected_revision\)/);
 assert.match(src,/if\(!applied\)throw new Error\("Core admission apply result is unverified/);
 assert.doesNotMatch(src,/Core admission review applied at revision "\+String\(result\.revision/);
});


test("UX-3 approval plan expires after preview and cannot be applied from an idle tab",()=>{
 const plan={change_plan_id:"cp_"+"b".repeat(32),valid_until:"2032-01-01T00:00:00Z",
  preview:{id:"host-a",before:"PENDING_APPROVAL",after:"APPROVED"},expected_revision:9};
 assert.equal(enroll.currentHostAdmissionApprovalIsActionable(plan,"host-a",Date.parse("2031-12-31T23:59:59Z")),true);
 assert.equal(enroll.currentHostAdmissionApprovalIsActionable(plan,"host-a",Date.parse(plan.valid_until)),false);
 for(const invalid of [null,{},[],{...plan,valid_until:"invalid"},
  {...plan,preview:{id:"host-b"}},{...plan,expected_revision:-1}]){
  assert.equal(enroll.currentHostAdmissionApprovalIsActionable(invalid,"host-a",Date.parse("2031-01-01T00:00:00Z")),false);
 }
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const approvalActionable=currentHostAdmissionApprovalIsActionable\(scopedPreview,visibleSelectedHost\)/);
 assert.match(src,/\|\|!approvalActionable\|\|confirm!==required/);
 assert.match(src,/if\(!currentHostAdmissionApprovalIsActionable\(scopedPreview,selectedHost\)\)\{/);
 assert.match(src,/disabled=\{!admin\|\|!matchingHostScope\|\|!approvalActionable\|\|confirm!==required\|\|busy\}/);
});

test("UX-3 uncertain Apply must retire the old plan rather than invite a blind retry",()=>{
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 const apply=src.split("  async function applyApproval(){")[1].split("  return <section")[0];
 assert.match(apply,/catch\(e:any\)\{[\s\S]*?setPreview\(null\);setConfirm\(""\);[\s\S]*?refresh Host inventory before deciding whether to retry/);
});

test("UX-3 enrollment forms fail early for Core-invalid ticket intent without issuing",()=>{
 for(const fields of [
  ["zero-touch","linux","60","",""],
  ["zero-touch","windows","86400","branch-gateway","note"],
  ["manual","macos","2592000","manual-host","operator context"]
 ])assert.equal(enroll.enrollmentIssuePreflight(...fields),null,JSON.stringify(fields));
 for(const [fields,reason] of [
  [["zero-touch","linux","0","",""],"TTL"],
  [["zero-touch","linux","86401","",""],"TTL"],
  [["manual","linux","2592001","",""],"TTL"],
  [["manual","windows","600","",""],"platform"],
  [["zero-touch","linux","1e3","",""],"TTL"],
  [["zero-touch","linux","60.0","",""],"TTL"],
  [["zero-touch","linux","not a number","",""],"TTL"],
  [["zero-touch","linux","120","A".repeat(129),""],"label"],
  [["zero-touch","linux","120","","N".repeat(1025)],"note"],
  [["zero-touch","linux","120","host\nspoof",""],"label"],
  [["zero-touch","linux","120","host\u202eadmin",""],"label"]
 ])assert.match(enroll.enrollmentIssuePreflight(...fields),new RegExp(reason,"i"),JSON.stringify(fields));
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const issueProblem=enrollmentIssuePreflight\(mode,platform,ttl,label,note\)/);
 assert.match(src,/if\(issueProblem\)\{setError\(issueProblem\);return;\}/);
 assert.match(src,/disabled=\{!admin\|\|busy\|\|!!issueProblem\}/);
 assert.match(src,/The ticket may exist; inspect Core enrollment history before retrying/);
});

test("UX-3 display-once Core issuance cannot silently alter Admin pre-approval or TTL",()=>{
 const request={mode:"zero-touch",platform:"linux",ttl:"3600",preApproved:false};
 const zero={mode:"zero-touch",platform:"linux",state:"pending",
  ttl_seconds:3600,pre_approved:false,display_once:true,management_only:true};
 assert.equal(enroll.issuedEnrollmentMatchesRequestedOptions(zero,request),true);
 for(const mismatch of [
  {...zero,pre_approved:true},
  {...zero,ttl_seconds:600},
  {...zero,ttl_seconds:"3600"},
  {...zero,platform:"windows"},
  {...zero,mode:"manual"},
  {...zero,ttl_seconds:3600.5},
  null,{},[]
 ])assert.equal(enroll.issuedEnrollmentMatchesRequestedOptions(mismatch,request),false,
   JSON.stringify(mismatch));
 assert.equal(enroll.issuedEnrollmentMatchesRequestedOptions({...zero,pre_approved:true},
   {...request,preApproved:true}),true);
 const manual={...zero,mode:"manual",platform:"macos",ttl_seconds:600,pre_approved:false};
 assert.equal(enroll.issuedEnrollmentMatchesRequestedOptions(manual,
   {mode:"manual",platform:"macos",ttl:"600",preApproved:false}),true);
 assert.equal(enroll.issuedEnrollmentMatchesRequestedOptions({...manual,pre_approved:true},
   {mode:"manual",platform:"macos",ttl:"600",preApproved:false}),false);
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/issuedEnrollmentMatchesRequestedOptions\(result,\{mode,platform,ttl,preApproved\}\)/);
 assert.match(src,/The ticket may exist; inspect Core enrollment history before retrying/);
});

test("UX-3 display-once Agent instructions are not copyable after Core expiry",()=>{
 const valid={mode:"manual",platform:"linux",expires_at:"2032-01-01T00:00:00Z",
  command:"SAFE_SAMPLE",enrollment_code:"",pre_approved:false,next_step:"Install"};
 assert.equal(enroll.currentIssuedCredentialIsUsable(valid,Date.parse("2031-12-31T23:59:59Z")),true);
 assert.equal(enroll.currentIssuedCredentialIsUsable(valid,Date.parse(valid.expires_at)),false);
 assert.equal(enroll.currentIssuedCredentialIsUsable({...valid,expires_at:"invalid"},Date.now()),false);
 assert.equal(enroll.currentIssuedCredentialIsUsable(null,Date.now()),false);
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const shownIssued=visibleIssued&&currentIssuedCredentialIsUsable\(visibleIssued\)\?visibleIssued:null/);
 assert.match(src,/if\(!currentIssuedCredentialIsUsable\(visibleIssued\)\)/);
 assert.match(src,/setIssued\(null\);setCopyStatus\(""\)/);
 assert.match(src,/\{shownIssued\?<div className="warning-box">/);
});

test("UX-3 late Host admission Apply cannot show old actor, Host or Change Plan success",()=>{
 const request={id:"admin-a",role:"Admin",hostId:"host-a",planId:"cp_"+ "a".repeat(24)};
 assert.equal(enroll.onboardingAdmissionApplyMatchesContext(request,{...request}),true);
 for(const changed of [
  {...request,id:"admin-b"},{...request,role:"Operator"},
  {...request,role:"Read Only"},{...request,hostId:"host-b"},
  {...request,planId:"cp_"+"b".repeat(24)},
  null,{},[]
 ])assert.equal(enroll.onboardingAdmissionApplyMatchesContext(request,changed),false,
   JSON.stringify(changed));
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 assert.match(src,/const currentApplyContext=useRef\(/);
 assert.match(src,/if\(generation!==approvalGeneration\.current\|\|!onboardingAdmissionApplyMatchesContext\(requestedContext,currentApplyContext\.current\)\)return;/);
 assert.match(src,/const scopedMessage=onboardingHostSnapshotMatchesActor\(messageScope,operator\)[\s\S]*?&&messageScope\?\.hostId===visibleSelectedHost\?message:""/);
 assert.match(src,/\{scopedMessage&&<p className="notice" role="status">\{scopedMessage\}<\/p>\}/);
});

test("UI-02 Remote Service to owning Host shows only exact Core IDs from two typed inventory pages",()=>{
 const hosts={resource_type:"managed-host",limit:100,next_cursor:null,items:[
   {id:"host-a",name:"Branch Gateway",secret:"DO_NOT_EXPOSE"},
   {id:"host-b",name:"Office Gateway"}
 ]};
 const services={resource_type:"remote-service",limit:100,next_cursor:null,items:[
   {id:"service-ssh",name:"SSH",managed_host_id:"host-a",managed_host:"spoofed name"},
   {id:"service-web",name:"Web",managed_host_id:"host-b"},
   {id:"service-unresolved",name:"Unknown owner",managed_host:"Branch Gateway"}
 ]};
 const proof=access.observedPublicationOwnership(services,hosts);
 assert.deepEqual(proof?.edges,[
   {serviceId:"service-ssh",serviceName:"SSH",hostId:"host-a",hostName:"Branch Gateway"},
   {serviceId:"service-web",serviceName:"Web",hostId:"host-b",hostName:"Office Gateway"}
 ]);
 assert.equal(proof?.unresolved,1);
 assert.equal(proof?.partial,false);
 assert.doesNotMatch(JSON.stringify(proof),/DO_NOT_EXPOSE|spoofed/);
 assert.equal(access.observedPublicationOwnership(
   {...services,next_cursor:"cursor"},hosts)?.partial,true);
 assert.equal(access.observedPublicationOwnership(
   services,{...hosts,next_cursor:"cursor"})?.partial,true);
 for(const wrong of [null,{},[],{...services,resource_type:"managed-host"},
   {...services,limit:200},{...services,next_cursor:23},
   {...services,items:[services.items[0],services.items[0]]}]){
   assert.equal(access.observedPublicationOwnership(wrong,hosts),null);
 }
 assert.equal(access.observedPublicationOwnership(services,
   {...hosts,items:[hosts.items[0],hosts.items[0]]}),null);
});
test("UI-02 renders role-scoped Core publication ownership separately from policy graph",()=>{
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 const main=readFileSync(join(webRoot,"src","main.tsx"),"utf8");
 assert.match(src,/resource_type=remote-service&limit=100/);
 assert.match(src,/resource_type=managed-host&limit=100/);
 assert.match(src,/Load published ownership/);
 assert.match(src,/Observed publication relationship/);
 assert.match(src,/Observed Service.*owning Host/);
 assert.match(main,/onInspectHost=\{hostId=>\{const target=observedHostInspectContext\(hostId\)/);
 assert.doesNotMatch(src,/network_topology===true&&.*managed_host_id/);
});

test("UI-02 Host inspect link preserves canonical colon/long Core IDs without typed-search ambiguity",()=>{
 const short="host:branch-17";
 assert.deepEqual(access.observedHostInspectContext(short),{
   inspectResourceId:short,savedFilter:"id:"+short
 });
 const bounded="h".repeat(117),long="h".repeat(160);
 assert.deepEqual(access.observedHostInspectContext(bounded),{
   inspectResourceId:bounded,savedFilter:"id:"+bounded
 });
 assert.deepEqual(access.observedHostInspectContext(long),{
   inspectResourceId:long,savedFilter:""
 });
 for(const bad of [null,{},[],"","x".repeat(161),"host broken","host\u202e",":leading"])
   assert.equal(access.observedHostInspectContext(bad),null);
 const main=readFileSync(join(webRoot,"src","main.tsx"),"utf8");
 assert.match(main,/onInspectHost=\{hostId=>\{const target=observedHostInspectContext\(hostId\)/);
 assert.match(main,/onNavigate\?\.\("hosts","infrastructure",target\)/);
 assert.doesNotMatch(main,/savedFilter:hostId\}/);
});

test("UX-1 Core trace cannot coerce arrays or nested evidence into an ALLOW or valid rule proof",()=>{
 for(const bogus of [["ALLOW"],["DENY"],{result:"ALLOW"},true,1,["ALLOW","DENY"]])
   assert.equal(access.reliableDecision(bogus),"UNKNOWN",JSON.stringify(bogus));
 const trace={final:{result:["ALLOW"],reason:{private:"SECRET_CAUSE"}},
   policy:{matched_rules:["allow-ssh",["fake-rule"],{id:"SECRET_RULE"},
     "allow-ssh\u202e", "a".repeat(161), "allow-ssh"]}};
 const projected=access.explainTrace(trace);
 assert.equal(projected.decision,"UNKNOWN");
 assert.equal(projected.reason,"Core did not provide a decision reason.");
 assert.deepEqual(projected.rules,["allow-ssh"]);
 assert.equal(projected.rulesQualified,false);
 assert.doesNotMatch(JSON.stringify(projected),/SECRET_CAUSE|SECRET_RULE|\u202e/);
 const good=access.explainTrace({final:{result:"DENY",reason:"No matching rule"},
   policy:{matched_rules:[]}});
 assert.equal(good.rulesQualified,true);
 assert.equal(good.decision,"DENY");
 assert.deepEqual(good.rules,[]);
 assert.equal(access.explainTrace({final:{result:"ALLOW",reason:"ok"},
   policy:{matched_rules:Array.from({length:300},(_,i)=>"rule-"+i)}}).rulesQualified,false);
});
test("UX-1 Core trace route and modeled path never present nested/bidi source as real evidence",()=>{
 assert.equal(access.observedTraceRouteValue({secret:"SECRET"},"fallback"),"UNKNOWN");
 assert.equal(access.observedTraceRouteValue(["host-a"],"fallback"),"UNKNOWN");
 assert.equal(access.observedTraceRouteValue("host\u202espoof","fallback"),"UNKNOWN");
 assert.equal(access.observedTraceRouteValue(undefined,"requested-host"),"requested-host");
 assert.equal(access.observedTraceRouteValue("core-host","requested-host"),"core-host");
 assert.equal(access.observedTraceRouteValue(undefined,"a".repeat(200)),"UNKNOWN");
 const path={plane:"remote",input:{plane:"remote",source:"host-a",destination:"app",
   service:"ssh"},decision:"ALLOW",rules:["rule-ok","spoof\u202e","rule-ok"]};
 const projected=access.modeledPathEvidence(path,"remote");
 assert.deepEqual(projected.ruleReferences,["rule-ok"]);
 assert.equal(projected.ruleReferencesLimited,true);
 assert.equal(access.modeledPathEvidence({...path,input:{...path.input,source:"host\u202espoof"}},"remote"),null);
 assert.equal(access.modeledPathEvidence({...path,input:{...path.input,service:"ssh\u202espoof"}},"remote"),null);
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(src,/observedTraceRouteValue\(visibleTrace\.normalized_input\?\.source,source\)/);
 assert.match(src,/observed\.rulesQualified/);
 assert.match(src,/visibleTrace\.mixed===true/);
});

test("UX-1 Core graph must match exact requested plane and bounded authoritative counts",()=>{
 const row={plane:"remote",input:{plane:"remote",source:"branch",destination:"app",service:"ssh"}};
 const valid={revision:22,scope:"policy-and-inventory",planes:["remote"],
   network_topology:false,paths:[row],nodes:[{secret:"SECRET_GRAPH_FIELD"}],
   limits:{path_count:1,max_paths:400,truncated:false}};
 const observed=access.observedCoreGraphSnapshot(valid,"remote");
 assert.deepEqual(observed,{revision:22,paths:[row],
   limits:{path_count:1,truncated:false},network_topology:false});
 assert.doesNotMatch(JSON.stringify(observed),/SECRET_GRAPH_FIELD/);
 for(const broken of [null,{},[],{...valid,planes:["internet"]},
   {...valid,planes:["remote","internet"]},{...valid,planes:[]},
   {...valid,revision:-1},{...valid,revision:"22"},
   {...valid,scope:"network-topology"},{...valid,network_topology:"false"},
   {...valid,limits:{...valid.limits,path_count:0}},
   {...valid,limits:{...valid.limits,max_paths:401}},
   {...valid,limits:{...valid.limits,truncated:"false"}},
   {...valid,limits:{...valid.limits,path_count:"1"}},
   {...valid,paths:[...valid.paths,valid.paths[0]]},
   {...valid,paths:null}
 ])assert.equal(access.observedCoreGraphSnapshot(broken,"remote"),null,JSON.stringify(broken));
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(src,/const validated=observedCoreGraphSnapshot\(next,plane\)/);
 assert.match(src,/if\(!validated\)throw new Error\(/);
 assert.match(src,/setGraphEvidence\(\{key:plane,value:validated\}\)/);
});

test("UX-2 Guided Policy Apply must have exact Core plan, rule and advanced revision receipt",()=>{
 const plan={change_plan_id:"cp_"+"a".repeat(32),change_type:"remote-access-rule",
  resource_type:"remote-access-rule",resource_ref:"allow-ssh",
  confirmation_class:"APPLY",expected_revision:30,no_change:false};
 const receipt={status:"APPLIED",change_type:"remote-access-rule",
   resource_type:"remote-access-rule",resource_ref:"allow-ssh",revision:31};
 assert.deepEqual(access.observedGuidedPolicyApplyReceipt(receipt,plan,"remote"),{revision:31});
 for(const bad of [null,{},[],{...receipt,status:"NO_CHANGE"},
  {...receipt,status:"QUEUED"},{...receipt,revision:30},
  {...receipt,revision:"31"},{...receipt,revision:NaN},
  {...receipt,change_type:"ai-access-rule"},
  {...receipt,resource_type:"ai-access-rule"},
  {...receipt,resource_ref:"other-rule"}
 ])assert.equal(access.observedGuidedPolicyApplyReceipt(bad,plan,"remote"),null,JSON.stringify(bad));
 for(const invalid of [
  {...plan,expected_revision:-1},{...plan,expected_revision:"30"},
  {...plan,change_plan_id:"not-a-change-plan"},{...plan,confirmation_class:"DELETE"},
  {...plan,no_change:true},{...plan,resource_ref:"other\u202erule"}
 ])assert.equal(access.observedGuidedPolicyApplyReceipt(receipt,invalid,"remote"),null,JSON.stringify(invalid));
 assert.equal(access.observedGuidedPolicyApplyReceipt(receipt,plan,"ai"),null);
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(src,/const confirmed=observedGuidedPolicyApplyReceipt\(result,preview,plane\)/);
 assert.match(src,/if\(!confirmed\)throw new Error\(/);
 assert.match(src,/setMessage\("Core applied rule change at revision "\+confirmed.revision\)/);
 assert.match(src,/Inspect Core Change History before retrying/);
});

test("UX-2 Guided Policy cannot Apply malformed, expired or incomplete Core Preview and test proof",()=>{
 const now=Date.parse("2030-12-31T23:59:59Z");
 const plan={change_plan_id:"cp_"+"a".repeat(32),operation_class:"CHANGE",
   operation:"guided.remote-access-rule.set",
   change_type:"remote-access-rule",resource_type:"remote-access-rule",resource_ref:"allow-ssh",
   confirmation_class:"APPLY",no_change:false,expected_revision:30,
   valid_until:"2031-01-01T00:00:00Z",blast_radius:{limits:{truncated:false},unknowns:[]},
   policy_regression:{ok:true,required_failed:0}};
 const tests={ok:true,required_failed:0};
 assert.equal(access.canApplyGuidedRule(plan,tests,false,now),true);
 assert.equal(access.canApplyGuidedRule(plan,tests,true,Date.parse(plan.valid_until)),false);
 for(const invalid of [
   {...plan,change_plan_id:{secret:"INVALID"}},{...plan,confirmation_class:"DELETE"},
   {...plan,no_change:"false"},{...plan,operation_class:"TEST"},
   {...plan,change_type:"internet-access-rule"},
   {...plan,expected_revision:-1},{...plan,expected_revision:"30"},
   {...plan,valid_until:"yesterday"},{...plan,resource_ref:{"id":"allow-ssh"}},
   {...plan,blast_radius:{limits:{truncated:"false"},unknowns:[]}},
   {...plan,blast_radius:{limits:{truncated:false},unknowns:{secret:1}}},
   {...plan,blast_radius:null},
   {...plan,policy_regression:{ok:true,required_failed:"0"}}
 ])assert.equal(access.canApplyGuidedRule(invalid,tests,true,now),false,JSON.stringify(invalid));
 for(const invalid of [
   {ok:true,required_failed:"0"},{ok:true,required_failed:null},
   {ok:true,required_failed:-1},{ok:1,required_failed:0},
   {ok:true,required_failed:NaN}
 ])assert.equal(access.canApplyGuidedRule(plan,invalid,true,now),false,JSON.stringify(invalid));
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(src,/if\(!canApplyGuidedRule\(preview,tests,acknowledge\)\)\{/);
 assert.match(src,/Core Change Plan expired\. Request a fresh Preview and policy tests\./);
 assert.match(src,/if\(!observedGuidedPreviewMatchesIntent\(result,plane,operation,payload\.name\)\)/);
});

test("UX-2 Guided Preview and Apply must bind to the exact requested rule name",()=>{
 const base={change_plan_id:"cp_"+"x".repeat(32),operation_class:"CHANGE",
   operation:"guided.remote-access-rule.set",change_type:"remote-access-rule",
   resource_type:"remote-access-rule",resource_ref:"allow-dev",
   confirmation_class:"APPLY",expected_revision:12,no_change:false,
   valid_until:"2032-01-01T00:00:00Z"};
 const at=Date.parse("2031-01-01T00:00:00Z");
 assert.equal(access.observedGuidedPreviewMatchesIntent(base,"remote","set"," allow-dev ",at),true);
 for(const bad of [
   {...base,resource_ref:"allow-prod"},
   {...base,resource_ref:{secret:"allow-dev"}},
   {...base,resource_ref:"allow-dev\u202espoof"},
   {...base,operation:"guided.remote-access-rule.delete"},
   {...base,change_type:"internet-access-rule"},
   {...base,valid_until:"invalid"},
   {...base,confirmation_class:"DELETE"},
   {...base,expected_revision:"12"}
 ])assert.equal(access.observedGuidedPreviewMatchesIntent(bad,"remote","set","allow-dev",at),false,JSON.stringify(bad));
 assert.equal(access.observedGuidedPreviewMatchesIntent(base,"remote","set","allow-prod",at),false);
 assert.equal(access.observedGuidedPreviewMatchesIntent(base,"remote","set","allow-dev",
   Date.parse(base.valid_until)),false);
 assert.equal(access.observedGuidedPreviewMatchesIntent(null,"remote","set","allow-dev",at),false);
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(src,/if\(!observedGuidedPreviewMatchesIntent\(result,plane,operation,payload\.name\)\)/);
 assert.match(src,/&&preview\?\.resource_ref===name\.trim\(\)/);
 assert.match(src,/preview\?\.resource_ref!==name\.trim\(\)/);
});

test("UX-1 Core policy trace must prove the exact requested flow before any ALLOW display",()=>{
 const trace={plane:"remote",
   normalized_input:{plane:"remote",source:"branch",destination:"app",service:"ssh"},
   final:{result:"ALLOW",reason:"Core enabled matching rule",hidden:{secret:"PRIVATE"}},
   policy:{mode:"WHITELIST",enforcement:"ENABLED",matched_rules:["ssh-allow"],
     internal:{secret:"DO_NOT_EXPOSE"}},
   mixed:false,member_results:[{secret:"NEVER_SHOW"}]};
 const valid=access.observedCoreTraceForFlow(trace,"remote","branch","app","ssh","");
 assert.equal(valid?.final.result,"ALLOW");
 assert.equal(valid?.final.reason,"Core enabled matching rule");
 assert.equal(valid?.normalized_input.service,"ssh");
 assert.deepEqual(valid?.policy.matched_rules,["ssh-allow"]);
 assert.doesNotMatch(JSON.stringify(valid),/PRIVATE|DO_NOT_EXPOSE|NEVER_SHOW/);
 const ai={...trace,plane:"ai",normalized_input:{plane:"ai",source:"bot",destination:"document",
   permission:"read",path:"/reports"}};
 assert.equal(access.observedCoreTraceForFlow(ai,"ai","bot","document","read","/reports")?.plane,"ai");
 assert.equal(access.observedCoreTraceForFlow(ai,"ai","bot","document","read","/other"),null);
 for(const invalid of [null,{},[],{...trace,plane:"internet"},
   {...trace,normalized_input:{...trace.normalized_input,source:"other"}},
   {...trace,normalized_input:{...trace.normalized_input,destination:"other"}},
   {...trace,normalized_input:{...trace.normalized_input,service:"http"}},
   {...trace,final:{...trace.final,result:["ALLOW"]}},
   {...trace,final:{...trace.final,result:"PERMIT"}},
   {...trace,final:{...trace.final,reason:"bad\u202espoof"}},
   {...trace,policy:{...trace.policy,matched_rules:["ssh-allow",{"secret":"x"}]}},
   {...trace,policy:{...trace.policy,mode:["WHITELIST"]}},
   {...trace,mixed:"false"}])
   assert.equal(access.observedCoreTraceForFlow(invalid,"remote","branch","app","ssh",""),null,
     JSON.stringify(invalid));
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(src,/const qualified=observedCoreTraceForFlow\(next,plane,source\.trim\(\),destination\.trim\(\),selector\.trim\(\),path\.trim\(\)\)/);
 assert.match(src,/if\(!qualified\)throw new Error\(/);
 assert.match(src,/setTraceEvidence\(\{key:requestKey,value:qualified\}\)/);
});

test("CUI-001 NetBird/Twingate focus can find observed Core paths beyond first 16, without invented reachability",()=>{
 const paths=Array.from({length:26},(_,i)=>({
   plane:"remote",input:{plane:"remote",source:i===23?"BRANCH-23":"src-"+i,
     destination:i===23?"Production DB":"target-"+i,service:i===23?"ssh":"http"},
   decision:i===23?"ALLOW":"UNKNOWN",rules:[i===23?"rule-branch-23":"rule-"+i],
   nested_private:{secret:"MUST_NOT_EXPOSE"}
 }));
 const all=access.focusCoreModeledPaths(paths,"remote","");
 assert.equal(all.loaded,26);
 assert.equal(all.matching,26);
 assert.equal(all.rows.length,16);
 assert.equal(all.limited,true);
 assert.deepEqual(all.rows.map(r=>r.index),Array.from({length:16},(_,i)=>i));
 assert.doesNotMatch(JSON.stringify(all),/MUST_NOT_EXPOSE/);
 for(const term of ["branch-23","PRODUCTION","SSH","RULE-BRANCH-23"]){
  const found=access.focusCoreModeledPaths(paths,"remote",term);
  assert.equal(found.loaded,26);
  assert.equal(found.matching,1,term);
  assert.equal(found.limited,false);
  assert.equal(found.rows[0].index,23);
  assert.equal(found.rows[0].evidence.decision,"ALLOW");
  assert.equal(found.rows[0].evidence.flow.source,"BRANCH-23");
 }
 const absent=access.focusCoreModeledPaths(paths,"remote","not-a-resource");
 assert.equal(absent.matching,0);
 assert.deepEqual(absent.rows,[]);
 assert.equal(absent.loaded,26);
 // An invalid Core row must not become a selectable modeled-policy path.
 const invalid=access.focusCoreModeledPaths([...paths,{plane:"remote",input:{source:{secret:"bad"}}}],
   "remote","bad");
 assert.equal(invalid.matching,0);
 assert.equal(invalid.unverifiable,1);
 assert.deepEqual(invalid.rows,[]);
 for(const invalidTerm of [null,{},[], "x".repeat(129),"invalid\u202e"]){
  assert.equal(access.focusCoreModeledPaths(paths,"remote",invalidTerm),null);
 }
 assert.equal(access.focusCoreModeledPaths({}, "remote","ssh"),null);
 assert.equal(access.focusCoreModeledPaths(paths,"other","ssh"),null);
});
test("CUI-001 focus UI reads all loaded Core-modeled rows and explicitly warns when only loaded scope is searched",()=>{
 const source=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(source,/const \[graphFocus,setGraphFocus\]=useState\(""\)/);
 assert.match(source,/const scopedPaths=focusCoreModeledPaths\(allPaths,plane,graphFocus\)/);
 assert.match(source,/value=\{graphFocus\}/);
 assert.match(source,/aria-label="Focus modeled paths"/);
 assert.match(source,/Only the first 16 matching loaded paths are displayed/);
 assert.match(source,/No matching paths in the loaded Core snapshot/);
 assert.match(source,/Absent paths are not proof of DENY/);
 assert.match(source,/paths\.map\(\(\{index,evidence:row\}\)/);
 assert.doesNotMatch(source,/allPaths\.slice\(0,16\)/);
});

test("CUI-002 Tailscale-inspired prepared policy overview includes every relevant current rule attribute",()=>{
 const set={plane:"remote",operation:"set",name:"allow-prod",mode:"whitelist",
   source:"corp",destination:"prod-app",selector:"ssh",expiresAt:"2035-01-01T00:00:00Z",
   enabled:false,paths:"",purpose:"reason"};
 const good=access.preparedGuidedPolicyChange(set);
 assert.deepEqual(good,{
   action:"SET",plane:"remote",rule:"allow-prod",
   effect:"Allow matching access",source:"corp",destination:"prod-app",selector:"ssh",
   expiry:"2035-01-01T00:00:00Z",enabled:"Disabled",aiPaths:[],pathsLimited:false
 });
 const deleteView=access.preparedGuidedPolicyChange({...set,operation:"delete",name:"obsolete-access"});
 assert.deepEqual(deleteView,{
   action:"DELETE",plane:"remote",rule:"obsolete-access",
   effect:"Remove existing rule · Core Preview and explicit Apply required",
   source:"NOT APPLICABLE",destination:"NOT APPLICABLE",selector:"NOT APPLICABLE",
   expiry:"NOT APPLICABLE",enabled:"NOT APPLICABLE",aiPaths:[],pathsLimited:false
 });
 const invalidExpiry=access.preparedGuidedPolicyChange({...set,expiresAt:"2035-02-30T00:00:00Z"});
 assert.equal(invalidExpiry.expiry,"INVALID / NOT VERIFIED");
 assert.equal(access.preparedGuidedPolicyChange({...set,source:"spoof\u202e"}).source,"INVALID / NOT VERIFIED");
 const ai=access.preparedGuidedPolicyChange({...set,plane:"ai",mode:"blacklist",
   enabled:true,paths:"/reports, /readme"});
 assert.equal(ai.effect,"Deny matching access");
 assert.equal(ai.enabled,"Enabled");
 assert.deepEqual(ai.aiPaths,["/reports","/readme"]);
 assert.equal(ai.selector,"ssh");
 assert.equal(access.preparedGuidedPolicyChange({...set,operation:"update"}),null);
 assert.equal(access.preparedGuidedPolicyChange(null),null);
 assert.doesNotMatch(JSON.stringify(good),/reason/);
});
test("CUI-002 guided form displays a complete draft review for both SET and DELETE before Core Preview",()=>{
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 assert.match(src,/const prepared=preparedGuidedPolicyChange\(\{/);
 assert.match(src,/aria-label="Prepared rule change · not applied"/);
 assert.match(src,/Prepared \{prepared\.action\} · \{prepared\.rule\}/);
 assert.match(src,/Status: \{prepared\.enabled\}/);
 assert.match(src,/Expiry: \{prepared\.expiry\}/);
 assert.match(src,/AI path limits: \{prepared\.aiPaths/);
 assert.match(src,/Not submitted to Core until a fresh Preview, required tests and explicit Apply/);
 assert.doesNotMatch(src,/This is an unverified draft\. No access is granted or denied until Core preview/);
});

test("R2.2/M2 Core onboarding Host first-100 must bind exact resource family, limit and cursor",()=>{
 const item={id:"host-a",name:"Lab Agent",admission_state:"PENDING_APPROVAL",
   trust_status:"trusted",connected:false,secret:"DO_NOT_COPY",row_version:19};
 const page={resource_type:"managed-host",limit:100,next_cursor:null,items:[item]};
 const good=enroll.observedEnrollmentHostPage(page);
 assert.deepEqual(good,{items:[{id:"host-a",name:"Lab Agent",
   admission_state:"PENDING_APPROVAL",trust_status:"trusted",connected:false}],
   complete:true});
 assert.doesNotMatch(JSON.stringify(good),/DO_NOT_COPY|row_version|secret/);
 const opaque="eyJ2IjoxLCJyZXNvdXJjZSI6Im1hbmFnZWQtaG9zdCJ9";
 assert.equal(enroll.observedEnrollmentHostPage({...page,next_cursor:opaque})?.complete,false);
 for(const bad of [null,{},[],{items:[]},
  {...page,resource_type:undefined},{...page,resource_type:"remote-service"},
  {...page,resource_type:"management-job"},{...page,limit:undefined},
  {...page,limit:50},{...page,limit:"100"},
  {...page,next_cursor:undefined},{...page,next_cursor:""},
  {...page,next_cursor:"bad cursor"},{...page,next_cursor:"../secret"},
  {...page,next_cursor:12},{...page,items:[],next_cursor:opaque},
  {...page,items:[item,item]},
 ])assert.equal(enroll.observedEnrollmentHostPage(bad),null,JSON.stringify(bad)?.slice(0,105));
 assert.deepEqual(enroll.observedEnrollmentHostPage({...page,items:[]})?.items,[]);
});

test("R2.2/M2 Core enrollment history requires observed fleet total before claiming zero tickets",()=>{
 const item={id:"enr-a",label:"lab",type:"zero-touch",state:"pending",
  first_host_admission:"PENDING_APPROVAL",remaining_seconds:300,
  token:"DO_NOT_COPY"};
 const observed=enroll.observedEnrollmentHistory({items:[item],total:1});
 assert.equal(observed.status,"ready");
 assert.equal(observed.total,1);
 assert.equal(observed.partial,false);
 assert.doesNotMatch(JSON.stringify(observed),/DO_NOT_COPY|token/);
 const validEmpty=enroll.observedEnrollmentHistory({items:[],total:0});
 assert.equal(validEmpty.status,"ready");
 assert.deepEqual(validEmpty.items,[]);
 for(const bad of [{items:[]},{items:[],total:null},{items:[],total:"0"},
  {items:[],total:2},{items:[item],total:0},{items:[item],total:-1},
  {items:[item],total:1.5},{items:[item,item],total:2}]){
  assert.equal(enroll.observedEnrollmentHistory(bad).status,"UNKNOWN",JSON.stringify(bad).slice(0,80));
 }
});

test("R3/R6 one-time enrollment issuance and Core admission Apply have synchronous non-idempotent request locks",()=>{
 const src=readFileSync(join(webRoot,"src","p0-enrollment.tsx"),"utf8");
 const issue=src.split("  async function issue(){",2)[1]?.split("  async function previewApproval(){",1)[0]||"";
 const apply=src.split("  async function applyApproval(){",2)[1]?.split("  return <section className=\"dr-p0-onboarding\"",1)[0]||"";
 assert.match(src,/const issueInFlight=useRef\(false\)/);
 assert.match(src,/const admissionApplyInFlight=useRef\(false\)/);
 assert.match(issue,/if\(!admin\|\|busy\|\|issueInFlight\.current\)return;/);
 assert.match(issue,/issueInFlight\.current=true;/);
 assert.match(issue,/finally\{issueInFlight\.current=false;setBusy\(false\)\}/);
 assert.match(issue,/The ticket may exist; inspect Core enrollment history before retrying/);
 assert.match(apply,/\|\|busy\|\|admissionApplyInFlight\.current\)return;/);
 assert.match(apply,/admissionApplyInFlight\.current=true;/);
 assert.match(apply,/finally\{admissionApplyInFlight\.current=false;setBusy\(false\)\}/);
 assert.match(apply,/Core admission apply result is unverified/);
});

test("M2/R6 Guided Core Change Plan issuance and one-shot Apply block overlapping non-idempotent POSTs",()=>{
 const src=readFileSync(join(webRoot,"src","p0-access-policy.tsx"),"utf8");
 const guided=src.split("export function GuidedPolicyJourney(",2)[1]||"";
 const review=guided.split("  async function review(){",2)[1]?.split("  async function verifyRequired(){",1)[0]||"";
 const apply=guided.split("  async function apply(){",2)[1]?.split("  return <section className=",1)[0]||"";
 assert.match(guided,/const previewInFlight=useRef\(false\)/);
 assert.match(guided,/const applyInFlight=useRef\(false\)/);
 assert.match(review,/if\(!ready\|\|busy\|\|previewInFlight\.current\)return;/);
 assert.match(review,/previewInFlight\.current=true;/);
 assert.match(review,/finally\{previewInFlight\.current=false;/);
 assert.match(apply,/if\(applyInFlight\.current\)return;/);
 assert.match(apply,/applyInFlight\.current=true;/);
 assert.match(apply,/finally\{applyInFlight\.current=false;/);
 assert.match(apply,/const confirmed=observedGuidedPolicyApplyReceipt\(result,preview,plane\)/);
 assert.match(apply,/Apply outcome UNKNOWN. Inspect Core Change History before retrying/);
 assert.doesNotMatch(apply,/catch\(e:any\).*setPreview\(preview\)/);
});
