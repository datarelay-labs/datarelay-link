import React, {useEffect, useRef, useState} from "react";
import {createRoot} from "react-dom/client";
import {QRCodeSVG} from "qrcode.react";
import {AdministrationHub,type AdministrationHubTask} from "@datarelay-labs/foundation";
import {createLinkFoundationAdministrationTasks} from "./foundation-administration";
import {backupToolReadiness} from "./foundation-administration";
import {observedCoreFlag,observedCoreCount,observedCoreNames} from "./uxb-impact-evidence";
import {AccessEvidenceExplorer,GuidedPolicyJourney,coreFlowKey,coreCutoffKey,visibleCoreEvidence,resolveCompletePolicyMatch,type AccessPlane} from "./p0-access-policy";
import {EnrollmentOnboarding} from "./p0-enrollment";
import {navGroups,groupFor,labelFor,pageDescriptions,visibleRoute,navMatches,setupContextForObjectFamily} from "./uxb-navigation";
import {FirstUseHome,isFreshInstallation,observedRecentFeed,observedNumber,accessPlaneCount,coreHealthState,type RecentFeed} from "./uxb-home";
import {requireObservedMenuPayload,requireObservedInventoryContinuation,requireObservedObjectContinuation,requireObservedAuditRetention,auditRetentionRunPermitted,requireObservedAccessHygiene,hygieneInspectTarget,requireObservedJobStart,requireObservedFleetApply,requireObservedFleetPreview,requireObservedFleetApplyForPreview,requireObservedAuditExport,requireObservedRolloutPreview,requireObservedInventoryExport,requireObservedJobDetail,requireObservedJobCancellation,isPartialCorePage,selectMenuPage,combineObservedPolicyPlanes,policyStateLabel,policyExpiryLabel,type MenuPagePosition} from "./uxb-menu-evidence";
import {RemoteServiceEditor} from "./uxb-remote-service";
import {RevisionHistory} from "./uxb-revisions";
import {AgentVersionDrift} from "./uxb-versions";
import {CoreDoctorWorkspace} from "./uxb-doctor";
import {SavedViewsWorkspace,saveDraftForResource,isSavedAdmission,type HostAdmission} from "./uxb-saved-views";
import {hostDetailSections,hostConnectionState} from "./uxb-host-detail";
import {hostInventoryFacts,hostVisibleIdentity} from "./uxb-host-detail";
import {serviceStateLabel,serviceDetailSections} from "./uxb-service-detail";
import {serviceVisibleIdentity} from "./uxb-service-detail";
import {filterObservedHosts} from "./uxb-host-search";
import {FirstConnectionSetup,connectionReviewContext,type SetupDraft} from "./uxb-setup";

type Json = Record<string, any>;

let csrf="";

async function api(path:string, init:RequestInit={}):Promise<Json>{
  const headers:Record<string,string>={"Accept":"application/json",...((init.headers||{}) as Record<string,string>)};
  if(init.method && init.method!=="GET"){
    headers["Content-Type"]="application/json";
    if(csrf)headers["X-CSRF-Token"]=csrf;
  }
  const res=await fetch(path,{...init,headers,credentials:"same-origin"});
  let body:Json={};try{body=await res.json()}catch{}
  if(!res.ok)throw new Error(body.error||("HTTP "+res.status));
  return body;
}

function useEscapeClose(enabled:boolean,onClose:()=>void){
  useEffect(()=>{
    if(!enabled)return;
    function handle(e:KeyboardEvent){if(e.key==="Escape")onClose()}
    window.addEventListener("keydown",handle);
    return()=>window.removeEventListener("keydown",handle);
  },[enabled,onClose]);
}

function Table({items}:{items:any[]}){
  if(!items?.length)return <div className="empty">No results</div>;
  const keys=Object.keys(items[0]).filter(k=>typeof items[0][k]!=="object").slice(0,9);
  return <table><thead><tr>{keys.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>
    {items.map((item,i)=><tr key={item.id||i}>{keys.map(k=><td key={k}>{item[k]===null?"":String(item[k]??"")}</td>)}</tr>)}
  </tbody></table>;
}
function Metric({label,value}:{label:string,value:any}){return <div className="card"><div className="muted">{label}</div><div className="metric">{String(value??"UNKNOWN")}</div></div>}

function PageSkeleton(){
  return <div className="dr-page-skeleton" aria-label="Loading page" aria-busy="true">
    <div className="dr-skeleton-line title"/><div className="dr-skeleton-line subtitle"/>
    <div className="dr-skeleton-grid">{[0,1,2,3].map(i=><div className="dr-skeleton-card" key={i}><div className="dr-skeleton-line short"/><div className="dr-skeleton-line metric"/></div>)}</div>
    <div className="dr-skeleton-panel"><div className="dr-skeleton-line short"/>{[0,1,2,3,4].map(i=><div className="dr-skeleton-row" key={i}><span/><span/><span/></div>)}</div>
  </div>;
}

function LoginIcon({kind}:{kind:"user"|"lock"|"eye"|"eyeoff"}){
  if(kind==="user")return <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4.6 3.5-7 8-7s7.2 2.4 8 7"/></svg>;
  if(kind==="eye")return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>;
  if(kind==="eyeoff")return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 6.2A10.7 10.7 0 0 1 12 6c6.1 0 9.5 6 9.5 6a14.7 14.7 0 0 1-3.1 3.6M6.1 6.2C3.8 8 2.5 12 2.5 12S5.9 18 12 18c1 0 1.9-.2 2.8-.4"/></svg>;
  return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>;
}

const loginResources=[
  ["Documentation","datarelay.run/docs","https://datarelay.run/docs","DOC"],
  ["Quick Start Guide","datarelay.run/quickstart","https://datarelay.run/quickstart","GO"],
  ["Release Notes","datarelay.run/releases","https://datarelay.run/releases","REL"],
  ["DataRelay Website","datarelay.run","https://datarelay.run","WEB"],
  ["Support","support@datarelay.run","mailto:support@datarelay.run","SUP"],
] as const;

function AuthScaffold({children}:{children:React.ReactNode}){
  return <div className="dr-login-page">
    <div className="dr-login-main">
      <div className="dr-login-grid">
        <section className="dr-login-identity">
          <header className="dr-login-brand-block">
            <img className="dr-login-logo" src="/logo/datarelay-logo.svg" alt="DataRelay logo"/>
            <div className="dr-login-wordmark"><span>Data</span><strong>Relay</strong></div>
            <p className="dr-login-product">Data Relay Link</p>
            <p className="dr-login-tagline">Secure Connectivity for Isolated Networks</p>
            <p className="dr-login-description">Relay only the connections that are actually needed. Manage Remote Access, Internet Access, and AI Access from one bounded control surface.</p>
          </header>
          <section className="dr-login-resources" aria-labelledby="dr-login-resources-title">
            <h2 id="dr-login-resources-title">Resources</h2>
            {loginResources.map(([title,subtitle,href,mark])=><a className="dr-login-resource" href={href} target={href.startsWith("http")?"_blank":undefined} rel={href.startsWith("http")?"noopener noreferrer":undefined} key={title}>
              <span className="dr-login-resource-icon">{mark}</span>
              <span className="dr-login-resource-copy"><strong>{title}</strong><small>{subtitle}</small></span>
              {href.startsWith("http")&&<span className="dr-login-external" aria-hidden="true">↗</span>}
            </a>)}
          </section>
        </section>
        <section className="dr-login-card">{children}</section>
      </div>
    </div>
    <footer className="dr-login-footer"><p>© 2026 DataRelay. All rights reserved.</p><p><a href="https://datarelay.run/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a><span>|</span><a href="https://datarelay.run/terms" target="_blank" rel="noopener noreferrer">Terms of Use</a><span>|</span><a href="https://datarelay.run/security" target="_blank" rel="noopener noreferrer">Security</a></p></footer>
  </div>;
}

function LoginCardHeader({title="Welcome to Data Relay Link",subtitle="Please sign in to continue."}:{title?:string,subtitle?:string}){
  return <div className="dr-login-card-head"><div className="dr-login-lock"><LoginIcon kind="lock"/></div><h1>{title}</h1><p>{subtitle}</p></div>;
}

function Login({onLogin}:{onLogin:(op:any)=>void}){
  const [username,setUsername]=useState("admin"),[password,setPassword]=useState(""),[totp,setTotp]=useState(""),[recovery,setRecovery]=useState(""),[showMfa,setShowMfa]=useState(false),[showPassword,setShowPassword]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [setup,setSetup]=useState<any>(null),[setupCode,setSetupCode]=useState(""),[showSetupSecret,setShowSetupSecret]=useState(false),[copiedSecret,setCopiedSecret]=useState(false),[recoveryCodes,setRecoveryCodes]=useState<string[]>([]),[pendingOperator,setPendingOperator]=useState<any>(null);
  async function submit(e:React.FormEvent){
    e.preventDefault();setError("");setBusy(true);
    try{
      const d=await api("/api/v1/auth/login",{method:"POST",body:JSON.stringify({username,password,totp,recovery_code:recovery})});
      if(d.mfa_setup_required){setSetup(d);setSetupCode("");return}
      csrf=d.csrf_token;onLogin(d.operator);
    }catch(err:any){setError(err.message||String(err))}finally{setBusy(false)}
  }
  async function finishMfa(e:React.FormEvent){
    e.preventDefault();setError("");setBusy(true);
    try{
      const d=await api("/api/v1/auth/mfa/enroll/confirm",{method:"POST",body:JSON.stringify({enrollment_token:setup.enrollment_token,totp:setupCode})});
      csrf=d.csrf_token;setRecoveryCodes(d.recovery_codes||[]);setPendingOperator(d.operator);
    }catch(err:any){setError(err.message||String(err))}finally{setBusy(false)}
  }
  async function cancelMfaSetup(){
    if(!setup?.enrollment_token){setSetup(null);return}
    setBusy(true);setError("");
    try{await api("/api/v1/auth/mfa/enroll/cancel",{method:"POST",body:JSON.stringify({enrollment_token:setup.enrollment_token})})}catch{}finally{setBusy(false);setSetup(null);setSetupCode("");setShowSetupSecret(false);setCopiedSecret(false);setPassword("")}
  }
  async function copySetupSecret(){
    try{await navigator.clipboard.writeText(String(setup?.totp_secret||""));setCopiedSecret(true);window.setTimeout(()=>setCopiedSecret(false),1400)}catch{setError("Copy is unavailable in this browser. Use Show key and copy it manually.")}
  }
  if(recoveryCodes.length&&pendingOperator)return <AuthScaffold><LoginCardHeader title="MFA enabled" subtitle="Store these recovery codes offline. They are displayed only now."/><pre className="dr-login-recovery">{recoveryCodes.join("\n")}</pre><button className="dr-login-submit" onClick={()=>onLogin(pendingOperator)}>I saved the recovery codes</button></AuthScaffold>;
  if(setup)return <AuthScaffold><LoginCardHeader title="Set up MFA" subtitle="MFA is required for this account. The temporary setup key is not active until you verify a current code."/><form className="dr-login-form" onSubmit={finishMfa}>{error&&<div className="dr-login-error">{error}</div>}<div className="dr-mfa-setup-note"><strong>1. Scan the QR code</strong><span>This setup challenge expires at {setup.expires_at||"the displayed expiry"}. Cancelling discards the temporary key.</span></div><div className="dr-mfa-qr-panel"><div className="dr-mfa-qr" role="img" aria-label="Authenticator setup QR code"><QRCodeSVG value={String(setup.otpauth_uri||"")} size={168} level="M"/></div><div className="dr-mfa-qr-copy"><strong>Scan with your authenticator app</strong><span>The QR code is rendered locally from this temporary setup challenge. Nothing is sent to an external QR service.</span></div></div><div className="dr-mfa-secret-row"><div><span className="dr-field-label">Can’t scan? Authenticator key</span><code>{showSetupSecret?String(setup.totp_secret||""):"•••• •••• •••• •••• •••• ••••"}</code></div><div className="dr-inline-actions"><button className="dr-login-secondary compact" type="button" onClick={()=>setShowSetupSecret(!showSetupSecret)}>{showSetupSecret?"Hide key":"Show key"}</button><button className="dr-login-secondary compact" type="button" onClick={copySetupSecret}>{copiedSecret?"Copied":"Copy"}</button></div></div><details className="dr-login-details"><summary>Advanced: authenticator URI</summary><pre>{setup.otpauth_uri}</pre></details><div className="dr-mfa-setup-note"><strong>2. Verify setup</strong><span>Enter the current 6-digit code. Recovery codes are issued only after verification succeeds.</span></div><label>MFA code<input inputMode="numeric" autoComplete="one-time-code" value={setupCode} onChange={e=>setSetupCode(e.target.value)} placeholder="6-digit TOTP"/></label><button className="dr-login-submit" type="submit" disabled={busy||!/^\d{6}$/.test(setupCode)}>{busy?"Verifying…":"Verify MFA and sign in"}</button><button className="dr-login-secondary" type="button" onClick={cancelMfaSetup} disabled={busy}>Cancel setup</button></form></AuthScaffold>;
  return <AuthScaffold>
    <LoginCardHeader/>
    <form className="dr-login-form" onSubmit={submit}>
      {error&&<div className="dr-login-error" role="alert">{error}</div>}
      <div><label htmlFor="drlink-login-user">Username</label><div className="dr-login-field"><span className="dr-login-field-icon"><LoginIcon kind="user"/></span><input id="drlink-login-user" name="username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} placeholder="Enter your username"/></div></div>
      <div><label htmlFor="drlink-login-password">Password</label><div className="dr-login-field"><span className="dr-login-field-icon"><LoginIcon kind="lock"/></span><input id="drlink-login-password" name="password" type={showPassword?"text":"password"} autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Enter your password"/><button className="dr-login-eye" type="button" onClick={()=>setShowPassword(!showPassword)} aria-label={showPassword?"Hide password":"Show password"}><LoginIcon kind={showPassword?"eyeoff":"eye"}/></button></div></div>
      <button className="dr-login-mfa-toggle" type="button" onClick={()=>setShowMfa(!showMfa)}>{showMfa?"Hide MFA / recovery":"Use MFA / recovery"}</button>
      {showMfa&&<div className="dr-login-mfa-fields"><label>MFA code<input inputMode="numeric" autoComplete="one-time-code" value={totp} onChange={e=>setTotp(e.target.value)} placeholder="6-digit TOTP"/></label><label>Recovery code<input value={recovery} onChange={e=>setRecovery(e.target.value)} placeholder="or recovery code"/></label></div>}
      <button className="dr-login-submit" type="submit" disabled={busy}>{busy?"Signing in…":"Sign In"}</button>
      <p className="dr-login-admin-note">Accounts are created by an administrator. Self-service registration is not available.</p>
    </form>
  </AuthScaffold>;
}

function DraftWorkflowReference({context,onNavigate}:{
  context?:any,onNavigate?:(id:string,groupId?:string,context?:any)=>void
}){
  const plane=["remote","internet","ai"].includes(String(context?.plane))
    ?String(context.plane) as AccessPlane:null;
  if(!plane)return null;
  const selected=connectionReviewContext(plane,context?.source,context?.destination,context?.selector);
  const complete="source" in selected;
  return <section className="card dr-uxb-context" role="note" aria-label="Access context for advanced draft">
    <strong>{plane.toUpperCase()} Access · selected task reference only</strong>
    {complete?<p>Source: {selected.source} · Destination: {selected.destination}
      · {plane==="ai"?"Permission":"Service"}: {selected.selector}</p>:
      <p>Core object selection is incomplete or unverified. Recheck the matching access plane.</p>}
    <p>This context is not added to ConfigurationBundle, does not represent a Core policy
      decision, and does not carry a Change Plan or approval across screens. The draft
      editor and explicit Core Test → Diff & Preview → typed Apply remain independent.</p>
    <div className="toolbar">
      <button className="secondary" onClick={()=>onNavigate?.("access","access",selected)}>
        Recheck selected access in Core →</button>
      {complete&&<button className="secondary" onClick={()=>onNavigate?.("policies","access",selected)}>
        Use Guided Policy for this flow →</button>}
    </div>
  </section>;
}

function DraftWorkspace(){
  const [bundle,setBundle]=useState("configurationBundle:\n  context: server\n  networkObjects: []\n");
  const [draftId,setDraftId]=useState("");
  const [testResult,setTestResult]=useState<any>(null);
  const [preview,setPreview]=useState<any>(null);
  const [confirmation,setConfirmation]=useState("");
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const planEpoch=useRef(0);

  function changeBundle(value:string){
    planEpoch.current+=1;
    setBundle(value);setPreview(null);setTestResult(null);setConfirmation("");
    setError("");setMessage("");
  }

  async function ensureDraft(){
    if(draftId){
      await api("/api/v1/drafts/"+draftId+"/update",{method:"POST",body:JSON.stringify({bundle_text:bundle})});
      return draftId;
    }
    const created=await api("/api/v1/drafts",{method:"POST",body:JSON.stringify({bundle_text:bundle})});
    setDraftId(created.id);
    return created.id as string;
  }
  async function doTest(){
    const epoch=++planEpoch.current;
    setError("");setMessage("");setPreview(null);setConfirmation("");
    try{
      const id=await ensureDraft();
      const result=await api("/api/v1/drafts/"+id+"/test",{method:"POST",body:"{}"});
      if(epoch!==planEpoch.current)return;
      setTestResult(result);setPreview(null);setConfirmation("");
      setMessage("ConfigurationBundle test PASS");
    }catch(e:any){if(epoch===planEpoch.current){setTestResult(null);setError(e.message||String(e))}}
  }
  async function doDiff(){
    const epoch=++planEpoch.current;
    setError("");setMessage("");setPreview(null);setConfirmation("");
    try{
      const id=await ensureDraft();
      const result=await api("/api/v1/drafts/"+id+"/diff",{method:"POST",body:"{}"});
      if(epoch!==planEpoch.current)return;
      setPreview(result);setTestResult(null);setConfirmation("");
    }catch(e:any){if(epoch===planEpoch.current){setPreview(null);setError(e.message||String(e))}}
  }
  async function doApply(){
    if(!draftId||!preview?.change_plan_id||confirmation!=="APPLY")return;
    setError("");setMessage("");
    try{
      // Apply the exact Core plan already previewed; never re-upload a modified
      // bundle while committing it. Core still validates hash and revision.
      const result=await api("/api/v1/drafts/"+draftId+"/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview.change_plan_id,confirmation})});
      setMessage("Applied at revision "+result.revision);setPreview(null);setTestResult(null);setDraftId("");setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doCancel(){
    if(!draftId)return;
    setError("");
    try{
      await api("/api/v1/drafts/"+draftId+"/cancel",{method:"POST",body:"{}"});
      setMessage("Draft cancelled with zero authoritative mutation");setDraftId("");setPreview(null);setTestResult(null);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doExportDraft(){
    if(!draftId)return;
    const epoch=++planEpoch.current;
    setError("");
    try{
      const result=await api("/api/v1/drafts/"+draftId+"/export");
      if(epoch!==planEpoch.current)return;
      changeBundle(result.bundle_text);setMessage("Draft ConfigurationBundle exported to the editor");
    }catch(e:any){if(epoch===planEpoch.current)setError(e.message||String(e))}
  }
  async function doExportCurrent(){
    const epoch=++planEpoch.current;
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/configuration/export");
      if(epoch!==planEpoch.current)return;
      changeBundle(result.bundle_text);
      setMessage("Current redacted configuration exported to the editor");
    }catch(e:any){if(epoch===planEpoch.current)setError(e.message||String(e))}
  }
  return <div className="draft-layout">
    <div className="card">
      <h3>Configuration Draft</h3>
      <div className="muted">Non-authoritative until Apply. Test and Diff use the canonical ConfigurationBundle engine; Apply is revision-bound.</div>
      {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
      <textarea className="draft-editor" value={bundle} onChange={e=>changeBundle(e.target.value)} spellCheck={false}/>
      <div className="toolbar">
        <button className="primary" onClick={doTest}>Test</button>
        <button className="primary" onClick={doDiff}>Diff & Preview</button>
        <button className="secondary" onClick={doExportCurrent}>Export Current</button>
        <button className="secondary" onClick={doExportDraft} disabled={!draftId}>Export Draft</button>
        <button className="secondary" onClick={doCancel} disabled={!draftId}>Cancel Draft</button>
      </div>
      {testResult&&<div className="notice">Validation PASS · {testResult.change_count} pending change(s) · {testResult.no_change?"NO CHANGE":"CHANGES PENDING"}</div>}
    </div>
    <div className="card">
      <h3>Change Plan</h3>
      {!preview&&<div className="muted">Run Diff & Preview to validate references, dependency ordering, revision, and security impact before Apply.</div>}
      {preview&&<>
        <pre className="plan">{preview.formatted_plan}</pre>
        {(preview.security_impact||[]).length>0&&<div className="warning-box">{preview.security_impact.map((x:string)=><div key={x}>{x}</div>)}</div>}
        <BlastRadiusView preview={preview}/>
        <label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label>
        <button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply Draft</button>
      </>}
    </div>
  </div>;
}

function BlastRadiusView({preview}:{preview:any}){
  const blast=preview?.blast_radius;
  const overlay=preview?.graph_overlay;
  const regression=preview?.policy_regression;
  if(!blast&&!overlay&&!regression)return null;
  const limits=blast?.limits||{};
  const changes=(Array.isArray(blast?.decision_changes)?blast.decision_changes:[])
    .filter((x:any)=>x&&typeof x==="object").slice(0,100).map((x:any)=>({
    plane:x.flow?.plane||"UNKNOWN",
    source:x.flow?.source||"UNKNOWN",
    destination:x.flow?.destination||"UNKNOWN",
    selector:x.flow?.service||x.flow?.permission||"UNKNOWN",
    current:x.current??"UNKNOWN",
    proposed:x.proposed??"UNKNOWN",
  }));
  const unknowns=Array.isArray(blast?.unknowns)?blast.unknowns:[];
  const overlayLimits=overlay?.limits||{};
  return <div className="card">
    <h4>Blast Radius / Draft Graph Overlay</h4>
    <div className="muted">Core-computed policy/inventory facts only. Unknowns are explicit; this is not network-topology discovery.</div>
    {blast&&<div className="grid">
      <Metric label="Broadens access" value={observedCoreFlag(blast.access_broadened)}/>
      <Metric label="Narrows access" value={observedCoreFlag(blast.access_narrowed)}/>
      <Metric label="Newly reachable" value={observedCoreCount(limits.newly_reachable_total)}/>
      <Metric label="Newly blocked" value={observedCoreCount(limits.newly_blocked_total)}/>
      <Metric label="Truncated" value={observedCoreFlag(limits.truncated)}/>
    </div>}
    {blast&&(typeof blast.access_broadened!=="boolean"||typeof blast.access_narrowed!=="boolean"
      ||typeof limits.truncated!=="boolean")&&<div className="warning-box" role="status">
      Missing impact fields are UNKNOWN, never proof of no access change. Review exact Core evidence before Apply.
    </div>}
    {limits.truncated===true&&<div className="warning-box">Blast Radius is bounded/truncated: {observedCoreNames(limits.truncated_by)}. Review the limit metadata before Apply.</div>}
    {regression&&<div className={regression.ok===true?"notice":"warning-box"}>Required Policy Tests: {observedCoreCount(regression.passed)}/{observedCoreCount(regression.count)} pass · failures {observedCoreCount(regression.required_failed)}</div>}
    {blast&&<div className="muted">Affected rules: {observedCoreNames(blast.affected_rules)} · Managed Hosts: {observedCoreNames(blast.affected_managed_hosts)} · Remote Services: {observedCoreNames(blast.affected_remote_services)}</div>}
    {changes.length>0&&<><p className="muted">Current → proposed Core policy decisions; these are modeled changes, not observed network sessions.</p><Table items={changes}/></>}
    {overlay&&<div className="muted">Graph references · added {observedCoreCount(overlayLimits.references_added_total)}
      · removed {observedCoreCount(overlayLimits.references_removed_total)}
      · unchanged returned {Array.isArray(overlay.unchanged_edge_ids)?overlay.unchanged_edge_ids.length:"UNKNOWN"} (bounded view)</div>}
    {unknowns.length>0&&<div className="warning-box">Unknown / not deterministically modeled: {observedCoreNames(unknowns)}</div>}
  </div>;
}

function GuidedApplyPanel({title,build}:{title:string,build:()=>any}){
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[message,setMessage]=useState(""),[error,setError]=useState("");
  async function doPreview(){setError("");setMessage("");try{const req=build();const result=await api("/api/v1/guided/preview",{method:"POST",body:JSON.stringify(req)});setPreview(result);setConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function doApply(){setError("");try{const result=await api("/api/v1/guided/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});setMessage("Applied at revision "+result.revision);setPreview(null);setConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  return <div className="card"><h3>{title}</h3>{error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}<button className="primary" onClick={doPreview}>Preview</button>{preview&&<div className="card"><pre className="plan">{JSON.stringify({change_type:preview.change_type,preview:preview.preview,impact:preview.impact,valid_until:preview.valid_until},null,2)}</pre><BlastRadiusView preview={preview}/><label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label><button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply</button></div>}</div>;
}

function ManagedHostMetadataPanel(){
  const [host,setHost]=useState(""),[label,setLabel]=useState(""),[description,setDescription]=useState("");
  const [tags,setTags]=useState("");
  function request(){
    const payload:any={host,description};
    if(label)payload.label=label;
    const tagMap:any={};tags.split(",").map(x=>x.trim()).filter(Boolean).forEach(item=>{const i=item.indexOf("=");if(i>0)tagMap[item.slice(0,i).trim()]=item.slice(i+1).trim()});
    if(Object.keys(tagMap).length)payload.tags=tagMap;
    return {change_type:"managed-host-metadata",payload};
  }
  return <div><div className="card"><h3>Guided Managed Host Metadata</h3><div className="toolbar"><input value={host} onChange={e=>setHost(e.target.value)} placeholder="Managed Host ID/name"/><input value={label} onChange={e=>setLabel(e.target.value)} placeholder="Optional label"/><input value={description} onChange={e=>setDescription(e.target.value)} placeholder="Description (blank clears)"/><input value={tags} onChange={e=>setTags(e.target.value)} placeholder="tags: env=prod,owner=netops"/></div></div><GuidedApplyPanel key={JSON.stringify([host,label,description,tags])} title="Managed Host Change Plan" build={request}/></div>;
}

function ManagedHostAdmissionPanel(){
  const [host,setHost]=useState(""),[operation,setOperation]=useState("quarantine");
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState("");
  const [message,setMessage]=useState(""),[error,setError]=useState("");
  async function doPreview(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/managed-hosts/admission/preview",{
        method:"POST",body:JSON.stringify({host,operation}),
      });
      setPreview(result);setConfirmation("");
    }catch(e:any){setPreview(null);setError(e.message||String(e))}
  }
  async function doApply(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/managed-hosts/admission/apply",{
        method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation}),
      });
      setMessage("Host admission "+(operation==="approve"?"approved":"quarantined")+" at revision "+result.revision+". Reload Managed Hosts to view the new state.");
      setPreview(null);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  const required=preview?.confirmation_class||"";
  return <div className="card">
    <h3>Managed Host Approval / Quarantine</h3>
    <p className="muted">Admission is separate from connection and management trust. Quarantine denies new Host access; active connections are not terminated. Identity, policy references, services and public ports are preserved. Approval restores normal policy evaluation, not unconditional access.</p>
    {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
    <div className="toolbar">
      <input value={host} onChange={e=>{setHost(e.target.value);setPreview(null)}} placeholder="Managed Host ID/name"/>
      <select aria-label="Admission action" value={operation} onChange={e=>{setOperation(e.target.value);setPreview(null);setConfirmation("")}}>
        <option value="quarantine">Quarantine new access</option>
        <option value="approve">Approve / restore access</option>
      </select>
      <button className="secondary" disabled={!host.trim()} onClick={doPreview}>Preview Admission Impact</button>
    </div>
    {preview&&<div className="warning-box">
      <pre className="plan">{JSON.stringify({preview:preview.preview,impact:preview.impact,valid_until:preview.valid_until},null,2)}</pre>
      <label className="apply-label">Type {required} to continue<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder={required}/></label>
      <button className={operation==="quarantine"?"danger":"primary"} disabled={confirmation!==required} onClick={doApply}>{operation==="quarantine"?"Quarantine Managed Host":"Approve Managed Host"}</button>
    </div>}
  </div>;
}

function ManagedHostLifecyclePanel(){
  const [host,setHost]=useState(""),[operation,setOperation]=useState("revoke-trust");
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[message,setMessage]=useState(""),[error,setError]=useState("");
  async function doPreview(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/managed-hosts/lifecycle/preview",{method:"POST",body:JSON.stringify({host,operation})});
      setPreview(result);setConfirmation("");
    }catch(e:any){setPreview(null);setError(e.message||String(e))}
  }
  async function doApply(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/managed-hosts/lifecycle/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});
      setMessage((operation==="retire"?"Managed Host retired":"Managed Host trust revoked")+" at revision "+result.revision);
      setPreview(null);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  const required=preview?.confirmation_class||"";
  return <div className="card">
    <h3>Managed Host Lifecycle</h3>
    <div className="muted">Trust revoke keeps the Managed Host record, Remote Services, and public port reservations but requires re-enrollment. Retire permanently removes reference-safe server-owned Host state and owned Remote Services/port reservations.</div>
    {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
    <div className="toolbar">
      <input value={host} onChange={e=>{setHost(e.target.value);setPreview(null);setConfirmation("")}} placeholder="Managed Host ID/name"/>
      <select value={operation} onChange={e=>{setOperation(e.target.value);setPreview(null);setConfirmation("")}}><option value="revoke-trust">Revoke trust</option><option value="retire">Retire Managed Host</option></select>
      <button className="primary" onClick={doPreview} disabled={!host}>Preview Impact</button>
    </div>
    {preview&&<div className="warning-box">
      <pre className="plan">{JSON.stringify({preview:preview.preview,impact:preview.impact,valid_until:preview.valid_until},null,2)}</pre>
      <label className="apply-label">Type {required} to continue<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder={required}/></label>
      <button className="danger" onClick={doApply} disabled={confirmation!==required}>{operation==="retire"?"Retire Managed Host":"Revoke Managed Host Trust"}</button>
    </div>}
  </div>;
}

function GuidedObjectPanel(){
  const [kind,setKind]=useState("network-object"),[operation,setOperation]=useState("set"),[name,setName]=useState(""),[value,setValue]=useState(""),[subtype,setSubtype]=useState("ip"),[port,setPort]=useState("22"),[items,setItems]=useState("");
  function request(){
    const payload:any={operation,name};
    if(operation==="set"){
      if(kind==="network-object"){payload.type=subtype;payload.value=value;}
      else if(kind==="service-object"){payload.type=subtype;payload.port=Number(port);}
      else if(kind==="permission-object")payload.permissions=items.split(",").map(x=>x.trim()).filter(Boolean);
      else payload.members=items.split(",").map(x=>x.trim()).filter(Boolean);
    }
    return {change_type:kind,payload};
  }
  return <div><div className="card"><h3>Guided Object / Group</h3><div className="toolbar"><select value={kind} onChange={e=>{setKind(e.target.value);setSubtype(e.target.value==="service-object"?"tcp":"ip")}}><option value="network-object">Network Object</option><option value="network-group">Network Group</option><option value="service-object">Service Object</option><option value="service-group">Service Group</option><option value="permission-object">Permission Object</option><option value="permission-group">Permission Group</option></select><select value={operation} onChange={e=>setOperation(e.target.value)}><option value="set">Create / edit</option><option value="delete">Delete</option></select><input value={name} onChange={e=>setName(e.target.value)} placeholder="Name"/>{operation==="set"&&kind==="network-object"&&<><input value={subtype} onChange={e=>setSubtype(e.target.value)} placeholder="ip/fqdn/network/host"/><input value={value} onChange={e=>setValue(e.target.value)} placeholder="Value"/></>}{operation==="set"&&kind==="service-object"&&<><input value={subtype} onChange={e=>setSubtype(e.target.value)} placeholder="tcp/udp/fixed-tcp"/><input value={port} onChange={e=>setPort(e.target.value)} placeholder="Port"/></>}{operation==="set"&&!(["network-object","service-object"] as string[]).includes(kind)&&<input value={items} onChange={e=>setItems(e.target.value)} placeholder={kind==="permission-object"?"Permissions, comma-separated":"Members, comma-separated"}/>}</div></div><GuidedApplyPanel key={JSON.stringify([kind,operation,name,value,subtype,port,items])} title="Object / Group Change Plan" build={request}/></div>;
}

function GuidedPolicySettingsPanel(){
  const [plane,setPlane]=useState("remote"),[operation,setOperation]=useState("set-enforcement"),[enabled,setEnabled]=useState(true);
  function request(){const payload:any={operation};if(operation==="set-enforcement")payload.enabled=enabled;return {change_type:plane+"-access-policy",payload};}
  return <div><div className="card"><h3>Access Policy Settings</h3><div className="muted">Enable/disable enforcement or reset policy mode and all rules through the same Core policy functions as CLI.</div><div className="toolbar"><select value={plane} onChange={e=>setPlane(e.target.value)}><option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option></select><select value={operation} onChange={e=>setOperation(e.target.value)}><option value="set-enforcement">Set enforcement</option><option value="reset">Reset policy + rules</option></select>{operation==="set-enforcement"&&<label><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> Enforcement enabled</label>}</div></div><GuidedApplyPanel key={JSON.stringify([plane,operation,enabled])} title="Access Policy Change Plan" build={request}/></div>;
}

function TemporaryAccessPanel(){
  const [plane,setPlane]=useState("remote"),[rule,setRule]=useState(""),[operation,setOperation]=useState("set"),[expiresAt,setExpiresAt]=useState("");
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[message,setMessage]=useState(""),[error,setError]=useState("");
  function resetChangePlan(){setPreview(null);setConfirmation("");setMessage("")}
  async function doPreview(){
    setError("");setMessage("");resetChangePlan();
    try{
      const body:any={plane,rule,operation};
      if(operation==="set")body.expires_at=expiresAt;
      const result=await api("/api/v1/temporary-access/preview",{method:"POST",body:JSON.stringify(body)});
      setPreview(result);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doApply(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/temporary-access/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});
      setMessage("Temporary Access applied at revision "+result.revision);setPreview(null);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  return <div className="card">
    <h3>Temporary Access</h3>
    <div className="muted">Set, change, or clear server-authoritative expiry on an existing WHITELIST grant.</div>
    {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
    <div className="toolbar">
      <select value={plane} onChange={e=>{resetChangePlan();setPlane(e.target.value)}}><option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option></select>
      <input value={rule} onChange={e=>{resetChangePlan();setRule(e.target.value)}} placeholder="Rule name"/>
      <select value={operation} onChange={e=>{resetChangePlan();setOperation(e.target.value)}}><option value="set">Set / change expiry</option><option value="clear">Clear expiry</option></select>
      {operation==="set"&&<input value={expiresAt} onChange={e=>{resetChangePlan();setExpiresAt(e.target.value)}} placeholder="2030-01-01T00:00:00Z"/>}
      <button className="primary" onClick={doPreview} disabled={!rule||operation==="set"&&!expiresAt}>Preview</button>
    </div>
    {preview&&<div className="card">
      <div><strong>Current:</strong> {preview.current_expires_at||"none"}</div>
      <div><strong>Desired:</strong> {preview.desired_expires_at||"none"}</div>
      <div><strong>Valid until:</strong> {preview.valid_until}</div>
      <BlastRadiusView preview={preview}/>
      <label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label>
      <button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply Temporary Access</button>
    </div>}
  </div>;
}

function PolicySafetyPanel({operator}:{operator:any}){
  const [plane,setPlane]=useState("remote"),[source,setSource]=useState(""),[destination,setDestination]=useState(""),[selector,setSelector]=useState(""),[path,setPath]=useState("");
  const [trace,setTrace]=useState<any>(null),[graph,setGraph]=useState<any>(null),[tests,setTests]=useState<any[]>([]),[runResult,setRunResult]=useState<any>(null);
  const [selected,setSelected]=useState(""),[testName,setTestName]=useState(""),[expected,setExpected]=useState("ALLOW"),[required,setRequired]=useState(true),[enabled,setEnabled]=useState(true);
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[message,setMessage]=useState(""),[error,setError]=useState("");
  function invalidateTestPreview(){setPreview(null);setConfirmation("");setMessage("")}
  useEffect(()=>{invalidateTestPreview()},[plane,source,destination,selector,path,testName,expected,required,enabled]);

  async function loadTests(){
    try{const result=await api("/api/v1/policy-tests");setTests(result.items||[])}
    catch(e:any){setError(e.message||String(e))}
  }
  useEffect(()=>{loadTests()},[]);

  function flow(){
    const body:any={plane,source,destination};
    if(plane==="ai"){body.permission=selector;if(path)body.path=path}
    else body.service=selector;
    return body;
  }
  async function simulate(){
    setError("");setTrace(null);
    try{setTrace(await api("/api/v1/policy/trace",{method:"POST",body:JSON.stringify(flow())}))}
    catch(e:any){setError(e.message||String(e))}
  }
  async function loadGraph(){
    setError("");setGraph(null);
    try{setGraph(await api("/api/v1/policy/graph?plane="+encodeURIComponent(plane)))}
    catch(e:any){setError(e.message||String(e))}
  }
  async function runSaved(){
    setError("");setRunResult(null);
    try{setRunResult(await api("/api/v1/policy-tests/run",{method:"POST",body:JSON.stringify({required_only:false})}))}
    catch(e:any){setError(e.message||String(e))}
  }
  function choose(value:string){
    setSelected(value);setPreview(null);setConfirmation("");setMessage("");
    if(!value){setTestName("");setExpected("ALLOW");setRequired(true);setEnabled(true);return}
    const item=tests.find((x:any)=>x.id===value);
    if(!item)return;
    setTestName(item.name||"");setPlane(item.plane||"remote");setSource(item.source||"");setDestination(item.destination||"");
    setSelector(item.plane==="ai"?(item.permission||""):(item.service||""));setPath(item.path||"");
    setExpected(item.expected||"ALLOW");setRequired(!!item.required);setEnabled(!!item.enabled);
  }
  async function previewSave(){
    setError("");setMessage("");
    try{
      const definition:any={name:testName,...flow(),expected,required,enabled};
      const result=await api("/api/v1/policy-tests/preview",{method:"POST",body:JSON.stringify({operation:"set",definition})});
      setPreview(result);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function previewDelete(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/policy-tests/preview",{method:"POST",body:JSON.stringify({operation:"delete",definition:{name:testName}})});
      setPreview(result);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function applyChange(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/policy-tests/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});
      setMessage("Policy Regression Test applied at revision "+result.revision);setPreview(null);setConfirmation("");setSelected("");setTestName("");await loadTests();
    }catch(e:any){setError(e.message||String(e))}
  }
  const ready=source&&destination&&selector;
  const requiredConfirmation=preview?.confirmation_class||"";
  return <>
    <div className="card">
      <h3>Policy Simulator / Decision Trace</h3>
      <div className="muted">Uses the same Core evaluator as CLI/runtime policy tests. A simulated ALLOW does not imply target reachability.</div>
      {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
      <div className="toolbar">
        <select value={plane} onChange={e=>{setPlane(e.target.value);setSelector("");setPath("")}}><option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option></select>
        <input value={source} onChange={e=>setSource(e.target.value)} placeholder={plane==="ai"?"AI Identity":"Source object/group"}/>
        <input value={destination} onChange={e=>setDestination(e.target.value)} placeholder="Destination"/>
        <input value={selector} onChange={e=>setSelector(e.target.value)} placeholder={plane==="ai"?"Permission object/group":"Service object/group"}/>
        {plane==="ai"&&<input value={path} onChange={e=>setPath(e.target.value)} placeholder="Optional path"/>}
        <button className="primary" onClick={simulate} disabled={!ready}>Simulate</button>
      </div>
      {trace&&<pre className="plan">{JSON.stringify(trace,null,2)}</pre>}
    </div>
    <div className="card">
      <h3>Effective Access Graph</h3>
      <div className="muted">Bounded policy/inventory graph from Core state and the canonical evaluator. It does not scan or infer network topology.</div>
      <div className="toolbar"><button className="secondary" onClick={loadGraph}>Refresh {plane} graph</button></div>
      {graph&&<>
        <div className="grid">
          <Metric label="Nodes" value={graph.limits?.node_count||0}/>
          <Metric label="Edges" value={graph.limits?.edge_count||0}/>
          <Metric label="Modeled flows" value={graph.limits?.path_count||0}/>
          <Metric label="Truncated" value={graph.limits?.truncated?"YES":"NO"}/>
        </div>
        <Table items={(graph.paths||[]).map((x:any)=>({source:x.input?.source,destination:x.input?.destination,selector:x.input?.service||x.input?.permission,rules:(x.rules||[]).join(","),decision:x.decision,status:x.status}))}/>
        {(graph.unknowns||[]).length>0&&<div className="warning-box">Unknown / not deterministically modeled: {(graph.unknowns||[]).slice(0,10).join(" · ")}</div>}
      </>}
    </div>
    <div className="card">
      <h3>Saved Policy Regression Tests</h3>
      <div className="muted">Required enabled tests are re-run against proposed security-relevant policy changes before Apply. A failure blocks mutation.</div>
      <div className="toolbar">
        <button className="secondary" onClick={runSaved}>Run Saved Tests</button>
        <select value={selected} onChange={e=>choose(e.target.value)}>
          <option value="">New test</option>
          {tests.map((x:any)=><option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </div>
      {runResult&&<pre className="plan">{JSON.stringify(runResult,null,2)}</pre>}
      <Table items={tests.map((x:any)=>({name:x.name,plane:x.plane,expected:x.expected,required:x.required,enabled:x.enabled}))}/>
      {operator.role!=="Read Only"&&<>
        <div className="toolbar">
          <input value={testName} onChange={e=>{invalidateTestPreview();setTestName(e.target.value)}} placeholder="Test name"/>
          <select value={expected} onChange={e=>{invalidateTestPreview();setExpected(e.target.value)}}><option value="ALLOW">Expect ALLOW</option><option value="DENY">Expect DENY</option></select>
          <label><input type="checkbox" checked={required} onChange={e=>{invalidateTestPreview();setRequired(e.target.checked)}}/> Required</label>
          <label><input type="checkbox" checked={enabled} onChange={e=>{invalidateTestPreview();setEnabled(e.target.checked)}}/> Enabled</label>
          <button className="primary" onClick={previewSave} disabled={!testName||!ready}>Preview Save</button>
          <button className="danger" onClick={previewDelete} disabled={!selected}>Preview Delete</button>
        </div>
      </>}
      {preview&&<div className="warning-box">
        <pre className="plan">{JSON.stringify({preview:preview.preview,impact:preview.impact,valid_until:preview.valid_until},null,2)}</pre>
        <label className="apply-label">Type {requiredConfirmation} to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder={requiredConfirmation}/></label>
        <button className="danger" onClick={applyChange} disabled={confirmation!==requiredConfirmation}>Apply Saved Test Change</button>
      </div>}
    </div>
  </>;
}


function LinkFoundationAdministration({
  operator, onNavigate
}:{
  operator:any,
  onNavigate?:(id:string,groupId?:string)=>void
}){
  const admin=operator.role==="Admin";
  const tasks=createLinkFoundationAdministrationTasks(operator.role);
  function openTask(task:AdministrationHubTask){
    // Link Core retains routing, session security and privileged settings authority.
    switch(task.target?.kind==="action"?task.target.actionId:""){
      case "link.users":
        if(admin)onNavigate?.("users","administration");
        break;
      case "link.audit":onNavigate?.("audit","observability");break;
      case "link.retention":onNavigate?.("audit","observability");break;
      case "link.health":onNavigate?.("health","observability");break;
      case "link.backup":
        // Navigate only to the existing native Core validator. Create and
        // restore remain separately restricted and confirmed by Link Core.
        const backupAdvanced=document.getElementById("drlink-core-advanced") as HTMLDetailsElement|null;
        if(backupAdvanced)backupAdvanced.open=true;
        document.getElementById("drlink-backup-status")?.scrollIntoView({block:"start"});
        break;
      case "link.certificate":
        // The shared read-only certificate shortcut reveals the distinct
        // product-owned Core panel; it is NOT Web HTTPS listener management.
        const advanced=document.getElementById("drlink-core-advanced") as HTMLDetailsElement|null;
        if(advanced)advanced.open=true;
        document.getElementById("drlink-certificate-status")?.scrollIntoView({block:"start"});
        break;
    }
  }
  return <section data-testid="drlink-foundation-administration">
    <AdministrationHub productId="link" tasks={tasks} showUnavailable onOpen={openTask}/>
  </section>;
}

function SystemPanel({data,operator}:{data:any,operator:any}){
  const [backupPath,setBackupPath]=useState("/var/lib/drlink/backups/");
  const [renewConfirmation,setRenewConfirmation]=useState(""),[restoreConfirmation,setRestoreConfirmation]=useState("");
  const [certMode,setCertMode]=useState(String(data.certificate?.mode||"AUTO_ACME").toLowerCase().replaceAll("_","-"));
  const [certHostname,setCertHostname]=useState(data.certificate?.hostname||""),[certEmail,setCertEmail]=useState(data.certificate?.contact_email||""),[acmeEnv,setAcmeEnv]=useState(String(data.certificate?.acme_environment||"PRODUCTION").toLowerCase());
  const [certConfigConfirmation,setCertConfigConfirmation]=useState(""),[issueConfirmation,setIssueConfirmation]=useState(""),[importConfirmation,setImportConfirmation]=useState("");
  const [certPem,setCertPem]=useState(""),[keyPem,setKeyPem]=useState(""),[chainPem,setChainPem]=useState("");
  const [productUpdateConfirmation,setProductUpdateConfirmation]=useState(""),[engineUpdateConfirmation,setEngineUpdateConfirmation]=useState("");
  const [preflight,setPreflight]=useState<any>(null),[renewal,setRenewal]=useState<any>(null),[certAction,setCertAction]=useState<any>(null),[updateResult,setUpdateResult]=useState<any>(null),[validation,setValidation]=useState<any>(null),[backupArtifact,setBackupArtifact]=useState<any>(null),[supportArtifact,setSupportArtifact]=useState<any>(null),[error,setError]=useState("");
  async function runPreflight(){setError("");try{setPreflight(await api("/api/v1/system/certificate/preflight",{method:"POST",body:"{}"}))}catch(e:any){setError(e.message||String(e))}}
  async function configureCertificate(){setError("");setCertAction(null);try{setCertAction(await api("/api/v1/system/certificate/configure",{method:"POST",body:JSON.stringify({mode:certMode,hostname:certHostname,contact_email:certEmail,acme_environment:acmeEnv,confirmation:certConfigConfirmation})}));setCertConfigConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function issueCertificate(){setError("");setCertAction(null);try{setCertAction(await api("/api/v1/system/certificate/issue",{method:"POST",body:JSON.stringify({confirmation:issueConfirmation})}));setIssueConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function importCertificate(){setError("");setCertAction(null);try{setCertAction(await api("/api/v1/system/certificate/import",{method:"POST",body:JSON.stringify({cert_pem:certPem,key_pem:keyPem,chain_pem:chainPem,confirmation:importConfirmation})}));setImportConfirmation("");setCertPem("");setKeyPem("");setChainPem("")}catch(e:any){setError(e.message||String(e))}}
  async function renewCertificate(){setError("");setRenewal(null);try{setRenewal(await api("/api/v1/system/certificate/renew",{method:"POST",body:JSON.stringify({confirmation:renewConfirmation})}));setRenewConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function checkUpdate(target:string){setError("");setUpdateResult(null);try{setUpdateResult(await api("/api/v1/system/update/check",{method:"POST",body:JSON.stringify({target})}))}catch(e:any){setError(e.message||String(e))}}
  async function updateProduct(){setError("");setUpdateResult(null);try{setUpdateResult(await api("/api/v1/system/update/product",{method:"POST",body:JSON.stringify({confirmation:productUpdateConfirmation})}));setProductUpdateConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function refreshProductUpdate(){if(!updateResult?.job_id)return;setError("");try{setUpdateResult(await api("/api/v1/system/update/product/status?job_id="+encodeURIComponent(updateResult.job_id)))}catch(e:any){setError(e.message||String(e))}}
  async function updateEngine(){setError("");setUpdateResult(null);try{setUpdateResult(await api("/api/v1/system/update/engine",{method:"POST",body:JSON.stringify({confirmation:engineUpdateConfirmation})}));setEngineUpdateConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function validateBackup(){setError("");setRestoreConfirmation("");try{setValidation(await api("/api/v1/system/backup/validate",{method:"POST",body:JSON.stringify({path:backupPath})}))}catch(e:any){setValidation(null);setError(e.message||String(e))}}
  async function restoreBackup(){setError("");try{await api("/api/v1/system/restore",{method:"POST",body:JSON.stringify({path:backupPath,confirmation:restoreConfirmation})});window.location.reload()}catch(e:any){setError(e.message||String(e))}}
  async function createBackup(){setError("");setBackupArtifact(null);try{setBackupArtifact(await api("/api/v1/system/backup/create",{method:"POST",body:"{}"}))}catch(e:any){setError(e.message||String(e))}}
  async function createSupportBundle(){setError("");setSupportArtifact(null);try{setSupportArtifact(await api("/api/v1/system/support-bundle",{method:"POST",body:"{}"}))}catch(e:any){setError(e.message||String(e))}}
  const identity=data.identity||{},certificate=data.certificate||{},backup=data.backup||{},support=data.support_bundle||{},update=data.update||{};
  return <>
    {error&&<div className="error">{error}</div>}
    <div className="grid">
      <Metric label="Data Relay Link" value={identity.display_identity||identity.project_version}/>
      <Metric label="Relay Engine" value={identity.relay_engine_version}/>
      <Metric label="Channel" value={identity.channel}/>
      <Metric label="Backup tools" value={backupToolReadiness(backup)}/>
    </div>
    <p className="muted" role="note">Backup tools reflect Core command availability only.
      This status does not verify an actual protected archive or a successful restore.
      Missing tool evidence remains UNKNOWN; any restore still needs a separately approved
      Core-authoritative check.</p>
    <div className="card">
      <h3>Release Provenance</h3>
      <Table items={[{source_ref:identity.source_ref,source_head:identity.source_head,bundle_sha256:identity.bundle_sha256||"not recorded"}]}/>
    </div>
    <div className="card">
      <h3>Update</h3>
      <div className="muted">Checks use the canonical read-only updater paths. Product apply is queued to a fixed privileged one-shot: Web is stopped before Core mutation and restarts only after an exact-source Web package passes SHA256 and Core/Web identity coupling.</div>
      <div className="toolbar">
        <button className="secondary" onClick={()=>checkUpdate("product")} disabled={!update.product_check_available}>Check Product Update</button>
        <button className="secondary" onClick={()=>checkUpdate("engine")} disabled={!update.engine_check_available}>Check Relay Engine Update</button>
      </div>
      {operator.role==="Admin"&&update.product_apply_via_web&&<div className="toolbar"><input value={productUpdateConfirmation} onChange={e=>setProductUpdateConfirmation(e.target.value)} placeholder="Type UPDATE PRODUCT"/><button className="danger" onClick={updateProduct} disabled={productUpdateConfirmation!=="UPDATE PRODUCT"}>Update Data Relay Link</button></div>}
      {operator.role==="Admin"&&update.engine_apply_via_web&&<div className="toolbar"><input value={engineUpdateConfirmation} onChange={e=>setEngineUpdateConfirmation(e.target.value)} placeholder="Type UPDATE ENGINE"/><button className="danger" onClick={updateEngine} disabled={engineUpdateConfirmation!=="UPDATE ENGINE"}>Update Relay Engine</button></div>}
      <div className="muted">Product update apply via Web: {update.product_apply_via_web?"enabled — exact-build queued mode":"unavailable; use local CLI recovery/update"}</div>
      {updateResult?.job_id&&<button className="secondary" onClick={refreshProductUpdate}>Refresh Product Update Status</button>}
      {updateResult&&<pre className="plan">{JSON.stringify(updateResult,null,2)}</pre>}
    </div>
    <div className="card" id="drlink-certificate-status">
      <h3>Certificate Status</h3>
      <Table items={[{mode:certificate.mode,hostname:certificate.hostname,certificate:certificate.certificate,issuer:certificate.issuer,expires:certificate.expires,days_remaining:certificate.days_remaining,auto_renewal:certificate.auto_renewal}]}/>
      <button className="secondary" onClick={runPreflight}>Run Certificate Preflight</button>
      {operator.role==="Admin"&&<>
        <h4>Certificate Intent</h4>
        <div className="toolbar">
          <select value={certMode} onChange={e=>setCertMode(e.target.value)}><option value="auto-acme">AUTO_ACME</option><option value="user-certificate">USER_CERTIFICATE</option><option value="private-ca">PRIVATE_CA</option></select>
          <input value={certHostname} onChange={e=>setCertHostname(e.target.value)} placeholder="mcp.example.com"/>
          <input value={certEmail} onChange={e=>setCertEmail(e.target.value)} placeholder="ACME contact email"/>
          <select value={acmeEnv} onChange={e=>setAcmeEnv(e.target.value)}><option value="production">Production</option><option value="staging">Staging</option></select>
        </div>
        <div className="toolbar"><input value={certConfigConfirmation} onChange={e=>setCertConfigConfirmation(e.target.value)} placeholder="Type APPLY"/><button className="danger" onClick={configureCertificate} disabled={certConfigConfirmation!=="APPLY"}>Apply Certificate Settings</button></div>
        {certMode!=="user-certificate"&&<div className="toolbar"><input value={issueConfirmation} onChange={e=>setIssueConfirmation(e.target.value)} placeholder="Type ISSUE"/><button className="danger" onClick={issueCertificate} disabled={issueConfirmation!=="ISSUE"}>Issue & Activate Certificate</button></div>}
        {certMode==="user-certificate"&&<div className="card">
          <div className="muted">PEM material is sent only in this request, staged under a private Core-owned directory, imported by the canonical TLS engine, then deleted.</div>
          <textarea className="draft-editor" value={certPem} onChange={e=>setCertPem(e.target.value)} placeholder="Certificate PEM"/>
          <textarea className="draft-editor" value={keyPem} onChange={e=>setKeyPem(e.target.value)} placeholder="Private key PEM"/>
          <textarea className="draft-editor" value={chainPem} onChange={e=>setChainPem(e.target.value)} placeholder="Optional chain PEM"/>
          <div className="toolbar"><input value={importConfirmation} onChange={e=>setImportConfirmation(e.target.value)} placeholder="Type IMPORT"/><button className="danger" onClick={importCertificate} disabled={importConfirmation!=="IMPORT"||!certPem||!keyPem}>Import & Activate Certificate</button></div>
        </div>}
        <div className="toolbar"><input value={renewConfirmation} onChange={e=>setRenewConfirmation(e.target.value)} placeholder="Type RENEW"/><button className="danger" onClick={renewCertificate} disabled={renewConfirmation!=="RENEW"}>Renew Certificate If Due</button></div>
      </>}
      {preflight&&<pre className="plan">{JSON.stringify(preflight,null,2)}</pre>}
      {certAction&&<pre className="plan">{JSON.stringify(certAction,null,2)}</pre>}
      {renewal&&<pre className="plan">{JSON.stringify(renewal,null,2)}</pre>}
    </div>
    <div className="card" id="drlink-backup-status">
      <h3>Backup</h3>
      <div className="muted">Backup archives are protected server-side artifacts containing secrets. Web never downloads or displays their contents.</div>
      {operator.role==="Admin"&&<button className="primary" onClick={createBackup} disabled={!backup.create_available}>Create Protected Backup</button>}
      {backupArtifact&&<pre className="plan">{JSON.stringify(backupArtifact,null,2)}</pre>}
      <h4>Validate Existing Backup</h4>
      <div className="muted">Validation is read-only and uses the same disaster-recovery validator as CLI restore preflight.</div>
      <div className="toolbar"><input value={backupPath} onChange={e=>{setBackupPath(e.target.value);setValidation(null);setRestoreConfirmation("")}} placeholder="/var/lib/drlink/backups/server-backup-....tar.gz"/><button className="secondary" onClick={validateBackup} disabled={!backupPath}>Validate Backup</button></div>
      {validation&&<pre className="plan">{JSON.stringify(validation,null,2)}</pre>}
      {operator.role==="Admin"&&validation?.valid&&<div className="warning-box"><strong>Restore replaces persistent Data Relay Link state.</strong><div>Canonical restore revalidates the archive, creates a pre-restore snapshot, rolls back on failure when possible, and revokes all Web sessions after success.</div><div className="toolbar"><input value={restoreConfirmation} onChange={e=>setRestoreConfirmation(e.target.value)} placeholder="Type RESTORE"/><button className="danger" onClick={restoreBackup} disabled={restoreConfirmation!=="RESTORE"}>Restore Validated Backup</button></div></div>}
    </div>
    <div className="card">
      <h3>Support Bundle</h3>
      <div className="muted">Creates a sanitized diagnostic archive in {support.directory||"/var/lib/drlink/support-bundles"}. Archive contents are not exposed through Web.</div>
      {operator.role!=="Read Only"&&<button className="secondary" onClick={createSupportBundle} disabled={!support.create_available}>Create Sanitized Support Bundle</button>}
      {supportArtifact&&<pre className="plan">{JSON.stringify(supportArtifact,null,2)}</pre>}
    </div>
  </>;
}

function AccessOperations({operator,onNavigate,context}:{operator:any,onNavigate?:(id:string,groupId?:string,context?:any)=>void,context?:any}){
  const initialPlane=["remote","internet","ai"].includes(String(context?.plane))?String(context.plane):"remote";
  const [plane,setPlane]=useState(initialPlane),[source,setSource]=useState(context?.source||""),[destination,setDestination]=useState(context?.destination||""),[selector,setSelector]=useState(context?.selector||"");
  const [diagnosisEvidence,setDiagnosisEvidence]=useState<{key:string,value:any}|null>(null);
  const [liveEvidence,setLiveEvidence]=useState<{key:string,value:any}|null>(null);
  const [diagnosisBusy,setDiagnosisBusy]=useState(false),[liveBusy,setLiveBusy]=useState(false),[error,setError]=useState("");
  const [liveResource,setLiveResource]=useState("");
  const [cutoffEvidence,setCutoffEvidence]=useState<{key:string,value:any}|null>(null);
  const cutoffGeneration=useRef(0);
  const diagnosisGeneration=useRef(0),liveGeneration=useRef(0);
  const currentDiagnosisKey=coreFlowKey(plane,source,destination,selector);
  const currentLiveKey=JSON.stringify([plane,liveResource.trim()]);
  const matchingDiagnosis=visibleCoreEvidence(diagnosisEvidence,currentDiagnosisKey);
  const matchingLive=visibleCoreEvidence(liveEvidence,currentLiveKey);
  const activeCutoffs=visibleCoreEvidence(cutoffEvidence,plane);
  const diagnosisReady=!!(source.trim()&&destination.trim()&&selector.trim());
  useEffect(()=>()=>{diagnosisGeneration.current+=1;liveGeneration.current+=1},[]);
  const [scopeKind,setScopeKind]=useState("plane"),[scopeRef,setScopeRef]=useState(""),[cutoffOperation,setCutoffOperation]=useState("apply"),[reason,setReason]=useState("");
  const [cutoffPreview,setCutoffPreview]=useState<{key:string,value:any}|null>(null),[cutoffConfirm,setCutoffConfirm]=useState(""),[cutoffMessage,setCutoffMessage]=useState("");
  const [cutoffBusy,setCutoffBusy]=useState(false);
  const cutoffPlanGeneration=useRef(0);
  const currentCutoffKey=coreCutoffKey(plane,scopeKind,scopeRef,cutoffOperation,reason);
  const currentCutoffPreview=visibleCoreEvidence(cutoffPreview,currentCutoffKey);
  useEffect(()=>()=>{cutoffPlanGeneration.current+=1},[]);
  const scopeOptions:Record<string,string[]>={remote:["plane","remote-service"],internet:["plane","managed-host"],ai:["plane","ai-identity"]};
  function invalidateCutoff(){cutoffPlanGeneration.current+=1;setCutoffPreview(null);setCutoffConfirm("");setCutoffMessage("")}
  function changeDiagnosisFlow(field:"source"|"destination"|"selector",value:string){
    if(field==="source")setSource(value);
    else if(field==="destination")setDestination(value);
    else setSelector(value);
    diagnosisGeneration.current+=1;setDiagnosisEvidence(null);setDiagnosisBusy(false);setError("");
  }

  async function loadCutoffs(){
    const token=++cutoffGeneration.current;
    setCutoffEvidence(null);
    try{
      const result=await api("/api/v1/emergency-cutoffs?plane="+encodeURIComponent(plane));
      if(cutoffGeneration.current!==token)return;
      if(!Array.isArray(result?.items))throw new Error("Core cutoff inventory response incomplete");
      setCutoffEvidence({key:plane,value:result});
    }catch(e:any){if(cutoffGeneration.current===token)setError("Core cutoff state unavailable: "+String(e.message||e))}
  }
  useEffect(()=>{void loadCutoffs();return()=>{cutoffGeneration.current+=1}},[plane]);
  function changePlane(value:string){
    if(plane===value||cutoffBusy)return;
    diagnosisGeneration.current+=1;liveGeneration.current+=1;
    setPlane(value);setSelector("");setDiagnosisEvidence(null);setLiveEvidence(null);
    setDiagnosisBusy(false);setLiveBusy(false);setLiveResource("");
    setScopeKind("plane");setScopeRef("");invalidateCutoff();
  }
  async function runDiagnosis(){
    if(!diagnosisReady||diagnosisBusy)return;
    const token=++diagnosisGeneration.current;
    const requestKey=currentDiagnosisKey;
    setError("");setDiagnosisEvidence(null);setDiagnosisBusy(true);
    try{
      const body:any={plane,source:source.trim(),destination:destination.trim()};
      if(plane==="ai")body.permission=selector.trim();else body.service=selector.trim();
      const result=await api("/api/v1/diagnose",{method:"POST",body:JSON.stringify(body)});
      if(diagnosisGeneration.current!==token)return;
      setDiagnosisEvidence({key:requestKey,value:result});
    }catch(e:any){if(diagnosisGeneration.current===token)setError(e.message||String(e))}
    finally{if(diagnosisGeneration.current===token)setDiagnosisBusy(false)}
  }
  async function loadLive(){
    if(liveBusy)return;
    const token=++liveGeneration.current;
    const requestKey=currentLiveKey;
    setError("");setLiveEvidence(null);setLiveBusy(true);
    try{
      const q=new URLSearchParams({plane,limit:"50"});
      if(liveResource.trim())q.set("resource",liveResource.trim());
      const result=await api("/api/v1/live-access?"+q.toString());
      if(liveGeneration.current!==token)return;
      setLiveEvidence({key:requestKey,value:result});
    }catch(e:any){if(liveGeneration.current===token)setError(e.message||String(e))}
    finally{if(liveGeneration.current===token)setLiveBusy(false)}
  }
  async function previewCutoff(){
    if(cutoffBusy)return;
    const token=++cutoffPlanGeneration.current;
    const requestKey=currentCutoffKey;
    setError("");setCutoffMessage("");setCutoffConfirm("");setCutoffPreview(null);setCutoffBusy(true);
    try{
      const body:any={plane,scope_kind:scopeKind,operation:cutoffOperation,reason:reason.trim()};
      if(scopeKind!=="plane")body.scope_ref=scopeRef.trim();
      const result=await api("/api/v1/emergency-cutoff/preview",{method:"POST",body:JSON.stringify(body)});
      if(cutoffPlanGeneration.current!==token)return;
      if(!result?.change_plan_id)throw new Error("Core cutoff preview returned no Change Plan ID");
      setCutoffPreview({key:requestKey,value:result});
    }catch(e:any){if(cutoffPlanGeneration.current===token){setCutoffPreview(null);setError(e.message||String(e))}}
    finally{if(cutoffPlanGeneration.current===token)setCutoffBusy(false)}
  }
  async function applyCutoff(){
    if(cutoffBusy||cutoffConfirm!=="CONFIRM CUTOFF"||!currentCutoffPreview?.change_plan_id)return;
    const token=++cutoffPlanGeneration.current;
    setError("");setCutoffBusy(true);
    try{
      const result=await api("/api/v1/emergency-cutoff/apply",{method:"POST",body:JSON.stringify({
        operation:cutoffOperation,
        change_plan_id:currentCutoffPreview.change_plan_id,
        confirmation:cutoffConfirm,
      })});
      if(cutoffPlanGeneration.current!==token)return;
      setCutoffMessage((cutoffOperation==="clear"?"Cutoff cleared":"Cutoff applied")+" at revision "+String(result.revision??"UNKNOWN")+"; existing sessions terminated: "+String(result.active_sessions_terminated??"UNKNOWN"));
      setCutoffPreview(null);setCutoffConfirm("");
      await loadLive();
      await loadCutoffs();
    }catch(e:any){if(cutoffPlanGeneration.current===token)setError(e.message||String(e))}
    finally{if(cutoffPlanGeneration.current===token)setCutoffBusy(false)}
  }
  const layers=(matchingDiagnosis?.layers||[]).map((x:any)=>({layer:x.layer,status:x.status,summary:x.summary}));
  const planeLabel=plane==="remote"?"Remote Access":plane==="internet"?"Internet Access":"AI Access";
  const flowContext=connectionReviewContext(plane as AccessPlane,source,destination,selector);
  return <div className="dr-access-workspace">
    {error&&<div className="error">{error}</div>}
    {context?.originId&&<section className="dr-uxb-context card" role="note"><strong>Investigating {context.originType||"resource"}: {context.originId}</strong><p>Core resource names are not automatically Network/Service Objects. Select the exact source, destination and selector before interpreting any Core access decision.</p><button className="secondary" onClick={()=>onNavigate?.("audit","activity",context)}>Review matching Activity log →</button></section>}
    <section className="dr-page-intro"><div><p className="dr-eyebrow">Access</p><h2>Access Workspace</h2><p className="muted">Understand who can reach what, why the decision is made, and what is active now.</p></div><div className="dr-page-actions"><button className="secondary" onClick={()=>onNavigate?.("policies","access",flowContext)}>Policies</button>{operator.role!=="Read Only"&&<button className="primary" onClick={()=>onNavigate?.("drafts","access",flowContext)}>Draft change</button>}</div></section>
    <div className="dr-access-tabs" role="tablist" aria-label="Access plane">{[["remote","Remote Access"],["internet","Internet Access"],["ai","AI Access"]].map(([value,label])=><button key={value} role="tab" aria-selected={plane===value} className={plane===value?"active":""} disabled={cutoffBusy} onClick={()=>changePlane(value)}>{label}</button>)}</div>
    <section className="card dr-access-map-card">
      <div className="dr-section-head"><div><p className="dr-eyebrow">Relationship</p><h3>{planeLabel}</h3></div><button className="dr-text-action" onClick={()=>onNavigate?.("policies","access")}>View policies →</button></div>
      <div className="dr-access-map" aria-label={planeLabel+" relationship preview"}>
        <div className="dr-access-node"><span>Source</span><strong>{source||((plane==="ai")?"AI identity":"Source object / group")}</strong><small>{source?"Selected input":"Enter a source below"}</small></div>
        <div className="dr-access-edge"><span>→</span><small>{selector||(plane==="ai"?"permission":"service")}</small></div>
        <div className="dr-access-node policy"><span>Decision</span><strong>{matchingDiagnosis?.overall||"Policy evaluation"}</strong><small>{matchingDiagnosis?.next_action||"Test against Core policy"}</small></div>
        <div className="dr-access-edge"><span>→</span><small>{planeLabel}</small></div>
        <div className="dr-access-node"><span>Destination</span><strong>{destination||"Destination object / group"}</strong><small>{matchingLive?.fidelity?"Live fidelity: "+matchingLive.fidelity:"Live evidence: UNKNOWN until refreshed"}</small></div>
      </div>
    </section>
    <AccessEvidenceExplorer api={api} plane={plane as AccessPlane} source={source} destination={destination} selector={selector}
      onSelect={flow=>{diagnosisGeneration.current+=1;setSource(flow.source);setDestination(flow.destination);setSelector(flow.selector);setDiagnosisEvidence(null);setDiagnosisBusy(false)}}
      onNavigate={(id,group,detail)=>onNavigate?.(id,group,detail??context)}/>
    <div className="card">
      <div className="dr-section-head"><div><p className="dr-eyebrow">Policy Simulator</p><h3>Connection Diagnosis</h3></div></div>
      <div className="muted">Side-effect-free Core correlation. No browser-triggered DNS or target probe is launched; missing evidence stays UNKNOWN.</div>
      <div className="toolbar">
        <input value={source} onChange={e=>changeDiagnosisFlow("source",e.target.value)} placeholder={plane==="ai"?"AI Identity / source":"Source Object / Group"}/>
        <input value={destination} onChange={e=>changeDiagnosisFlow("destination",e.target.value)} placeholder="Destination Object / Group"/>
        <input value={selector} onChange={e=>changeDiagnosisFlow("selector",e.target.value)} placeholder={plane==="ai"?"Permission Object / Group":"Service Object / Group"}/>
        <button className="primary" disabled={!diagnosisReady||diagnosisBusy} onClick={runDiagnosis}>{diagnosisBusy?"Checking Core…":"Diagnose"}</button>
      </div>
      {matchingDiagnosis&&<>
        <div className="grid"><Metric label="Overall" value={matchingDiagnosis.overall}/><Metric label="Network probe" value={matchingDiagnosis.network_probe_performed?"YES":"NO"}/></div>
        <Table items={layers}/>
        <div className="muted">Next action: {matchingDiagnosis.next_action}</div>
      </>}
      {!matchingDiagnosis&&!diagnosisBusy&&<p className="muted" role="status">Diagnosis: UNKNOWN until the current source, destination and selector have a fresh Core result.</p>}
    </div>
    <div className="card">
      <h3>Live Access Visibility</h3>
      <div className="muted">Bounded current-use evidence only. Remote Access remains UNKNOWN unless official FRP can prove exact lifecycle state.</div>
      <div className="toolbar">
        <input value={liveResource} onChange={e=>{liveGeneration.current+=1;setLiveResource(e.target.value);setLiveEvidence(null);setLiveBusy(false)}} placeholder="Optional resource/session/identity filter"/>
        <button className="secondary" disabled={liveBusy} onClick={loadLive}>{liveBusy?"Refreshing Core…":"Refresh "+plane+" live access"}</button>
      </div>
      {matchingLive&&<>
        <div className="grid"><Metric label="Fidelity" value={matchingLive.fidelity}/><Metric label="Active count" value={matchingLive.active_count??"UNKNOWN"}/><Metric label="Returned" value={(matchingLive.observations||[]).length}/></div>
        {matchingLive.reason&&<div className="warning-box">{matchingLive.reason}</div>}
        <Table items={matchingLive.observations||[]}/>
      </>}
      {!matchingLive&&!liveBusy&&<p className="muted" role="status">Live access: UNKNOWN until Core returns current evidence for this plane and optional filter.</p>}
    </div>
    <div className="card">
      <h3>Active Emergency Cutoffs</h3>
      <div className="muted">Authoritative active override state for the selected plane. Clearing a cutoff reveals the unchanged normal policy.</div>
      {activeCutoffs?<div className="grid"><Metric label="Active" value={activeCutoffs.count??"UNKNOWN"}/><Metric label="Returned" value={activeCutoffs.returned??"UNKNOWN"}/><Metric label="Truncated" value={typeof activeCutoffs.truncated==="boolean"?(activeCutoffs.truncated?"YES":"NO"):"UNKNOWN"}/></div>:
        <p className="muted" role="status">Cutoff evidence: UNKNOWN until Core returns current-plane override state.</p>}
      <Table items={activeCutoffs?.items||[]}/>
    </div>
    {operator.role==="Admin"&&<div className="card">
      <h3>Emergency New-Access Cutoff</h3>
      <div className="warning-box">This reversible override affects new authorization only. Existing sessions are not claimed to be terminated.</div>
      {cutoffMessage&&<div className="notice">{cutoffMessage}</div>}
      <div className="toolbar">
        <select value={cutoffOperation} disabled={cutoffBusy} onChange={e=>{invalidateCutoff();setCutoffOperation(e.target.value)}}><option value="apply">Apply cutoff</option><option value="clear">Clear cutoff</option></select>
        <select value={scopeKind} disabled={cutoffBusy} onChange={e=>{invalidateCutoff();setScopeKind(e.target.value);setScopeRef("")}}>{scopeOptions[plane].map(x=><option key={x} value={x}>{x}</option>)}</select>
        {scopeKind!=="plane"&&<input value={scopeRef} disabled={cutoffBusy} onChange={e=>{invalidateCutoff();setScopeRef(e.target.value)}} placeholder={scopeKind+" selector"}/>}
        {cutoffOperation==="apply"&&<input value={reason} disabled={cutoffBusy} onChange={e=>{invalidateCutoff();setReason(e.target.value)}} placeholder="Incident reason (optional)"/>}
        <button className="danger" disabled={cutoffBusy} onClick={previewCutoff}>{cutoffBusy?"Checking Core…":"Preview cutoff"}</button>
      </div>
      {currentCutoffPreview&&<>
        <pre className="plan">{JSON.stringify({scope_kind:currentCutoffPreview.scope_kind,scope_ref:currentCutoffPreview.scope_ref,scope_display:currentCutoffPreview.scope_display,currently_active:currentCutoffPreview.currently_active,desired_active:currentCutoffPreview.desired_active,impact:currentCutoffPreview.impact,active_sessions_terminated:currentCutoffPreview.active_sessions_terminated},null,2)}</pre>
        <label className="apply-label">Type CONFIRM CUTOFF<input value={cutoffConfirm} disabled={cutoffBusy} onChange={e=>setCutoffConfirm(e.target.value)} placeholder="CONFIRM CUTOFF"/></label>
        <button className="danger" onClick={applyCutoff} disabled={cutoffBusy||cutoffConfirm!=="CONFIRM CUTOFF"||!currentCutoffPreview?.change_plan_id}>{cutoffOperation==="clear"?"Clear Cutoff":"Apply Cutoff"}</button>
      </>}
    </div>}
  </div>;
}

function AuditExplorer({operator,context}:{operator:any,context?:any}){
  const [data,setData]=useState<any>(null),[retention,setRetention]=useState<any>(null),[error,setError]=useState(""),[message,setMessage]=useState(""),[exportResult,setExportResult]=useState<any>(null);
  const [auditState,setAuditState]=useState<"loading"|"ready"|"unknown"|"idle">("loading");
  const auditReadEpoch=useRef(0);
  const exportInFlight=useRef(false);
  const [exportBusy,setExportBusy]=useState(false),[exportError,setExportError]=useState("");
  const retentionReadEpoch=useRef(0);
  const [retentionState,setRetentionState]=useState<"loading"|"ready"|"unknown">("loading");
  const [retentionError,setRetentionError]=useState(""),[retentionWriteBusy,setRetentionWriteBusy]=useState(false);
  const [retentionConfirmation,setRetentionConfirmation]=useState("");
  const [auditPage,setAuditPage]=useState<MenuPagePosition>({cursor:"",history:[]});
  const [auditFilterKey,setAuditFilterKey]=useState<string|null>(null);
  const [start,setStart]=useState(""),[end,setEnd]=useState(""),[category,setCategory]=useState(""),[eventType,setEventType]=useState(""),[actor,setActor]=useState(""),[resource,setResource]=useState(String(context?.originId||"")),[result,setResult]=useState(""),[correlation,setCorrelation]=useState("");
  const [controlDays,setControlDays]=useState("365"),[accessDays,setAccessDays]=useState("90"),[maxEvents,setMaxEvents]=useState("500000");

  function filterParams(){
    const q=new URLSearchParams({limit:"50"});
    for(const [key,value] of [["start",start],["end",end],["category",category],["event_type",eventType],["actor",actor],["resource",resource],["result",result],["correlation_id",correlation]] as string[][]){if(value.trim())q.set(key,value.trim())}
    return q;
  }
  function exportFilters(){
    const out:any={};
    for(const [key,value] of [["start",start],["end",end],["category",category],["event_type",eventType],["actor",actor],["resource",resource],["result",result],["correlation",correlation]] as string[][]){if(value.trim())out[key]=value.trim()}
    return out;
  }
  async function load(position:MenuPagePosition={cursor:"",history:[]}){
    const epoch=++auditReadEpoch.current;
    setError("");setData(null);setAuditState("loading");
    const q=filterParams();
    const filterKey=q.toString();
    try{
      if(position.cursor)q.set("cursor",position.cursor);
      const page=requireObservedMenuPayload("audit",await api("/api/v1/audit?"+q.toString()));
      if(epoch!==auditReadEpoch.current)return;
      setData(page);setAuditPage(position);setAuditFilterKey(filterKey);setAuditState("ready");
    }catch(e:any){
      if(epoch!==auditReadEpoch.current)return;
      setData(null);setAuditState("unknown");setError(e.message||String(e));
    }
  }
  async function loadRetention(){
    const epoch=++retentionReadEpoch.current;
    setRetention(null);setRetentionState("loading");setRetentionError("");setRetentionConfirmation("");
    try{
      const value=requireObservedAuditRetention(await api("/api/v1/audit/retention"));
      if(epoch!==retentionReadEpoch.current)return;
      setRetention(value);
      setControlDays(String(value.config.control_days));
      setAccessDays(String(value.config.access_days));
      setMaxEvents(String(value.config.max_events));
      setRetentionState("ready");
    }catch(e:any){
      if(epoch!==retentionReadEpoch.current)return;
      setRetention(null);setRetentionState("unknown");
      setRetentionError(e.message||String(e));
    }
  }
  useEffect(()=>{load();loadRetention();return()=>{auditReadEpoch.current+=1;retentionReadEpoch.current+=1}},[]);
  async function exportAudit(){
    if(exportInFlight.current)return;
    exportInFlight.current=true;
    const selectedFilters=exportFilters();
    setExportResult(null);setExportError("");setMessage("");setExportBusy(true);
    try{
      const value=requireObservedAuditExport(await api("/api/v1/audit/export",{
        method:"POST",body:JSON.stringify({filters:selectedFilters})
      }),selectedFilters);
      setExportResult(value);
      setMessage("Core confirmed a server-side Audit Export: "+String(value.event_count)+" events. No Web download is available.");
    }catch(e:any){
      setExportError("Core Audit Export status UNKNOWN. "+(e.message||String(e)));
    }finally{
      exportInFlight.current=false;setExportBusy(false);
    }
  }
  async function configureRetention(){
    if(retentionState!=="ready"||retentionWriteBusy)return;
    setError("");setMessage("");setRetentionWriteBusy(true);
    try{
      await api("/api/v1/audit/retention/configure",{method:"POST",body:JSON.stringify({control_days:Number(controlDays),access_days:Number(accessDays),max_events:Number(maxEvents)})});
      setMessage("Core accepted the retention configuration. Reloading authoritative status.");
      await loadRetention();
      await load();
    }catch(e:any){setError(e.message||String(e))}
    finally{setRetentionWriteBusy(false)}
  }
  async function runRetention(){
    if(!auditRetentionRunPermitted(retention,retentionDraft,retentionState,retentionWriteBusy,retentionConfirmation))return;
    setError("");setMessage("");setRetentionWriteBusy(true);setRetentionConfirmation("");
    try{
      const value=await api("/api/v1/audit/retention/run",{method:"POST",body:"{}"});
      const counts=[value?.control_deleted,value?.access_deleted,value?.capacity_deleted];
      const count=counts.every(n=>Number.isSafeInteger(n)&&n>=0)
        ?String(counts.reduce((sum,n)=>sum+n,0)):"UNKNOWN";
      setMessage("Core retention result: "+String(value?.status||"UNKNOWN")+" · deleted "+count);
      await loadRetention();await load();
    }catch(e:any){setError(e.message||String(e))}
    finally{setRetentionWriteBusy(false)}
  }
  const retentionDraft={control_days:controlDays,access_days:accessDays,max_events:maxEvents};
  const retentionEdited=retentionState==="ready"&&retention&&(
    controlDays!==String(retention.config.control_days)||
    accessDays!==String(retention.config.access_days)||
    maxEvents!==String(retention.config.max_events)
  );
  const retentionRunAllowed=auditRetentionRunPermitted(retention,retentionDraft,retentionState,retentionWriteBusy,retentionConfirmation);
  const auditFiltersEdited=auditState==="ready"&&auditFilterKey!==filterParams().toString();
  const rows=(data?.items||[]).map((x:any)=>({
    event_id:x.event_id||("legacy:"+x.row_id),
    occurred_at:x.occurred_at,
    category:x.category,
    event_type:x.event_type,
    actor:x.actor_id,
    interface:x.interface,
    resource:(x.resource_type||"")+":"+(x.resource_id||""),
    result:x.result,
    reason:x.reason_code||"",
  }));
  return <>
    {error&&<div className="error" role="alert">{error}</div>}{message&&<div className="notice">{message}</div>}
    <section className="card dr-audit-card">
      <div className="dr-section-head"><div><p className="dr-eyebrow">Activity & Health</p><h3>Audit Explorer</h3><p className="muted">Unified control, access-decision and security-lifecycle history with bounded keyset pagination.</p></div><button className="secondary" onClick={exportAudit} disabled={exportBusy}>{exportBusy?"Exporting with Core…":"Export NDJSON"}</button></div>
      {exportError&&<p role="alert" className="warning-box">{exportError} The result may have been committed; inspect Activity log before trying again.</p>}
      <div className="dr-audit-filter-grid">
        <label className="dr-field"><span>Start UTC</span><input value={start} onChange={e=>setStart(e.target.value)} placeholder="YYYY-MM-DDTHH:MM:SSZ"/></label>
        <label className="dr-field"><span>End UTC</span><input value={end} onChange={e=>setEnd(e.target.value)} placeholder="YYYY-MM-DDTHH:MM:SSZ"/></label>
        <label className="dr-field"><span>Category</span><select value={category} onChange={e=>setCategory(e.target.value)}><option value="">All categories</option><option value="CONTROL">CONTROL</option><option value="ACCESS_DECISION">ACCESS_DECISION</option><option value="SECURITY_LIFECYCLE">SECURITY_LIFECYCLE</option></select></label>
        <label className="dr-field"><span>Event type</span><input value={eventType} onChange={e=>setEventType(e.target.value)} placeholder="web.login.succeeded"/></label>
        <label className="dr-field"><span>Actor</span><input value={actor} onChange={e=>setActor(e.target.value)} placeholder="Actor ID"/></label>
        <label className="dr-field"><span>Resource</span><input value={resource} onChange={e=>setResource(e.target.value)} placeholder="Resource ID"/></label>
        <label className="dr-field"><span>Result</span><input value={result} onChange={e=>setResult(e.target.value)} placeholder="success / deny"/></label>
        <label className="dr-field"><span>Correlation ID</span><input value={correlation} onChange={e=>setCorrelation(e.target.value)} placeholder="Correlation ID"/></label>
      </div>
      <div className="dr-form-actions"><button className="primary" onClick={()=>load()}>Search audit</button><button className="secondary" onClick={()=>{auditReadEpoch.current+=1;setData(null);setAuditState("idle");setAuditPage({cursor:"",history:[]});setAuditFilterKey(null);setError("");setStart("");setEnd("");setCategory("");setEventType("");setActor("");setResource("");setResult("");setCorrelation("")}}>Clear filters</button></div>
      {auditFiltersEdited&&<p className="dr-uxb-catalog-page-notice" role="status">Filters changed since the loaded Audit page. Select Search audit to apply them; results below still belong to the previous search.</p>}
      <div className="dr-audit-table">{auditState==="ready"?<Table items={rows}/>:
        <p role="status" className="warning-box">{auditState==="loading"?"Loading Activity log from Core…":auditState==="idle"?"Filters cleared. Select Search audit to load current Core records.":"UNKNOWN · Core Audit inventory unavailable. No empty history was confirmed. Retry with Search audit."}</p>}
      </div>
      {auditState==="ready"&&!auditFiltersEdited&&(auditPage.history.length>0||isPartialCorePage(data))&&
      <div className="dr-form-actions" role="group" aria-label="Audit pagination">
        <span className="muted">Page {auditPage.history.length+1} · current Core query</span>
        {auditPage.history.length>0&&<button className="secondary" onClick={()=>{const previous=selectMenuPage(auditPage,data?.next_cursor,"newer");if(previous)load(previous)}}>← Newer Audit</button>}
        {isPartialCorePage(data)&&<button className="secondary" onClick={()=>{const older=selectMenuPage(auditPage,data.next_cursor,"older");if(older)load(older)}}>Older Audit →</button>}
      </div>}
      {exportResult&&<section role="status" className="dr-export-evidence">
        <strong>Core Audit Export CREATED · No Web download</strong>
        <p className="muted">The artifact is stored on the Server for the exact submitted filters shown here. Editing the search fields does not change this export; no browser download endpoint exists.</p>
        <pre className="plan">{JSON.stringify({status:exportResult.status,path:exportResult.path,event_count:exportResult.event_count,size_bytes:exportResult.size_bytes,schema_version:exportResult.schema_version,sha256:exportResult.sha256,filters:exportResult.filters,download_exposed:exportResult.download_exposed},null,2)}</pre>
      </section>}
    </section>
    <section className="card dr-retention-card">
      <div className="dr-section-head"><div><p className="dr-eyebrow">Storage policy</p><h3>Audit Retention</h3><p className="muted">{retentionState==="ready"&&retention?retention.capacity_policy:"Core Audit Retention status requires a verified read; missing metrics are not zero or Normal."}</p></div></div>
      {retentionState==="loading"&&<p role="status" className="muted">Loading Audit Retention status from Core…</p>}
      {retentionState==="unknown"&&<div role="alert" className="warning-box">
        <strong>UNKNOWN · Audit Retention Core status unavailable</strong>
        <p>{retentionError||"No valid Core retention evidence was observed."} Storage safety and event counts cannot be inferred.</p>
        <button type="button" className="secondary" onClick={loadRetention}>Retry Audit Retention read →</button>
      </div>}
      {retentionState==="ready"&&retention&&<div className="dr-kpi-strip dr-retention-metrics">
        <div><span>Events</span><strong>{retention.total_events}</strong><small>Core-reported retained audit events</small></div>
        <div><span>DB bytes</span><strong>{retention.db_size_bytes}</strong><small>Core-reported database file size</small></div>
        <div><span>Capacity</span><strong>{retention.capacity_exceeded?"Exceeded":"Normal"}</strong><small>{retention.capacity_exceeded?"Core reports configured capacity exceeded":"Within configured event-count bound, per Core"}</small></div>
      </div>}
      {operator.role==="Admin"&&<div className="dr-retention-config">
        {retentionState!=="ready"&&<p className="muted" role="status">Retention changes are unavailable until current Core configuration is verified.</p>}
        <div className="dr-form-grid three">
          <label className="dr-field"><span>Control / security days</span><input value={retentionState==="ready"?controlDays:""} onChange={e=>{setControlDays(e.target.value);setRetentionConfirmation("")}} inputMode="numeric" placeholder="UNKNOWN" disabled={retentionState!=="ready"||retentionWriteBusy}/></label>
          <label className="dr-field"><span>Access decision days</span><input value={retentionState==="ready"?accessDays:""} onChange={e=>{setAccessDays(e.target.value);setRetentionConfirmation("")}} inputMode="numeric" placeholder="UNKNOWN" disabled={retentionState!=="ready"||retentionWriteBusy}/></label>
          <label className="dr-field"><span>Maximum events</span><input value={retentionState==="ready"?maxEvents:""} onChange={e=>{setMaxEvents(e.target.value);setRetentionConfirmation("")}} inputMode="numeric" placeholder="UNKNOWN" disabled={retentionState!=="ready"||retentionWriteBusy}/></label>
        </div>
        {retentionEdited&&<p role="status" className="dr-uxb-catalog-page-notice">Unsaved retention policy changes are present. Save policy and reload Core status before running retention; the operation only uses the last Core-saved policy.</p>}
        <p className="warning-box">Audit retention permanently deletes audit rows older than the saved control/access windows and may prune oldest access decisions for capacity. Review the observed settings above. This Web confirmation does not replace Core Admin authorization.</p>
        <label className="dr-field"><span>Type RUN RETENTION to confirm deletion using the observed saved policy</span>
          <input value={retentionConfirmation} onChange={e=>setRetentionConfirmation(e.target.value)} placeholder="RUN RETENTION" autoComplete="off"
            disabled={retentionState!=="ready"||retentionWriteBusy||!!retentionEdited}/>
        </label>
        <div className="dr-form-actions">
          <button className="secondary" onClick={configureRetention} disabled={retentionState!=="ready"||retentionWriteBusy}>Save policy</button>
          <button className="danger" onClick={runRetention} disabled={!retentionRunAllowed}>Run retention now</button>
        </div>
      </div>}
    </section>
  </>;
}

function AgentRolloutPreviewPanel(){
  const [hosts,setHosts]=useState(""),[canaries,setCanaries]=useState(""),[version,setVersion]=useState(""),[sourceRef,setSourceRef]=useState(""),[digest,setDigest]=useState("");
  const [wave,setWave]=useState("1"),[threshold,setThreshold]=useState("20"),[preview,setPreview]=useState<any>(null),[error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const previewGeneration=useRef(0);
  const previewInFlight=useRef(false);
  useEffect(()=>{return()=>{previewGeneration.current+=1};},[]);
  function edit(setter:(value:string)=>void,value:string){
    previewGeneration.current+=1;
    previewInFlight.current=false;
    setBusy(false);setter(value);setPreview(null);setError("");
  }
  async function inspect(){
    if(previewInFlight.current)return;
    const epoch=++previewGeneration.current;
    previewInFlight.current=true;setBusy(true);
    setPreview(null);setError("");
    try{
      const body={targets:hosts.split(",").map(x=>x.trim()).filter(Boolean),canary_targets:canaries.split(",").map(x=>x.trim()).filter(Boolean),
        artifact:{version:version.trim(),source_ref:sourceRef.trim(),sha256:digest.trim()},
        wave_size:Number(wave),failure_threshold_percent:Number(threshold)};
      const result=requireObservedRolloutPreview(await api("/api/v1/jobs/agent-update-rollout/preview",{
        method:"POST",body:JSON.stringify(body)
      }),body);
      if(epoch!==previewGeneration.current)return;
      setPreview(result);
    }catch(e:any){
      if(epoch===previewGeneration.current)setError("UNKNOWN · Core Agent Update Preview did not complete for the current inputs: "+(e.message||String(e)));
    }finally{
      if(epoch===previewGeneration.current){previewInFlight.current=false;setBusy(false)}
    }
  }
  return <section className="card" aria-label="Agent update preview">
    <h3>Managed Agent Updates · Read-only Preview</h3>
    <p className="muted">Inspect an explicit bounded target set and canary wave. This does not enqueue updates or authorize an Apply. Artifact signatures, provenance, live Agent health and rollback remain unverified.</p>
    <div className="dr-form-grid three">
      <label className="dr-field"><span>Managed Host IDs (comma-separated)</span><input value={hosts} onChange={e=>edit(setHosts,e.target.value)} placeholder="host-a, host-b"/></label>
      <label className="dr-field"><span>Canary Host IDs (optional)</span><input value={canaries} onChange={e=>edit(setCanaries,e.target.value)} placeholder="host-a"/></label>
      <label className="dr-field"><span>Target version</span><input value={version} onChange={e=>edit(setVersion,e.target.value)} placeholder="3.0.0-rc.1"/></label>
      <label className="dr-field"><span>Source commit (40-character SHA)</span><input value={sourceRef} onChange={e=>edit(setSourceRef,e.target.value)} placeholder="Immutable Git commit"/></label>
      <label className="dr-field"><span>Artifact SHA256 (64 hex characters)</span><input value={digest} onChange={e=>edit(setDigest,e.target.value)} placeholder="SHA256 digest"/></label>
      <label className="dr-field"><span>Wave size</span><input type="number" min="1" max="25" value={wave} onChange={e=>edit(setWave,e.target.value)}/></label>
      <label className="dr-field"><span>Failure threshold (%)</span><input type="number" min="0" max="100" value={threshold} onChange={e=>edit(setThreshold,e.target.value)}/></label>
    </div>
    <div className="dr-form-actions"><button className="secondary" disabled={busy||!hosts.trim()||!version.trim()||!sourceRef.trim()||!digest.trim()} onClick={inspect}>{busy?"Inspecting Core…":"Preview only · No updates"}</button></div>
    {busy&&<p role="status" className="muted">Waiting for the current read-only Core preview. Editing any field invalidates this response.</p>}
    {error&&<div className="error">{error}</div>}
    {preview&&<div className="dr-preview-panel">
      <p className="muted"><strong>Qualification: {preview.artifact_qualification}</strong> · Ready to apply: NO. Preview is advisory and must be revalidated before any future Apply.</p>
      <div className="dr-table-scroll"><table className="dr-resource-table">
        <thead><tr><th>Host</th><th>Platform</th><th>Observed version</th><th>Target version</th><th>Version comparison</th><th>Provenance</th><th>Update available</th></tr></thead>
        <tbody>{(preview.target_observations||[]).map((host:any)=><tr key={host.target_id}>
          <td>{host.target_id}</td><td>{host.platform}</td><td>{host.current_version}</td><td>{host.target_version}</td>
          <td>{host.version_relation}</td><td>{host.provenance}</td><td>{host.update_available}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="muted">Version comparison comes only from previously recorded inventory, not current Agent health or signed package provenance. Update availability remains UNKNOWN.</p>
      <pre className="plan">{JSON.stringify({targets:preview.targets,canaries:preview.canary_targets,blocked:preview.blocked_targets,wave_size:preview.wave_size,artifact:preview.artifact,qualification_note:preview.qualification_note},null,2)}</pre>
    </div>}
  </section>;
}

function JobOperations({operator}:{operator:any}){
  const [jobs,setJobs]=useState<any>(null),[detail,setDetail]=useState<any>(null),[error,setError]=useState(""),[message,setMessage]=useState(""),[inventoryExport,setInventoryExport]=useState<any>(null);
  const [jobsState,setJobsState]=useState<"loading"|"ready"|"error">("loading");
  const [jobsCursor,setJobsCursor]=useState("");
  const [jobsHistory,setJobsHistory]=useState<string[]>([]);
  const jobsReadEpoch=useRef(0);
  const [jobType,setJobType]=useState("doctor"),[resourceType,setResourceType]=useState("managed-host"),[resource,setResource]=useState(""),[detailId,setDetailId]=useState("");
  const [fleetResourceType,setFleetResourceType]=useState("managed-host"),[fleetResource,setFleetResource]=useState(""),[fleetDescription,setFleetDescription]=useState(""),[fleetTags,setFleetTags]=useState(""),[fleetRemoveTags,setFleetRemoveTags]=useState(""),[fleetAddGroups,setFleetAddGroups]=useState(""),[fleetRemoveGroups,setFleetRemoveGroups]=useState(""),[fleetPreview,setFleetPreview]=useState<any>(null),[fleetConfirm,setFleetConfirm]=useState("");
  const [fleetApplyBusy,setFleetApplyBusy]=useState(false);
  const fleetApplyInFlight=useRef(false);
  const fleetPreviewInFlight=useRef(false);
  const fleetPreviewEpoch=useRef(0);
  const [fleetPreviewBusy,setFleetPreviewBusy]=useState(false);
  const [fleetPreviewKey,setFleetPreviewKey]=useState<string|null>(null);
  const fleetDraftKey=JSON.stringify([
    fleetResourceType,fleetResource,fleetDescription,fleetTags,fleetRemoveTags,fleetAddGroups,fleetRemoveGroups
  ]);
  const [jobStartBusy,setJobStartBusy]=useState(false);
  const detailReadEpoch=useRef(0);
  const [detailBusy,setDetailBusy]=useState(false);
  const cancelInFlight=useRef(false);
  const [cancelBusy,setCancelBusy]=useState(false);
  const inventoryExportInFlight=useRef(false);
  const [inventoryExportBusy,setInventoryExportBusy]=useState(false);
  async function refresh(){
    const epoch=++jobsReadEpoch.current;
    setError("");setJobsState("loading");
    try{
      const result=requireObservedMenuPayload("jobs",await api("/api/v1/jobs?limit=50"+(jobsCursor?"&cursor="+encodeURIComponent(jobsCursor):"")));
      if(epoch!==jobsReadEpoch.current)return;
      setJobs(result);setJobsState("ready");
    }catch(e:any){
      if(epoch!==jobsReadEpoch.current)return;
      setJobs(null);setJobsState("error");setError(e.message||String(e));
    }
  }
  useEffect(()=>{refresh();return()=>{jobsReadEpoch.current+=1}},[jobsCursor]);
  useEffect(()=>()=>{detailReadEpoch.current+=1;fleetPreviewEpoch.current+=1},[]);
  function olderJobsPage(){
    if(!isPartialCorePage(jobs))return;
    setJobsHistory([...jobsHistory,jobsCursor]);
    setJobsCursor(jobs.next_cursor);
  }
  function newerJobsPage(){
    if(!jobsHistory.length)return;
    setJobsCursor(jobsHistory[jobsHistory.length-1]);
    setJobsHistory(jobsHistory.slice(0,-1));
  }
  async function start(){
    if(jobStartBusy)return;
    setError("");setMessage("");setJobStartBusy(true);
    try{
      const body:any={job_type:jobType,resource_type:resourceType};
      if(resource)body.resource=resource;
      const result=requireObservedJobStart(await api("/api/v1/jobs/diagnostic",{method:"POST",body:JSON.stringify(body)}),jobType);
      detailReadEpoch.current+=1;setDetailBusy(false);
      setDetail(result.job);
      setDetailId(result.job.id);
      setMessage("Core job request accepted: "+result.job.id+" · status "+result.job.status+" · "+result.selection.target_count+" Managed Host(s). Completion NOT VERIFIED.");
      if(jobsCursor){setJobsCursor("");setJobsHistory([])}
      else await refresh();
    }catch(e:any){setError("UNKNOWN · Core Job start response could not be confirmed. Inspect Jobs before retrying: "+(e.message||String(e)))}
    finally{setJobStartBusy(false)}
  }
  async function loadDetail(id?:string){
    const target=(id||detailId).trim();
    if(!target||cancelBusy)return;
    const epoch=++detailReadEpoch.current;
    setDetail(null);setDetailBusy(true);setError("");
    try{
      const result=requireObservedJobDetail(await api("/api/v1/jobs/"+encodeURIComponent(target)),target);
      if(epoch!==detailReadEpoch.current)return;
      setDetail(result);setDetailId(target);
    }catch(e:any){
      if(epoch===detailReadEpoch.current)setError("UNKNOWN · Core Job Detail does not match the requested Job ID: "+(e.message||String(e)));
    }finally{
      if(epoch===detailReadEpoch.current)setDetailBusy(false);
    }
  }
  function csvList(value:string){return value.split(",").map(x=>x.trim()).filter(Boolean)}
  function invalidateFleetReview(){
    fleetPreviewEpoch.current+=1;
    fleetPreviewInFlight.current=false;
    setFleetPreview(null);setFleetPreviewKey(null);setFleetConfirm("");
    setFleetPreviewBusy(false);setError("");setMessage("");
  }
  async function previewFleetMetadata(){
    if(fleetPreviewInFlight.current||fleetApplyInFlight.current||fleetApplyBusy)return;
    fleetPreviewInFlight.current=true;
    const epoch=++fleetPreviewEpoch.current;
    const requestedKey=fleetDraftKey;
    setError("");setMessage("");setFleetConfirm("");
    setFleetPreview(null);setFleetPreviewKey(null);setFleetPreviewBusy(true);
    try{
      const changes:any={};
      if(fleetDescription!=="")changes.description=fleetDescription;
      if(fleetTags.trim()){
        const parsed=JSON.parse(fleetTags);
        if(!parsed||typeof parsed!=="object"||Array.isArray(parsed)
          ||Object.entries(parsed).some(([key,value])=>!key.trim()||typeof value!=="string"))
          throw new Error("Fleet tags must be a JSON object with text keys and text values.");
        if(Object.keys(parsed).length)changes.tags=parsed;
      }
      const removeTags=csvList(fleetRemoveTags);if(removeTags.length)changes.remove_tags=removeTags;
      const addGroups=csvList(fleetAddGroups);if(addGroups.length)changes.add_groups=addGroups;
      const removeGroups=csvList(fleetRemoveGroups);if(removeGroups.length)changes.remove_groups=removeGroups;
      if(!Object.keys(changes).length)
        throw new Error("Enter a description, tags or group membership change before Preview.");
      const request={resource_type:fleetResourceType,resource:fleetResource,changes};
      const result=requireObservedFleetPreview(await api("/api/v1/fleet/metadata/preview",{
        method:"POST",body:JSON.stringify(request)
      }),request);
      if(epoch!==fleetPreviewEpoch.current)return;
      setFleetPreview(result);setFleetPreviewKey(requestedKey);
    }catch(e:any){
      if(epoch===fleetPreviewEpoch.current){
        setFleetPreview(null);setFleetPreviewKey(null);
        setError(e.message||String(e));
      }
    }finally{
      if(epoch===fleetPreviewEpoch.current){fleetPreviewInFlight.current=false;setFleetPreviewBusy(false)}
    }
  }
  const fleetPreviewGuard=!!fleetPreview&&fleetPreviewKey===fleetDraftKey&&!fleetPreviewBusy&&!fleetApplyBusy
    &&typeof fleetPreview.change_plan_id==="string";
  async function applyFleetMetadata(){
    if(fleetApplyInFlight.current)return;
    if(!fleetPreviewGuard||fleetConfirm!=="APPLY")return;
    fleetApplyInFlight.current=true;
    setError("");setMessage("");setFleetApplyBusy(true);
    try{
      const reviewed=fleetPreview;
      const result=requireObservedFleetApplyForPreview(await api("/api/v1/fleet/metadata/apply",{method:"POST",body:JSON.stringify({
        change_plan_id:reviewed.change_plan_id,confirmation:fleetConfirm
      })}),reviewed);
      setMessage("Core confirmed Fleet metadata APPLIED at revision "+result.revision+" to "+result.result.target_count+" Managed Host(s).");
      setFleetPreview(null);setFleetPreviewKey(null);setFleetConfirm("");
    }catch(e:any){
      // The Core may have committed even if the Web response was interrupted.
      // Never allow reusing an ambiguous Apply plan without fresh Preview.
      setFleetPreview(null);setFleetPreviewKey(null);setFleetConfirm("");
      setError("UNKNOWN · Fleet metadata apply response could not be confirmed. Inspect Change History before attempting a fresh Preview: "+(e.message||String(e)));
    }finally{fleetApplyInFlight.current=false;setFleetApplyBusy(false)}
  }
  async function exportInventory(){
    if(inventoryExportInFlight.current)return;
    inventoryExportInFlight.current=true;setInventoryExportBusy(true);
    setError("");setMessage("");setInventoryExport(null);
    try{
      const result=requireObservedInventoryExport(await api("/api/v1/inventory/export",{method:"POST",body:"{}"}));
      setInventoryExport(result);
      setMessage("Core confirmed a bounded server-side Inventory Export: "+result.record_count+" resources. No Web download is available.");
    }catch(e:any){
      setError("Core Inventory Export status UNKNOWN. "+(e.message||String(e))+" The export may already exist; inspect Core before retrying.");
    }finally{
      inventoryExportInFlight.current=false;setInventoryExportBusy(false);
    }
  }
  async function cancelJob(){
    if(cancelInFlight.current||!detail?.id||detailBusy)return;
    cancelInFlight.current=true;setCancelBusy(true);
    const jobId=String(detail.id);
    detailReadEpoch.current+=1;setError("");setMessage("");
    try{
      const confirmed=requireObservedJobCancellation(await api("/api/v1/jobs/cancel",{
        method:"POST",body:JSON.stringify({job_id:jobId})
      }),jobId);
      setDetail(confirmed.job);
      setMessage(confirmed.outcome==="REQUESTED"
        ?"Cancellation request recorded; running targets may still finish."
        :"Already terminal; no new cancellation was applied.");
      await refresh();
    }catch(e:any){
      // An ambiguous response could represent a real Core cancellation.
      // Do not claim success or blindly send another cancel.
      setDetail(null);
      setError("UNKNOWN · Core Job cancellation response did not confirm the exact Job. Load Detail before retrying: "+(e.message||String(e)));
    }finally{
      cancelInFlight.current=false;setCancelBusy(false);
    }
  }
  const rows=(jobs?.items||[]).map((x:any)=>({id:x.id,job_type:x.job_type,status:x.status,resource_type:x.resource_type,resource_ref:x.resource_ref,target_count:x.target_count,created_at:x.created_at,finished_at:x.finished_at||""}));
  return <>
    {error&&<div className="error" role="alert">{error}</div>}{message&&<div className="notice">{message}</div>}
    {operator.role==="Admin"&&<AgentRolloutPreviewPanel/>}
    <div className="card">
      <h3>Bounded Management Jobs</h3>
      <div className="muted">Safe fleet operations only. Jobs are bounded to at most 100 trusted Managed Hosts and use the signed Agent claim/complete transport.</div>
      {operator.role!=="Read Only"&&<div className="toolbar">
        <select value={jobType} onChange={e=>setJobType(e.target.value)}><option value="doctor">Doctor diagnostics</option><option value="refresh">Synchronize / refresh</option><option value="version-check">Version check</option><option value="support-bundle">Support bundle</option></select>
        <select value={resourceType} onChange={e=>{setResourceType(e.target.value);setResource("")}}><option value="managed-host">Managed Host(s)</option><option value="managed-host-group">Managed Host Group</option></select>
        <input value={resource} onChange={e=>setResource(e.target.value)} placeholder={resourceType==="managed-host"?"Host selector; blank = all trusted":"Managed Host Group name / ID"}/>
        <button className="primary" onClick={start} disabled={jobStartBusy||(resourceType==="managed-host-group"&&!resource.trim())}>{jobStartBusy?"Submitting Core Job…":"Start Job"}</button>
      </div>}
      <div className="toolbar"><button className="secondary" onClick={refresh}>Refresh Jobs</button><input value={detailId} onChange={e=>{detailReadEpoch.current+=1;setDetail(null);setDetailBusy(false);setDetailId(e.target.value)}} placeholder="Job ID" disabled={cancelBusy}/><button className="secondary" onClick={()=>loadDetail()} disabled={detailBusy||cancelBusy}>{detailBusy?"Loading Core Job…":"Load Detail"}</button><button className="secondary" onClick={exportInventory} disabled={inventoryExportBusy}>{inventoryExportBusy?"Exporting inventory…":"Export Inventory"}</button></div>
      {inventoryExport&&<section role="status" className="dr-export-evidence">
        <strong>Core Inventory Export CREATED · No Web download</strong>
        <p className="muted">This bounded sanitized inventory artifact is stored on the Server. It is not a downloadable browser file or a complete history of every resource type.</p>
        <pre className="plan">{JSON.stringify({status:inventoryExport.status,path:inventoryExport.path,record_count:inventoryExport.record_count,counts:inventoryExport.counts,limits:inventoryExport.limits,size_bytes:inventoryExport.size_bytes,sha256:inventoryExport.sha256,download_exposed:inventoryExport.download_exposed},null,2)}</pre>
      </section>}
      {jobsState!=="ready"?<p role="status" className="warning-box">
        {jobsState==="loading"?"Loading Management Jobs from Core…":"UNKNOWN · Core Jobs inventory is unavailable. Retry using Refresh Jobs; an empty list has not been confirmed."}
      </p>:<>
        {isPartialCorePage(jobs)&&<p className="dr-uxb-catalog-page-notice" role="status">Partial Core Jobs list · older jobs exist beyond this page. Browse the actual Core pages below.</p>}
        <Table items={rows}/>
        {(jobsHistory.length>0||isPartialCorePage(jobs))&&<div className="toolbar" aria-label="Jobs pagination">
          <button type="button" className="secondary" onClick={newerJobsPage} disabled={!jobsHistory.length}>← Newer Jobs</button>
          <span role="status">Core Jobs page {jobsHistory.length+1}</span>
          <button type="button" className="secondary" onClick={olderJobsPage} disabled={!isPartialCorePage(jobs)}>Older Jobs →</button>
        </div>}
      </>}
    </div>
    {operator.role!=="Read Only"&&<section className="card dr-fleet-card">
      <div className="dr-section-head"><div><p className="dr-eyebrow">Fleet change</p><h3>Fleet Metadata Change Plan</h3><p className="muted">Bounded to 100 trusted Managed Hosts. Changes apply atomically as one revision after Preview.</p></div></div>
      <div className="dr-form-section"><h4>Target scope</h4><div className="dr-form-grid two">
        <label className="dr-field"><span>Target type</span><select value={fleetResourceType} disabled={fleetApplyBusy} onChange={e=>{invalidateFleetReview();setFleetResourceType(e.target.value);setFleetResource("")}}><option value="managed-host">Managed Host(s)</option><option value="managed-host-group">Managed Host Group</option></select></label>
        <label className="dr-field"><span>Target selector</span><input value={fleetResource} disabled={fleetApplyBusy} onChange={e=>{invalidateFleetReview();setFleetResource(e.target.value)}} placeholder={fleetResourceType==="managed-host"?"Blank selects all trusted hosts":"Managed Host Group name / ID"}/></label>
      </div></div>
      <div className="dr-form-section"><h4>Metadata</h4><div className="dr-form-grid two">
        <label className="dr-field"><span>Description</span><input value={fleetDescription} disabled={fleetApplyBusy} onChange={e=>{invalidateFleetReview();setFleetDescription(e.target.value)}} placeholder="Optional description for selected hosts"/></label>
        <label className="dr-field"><span>Tags JSON</span><input value={fleetTags} disabled={fleetApplyBusy} onChange={e=>{invalidateFleetReview();setFleetTags(e.target.value)}} placeholder='{"site":"lab","owner":"secops"}'/></label>
        <label className="dr-field"><span>Remove tag keys</span><input value={fleetRemoveTags} disabled={fleetApplyBusy} onChange={e=>{invalidateFleetReview();setFleetRemoveTags(e.target.value)}} placeholder="owner,environment"/></label>
      </div></div>
      <div className="dr-form-section"><h4>Group membership</h4><div className="dr-form-grid two">
        <label className="dr-field"><span>Add groups</span><input value={fleetAddGroups} disabled={fleetApplyBusy} onChange={e=>{invalidateFleetReview();setFleetAddGroups(e.target.value)}} placeholder="group-a, group-b"/></label>
        <label className="dr-field"><span>Remove groups</span><input value={fleetRemoveGroups} disabled={fleetApplyBusy} onChange={e=>{invalidateFleetReview();setFleetRemoveGroups(e.target.value)}} placeholder="group-c"/></label>
      </div></div>
      <div className="dr-form-actions"><button className="primary" onClick={previewFleetMetadata} disabled={fleetPreviewBusy||fleetApplyBusy||(fleetResourceType==="managed-host-group"&&!fleetResource.trim())}>{fleetPreviewBusy?"Reading Core Preview…":"Preview fleet change"}</button></div>
      {fleetPreviewBusy&&<p role="status" className="muted">Waiting for this form's Core Change Plan. Editing the form invalidates this request.</p>}
      {fleetPreview&&fleetPreviewKey===fleetDraftKey&&<div className="dr-preview-panel">
        <p className="muted">This Core Change Plan is for the exact form values shown. Review impacted Managed Hosts before Apply; Preview alone makes no change.</p>
        <pre className="plan">{JSON.stringify({selection:fleetPreview.selection,changes:fleetPreview.changes,preview:fleetPreview.preview,impact:fleetPreview.impact},null,2)}</pre>
        <label className="apply-label">Type APPLY to commit<input value={fleetConfirm} onChange={e=>setFleetConfirm(e.target.value)} placeholder="APPLY" disabled={fleetApplyBusy}/></label>
        <button className="danger" onClick={applyFleetMetadata} disabled={!fleetPreviewGuard||fleetConfirm!=="APPLY"}>{fleetApplyBusy?"Confirming Core Apply…":"Apply Fleet Metadata"}</button>
      </div>}
    </section>}
    {detail&&<div className="card">
      <h3>Job Detail</h3>
      <div className="grid"><Metric label="Status" value={detail.status}/><Metric label="Targets" value={detail.target_count}/><Metric label="Type" value={detail.job_type}/></div>
      {operator.role!=="Read Only"&&["QUEUED","RUNNING"].includes(String(detail.status||""))&&<button className="danger" onClick={cancelJob} disabled={cancelBusy||detailBusy}>{cancelBusy?"Requesting Core cancellation…":"Cancel Job"}</button>}
      <Table items={(detail.targets||[]).map((x:any)=>({target_id:x.target_id,status:x.status,attempt:x.attempt,error:x.error||"",updated_at:x.updated_at}))}/>
      <pre className="plan">{JSON.stringify({id:detail.id,resource_type:detail.resource_type,resource_ref:detail.resource_ref,deadline_at:detail.deadline_at,last_error:detail.last_error,targets:(detail.targets||[]).map((x:any)=>({target_id:x.target_id,status:x.status,result:x.result,error:x.error}))},null,2)}</pre>
    </div>}
  </>;
}

function ObjectsWorkspace({data,onNavigate,context,api}:{data:any,onNavigate?:(id:string,groupId?:string,context?:any)=>void,context?:any,api:(path:string)=>Promise<any>}){
  const initialFamily=["all","network","service","permission","ai"].includes(String(context?.family||""))
    ?String(context.family):"all";
  const [family,setFamily]=useState(initialFamily),[filter,setFilter]=useState(""),[selected,setSelected]=useState<any>(null);
  useEffect(()=>{setFamily(initialFamily);setFilter("");setSelected(null)},[initialFamily]);
  useEscapeClose(!!selected,()=>setSelected(null));
  const resources=data?.resources&&typeof data.resources==="object"?data.resources:null;
  const requiredTypes=["network-object","network-group","service-object","service-group",
    "permission-object","permission-group","ai-identity"];
  const incomplete=!resources||requiredTypes.some(type=>!Array.isArray(resources[type]?.items));
  const [extraByType,setExtraByType]=useState<Record<string,any[]>>({});
  const [nextByType,setNextByType]=useState<Record<string,string|null>>(()=>Object.fromEntries(
    requiredTypes.map(type=>[type,isPartialCorePage(resources?.[type])?resources[type].next_cursor:null])
  ));
  const [busyType,setBusyType]=useState(""),[pageError,setPageError]=useState("");
  const pageEpoch=useRef(0);
  useEffect(()=>{
    pageEpoch.current+=1;setExtraByType({});setPageError("");setBusyType("");
    setNextByType(Object.fromEntries(requiredTypes.map(type=>[
      type,isPartialCorePage(resources?.[type])?resources[type].next_cursor:null
    ])));
    return()=>{pageEpoch.current+=1};
  },[data]);
  async function loadObjectPage(type:string){
    const cursor=nextByType[type];
    if(!cursor||busyType)return;
    const generation=++pageEpoch.current;
    setBusyType(type);setPageError("");
    try{
      const query="/api/v1/inventory?resource_type="+encodeURIComponent(type)+
        "&limit=50&cursor="+encodeURIComponent(cursor);
      const page=requireObservedObjectContinuation(type,await api(query),cursor,50);
      if(generation!==pageEpoch.current)return;
      const loaded=[...(resources?.[type]?.items||[]),...(extraByType[type]||[])];
      const known=new Set(loaded.map((row:any)=>row.id));
      const fresh=page.items.filter((row:any)=>!known.has(row.id));
      if(page.items.length&&!fresh.length)
        throw new Error("Core returned previously loaded object IDs only. State is UNKNOWN.");
      setExtraByType(previous=>({...previous,[type]:[...(previous[type]||[]),...fresh]}));
      setNextByType(previous=>({...previous,[type]:isPartialCorePage(page)?page.next_cursor:null}));
    }catch(e:any){
      if(generation===pageEpoch.current)setPageError(e.message||String(e));
    }finally{
      if(generation===pageEpoch.current)setBusyType("");
    }
  }
  const all=Object.entries(resources||{}).flatMap(([type,page]:any)=>
    [...(Array.isArray(page?.items)?page.items:[]),...(extraByType[type]||[])]
      .map((item:any)=>({...item,resource_type:type})));
  const familyFor=(type:string)=>type.startsWith("network-")?"network":type.startsWith("service-")?"service":type.startsWith("permission-")?"permission":type==="ai-identity"?"ai":"other";
  const availableTypes=requiredTypes.filter(type=>
    (family==="all"||familyFor(type)===family)&&!!nextByType[type]);
  const truncated=availableTypes.length>0;
  const q=filter.trim().toLowerCase();
  const rows=all.filter((item:any)=>(family==="all"||familyFor(item.resource_type)===family)&&(!q||Object.values(item).some(v=>String(v??"").toLowerCase().includes(q))));
  const families=[["all","All"],["network","Network"],["service","Service"],["permission","Permission"],["ai","AI Identity"]];
  return <div className="dr-resource-workspace">
    <section className="dr-page-intro"><div><p className="dr-eyebrow">Access · Advanced</p><h2>Objects & Groups</h2><p className="muted">Reusable network, service, permission and AI identity selectors for policy work.</p></div><div className="dr-page-actions"><button className="secondary" onClick={()=>onNavigate?.("policies","access")}>Use in policy</button></div></section>
    <div className="dr-access-tabs" role="tablist" aria-label="Object family">{families.map(([id,label])=><button key={id} role="tab" aria-selected={family===id} className={family===id?"active":""} onClick={()=>setFamily(id)}>{label}</button>)}</div>
    <section className="card dr-list-card"><div className="dr-list-toolbar"><div><strong>{rows.length}</strong><span>visible Core resources</span></div><label className="dr-filter-field"><WorkspaceIcon kind="search"/><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter loaded objects and groups…"/>{filter&&<button onClick={()=>setFilter("")} aria-label="Clear filter">×</button>}</label></div>
      {incomplete&&<p className="warning-box" role="alert">UNKNOWN · Core Objects & Groups inventory is incomplete. Some names may not be visible; check System Health before interpreting missing records.</p>}
      {truncated&&<div className="dr-uxb-catalog-page-notice" role="status"><span>Partial Core snapshot · more names exist for {availableTypes.join(", ")}. The filter checks only loaded records.</span>
        <button type="button" className="secondary" onClick={()=>onNavigate?.("setup","connections",setupContextForObjectFamily(family)||undefined)}>Find another Core name →</button>
      </div>}
      {pageError&&<p className="warning-box" role="alert">UNKNOWN · Core Objects & Groups page unavailable: {pageError}. Existing observed names remain visible.</p>}
      {availableTypes.length>0&&<div className="toolbar" role="group" aria-label="Object inventory pagination">
        {availableTypes.map(type=><button key={type} type="button" className="secondary"
          disabled={!!busyType} onClick={()=>loadObjectPage(type)}>
          {busyType===type?"Loading "+type+"…":"Load more "+type.replaceAll("-"," ")+" →"}
        </button>)}
      </div>}
      {!rows.length?<div className="dr-empty-state"><span className="dr-empty-icon"><WorkspaceIcon kind="infrastructure"/></span>
        <strong>{incomplete?"Core resource evidence UNKNOWN":truncated?"No match in loaded Core resources":"No matching objects"}</strong>
        <p>{incomplete?"A failed or malformed inventory read does not prove an object is missing.":
          truncated?"Other names may exist beyond this first page. Use Find another Core name for a fresh Core search.":
          "Create or adjust a reusable object below, or change the current filter."}</p>
      </div>:<div className="dr-table-scroll"><table className="dr-resource-table"><thead><tr><th>Name</th><th>Kind</th><th>Type</th><th>Status</th><th>Description</th></tr></thead><tbody>{rows.map((item:any)=><tr key={item.resource_type+":"+item.id} tabIndex={0} onClick={()=>setSelected(item)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelected(item)}}}><td><strong>{item.name||item.id}</strong><small>{item.id}</small></td><td>{item.resource_type}</td><td>{item.type||"—"}</td><td>{item.status||item.credential_status||(item.enabled===undefined?"—":item.enabled?"Enabled":"Disabled")}</td><td>{item.description||"—"}</td></tr>)}</tbody></table></div>}
    </section>
    {selected&&<div className="dr-drawer-backdrop" onMouseDown={e=>{if(e.currentTarget===e.target)setSelected(null)}}><aside className="dr-detail-drawer" role="dialog" aria-modal="true" aria-label="Object detail" tabIndex={-1} autoFocus><header><div><p className="dr-eyebrow">{selected.resource_type}</p><h2>{selected.name||selected.id}</h2><p>{selected.id}</p></div><button className="dr-icon-button" onClick={()=>setSelected(null)} aria-label="Close detail">×</button></header><div className="dr-detail-fields">{Object.entries(selected).filter(([,value])=>typeof value!=="object"&&value!==null&&value!=="").map(([key,value])=><div key={key}><span>{key.replaceAll("_"," ")}</span><strong>{String(value)}</strong></div>)}</div><footer><button className="primary" onClick={()=>{setSelected(null);onNavigate?.("policies","access")}}>Use in policy</button></footer></aside></div>}
  </div>;
}

function PolicyWorkspace({data,operator,onNavigate,api,context}:{data:any,operator:any,onNavigate?:(id:string,groupId?:string,context?:any)=>void,api:(path:string)=>Promise<any>,context?:any}){
  const focusPlane=["remote","internet","ai"].includes(context?.focusPolicy?.plane)
    ?String(context.focusPolicy.plane) as AccessPlane:null;
  const carriedPlane=["remote","internet","ai"].includes(String(context?.plane))
    ?String(context.plane) as AccessPlane:focusPlane;
  const carriedFlow=carriedPlane?connectionReviewContext(
    carriedPlane,context?.source,context?.destination,context?.selector):null;
  const focusName=typeof context?.focusPolicy?.name==="string"&&context.focusPolicy.name.length<=160
    ?context.focusPolicy.name:"";
  const [plane,setPlane]=useState<string>(focusPlane||carriedPlane||"all"),[filter,setFilter]=useState(focusName),[selected,setSelected]=useState<any>(null);
  const [additional,setAdditional]=useState<any[]>([]);
  const [nextByPlane,setNextByPlane]=useState<Record<string,string|null>>(data.next_cursor_by_plane||{});
  const [exhausted,setExhausted]=useState<string[]>([]);
  const [loadingPlane,setLoadingPlane]=useState(""),[pageError,setPageError]=useState("");
  const pageEpoch=useRef(0);
  useEscapeClose(!!selected,()=>setSelected(null));
  useEffect(()=>{
    setAdditional([]);setNextByPlane(data.next_cursor_by_plane||{});
    setExhausted([]);setPageError("");setLoadingPlane("");
    return()=>{pageEpoch.current+=1};
  },[data]);
  async function loadMore(planeName:string){
    const cursor=nextByPlane[planeName];
    if(loadingPlane||!cursor)return;
    const generation=++pageEpoch.current;
    setLoadingPlane(planeName);setPageError("");
    try{
      const query="/api/v1/policies?plane="+planeName+"&limit=100&cursor="+encodeURIComponent(cursor);
      const page=requireObservedMenuPayload("policies",await api(query));
      if(generation!==pageEpoch.current)return;
      if(page.plane!==planeName||page.limit!==100
        ||page.items.length>100||page.items.some((row:any)=>row.plane!==planeName))
        throw new Error("Core policy page belongs to another access plane. State is UNKNOWN.");
      const seen=new Set([...data.items,...additional].map((row:any)=>row.plane+":"+row.id));
      const fresh=page.items.filter((row:any)=>!seen.has(row.plane+":"+row.id));
      setAdditional(previous=>[...previous,...fresh]);
      setNextByPlane(previous=>({...previous,[planeName]:page.next_cursor||null}));
      if(!page.next_cursor)setExhausted(previous=>[...new Set([...previous,planeName])]);
    }catch(e:any){
      if(generation===pageEpoch.current)setPageError(e.message||String(e));
    }finally{
      if(generation===pageEpoch.current)setLoadingPlane("");
    }
  }
  const q=filter.trim().toLowerCase();
  const partial=isPartialCorePage(data);
  const limitedPlanes=(Array.isArray(data.possibly_truncated_planes)?data.possibly_truncated_planes:[])
    .filter((kind:string)=>!exhausted.includes(kind));
  const selectedMayBeLimited=limitedPlanes.some((kind:string)=>plane==="all"||plane===kind);
  const focusComplete=!!focusPlane&&!limitedPlanes.includes(focusPlane)&&!nextByPlane[focusPlane];
  const focusedPolicy=focusPlane&&focusName?resolveCompletePolicyMatch(
    [...(data.items||[]),...additional],focusPlane,focusName,focusComplete):null;
  const rows=[...(data.items||[]),...additional].filter((item:any)=>
    (plane==="all"||item.plane===plane)&&(!q||Object.values(item).some(v=>String(v??"").toLowerCase().includes(q))));
  const tabs=[["all","All"],["remote","Remote"],["internet","Internet"],["ai","AI"]];
  return <div className="dr-resource-workspace">
    <section className="dr-page-intro"><div><p className="dr-eyebrow">Access</p><h2>Policies</h2><p className="muted">One policy workspace with separate Remote, Internet and AI security semantics.</p></div><div className="dr-page-actions"><button className="secondary" onClick={()=>onNavigate?.("access","access",carriedFlow||undefined)}>Test & explain access</button>{operator.role!=="Read Only"&&<button className="primary" onClick={()=>onNavigate?.("drafts","access",carriedFlow||undefined)}>Draft change</button>}</div></section>
    <div className="dr-access-tabs" role="tablist" aria-label="Policy plane">{tabs.map(([id,label])=><button key={id} role="tab" aria-selected={plane===id} className={plane===id?"active":""} onClick={()=>setPlane(id)}>{label}</button>)}</div>
    {carriedFlow&&"source" in carriedFlow&&<section className="card dr-uxb-context" role="note" aria-label="Selected Core policy task">
      <strong>Selected {carriedFlow.plane.toUpperCase()} Access flow · reference only</strong>
      <p>Source: {carriedFlow.source} · Destination: {carriedFlow.destination}
        · {carriedFlow.plane==="ai"?"Permission":"Service"}: {carriedFlow.selector}</p>
      <p>The selected names are not an approved rule, current Core decision, or draft.
        Review the explicit Core Preview and required tests below before any change.</p>
    </section>}
    {focusPlane&&focusName&&plane===focusPlane&&<section className="card dr-uxb-context" role="status">
      <strong>Rule requested from a fresh Core access trace: {focusName}</strong>
      <p>Trace rule names are not policy IDs. A detail link is available only when the entire
        {focusPlane.toUpperCase()} Core policy list proves exactly one matching name and identifier.</p>
      {focusedPolicy?<button type="button" className="primary" onClick={()=>setSelected(focusedPolicy)}>
        Open verified policy detail →</button>:
        <p className="muted">{focusComplete?"Exact rule identity is missing or ambiguous in Core policy inventory.":
          "Policy inventory is incomplete. Load remaining Core pages before resolving this rule."}</p>}
    </section>}
    <section className="card dr-list-card"><div className="dr-list-toolbar"><div><strong>{rows.length}</strong><span>policy rules</span></div><label className="dr-filter-field"><WorkspaceIcon kind="search"/><input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter policies…"/>{filter&&<button onClick={()=>setFilter("")} aria-label="Clear filter">×</button>}</label></div>
      {(partial||selectedMayBeLimited)&&<p className="dr-uxb-catalog-page-notice" role="status">Core policy list may be incomplete · {limitedPlanes.length?limitedPlanes.map((kind:string)=>kind.toUpperCase()).join(", ")+" reached the per-plane 100-rule API limit.": "Additional rules exist beyond the loaded page."} Filters inspect only loaded rules. Use Search to find a specific policy.</p>}
      {pageError&&<p className="warning-box" role="alert">Core policy page unavailable: {pageError}. Existing rows remain visible; retry Load more.</p>}
      {Object.entries(nextByPlane).filter(([kind,cursor])=>!!cursor&&(plane==="all"||plane===kind)).map(([kind])=>
        <button key={kind} type="button" className="secondary" disabled={!!loadingPlane}
          onClick={()=>loadMore(kind)}>{loadingPlane===kind?"Loading "+kind+" rules…":"Load more "+kind+" rules →"}</button>)}
      {!rows.length?<div className="dr-empty-state"><span className="dr-empty-icon"><WorkspaceIcon kind="access"/></span><strong>{partial||selectedMayBeLimited?"No match in loaded policy rules":"No matching policy rules"}</strong><p>{partial||selectedMayBeLimited?"Other rules may exist beyond the fetched Core policy pages. Use Search for a specific policy.":"Change the filter or use the guided policy controls below."}</p></div>:<div className="dr-table-scroll"><table className="dr-resource-table"><thead><tr><th>Policy</th><th>Plane</th><th>Action</th><th>State</th><th>Expires</th><th>Description</th></tr></thead><tbody>{rows.map((item:any)=><tr key={(item.plane||"policy")+":"+item.id} tabIndex={0} onClick={()=>setSelected(item)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelected(item)}}}><td><strong>{item.name||item.id}</strong><small>{item.id}</small></td><td>{item.plane||"—"}</td><td>{item.action||"—"}</td><td><span className={policyStateLabel(item.enabled)==="Enabled"?"dr-state active":"dr-state"}><i/>{policyStateLabel(item.enabled)}</span></td><td>{policyExpiryLabel(item)}</td><td>{item.description||"—"}</td></tr>)}</tbody></table></div>}
    </section>
    {selected&&<div className="dr-drawer-backdrop" onMouseDown={e=>{if(e.currentTarget===e.target)setSelected(null)}}><aside className="dr-detail-drawer" role="dialog" aria-modal="true" aria-label="Policy detail" tabIndex={-1} autoFocus><header><div><p className="dr-eyebrow">{selected.plane||"Policy"} access</p><h2>{selected.name||selected.id}</h2><p>{selected.id}</p></div><button className="dr-icon-button" onClick={()=>setSelected(null)} aria-label="Close detail">×</button></header><div className="dr-drawer-status"><span className={policyStateLabel(selected.enabled)==="Enabled"?"dr-state active":"dr-state"}><i/>{policyStateLabel(selected.enabled)}</span></div><div className="dr-detail-fields">{Object.entries(selected).filter(([,value])=>typeof value!=="object"&&value!==null&&value!=="").map(([key,value])=><div key={key}><span>{key.replaceAll("_"," ")}</span><strong>{String(value)}</strong></div>)}</div><footer><button className="secondary" onClick={()=>{const target={originId:String(selected.id||selected.name||""),originType:"access-rule"};setSelected(null);onNavigate?.("audit","activity",target)}}>Recent activity</button><button className="primary" onClick={()=>{const target={originId:String(selected.id||selected.name||""),originType:"access-rule",plane:selected.plane||"remote",source:String(selected.source||""),destination:String(selected.destination||""),selector:String(selected.plane==="ai"?selected.permission||"":selected.service||"")};setSelected(null);onNavigate?.("access","access",target)}}>Why allowed / denied?</button></footer></aside></div>}
  </div>;
}

function ResourceWorkspace({kind,data,operator,onNavigate,api,initialFilter="",initialAdmission="all"}:{kind:"host"|"service",data:any,operator:any,onNavigate?:(id:string,groupId?:string,context?:any)=>void,api:(path:string)=>Promise<any>,initialFilter?:string,initialAdmission?:unknown}){
  const isHost=kind==="host";
  const [filter,setFilter]=useState(initialFilter),[selected,setSelected]=useState<any>(null);
  useEffect(()=>{setFilter(initialFilter)},[kind,initialFilter]);
  const [admissionFilter,setAdmissionFilter]=useState<HostAdmission>(isHost&&isSavedAdmission(initialAdmission)?initialAdmission:"all");
  useEffect(()=>{setAdmissionFilter(isHost&&isSavedAdmission(initialAdmission)?initialAdmission:"all")},[isHost,initialAdmission]);
  const [loaded,setLoaded]=useState<any[]>(data.items||[]);
  const [cursor,setCursor]=useState<string|null>(isPartialCorePage(data)?data.next_cursor:null);
  const [moreBusy,setMoreBusy]=useState(false),[moreError,setMoreError]=useState("");
  const [pagesLoaded,setPagesLoaded]=useState(1);
  const loadEpoch=useRef(0);
  useEscapeClose(!!selected,()=>setSelected(null));
  useEffect(()=>{
    loadEpoch.current+=1;setLoaded(data.items||[]);
    setCursor(isPartialCorePage(data)?data.next_cursor:null);
    setMoreBusy(false);setMoreError("");setPagesLoaded(1);setSelected(null);
    return()=>{loadEpoch.current+=1};
  },[kind,data]);
  const partial=!!cursor;
  async function loadMore(){
    const requestedCursor=cursor;
    if(!requestedCursor||moreBusy)return;
    const epoch=++loadEpoch.current;
    setMoreBusy(true);setMoreError("");
    try{
      const type=isHost?"managed-host":"remote-service";
      const route=isHost?"hosts":"services";
      const path="/api/v1/inventory?resource_type="+type+"&limit=100&cursor="+encodeURIComponent(requestedCursor);
      const page=requireObservedInventoryContinuation(route,await api(path),requestedCursor,100);
      if(epoch!==loadEpoch.current)return;
      const seen=new Set(loaded.map((item:any)=>item.id));
      const fresh=page.items.filter((item:any)=>!seen.has(item.id));
      if(page.items.length&&!fresh.length)
        throw new Error("Core returned only previously loaded resources. State is UNKNOWN; retry the page.");
      setLoaded(previous=>[...previous,...fresh]);
      setCursor(isPartialCorePage(page)?page.next_cursor:null);
      setPagesLoaded(previous=>previous+1);
    }catch(e:any){
      if(epoch===loadEpoch.current)setMoreError(e.message||String(e));
    }finally{
      if(epoch===loadEpoch.current)setMoreBusy(false);
    }
  }
  // Typed Host search is expressly limited to already authorized/loaded Core
  // inventory pages. Core currently supports name-only server-side query.
  const hostSearch=isHost?filterObservedHosts(loaded,filter,admissionFilter):null;
  const q=filter.trim().toLowerCase();
  const rows=(isHost?(hostSearch?.items||loaded):loaded
    .filter((item:any)=>!q||Object.values(item).some(value=>String(value??"").toLowerCase().includes(q))))
    .sort((a:any,b:any)=>isHost?
      (a.admission_state==="PENDING_APPROVAL"?-1:a.admission_state==="QUARANTINED"?0:1)
      -(b.admission_state==="PENDING_APPROVAL"?-1:b.admission_state==="QUARANTINED"?0:1):0);
  const heading=isHost?"Managed Hosts":"Remote Services";
  const description=isHost?"Agent inventory, trust, connectivity, platform and version in one resource workspace.":"Published services, owning hosts, ports and release state with contextual access actions.";
  const savedDraft=(!isHost||!hostSearch?.error)
    ?saveDraftForResource(kind,filter,isHost?admissionFilter:"all"):null;
  return <div className="dr-resource-workspace">
    <section className="dr-page-intro"><div><p className="dr-eyebrow">Connections</p><h2>{heading}</h2><p className="muted">{description}</p></div><div className="dr-page-actions">{isHost&&operator.role==="Admin"&&<button className="primary" onClick={()=>onNavigate?.("enrollments","infrastructure")}>Connect Agent</button>}<button className="secondary" onClick={()=>onNavigate?.("access","access")}>Access workspace</button></div></section>
    <section className="card dr-list-card">
      <div className="dr-list-toolbar"><div><strong>{rows.length}</strong><span>{heading.toLowerCase()}</span></div>
        {isHost&&<select aria-label="Filter Managed Host admission" value={admissionFilter} onChange={e=>setAdmissionFilter(isSavedAdmission(e.target.value)?e.target.value:"all")}>
          <option value="all">All admission states</option>
          <option value="PENDING_APPROVAL">Pending approval</option>
          <option value="APPROVED">Approved</option>
          <option value="QUARANTINED">Quarantined</option>
        </select>}
        <label className="dr-filter-field"><WorkspaceIcon kind="search"/><input value={filter} maxLength={120} onChange={e=>setFilter(e.target.value)} placeholder={isHost?"Filter hosts (name:, host:, os:, admission:)…":"Filter services…"}/>{filter&&<button onClick={()=>setFilter("")} aria-label="Clear filter">×</button>}</label></div>
      {isHost&&hostSearch?.error&&<p className="warning-box" role="alert">Typed Host search not applied: {hostSearch.error} Displaying only previously loaded Core records, still scoped by admission state.</p>}
      {isHost&&hostSearch?.warning&&<p className="dr-uxb-catalog-page-notice" role="status">{hostSearch.warning}</p>}
      {savedDraft&&<div className="toolbar"><button type="button" className="secondary"
        onClick={()=>onNavigate?.("views","activity",{savedViewDraft:savedDraft})}>Save this view →</button>
        <span className="muted">Saves the visible text filter and optional Host admission selection as a private display preference after you name it. Unloaded Core inventory pages are not included.</span></div>}
      {partial&&<p className="dr-uxb-catalog-page-notice" role="status">Partial Core inventory · more {isHost?"Managed Hosts":"Remote Services"} exist beyond the loaded pages. Filters check loaded rows only. Load more to inspect additional Core records.</p>}
      {moreError&&<p className="warning-box" role="alert">UNKNOWN · Next Core inventory page unavailable: {moreError} Existing observed resources remain visible.</p>}
      <div className="toolbar" role="status">
        <span>{loaded.length} Core records observed in {pagesLoaded} page{pagesLoaded===1?"":"s"} · not a total inventory count</span>
        {partial&&<button type="button" className="secondary" disabled={moreBusy}
          onClick={loadMore}>{moreBusy?"Loading next Core page…":isHost?"Load more Managed Hosts →":"Load more Remote Services →"}</button>}
      </div>
      {!isHost&&<p className="muted">Enabled means configuration is selected, not that an Agent job completed
        or the service is reachable. Check Core access evidence and actual Agent/client activity separately.</p>}
      {isHost&&<p className="muted">Host table: Last activity is the Core last_seen observation, not the Agent heartbeat.
        Unrecognized or missing trust, platform, version and activity facts remain UNKNOWN.
        View a Host for its separate heartbeat, approval and connection evidence.</p>}
      {!rows.length?<div className="dr-empty-state"><span className="dr-empty-icon"><WorkspaceIcon kind="infrastructure"/></span><strong>{isHost&&hostSearch?.error?"Search not applied":isHost&&!!hostSearch?.unknownCount&&!!filter?"No confirmed match in observed Hosts":partial?"No match in loaded resources":filter?"No matching resources":"No resources yet"}</strong><p>{isHost&&hostSearch?.error?"Correct the unsupported filter; no unobserved Core data was searched.":isHost&&!!hostSearch?.unknownCount&&!!filter?"Some loaded Hosts have UNKNOWN values for that field. No-match does not prove their absence.":partial?"Other resources may exist beyond this Core page. Use Search to find them.":filter?"Try a different filter.":isHost?"Connect an Agent to populate managed inventory.":"Publish a Remote Service from a managed host."}</p>{!filter&&isHost&&operator.role==="Admin"&&<button className="primary" onClick={()=>onNavigate?.("enrollments","infrastructure")}>Connect Agent</button>}</div>:
      <div className="dr-table-scroll"><table className="dr-resource-table"><thead><tr>{isHost?<><th>Host</th><th>Admission</th><th>Connection</th><th>Trust</th><th>Platform</th><th>Version</th><th>Last activity</th></>:<><th>Service</th><th>Managed host</th><th>Type</th><th>Public port</th><th>Target</th><th>State</th></>}</tr></thead><tbody>{rows.map((item:any)=><tr key={item.id} tabIndex={0} onClick={()=>setSelected(item)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setSelected(item)}}}>{isHost?<><td><strong>{hostVisibleIdentity(item).primary}</strong><small>{hostVisibleIdentity(item).secondary}</small></td><td><span className={item.admission_state==="APPROVED"?"dr-state active":"dr-state"}><i/>{item.admission_state==="APPROVED"?"Approved":item.admission_state==="PENDING_APPROVAL"?"Pending approval":item.admission_state==="QUARANTINED"?"Quarantined":"Unknown"}</span></td><td><span className={hostConnectionState(item)==="Connected"?"dr-state active":"dr-state"}><i/>{hostConnectionState(item)}</span></td><td>{hostInventoryFacts(item).trust}</td><td>{hostInventoryFacts(item).platform}</td><td>{hostInventoryFacts(item).version}</td><td title="Last Core activity; Agent heartbeat is separate">{hostInventoryFacts(item).lastActivity}</td></>:<><td><strong>{serviceVisibleIdentity(item).primary}</strong><small>{serviceVisibleIdentity(item).secondary}</small></td><td>{item.managed_host||item.managed_host_id||"—"}</td><td>{item.service_type||"—"}</td><td>{item.public_port??"—"}</td><td>{[item.target_host,item.target_port].filter(Boolean).join(":")||item.target_mode||"—"}</td><td><span className={serviceStateLabel(item)==="Enabled"?"dr-state active":"dr-state"}><i/>{serviceStateLabel(item)}</span></td></>}</tr>)}</tbody></table></div>}
    </section>
    {selected&&<div className="dr-drawer-backdrop" onMouseDown={e=>{if(e.currentTarget===e.target)setSelected(null)}}><aside className="dr-detail-drawer" role="dialog" aria-modal="true" aria-label={heading+" detail"} tabIndex={-1} autoFocus><header><div><p className="dr-eyebrow">{isHost?"Managed Host":"Remote Service"}</p><h2>{isHost?hostVisibleIdentity(selected).primary:serviceVisibleIdentity(selected).primary}</h2><p>{isHost?hostVisibleIdentity(selected).secondary:serviceVisibleIdentity(selected).secondary}</p></div><button className="dr-icon-button" onClick={()=>setSelected(null)} aria-label="Close detail">×</button></header><div className="dr-drawer-status"><span className={(isHost?hostConnectionState(selected)==="Connected":serviceStateLabel(selected)==="Enabled")?"dr-state active":"dr-state"}><i/>{isHost?hostConnectionState(selected):serviceStateLabel(selected)}</span>{isHost&&<span className={selected.admission_state==="APPROVED"?"dr-state active":"dr-state"}>{selected.admission_state==="PENDING_APPROVAL"?"Pending approval":selected.admission_state==="QUARANTINED"?"Quarantined":selected.admission_state==="APPROVED"?"Approved":"Unknown admission"}</span>}</div><div className="dr-detail-fields">{isHost?hostDetailSections(selected).map(section=><section key={section.title} className="dr-host-detail-section"><h3>{section.title}</h3>{section.fields.map(field=><div key={field.label}><span>{field.label}</span><strong>{field.value}</strong></div>)}</section>):serviceDetailSections(selected).map(section=><section key={section.title} className="dr-host-detail-section">
  <h3>{section.title}</h3>{section.fields.map(field=><div key={field.label}>
    <span>{field.label}</span><strong>{field.value}</strong></div>)}</section>)}</div><footer><button className="secondary" onClick={()=>{const target={originType:isHost?"managed-host":"remote-service",originId:String(selected.id||"")};setSelected(null);onNavigate?.("audit","activity",target)}}>Recent activity</button><button className="primary" onClick={()=>{const target={originType:isHost?"managed-host":"remote-service",originId:String(selected.id||""),plane:"remote"};setSelected(null);onNavigate?.("access","access",target)}}>Why can / cannot connect?</button></footer></aside></div>}
  </div>;
}

function UsersPanel({operator}:{operator:any}){
  const [data,setData]=useState<any>(null),[error,setError]=useState(""),[busy,setBusy]=useState("");
  const [loading,setLoading]=useState(true);
  const [newUsername,setNewUsername]=useState(""),[newPassword,setNewPassword]=useState(""),[newRole,setNewRole]=useState("Read Only");
  async function refresh(){
    setLoading(true);setError("");
    try{setData(requireObservedMenuPayload("users",await api("/api/v1/operators")))}
    catch(e:any){setData(null);setError(e.message||String(e))}
    finally{setLoading(false)}
  }
  useEffect(()=>{refresh()},[]);
  async function setMfa(id:string,required:boolean){
    setBusy(id);setError("");
    try{
      await api("/api/v1/operators/"+encodeURIComponent(id)+"/mfa",{method:"POST",body:JSON.stringify({required})});
      if(id===operator.id){window.location.reload();return}
      await refresh();
    }catch(e:any){setError(e.message||String(e))}finally{setBusy("")}
  }
  async function createUser(e:any){
    e.preventDefault();setBusy("create");setError("");
    try{await api("/api/v1/operators",{method:"POST",body:JSON.stringify({username:newUsername,password:newPassword,role:newRole})});setNewUsername("");setNewPassword("");setNewRole("Read Only");await refresh()}
    catch(e:any){setError(e.message||String(e))}finally{setBusy("")}
  }
  if(!data)return <section className="card" role={loading?"status":"alert"}>
    <h3>Web Users · {loading?"Loading":"UNKNOWN"}</h3>
    <p>{loading?"Reading authorized Core user inventory…":error||"Users inventory unavailable. No empty result was confirmed."}</p>
    {!loading&&<button type="button" className="secondary" onClick={refresh}>Retry Users read →</button>}
  </section>;
  return <>{error&&<div className="error" role="alert">{error}</div>}<div className="card">
    <h3>Web Users</h3>
    <form className="toolbar" onSubmit={createUser}><input value={newUsername} onChange={e=>setNewUsername(e.target.value)} placeholder="Username" autoComplete="off"/><input type="password" value={newPassword} onChange={e=>setNewPassword(e.target.value)} placeholder="Initial password" autoComplete="new-password"/><select value={newRole} onChange={e=>setNewRole(e.target.value)}><option>Read Only</option><option>Operator</option><option>Admin</option></select><button className="primary" type="submit" disabled={busy==="create"||!newUsername||!newPassword}>{busy==="create"?"Creating…":"Create user"}</button></form>
    <div className="muted">MFA is disabled by default. Enable it per user. Enabling MFA revokes that user's active sessions; on the next password sign-in the user completes TOTP setup and receives recovery codes directly.</div>
    <table><thead><tr><th>User</th><th>Role</th><th>Status</th><th>MFA</th><th>Last login</th><th>Action</th></tr></thead><tbody>
      {(data.items||[]).map((x:any)=>{const mfa=x.mfa_required?(x.mfa_enrolled?"Enabled":"Setup pending"):"Disabled";return <tr key={x.id}><td>{x.username}{x.recovery_admin?" · recovery admin":""}</td><td>{x.role}</td><td>{x.enabled?"Enabled":"Disabled"}</td><td>{mfa}</td><td>{x.last_login_at||"-"}</td><td><button className={x.mfa_required?"secondary":"primary"} disabled={busy===x.id} onClick={()=>setMfa(x.id,!x.mfa_required)}>{x.mfa_required?"Disable MFA":"Enable MFA"}</button></td></tr>})}
    </tbody></table>
  </div></>;
}

function IntegrationsPanel(){
  const [accounts,setAccounts]=useState<any[]>([]),[hooks,setHooks]=useState<any[]>([]);
  const [inventoryState,setInventoryState]=useState<"loading"|"ready"|"unknown">("loading");
  const [error,setError]=useState(""),[busy,setBusy]=useState(false),[once,setOnce]=useState<any>(null);
  const [accountName,setAccountName]=useState(""),[accountExpiry,setAccountExpiry]=useState("");
  const [permissions,setPermissions]=useState<string[]>(["management-read"]);
  const [hookName,setHookName]=useState(""),[hookUrl,setHookUrl]=useState("");
  const [hookEvent,setHookEvent]=useState("attention");
  const allowedPermissions=["management-read","management-diagnose","management-policy-test","management-job-observe"];
  async function refresh(){
    setInventoryState("loading");setError("");
    try{
      const [a,w]=await Promise.all([api("/api/v1/service-accounts"),api("/api/v1/webhooks")]);
      const accountsPage=requireObservedMenuPayload("service-accounts",a);
      const hooksPage=requireObservedMenuPayload("webhooks",w);
      setAccounts(accountsPage.items);setHooks(hooksPage.items);
      setInventoryState("ready");
    }catch(e:any){
      setAccounts([]);setHooks([]);setInventoryState("unknown");
      setError(e.message||String(e));
    }
  }
  useEffect(()=>{refresh()},[]);
  async function mutate(path:string,body:any,secretKind?:string){
    setBusy(true);setError("");setOnce(null);
    try{
      const result=await api(path,{method:"POST",body:JSON.stringify(body)});
      if(secretKind)setOnce({kind:secretKind,secret:result.credential||result.secret,id:result.id||result.credential_id});
      await refresh();
    }catch(e:any){setError(e.message||String(e))}finally{setBusy(false)}
  }
  async function createAccount(e:React.FormEvent){
    e.preventDefault();if(!accountName||!permissions.length)return;
    await mutate("/api/v1/service-accounts",{name:accountName,permissions,expires_at:accountExpiry?new Date(accountExpiry).toISOString():undefined},"Service Account token");
    setAccountName("");setAccountExpiry("");
  }
  async function createWebhook(e:React.FormEvent){
    e.preventDefault();if(!hookName||!hookUrl)return;
    await mutate("/api/v1/webhooks",{name:hookName,url:hookUrl,event_classes:[hookEvent]},"Webhook signing secret");
    setHookName("");setHookUrl("");
  }
  return <div>
    <section className="dr-page-intro"><div><p className="dr-eyebrow">Administration</p><h2>Integrations</h2><p className="muted">Manage scoped non-human API access and optional signed HTTPS events. Web login credentials and these integration secrets are never shared.</p></div></section>
    {error&&<div className="error">{error}</div>}
    {once&&<div className="card" role="status"><h3>Copy once: {once.kind}</h3><p className="muted">This value will not appear in inventory or after a refresh. Store it in an approved secret manager.</p>
      <div className="toolbar"><input aria-label="One-time integration secret" readOnly value={once.secret} style={{minWidth:320,flex:1}}/><button className="secondary" onClick={()=>navigator.clipboard?.writeText(once.secret)}>Copy</button><button className="primary" onClick={()=>setOnce(null)}>Done</button></div></div>}
    {inventoryState!=="ready"?<section className="card" role={inventoryState==="loading"?"status":"alert"}>
      <h3>Integration inventory · {inventoryState==="loading"?"Loading":"UNKNOWN"}</h3>
      <p>{inventoryState==="loading"?"Reading authorized integration inventory…":error||"Core API inventory is unavailable. No empty list has been confirmed."}</p>
      {inventoryState==="unknown"&&<button type="button" className="secondary" onClick={refresh}>Retry integrations read →</button>}
    </section>:<>
    <section className="card"><h3>Service Accounts</h3><p className="muted">The public Automation API uses Bearer tokens, per-account rate limits and explicit read-only Core operations in this phase.</p>
      <form onSubmit={createAccount}><div className="toolbar"><input value={accountName} onChange={e=>setAccountName(e.target.value)} placeholder="Account name" required/><input type="datetime-local" value={accountExpiry} onChange={e=>setAccountExpiry(e.target.value)} title="Optional token expiry"/></div>
        <div className="toolbar">{allowedPermissions.map(p=><label key={p}><input type="checkbox" checked={permissions.includes(p)} onChange={e=>setPermissions(a=>e.target.checked?[...a,p]:a.filter(x=>x!==p))}/>{p}</label>)}</div>
        <button className="primary" disabled={busy||!accountName||!permissions.length} type="submit">Create Service Account</button>
      </form>
      <table><thead><tr><th>Account</th><th>Permissions</th><th>Expires</th><th>Status</th><th>Actions</th></tr></thead><tbody>{accounts.map(a=><tr key={a.id}><td>{a.name}</td><td>{(a.permissions||[]).join(", ")}</td><td>{a.expires_at||"No expiry"}</td><td>{a.enabled?"Active":"Revoked"}</td><td>{a.enabled&&<><button className="secondary" disabled={busy} onClick={()=>mutate("/api/v1/service-accounts/rotate",{account_id:a.id},"Rotated Service Account token")}>Rotate</button><button className="danger" disabled={busy} onClick={()=>{if(window.confirm("Revoke this Service Account now?"))mutate("/api/v1/service-accounts/revoke",{account_id:a.id})}}>Revoke</button></>}</td></tr>)}</tbody></table>
    </section>
    <section className="card"><h3>Signed Event Webhooks</h3><p className="muted">HTTPS only, certificate-verified and DNS-pinned. Failed deliveries use bounded retries; event delivery never controls access enforcement.</p>
      <form className="toolbar" onSubmit={createWebhook}><input value={hookName} onChange={e=>setHookName(e.target.value)} placeholder="Endpoint name" required/><input value={hookUrl} onChange={e=>setHookUrl(e.target.value)} placeholder="https://hooks.example.com/events" required type="url"/><select value={hookEvent} onChange={e=>setHookEvent(e.target.value)}><option value="attention">Attention</option><option value="security.lifecycle">Security lifecycle</option><option value="policy.change">Policy change</option><option value="managed_host.lifecycle">Managed Host lifecycle</option></select><button className="primary" disabled={busy||!hookName||!hookUrl} type="submit">Add webhook</button></form>
      <table><thead><tr><th>Endpoint</th><th>URL</th><th>Events</th><th>Status</th><th>Delivery</th><th>Actions</th></tr></thead><tbody>{hooks.map(h=><tr key={h.id}><td>{h.name}</td><td>{h.url}</td><td>{(h.event_classes||[]).join(", ")}</td><td>{h.enabled?"Enabled":"Disabled"}</td><td>{Object.entries(h.delivery_counts||{}).map(([k,v])=>k+":"+v).join(" · ")||"—"}</td><td>{h.enabled&&<><button className="secondary" disabled={busy} onClick={()=>mutate("/api/v1/webhooks/rotate",{webhook_id:h.id},"Rotated Webhook secret")}>Rotate</button><button className="danger" disabled={busy} onClick={()=>{if(window.confirm("Disable this webhook and fail queued deliveries?"))mutate("/api/v1/webhooks/disable",{webhook_id:h.id})}}>Disable</button></>}</td></tr>)}</tbody></table>
    </section>
    </>}
  </div>;
}

function CommandCenter({data,operator,onNavigate}:{data:any,operator:any,onNavigate?:(id:string,groupId?:string,context?:any)=>void}){
  const [activity,setActivity]=useState<RecentFeed>({status:"loading",items:[]});
  const [changes,setChanges]=useState<RecentFeed>({status:"loading",items:[]});
  useEffect(()=>{
    let cancelled=false;
    Promise.allSettled([api("/api/v1/audit?limit=6"),api("/api/v1/revisions?limit=6")]).then(results=>{
      if(cancelled)return;
      const [auditResult,revisionResult]=results;
      setActivity(observedRecentFeed(auditResult));
      setChanges(observedRecentFeed(revisionResult));
    });
    return()=>{cancelled=true};
  },[]);
  const h=data.overview?.managed_hosts||{},svc=data.overview?.remote_services||{},j=data.overview?.management_jobs||{},pol=data.overview?.policies||{};
  const attention=Array.isArray(data.attention?.items)?data.attention.items:null;
  const observed=observedNumber;
  const policyRows=[
    {label:"Remote Access",key:"remote",value:pol.remote||{}},
    {label:"Internet Access",key:"internet",value:pol.internet||{}},
    {label:"AI Access",key:"ai",value:pol.ai||{}},
  ];
  if(isFreshInstallation(data))return <div className="dr-command-center dr-uxb-first-install" data-testid="uxb-fresh-home">
    <section className="dr-hero-row"><div><p className="dr-eyebrow">Welcome · First connection</p>
      <h2>Start with one protected connection</h2>
      <p className="muted">Core reports no Managed Hosts, Remote Services or policy rules. Pick what you want to connect; the guide explains each step.</p></div>
      <button className="secondary" onClick={()=>onNavigate?.("health","activity")}>Check system readiness →</button>
    </section>
    <FirstUseHome data={data} operator={operator} api={api} onNavigate={onNavigate}/>
    <section className="card dr-uxb-first-install-note"><h3>No network access has been verified yet</h3>
      <p className="muted">Adding an Agent, publishing a service and allowing a source are separate actions. The final Core decision and actual connection must be verified independently.</p>
      <button type="button" className="secondary" onClick={()=>onNavigate?.("setup","connections")}>Open first-connection guide →</button>
    </section>
  </div>;
  return <div className="dr-command-center">
    <section className="dr-hero-row"><div><p className="dr-eyebrow">Welcome · Data Relay Link</p><h2>Connect one service. Control who can use it.</h2><p className="muted">Start with the steps below, or inspect the existing Core status and activity.</p></div><div className="dr-hero-actions">{operator.role==="Admin"&&<button className="primary" onClick={()=>onNavigate?.("setup","connections")}>Set up a connection →</button>}<button className="secondary" onClick={()=>onNavigate?.("access","access")}>Test access</button></div></section>
    <FirstUseHome data={data} operator={operator} api={api} onNavigate={onNavigate}/>
    <section className="dr-kpi-strip"><div><span>Managed Hosts</span><strong>{observed(h.total)}</strong><small>{observed(h.connected)} connected</small></div><div><span>Remote Services</span><strong>{observed(svc.total)}</strong><small>{observed(svc.enabled)} enabled</small></div><div><span>Active Jobs</span><strong>{observed(j.active_jobs)}</strong><small>{observed(j.failed_jobs)} failed</small></div><div><span>Needs Attention</span><strong>{attention?attention.length:"UNKNOWN"}</strong><small>{!attention?"Core attention evidence unavailable":attention.some((x:any)=>x.severity==="critical")?"Critical item present":"Current findings"}</small></div></section>
    <div className="dr-overview-columns">
      <section className="card dr-attention-card"><div className="dr-section-head"><div><p className="dr-eyebrow">Posture</p><h3>Needs Attention</h3></div><button className="dr-text-action" onClick={()=>onNavigate?.("doctor","observability")}>Troubleshoot →</button></div>{!attention?<div className="dr-compact-empty">UNKNOWN · Core attention evidence unavailable. Check System Health.</div>:attention.length?<div className="dr-attention-list">{attention.slice(0,8).map((x:any)=><div className="dr-attention-row" key={x.kind}><span className={"dr-severity-dot "+x.severity}/><span><strong>{x.label}</strong><small>{x.count} affected</small></span><span className={"badge "+x.severity}>{x.severity}</span></div>)}</div>:<div className="dr-good-state"><span className="dr-good-mark">✓</span><div><strong>No current attention items</strong><p>Core-derived checks are not reporting operator action.</p></div></div>}</section>
      <section className="card dr-access-card"><div className="dr-section-head"><div><p className="dr-eyebrow">Access</p><h3>Policy Coverage</h3></div><button className="dr-text-action" onClick={()=>onNavigate?.("access","access")}>Open workspace →</button></div><div className="dr-access-posture">{policyRows.map(row=><button key={row.key} onClick={()=>onNavigate?.("policies","access")}><span className="dr-access-icon"><WorkspaceIcon kind="access"/></span><span><strong>{row.label}</strong><small>{observed(row.value.enabled)} enabled of {observed(row.value.total)}</small></span><b>{observed(row.value.enabled)}</b></button>)}</div></section>
    </div>
    <div className="dr-overview-columns">
      <section className="card"><div className="dr-section-head"><div><p className="dr-eyebrow">Activity</p><h3>Recent Activity</h3></div><button className="dr-text-action" onClick={()=>onNavigate?.("audit","observability")}>Open audit →</button></div>{activity.status!=="ready"?<div className="dr-compact-empty" role="status">{activity.status==="loading"?"Loading recent activity…":"UNKNOWN · Recent Activity unavailable. Open Audit to retry."}</div>:activity.items.length?<div className="dr-activity-list">{activity.items.map((item:any,i:number)=><button key={item.event_id||item.id||i} onClick={()=>onNavigate?.("audit","observability")}><span className={item.result==="deny"||item.result==="failed"?"dr-activity-mark warning":"dr-activity-mark"}/><span><strong>{item.event_type||item.action||item.operation||"Activity"}</strong><small>{item.actor_id||item.actor||"system"} · {item.occurred_at||item.timestamp||""}</small></span><span>{item.result||item.category||""}</span></button>)}</div>:<div className="dr-compact-empty">No retained recent activity.</div>}</section>
      <section className="card"><div className="dr-section-head"><div><p className="dr-eyebrow">Configuration</p><h3>Recent Changes</h3></div><button className="dr-text-action" onClick={()=>onNavigate?.("revisions","operations")}>Change history →</button></div>{changes.status!=="ready"?<div className="dr-compact-empty" role="status">{changes.status==="loading"?"Loading recent changes…":"UNKNOWN · Change History unavailable. Open Change history to retry."}</div>:changes.items.length?<div className="dr-activity-list">{changes.items.map((item:any,i:number)=><button key={item.revision||item.id||i} onClick={()=>onNavigate?.("revisions","operations")}><span className="dr-change-index">{item.revision??"#"}</span><span><strong>{item.summary||item.message||item.operation||"Configuration revision"}</strong><small>{item.actor||item.actor_id||"system"} · {item.timestamp||item.created_at||""}</small></span><span>→</span></button>)}</div>:<div className="dr-compact-empty">No retained configuration changes.</div>}</section>
    </div>
    <section className="card dr-quick-actions"><div className="dr-section-head"><div><p className="dr-eyebrow">Workspace</p><h3>Common Tasks</h3></div></div><div className="dr-action-grid"><button onClick={()=>onNavigate?.("hosts","infrastructure")}><WorkspaceIcon kind="infrastructure"/><span><strong>Inspect a host</strong><small>Connectivity, services, version, lifecycle</small></span></button><button onClick={()=>onNavigate?.("access","access")}><WorkspaceIcon kind="access"/><span><strong>Explain access</strong><small>Current use, policy test, cutoff state</small></span></button><button onClick={()=>onNavigate?.("audit","observability")}><WorkspaceIcon kind="observability"/><span><strong>Review activity</strong><small>Audit events and access decisions</small></span></button><button onClick={()=>onNavigate?.("system","administration")}><WorkspaceIcon kind="administration"/><span><strong>System readiness</strong><small>Backup, certificate, update, support</small></span></button></div></section>
  </div>;
}

function HealthWorkspace({data,onNavigate}:{data:any,onNavigate?:(id:string,groupId?:string)=>void}){
  const generations=data.generations||{};
  const jobs=data.management_jobs||{};
  const planes=["remote","internet","ai"].map(name=>({name,value:generations[name]||{}}));
  const coreStatus=coreHealthState(data);
  const coreHealthy=coreStatus==="Healthy";
  const configuredPlanes=accessPlaneCount(data);
  return <div className="dr-resource-workspace">
    <section className="dr-page-intro"><div><p className="dr-eyebrow">Activity & Health</p><h2>Health</h2><p className="muted">Core readiness, runtime generations and bounded management capacity without raw-debug-first presentation.</p></div><div className="dr-page-actions"><button className="secondary" onClick={()=>onNavigate?.("doctor","observability")}>Troubleshoot</button><button className="secondary" onClick={()=>onNavigate?.("system","administration")}>System readiness</button></div></section>
    <section className="dr-health-summary">
      <article className="card dr-health-card"><span>Core</span><strong className={coreHealthy?"healthy":"attention"}>{coreStatus}</strong><small>{coreStatus==="UNKNOWN"?"Core health evidence incomplete":data.mismatch?"Runtime generation mismatch":data.db_healthy?"Control database healthy":"Control database issue"}</small></article>
      <article className="card dr-health-card"><span>Control DB</span><strong className={data.db_healthy===true?"healthy":"critical-text"}>{typeof data.db_healthy!=="boolean"?"UNKNOWN":data.db_healthy?"Healthy":"Critical"}</strong><small>Schema {data.schema??"—"} · Revision {data.revision??"—"}</small></article>
      <article className="card dr-health-card"><span>Access planes</span><strong>{configuredPlanes===null?"UNKNOWN":configuredPlanes+" / 3"}</strong><small>{configuredPlanes===null?"Core generation evidence unavailable":"Active Core runtime generations; not proof of application reachability"}</small></article>
      <article className="card dr-health-card"><span>Management jobs</span><strong className={jobs.saturated===false?"healthy":"attention"}>{typeof jobs.saturated!=="boolean"?"UNKNOWN":jobs.saturated?"Saturated":"Healthy"}</strong><small>{jobs.active_jobs??"UNKNOWN"} active · {jobs.queued_jobs??"UNKNOWN"} queued</small></article>
    </section>
    <section className="card dr-health-section"><div className="dr-section-head"><div><p className="dr-eyebrow">Runtime</p><h3>Policy planes</h3><p className="muted">Compiled generation state stays separate from configured policy state.</p></div></div><div className="dr-health-plane-list">{planes.map(row=>{const state=String(row.value.status||"unknown");const good=state==="active"||state==="not_configured";return <div className="dr-health-plane" key={row.name}><span className={good?"dr-severity-dot":"dr-severity-dot warning"}/><div><strong>{row.name[0].toUpperCase()+row.name.slice(1)}</strong><small>DB rev {row.value.db_revision??"—"} · generation {row.value.generation??"—"}</small></div><span className={state==="active"?"dr-state active":"dr-state"}><i/>{state.replaceAll("_"," ")}</span>{row.value.error&&<small className="dr-health-error">{row.value.error}</small>}</div>})}</div></section>
    <section className="card dr-health-section"><div className="dr-section-head"><div><p className="dr-eyebrow">Capacity</p><h3>Management workload</h3><p className="muted">Bounded job engine status for asynchronous fleet operations.</p></div><button className="dr-text-action" onClick={()=>onNavigate?.("jobs","operations")}>Open jobs →</button></div><div className="dr-kpi-strip"><div><span>Active</span><strong>{observedNumber(jobs.active_jobs)}</strong><small>Currently active jobs</small></div><div><span>Queued</span><strong>{observedNumber(jobs.queued_jobs)}</strong><small>{observedNumber(jobs.queued_targets)} queued targets</small></div><div><span>Running</span><strong>{observedNumber(jobs.running_jobs)}</strong><small>{observedNumber(jobs.running_targets)} running targets</small></div><div><span>Failed</span><strong>{observedNumber(jobs.failed_jobs)}</strong><small>Completed with failure</small></div></div></section>
    <details className="card dr-advanced-details"><summary>Advanced · raw health payload</summary><p className="muted">For diagnostics and support. Normal operation should use the structured health views above.</p><pre className="plan">{JSON.stringify(data,null,2)}</pre></details>
  </div>;
}

function AccessHygienePanel({data,onRefresh,onNavigate,operator}:{data:any,onRefresh:()=>void,onNavigate?:(id:string,groupId?:string)=>void,operator:any}){
  const [quality,setQuality]=useState("all"),[filter,setFilter]=useState("");
  const [severityFilter,setSeverityFilter]=useState("all"),[kindFilter,setKindFilter]=useState("all"),[ageFilter,setAgeFilter]=useState("all");
  const source=Array.isArray(data?.items)?data.items:[];
  const partial=data.count>source.length;
  const kinds=Array.from(new Set(source.map((x:any)=>String(x.kind||"")).filter(Boolean))).sort();
  const items=source.filter((x:any)=>{
    if(severityFilter!=="all"&&x.severity!==severityFilter)return false;
    if(kindFilter!=="all"&&x.kind!==kindFilter)return false;
    const observedAge=typeof x.age_days==="number"&&Number.isFinite(x.age_days)?x.age_days:null;
    if(ageFilter==="unknown"&&observedAge!==null)return false;
    if(ageFilter!=="all"&&ageFilter!=="unknown"&&(observedAge===null||observedAge<Number(ageFilter)))return false;
    if(quality==="ORPHANED"&&x.kind!=="orphan-object")return false;
    if(quality!=="all"&&quality!=="ORPHANED"&&x.finding_status!==quality)return false;
    const q=filter.trim().toLowerCase();
    return !q||[x.kind,x.resource_type,x.resource_id,x.label,x.plane].some(v=>String(v||"").toLowerCase().includes(q));
  });
  const unknown=data.summary.unknown_evidence;
  return <div className="dr-resource-workspace">
    <section className="dr-page-intro"><div><p className="dr-eyebrow">Operations · Access Hygiene</p>
      <h2>Access Hygiene</h2><p className="muted">Evidence-qualified review only. No access rule, Host, account, or permission is changed automatically.</p></div>
      <div className="dr-page-actions"><button className="secondary" onClick={onRefresh}>Refresh evidence</button></div>
    </section>
    <div className="grid"><Metric label="Review findings" value={data.count}/><Metric label="Unknown evidence" value={unknown}/></div>
    <p className="muted">Read-only Core hygiene snapshot generated at {data.generated_at}. This report is advisory, not an authorization or completed remediation.</p>
    {partial&&<p role="status" className="dr-uxb-catalog-page-notice">Some Core findings were not included in this bounded read. Filters and Inspect apply only to the {source.length} observed findings; the reported total is {data.count}. Do not interpret an unmatched filter as a clean Core inventory.</p>}
    <section className="card">
      <div className="dr-list-toolbar"><div><strong>{items.length}</strong><span>visible recommendations</span></div>
        <div className="toolbar"><input aria-label="Filter access hygiene" value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter resource or finding"/>
          <select aria-label="Finding status" value={quality} onChange={e=>setQuality(e.target.value)}>
            <option value="all">All findings</option><option value="STALE_OR_UNUSED">Stale</option>
            <option value="ACTION_REQUIRED">Action required</option><option value="ORPHANED">Orphaned</option>
            <option value="UNKNOWN_EVIDENCE">Unknown evidence</option>
          </select>
          <select aria-label="Filter finding severity" value={severityFilter} onChange={e=>setSeverityFilter(e.target.value)}>
            <option value="all">All severities</option><option value="warning">Warning</option><option value="info">Informational</option><option value="critical">Critical</option>
          </select>
          <select aria-label="Filter finding type" value={kindFilter} onChange={e=>setKindFilter(e.target.value)}>
            <option value="all">All types</option>{kinds.map(kind=><option key={kind} value={kind}>{kind.replaceAll("-"," ")}</option>)}
          </select>
          <select aria-label="Filter observed age" value={ageFilter} onChange={e=>setAgeFilter(e.target.value)}>
            <option value="all">All ages</option><option value="7">7+ days</option><option value="30">30+ days</option><option value="90">90+ days</option><option value="unknown">Age unknown</option>
          </select>
        </div>
      </div>
      <p className="muted">Incomplete or unverified audit coverage is UNKNOWN_EVIDENCE, not proof of unused access. Recommendations are always advisory.</p>
      {!items.length?<div className="dr-empty-state"><strong>{partial?"No match in loaded findings":"No matching findings"}</strong><p>{partial?"More Core findings may exist outside the loaded first page. The current filters cover observed items only.":"There is no evidence-qualified action matching the current filters."}</p></div>:
      <div className="dr-table-scroll"><table className="dr-resource-table"><thead><tr><th>Resource</th><th>Review</th><th>Evidence</th><th>Observed age</th><th>Window</th><th>Recommendation</th><th>Inspect</th></tr></thead>
      <tbody>{items.map((x:any,i:number)=><tr key={x.kind+":"+x.resource_id+":"+i}><td><strong>{x.label||x.resource_id}</strong><small>{x.resource_type||""} · {x.kind||""}</small></td>
        <td><span className={x.finding_status==="UNKNOWN_EVIDENCE"?"dr-state":"dr-state active"}><i/>{x.finding_status||"UNKNOWN_EVIDENCE"}</span></td>
        <td>{x.evidence_quality||"UNKNOWN_EVIDENCE"}</td><td title={x.age_reference||"No verified age timestamp"}>{typeof x.age_days==="number"?x.age_days+" days":"Unknown"}</td><td>{x.observation_window_days===0?"Current":(x.observation_window_days??"—")+" days"}</td>
        <td>{x.recommendation||"Review the authoritative resource."}</td>
        <td>{hygieneInspectTarget(x.resource_type,operator.role)?
          <button className="secondary" onClick={()=>{const target=hygieneInspectTarget(x.resource_type,operator.role);if(target)onNavigate?.(target.route,target.group)}}>Inspect</button>:
          <span className="muted">{x.resource_type==="service-account"&&operator.role!=="Admin"?"Admin role required":"No compatible detail workspace"}</span>}</td>
      </tr>)}</tbody></table></div>}
    </section>
  </div>;
}

function SystemAdministrationWorkspace({data,operator,onNavigate}:{data:any,operator:any,onNavigate?:(id:string,groupId?:string)=>void}){
  return <div className="dr-uxb-system">
    <LinkFoundationAdministration operator={operator} onNavigate={onNavigate}/>
    <section className="card dr-uxb-admin-guide" aria-label="System administration guidance">
      <p className="dr-eyebrow">Administration · First use</p><h2>Which settings are routine and which change the system?</h2>
      <div className="dr-uxb-admin-guide-grid">
        <div><strong>Routine · read-only</strong><p>Use System Health and the Activity log to inspect Core and access decisions. No access changes are made by viewing these pages.</p>
          <button className="secondary" onClick={()=>onNavigate?.("health","activity")}>System health →</button></div>
        <div><strong>Admin-only changes</strong><p>Users & MFA, integration credentials and approved configuration changes require role checks. Read Only users cannot perform mutations.</p>
          {operator.role==="Admin"?<button className="secondary" onClick={()=>onNavigate?.("users","administration")}>Users & MFA →</button>:<span className="dr-uxb-role-hint">Admin role required</span>}</div>
        <div><strong>Advanced · confirm before applying</strong><p>Core-owned MCP TLS certificates, product updates, backup and restore are sensitive operations. Web HTTPS listener settings are not implemented here.</p>
          <button className="secondary" onClick={()=>{const advanced=document.getElementById("drlink-core-advanced") as HTMLDetailsElement|null;if(advanced){advanced.open=true;advanced.scrollIntoView({block:"start"})}}}>Review advanced controls →</button></div>
      </div>
    </section>
    <details id="drlink-core-advanced" className="dr-uxb-advanced-panel">
      <summary>Advanced Core operations · certificates, update, backup and recovery</summary>
      <p className="muted">Sensitive changes remain Core-authoritative and role/confirmation guarded. This is not the shared Web HTTPS listener management screen.</p>
      <SystemPanel data={data} operator={operator}/>
    </details>
  </div>;
}

function View({active,operator,onNavigate,context,setupDraft,onSetupDraftChange}:{active:string,operator:any,onNavigate?:(id:string,groupId?:string,context?:any)=>void,context?:any,setupDraft?:SetupDraft|null,onSetupDraftChange?:(draft:SetupDraft)=>void}){
  const [data,setData]=useState<any>(null),[error,setError]=useState(""),[query,setQuery]=useState("");
  const [retryNonce,setRetryNonce]=useState(0);
  useEffect(()=>{
    let current=true;
    setData(null);setError("");
    const paths:Record<string,string>={
      overview:"/api/v1/overview",hosts:"/api/v1/inventory?resource_type=managed-host&limit=100",
      services:"/api/v1/inventory?resource_type=remote-service&limit=100",
      objects:"/api/v1/objects-groups?limit=50",
      versions:"/api/v1/versions",hygiene:"/api/v1/access-hygiene",system:"/api/v1/system",revisions:"/api/v1/revisions?limit=100",
      doctor:"/api/v1/doctor",health:"/api/v1/health",views:"/api/v1/saved-views",enrollments:"/api/v1/enrollments?limit=50",
    };
    if(active==="policies"){
      // A combined 100-rule Core query may hide later Internet/AI planes entirely.
      // Observe all three independently, then display any per-plane limit honestly.
      Promise.all(["remote","internet","ai"].map(plane=>
        api("/api/v1/policies?plane="+plane+"&limit=100")
      )).then(pages=>{
        if(!current)return;
        try{setData(combineObservedPolicyPlanes(pages,100))}
        catch(e:any){setError(e.message||String(e))}
      }).catch((e:any)=>{if(current)setError(e.message||String(e))});
    }else if(paths[active])api(paths[active]).then(payload=>{
      if(!current)return;
      try{setData(active==="hygiene"?requireObservedAccessHygiene(payload):requireObservedMenuPayload(active,payload))}
      catch(e:any){setError(e.message||String(e))}
    }).catch((e:any)=>{if(current)setError(e.message||String(e))});
    return()=>{current=false};
  },[active,retryNonce]);
  if(error)return <section className="error" role="alert"><strong>Core data unavailable · UNKNOWN</strong>
    <p>{error}</p><button type="button" className="secondary" onClick={()=>setRetryNonce(n=>n+1)}>Retry Core read →</button>
  </section>;
  if(active==="users")return <UsersPanel operator={operator}/>;
  if(active==="integrations")return operator.role==="Admin"?<IntegrationsPanel/>:<div className="error">Admin role required</div>;
  if(active==="drafts")return <><DraftWorkflowReference context={context} onNavigate={onNavigate}/><DraftWorkspace/></>;
  if(active==="access")return <AccessOperations operator={operator} onNavigate={onNavigate} context={context}/>;
  if(active==="jobs")return <JobOperations operator={operator}/>;
  if(active==="hygiene"&&data)return <AccessHygienePanel data={data} operator={operator} onRefresh={()=>api("/api/v1/access-hygiene").then(payload=>setData(requireObservedAccessHygiene(payload))).catch((e:any)=>setError(e.message||String(e)))} onNavigate={onNavigate}/>;
  if(active==="audit")return <AuditExplorer operator={operator} context={context}/>;
  if(active==="enrollments"&&data)return <EnrollmentOnboarding api={api} data={data} operator={operator} onNavigate={onNavigate} refresh={()=>api("/api/v1/enrollments?limit=50").then(payload=>setData(requireObservedMenuPayload("enrollments",payload))).catch((e:any)=>setError(e.message||String(e)))}/>;
  if(active==="setup"){
    const requestedPlane=["remote","internet","ai"].includes(String(context?.plane||""))?context.plane:null;
    const draft=requestedPlane?(setupDraft?.plane===requestedPlane?{...setupDraft,step:1}:{plane:requestedPlane,step:1}):setupDraft;
    return <FirstConnectionSetup api={api} operator={operator} onNavigate={onNavigate} initialDraft={draft} onDraftChange={onSetupDraftChange}/>;
  }
  if(active==="search")return <div><div className="toolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search resources and policy"/><button className="primary" onClick={()=>api("/api/v1/search?q="+encodeURIComponent(query)+"&limit=50").then(setData).catch((e:any)=>setError(e.message))}>Search</button></div>{data&&<Table items={(data.items||[]).map((x:any)=>({type:x.resource_type,id:x.id,name:x.name}))}/>}</div>;
  if(active==="overview"&&data)return <CommandCenter data={data} operator={operator} onNavigate={onNavigate}/>;
  if(active==="versions"&&data)return <AgentVersionDrift data={data} onNavigate={onNavigate}/>;
  if(active==="system"&&data)return <SystemAdministrationWorkspace data={data} operator={operator} onNavigate={onNavigate}/>;
  if(active==="objects"&&data)return <><ObjectsWorkspace data={data} onNavigate={onNavigate} context={context} api={api}/>{operator.role!=="Read Only"&&<GuidedObjectPanel/>}</>;
  if(active==="hosts"&&data)return <><ResourceWorkspace kind="host" data={data} operator={operator} onNavigate={onNavigate} api={api} initialFilter={String(context?.savedFilter||"").slice(0,120)} initialAdmission={context?.savedAdmission}/>{operator.role!=="Read Only"&&<ManagedHostMetadataPanel/>}{operator.role==="Admin"&&<ManagedHostAdmissionPanel/>}{operator.role==="Admin"&&<ManagedHostLifecyclePanel/>}</>;
  if(active==="services"&&data)return <><ResourceWorkspace kind="service" data={data} operator={operator} onNavigate={onNavigate} api={api} initialFilter={String(context?.savedFilter||"").slice(0,120)}/>{operator.role!=="Read Only"&&<RemoteServiceEditor api={api}/>}</>;
  if(active==="policies"&&data){
    const selectedPlane=["remote","internet","ai"].includes(String(context?.plane||context?.focusPolicy?.plane))
      ?String(context?.plane||context?.focusPolicy?.plane) as AccessPlane:"remote";
    const initialFlow=connectionReviewContext(selectedPlane,context?.source,context?.destination,context?.selector);
    return <><PolicyWorkspace data={data} operator={operator} onNavigate={onNavigate} api={api} context={context}/>
      {operator.role!=="Read Only"&&<GuidedPolicyJourney api={api} onNavigate={onNavigate}
        initialPlane={selectedPlane} initialFlow={"source" in initialFlow?initialFlow:undefined}/>}<PolicySafetyPanel operator={operator}/>{operator.role!=="Read Only"&&<><GuidedPolicySettingsPanel/><TemporaryAccessPanel/></>}</>;
  }
  if(active==="doctor"&&data)return <CoreDoctorWorkspace data={data} onNavigate={onNavigate}/>;
  if(active==="health"&&data)return <HealthWorkspace data={data} onNavigate={onNavigate}/>;
  if(active==="revisions"&&data)return <RevisionHistory initial={data} api={api}/>;
  if(active==="views"&&data)return <SavedViewsWorkspace data={data} api={api} onNavigate={onNavigate} initialDraft={context?.savedViewDraft} refresh={()=>api("/api/v1/saved-views").then(payload=>setData(requireObservedMenuPayload("views",payload))).catch((e:any)=>setError(e.message||String(e)))}/>;
  if(data)return <Table items={data.items||[]}/>;
  return <PageSkeleton/>;
}

function WorkspaceIcon({kind}:{kind:string}){
  const common={viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:1.8,strokeLinecap:"round" as const,strokeLinejoin:"round" as const,"aria-hidden":true};
  if(kind==="overview")return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>;
  if(kind==="connections"||kind==="infrastructure")return <svg {...common}><rect x="4" y="4" width="16" height="6" rx="2"/><rect x="4" y="14" width="16" height="6" rx="2"/><path d="M8 7h.01M8 17h.01M12 7h5M12 17h5"/></svg>;
  if(kind==="access")return <svg {...common}><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>;
  if(kind==="operations")return <svg {...common}><path d="M4 12h3l2-5 4 10 2-5h5"/></svg>;
  if(kind==="activity"||kind==="observability")return <svg {...common}><path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>;
  if(kind==="administration")return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>;
  if(kind==="search")return <svg {...common}><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg>;
  if(kind==="refresh")return <svg {...common}><path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.2 9A7 7 0 0 0 6.4 6.4L4 9m16 6-2.4 2.6A7 7 0 0 1 5.8 15"/></svg>;
  if(kind==="moon")return <svg {...common}><path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/></svg>;
  if(kind==="sun")return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>;
  if(kind==="collapse")return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 9l-3 3 3 3"/></svg>;
  if(kind==="expand")return <svg {...common}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M12 9l3 3-3 3"/></svg>;
  if(kind==="logout")return <svg {...common}><path d="M10 17l5-5-5-5M15 12H3"/><path d="M13 4h5a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5"/></svg>;
  return <svg {...common}><circle cx="12" cy="12" r="8"/></svg>;
}

function GlobalSearch({open,onClose,onNavigate,operator,returnFocusRef}:{
  open:boolean,onClose:()=>void,onNavigate:(id:string,groupId?:string)=>void,
  operator:any,returnFocusRef:React.RefObject<HTMLElement|null>
}){
  const [query,setQuery]=useState(""),[results,setResults]=useState<any[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const requestGeneration=useRef(0);
  const dialogRef=useRef<HTMLElement|null>(null);
  const navigatingRef=useRef(false);
  const onCloseRef=useRef(onClose);
  onCloseRef.current=onClose;
  function changeQuery(value:string){
    // Old Core resource results must never follow a newer query.
    requestGeneration.current+=1;
    setQuery(value);setResults([]);setError("");setBusy(false);
  }
  useEffect(()=>{if(!open){
    requestGeneration.current+=1;
    setQuery("");setResults([]);setError("");setBusy(false);
  }},[open]);
  useEffect(()=>{
    if(!open)return;
    function onKey(e:KeyboardEvent){
      if(e.key==="Escape"){
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if(e.key!=="Tab"||!dialogRef.current)return;
      const dialog=dialogRef.current;
      const focusable=Array.from(dialog.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
      )).filter(element=>element.getClientRects().length>0&&!element.closest("[inert],[hidden]"));
      if(!focusable.length){e.preventDefault();dialog.focus();return}
      const first=focusable[0],last=focusable[focusable.length-1];
      const active=document.activeElement;
      if(e.shiftKey&&(active===first||!dialog.contains(active))){
        e.preventDefault();last.focus();
      }else if(!e.shiftKey&&(active===last||!dialog.contains(active))){
        e.preventDefault();first.focus();
      }
    }
    window.addEventListener("keydown",onKey);
    return()=>{
      window.removeEventListener("keydown",onKey);
      // Closing returns to the opener; choosing a result moves focus into
      // the destination instead of leaving keyboard users at Search again.
      const target=returnFocusRef.current;
      returnFocusRef.current=null;
      if(navigatingRef.current){
        navigatingRef.current=false;
        document.getElementById("drlink-main-content")?.focus();
      }else if(target?.isConnected){
        target.focus();
      }
    };
  },[open,returnFocusRef]);
  const localMatches=navMatches(query,operator.role);
  if(!open)return null;
  function targetFor(type:string):[string,string]{
    const value=String(type||"").toLowerCase();
    if(value.includes("managed-host"))return ["hosts","infrastructure"];
    if(value.includes("remote-service"))return ["services","infrastructure"];
    if(value.includes("policy")||value.includes("access"))return ["policies","access"];
    if(value.includes("job"))return ["jobs","operations"];
    if(value.includes("audit"))return ["audit","observability"];
    return ["objects","infrastructure"];
  }
  async function search(e?:React.FormEvent){
    e?.preventDefault();
    const q=query.trim();
    const generation=++requestGeneration.current;
    if(!q){setResults([]);return}
    setBusy(true);setError("");setResults([]);
    try{
      const data=await api("/api/v1/search?q="+encodeURIComponent(q)+"&limit=20");
      if(requestGeneration.current!==generation)return;
      if(!Array.isArray(data?.items))throw new Error("Core search response missing resource items");
      setResults(data.items);
    }catch(err:any){if(requestGeneration.current===generation)setError(err.message||String(err))}
    finally{if(requestGeneration.current===generation)setBusy(false)}
  }
  function go(id:string,group?:string){
    if(!visibleRoute(id,operator.role)){
      setError("Your role cannot open this page.");
      return;
    }
    navigatingRef.current=true;
    onNavigate(id,group);
    onClose();
  }
  return <div className="dr-command-overlay" role="presentation" onMouseDown={e=>{if(e.currentTarget===e.target)onClose()}}>
    <section ref={dialogRef} tabIndex={-1} className="dr-command-palette" role="dialog" aria-modal="true" aria-label="Global search">
      <form className="dr-command-search" onSubmit={search}><WorkspaceIcon kind="search"/><input autoFocus value={query} onChange={e=>changeQuery(e.target.value)} placeholder="Search hosts, services, policies, identities…"/><kbd>Esc</kbd></form>
      {error&&<div className="dr-command-error" role="alert">{error}</div>}
      <div className="dr-command-body">
        {!query.trim()&&<><p className="dr-command-label">Quick actions</p><div className="dr-command-actions">
          {operator.role==="Admin"&&<button onClick={()=>go("setup","connections")}><WorkspaceIcon kind="connections"/><span><strong>Set up a connection</strong><small>Add an Agent, publish one service and define narrow access</small></span></button>}
          <button onClick={()=>go("access","access")}><WorkspaceIcon kind="access"/><span><strong>Access workspace</strong><small>Diagnose and inspect current access</small></span></button>
          <button onClick={()=>go("views","observability")}><WorkspaceIcon kind="observability"/><span><strong>Saved Views</strong><small>Open operator-saved filters</small></span></button>
          <button onClick={()=>go("doctor","observability")}><WorkspaceIcon kind="observability"/><span><strong>Troubleshoot</strong><small>Open bounded Doctor checks</small></span></button>
        </div></>}
        {query.trim()&&<><div className="dr-command-results-head"><p className="dr-command-label">Pages and tasks · old names also work</p><button className="dr-text-action" onClick={()=>search()} disabled={busy}>{busy?"Searching…":"Search resources"}</button></div>
        <p className="dr-command-label" role="status" aria-live="polite">{busy?"Searching Core resources…":results.length?results.length+" Core matches returned":""}</p>
        {localMatches.length>0&&<div className="dr-command-results" aria-label="Page and task matches">{localMatches.map(item=><button key={"nav:"+item.id} onClick={()=>go(item.id,item.group)}><span className="dr-search-kind">Page</span><span><strong>{item.label}</strong><small>{item.description}</small></span><span aria-hidden="true">→</span></button>)}</div>}
        {!busy&&!results.length&&!localMatches.length&&<div className="dr-command-empty">No local page matches. Press Enter to search Core resources.</div>}<div className="dr-command-results" role="group" aria-label="Core resource matches" aria-busy={busy}>{results.map((item:any,i:number)=>{const [id,group]=targetFor(item.resource_type);return <button key={item.id||i} onClick={()=>go(id,group)}><span className="dr-search-kind">{item.resource_type||"resource"}</span><span><strong>{item.name||item.id}</strong><small>{item.id||""}</small></span><span aria-hidden="true">→</span></button>})}</div></>}
      </div>
      <footer className="dr-command-footer"><span><kbd>Enter</kbd> search</span><span><kbd>Esc</kbd> close</span><span>Security state is never stored in browser preferences.</span></footer>
    </section>
  </div>;
}

function Shell({operator,onLogout}:{operator:any,onLogout:()=>void}){
  const [active,setActive]=useState("overview");
  const [collapsed,setCollapsed]=useState(()=>{try{return localStorage.getItem("drlink_web_sidebar_collapsed")==="1"}catch{return false}});
  const [dark,setDark]=useState(()=>{try{return localStorage.getItem("drlink_web_theme")==="dark"}catch{return false}});
  const [refreshNonce,setRefreshNonce]=useState(0);
  const [coreHealthy,setCoreHealthy]=useState<"loading"|"healthy"|"attention"|"unknown">("loading");
  const [searchOpen,setSearchOpen]=useState(false);
  const searchReturnFocusRef=useRef<HTMLElement|null>(null);
  const [navigationContext,setNavigationContext]=useState<any>(null);
  // Current authenticated React session only, never URL or localStorage.
  // Store only non-secret wizard choices; Core plans and tokens always expire.
  const [setupDraft,setSetupDraft]=useState<SetupDraft|null>(null);
  const activeGroup=groupFor(active);
  const [expanded,setExpanded]=useState<Record<string,boolean>>(()=>Object.fromEntries(navGroups.map(group=>[group.id,group.id===activeGroup||group.id==="connections"])));

  useEffect(()=>{
    document.documentElement.setAttribute("data-dr-theme",dark?"dark":"light");
    try{localStorage.setItem("drlink_web_theme",dark?"dark":"light")}catch{}
  },[dark]);
  useEffect(()=>{try{localStorage.setItem("drlink_web_sidebar_collapsed",collapsed?"1":"0")}catch{}},[collapsed]);
  useEffect(()=>{
    let active=true;
    setCoreHealthy("loading");
    api("/api/v1/health").then(result=>{
      if(!active)return;
      const status=coreHealthState(result);
      setCoreHealthy(status==="Healthy"?"healthy":status==="Attention"?"attention":"unknown");
    }).catch(()=>{if(active)setCoreHealthy("unknown")});
    return()=>{active=false};
  },[refreshNonce]);
  function openSearch(invoker?:HTMLElement){
    // Safari need not focus a button clicked with the pointer.
    searchReturnFocusRef.current=invoker||(
      document.activeElement instanceof HTMLElement?document.activeElement:null
    );
    setSearchOpen(true);
  }
  useEffect(()=>{
    function onKey(e:KeyboardEvent){
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){
        e.preventDefault();
        // Repeated shortcuts while the dialog is open must not replace its return target.
        if(!searchOpen)openSearch();
      }
    }
    window.addEventListener("keydown",onKey);return()=>window.removeEventListener("keydown",onKey);
  },[searchOpen]);

  async function logout(){try{await api("/api/v1/auth/logout",{method:"POST",body:"{}"})}finally{csrf="";onLogout()}}
  function visible(id:string){return visibleRoute(id,operator.role)}
  function activate(id:string,groupId?:string,context?:any){
    if(!visible(id))return;
    // Navigation context is ephemeral, never written to browser storage or URL.
    setNavigationContext(context||null);
    setActive(id);
    // Legacy components still emit "infrastructure"/"observability"/"operations".
    // Derive the canonical grouping from the stable route id.
    const group=groupFor(id);
    if(group)setExpanded(prev=>({...prev,[group]:true}));
  }
  function chooseGroup(groupId:string){
    if(collapsed){setCollapsed(false);setExpanded(prev=>({...prev,[groupId]:true}));return}
    setExpanded(prev=>({...prev,[groupId]:!prev[groupId]}));
  }
  const title=labelFor(active);
  const crumb=navGroups.find(group=>group.id===activeGroup)?.label||"Connections";
  const healthText={loading:"Checking",healthy:"Healthy",attention:"Attention",unknown:"UNKNOWN"}[coreHealthy];
  return <div className={collapsed?"shell dr-shell is-collapsed":"shell dr-shell"}>
    <a className="dr-skip-link" href="#drlink-main-content">Skip to content</a>
    <aside className={collapsed?"sidebar dr-sidebar is-collapsed":"sidebar dr-sidebar"}>
      <div className="dr-sidebar-brand">
        <button className="dr-brand-home" onClick={()=>activate("overview")} aria-label="DataRelay Link — Home">
          <img src="/logo/datarelay-logo.svg" alt=""/><span className="dr-brand-copy"><strong><span>Data</span><em>Relay</em></strong><small>Data Relay Link</small></span>
        </button>
        <button className="dr-icon-button dr-collapse" onClick={()=>setCollapsed(!collapsed)} aria-label={collapsed?"Expand menu":"Collapse menu"}><WorkspaceIcon kind={collapsed?"expand":"collapse"}/></button>
      </div>
      <nav className="nav dr-nav" aria-label="Primary navigation">
        <button className={active==="overview"?"active nav-home":"nav-home"} onClick={()=>activate("overview")} title={collapsed?"Home":undefined}><span className="dr-nav-icon"><WorkspaceIcon kind="overview"/></span><span className="dr-nav-label">Home</span></button>
        {navGroups.map(group=>{
          const items=group.items.filter(([id])=>visible(id));
          if(!items.length)return null;
          const open=!!expanded[group.id];
          const hasActive=items.some(([id])=>id===active);
          return <section className={hasActive?"nav-group has-active":"nav-group"} key={group.id}>
            <button className="nav-group-toggle" aria-expanded={open} onClick={()=>chooseGroup(group.id)} title={collapsed?group.label:undefined}>
              <span className="dr-nav-icon"><WorkspaceIcon kind={group.id}/></span><span className="dr-nav-label">{group.label}</span><span className="nav-chevron" aria-hidden="true">{open?"▾":"▸"}</span>
            </button>
            {!collapsed&&open&&<div className="nav-group-items">
              {items.filter(([id])=>id!=="objects"&&id!=="versions").map(([id,label])=><button key={id} className={id===active?"active":""} onClick={()=>activate(id,group.id)} title={pageDescriptions[id]||label}>{label}</button>)}
              {items.some(([id])=>id==="objects"||id==="versions")&&<details className="dr-uxb-nav-advanced" open={items.some(([id])=>id===active&&(id==="objects"||id==="versions"))}>
                <summary>Advanced tools</summary>
                {items.filter(([id])=>id==="objects"||id==="versions").map(([id,label])=><button key={id} className={id===active?"active":""} onClick={()=>activate(id,group.id)} title={pageDescriptions[id]||label}>{label}</button>)}
              </details>}
            </div>}
          </section>;
        })}
      </nav>
      <div className="dr-sidebar-footer">
        {!collapsed&&<div className="dr-environment"><span className="dr-status-dot"/><span><small>Environment</small><strong>Development</strong></span></div>}
        <button className="dr-user-chip" onClick={()=>operator.role==="Admin"&&activate("users","administration")} title={collapsed?`${operator.username} · ${operator.role}`:undefined}>
          <span className="dr-avatar">{String(operator.username||"?").slice(0,2).toUpperCase()}</span><span className="dr-user-copy"><strong>{operator.username}</strong><small>{operator.role}</small></span>
        </button>
        <button className="dr-sidebar-signout" onClick={logout} title={collapsed?"Sign out":undefined} aria-label="Sign out"><span className="dr-nav-icon"><WorkspaceIcon kind="logout"/></span><span className="dr-user-copy">Sign out</span></button>
      </div>
    </aside>
    <div className="dr-shell-main">
      <header className="dr-topbar">
        <div className="dr-topbar-context"><div className="dr-uxb-header">
          <nav className="dr-uxb-breadcrumb" aria-label="Breadcrumb"><button type="button" onClick={()=>activate("overview")}>Home</button>{active!=="overview"&&<><span aria-hidden="true">/</span><span>{crumb}</span><span aria-hidden="true">/</span><strong>{title}</strong></>}</nav>
          <div className="dr-uxb-title"><h1>{title}</h1><span className={coreHealthy==="attention"||coreHealthy==="unknown"?"dr-health-pill attention":"dr-health-pill"}><i/>{healthText}</span></div>
          <p>{pageDescriptions[active]||"Core-backed management workspace"}</p></div></div>
        <div className="dr-topbar-actions">
          <button className="dr-search-trigger" onClick={e=>openSearch(e.currentTarget)}><WorkspaceIcon kind="search"/><span>Search</span><kbd>⌘K</kbd></button>
          <button className="dr-icon-button" onClick={()=>setRefreshNonce(x=>x+1)} title="Refresh"><WorkspaceIcon kind="refresh"/></button>
          <button className="dr-icon-button" onClick={()=>setDark(!dark)} title="Toggle theme"><WorkspaceIcon kind={dark?"sun":"moon"}/></button>
        </div>
      </header>
      <main id="drlink-main-content" className="content dr-workspace" tabIndex={-1}><div className="dr-content-frame"><View key={active+":"+refreshNonce+":"+(navigationContext?.originId||"")} active={active} operator={operator} onNavigate={activate} context={navigationContext} setupDraft={setupDraft} onSetupDraftChange={setSetupDraft}/></div></main>
    </div>
    <GlobalSearch open={searchOpen} onClose={()=>setSearchOpen(false)} onNavigate={activate} operator={operator} returnFocusRef={searchReturnFocusRef}/>
  </div>;
}

function App(){
  const [operator,setOperator]=useState<any>(undefined);
  useEffect(()=>{
    // The HttpOnly cookie survives a reload; the in-memory CSRF token does
    // not. Rehydrate it from the authenticated, no-store same-origin session
    // API before allowing any Web/Core POST action.
    let active=true;
    api("/api/v1/session").then(d=>{
      if(!active)return;
      if(!d?.operator||typeof d.csrf_token!=="string"||!d.csrf_token){
        throw new Error("Incomplete authenticated Web session");
      }
      csrf=d.csrf_token;
      setOperator(d.operator);
    }).catch(()=>{if(active){csrf="";setOperator(null)}});
    return()=>{active=false};
  },[]);
  if(operator===undefined)return <div className="login-wrap"><div className="muted">Loading…</div></div>;
  if(!operator)return <Login onLogin={setOperator}/>;
  return <Shell operator={operator} onLogout={()=>setOperator(null)}/>;
}

createRoot(document.getElementById("app")!).render(<App/>);
