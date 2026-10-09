import React, {useEffect, useRef, useState} from "react";
import {CoreChoiceField,useCoreCatalog,type CoreCatalog} from "./uxb-core-choices";

export type LinkApi = (path:string, init?:RequestInit)=>Promise<Record<string,any>>;
type Navigate = (id:string,groupId?:string)=>void;
export type AccessPlane = "remote"|"internet"|"ai";
type SelectedFlow = {source:string,destination:string,selector:string,path?:string};

export function reliableDecision(value:unknown):"ALLOW"|"DENY"|"UNKNOWN" {
  const text=String(value??"").toUpperCase();
  return text==="ALLOW"||text==="DENY"?text:"UNKNOWN";
}

/** The browser must never authorize based on policy simulation or stale views. */
export function explainTrace(trace:any):{decision:"ALLOW"|"DENY"|"UNKNOWN",reason:string,rules:string[]} {
  const decision=reliableDecision(trace?.final?.result);
  const reason=String(trace?.final?.reason||"Core did not provide a decision reason.");
  const rules=Array.isArray(trace?.policy?.matched_rules)
    ?trace.policy.matched_rules.map((item:any)=>String(item)).filter(Boolean).slice(0,20):[];
  return {decision,reason,rules};
}

export function canApplyGuidedRule(preview:any,tests:any,acknowledgedUnknowns:boolean):boolean {
  if(!preview?.change_plan_id||preview.no_change||tests?.ok!==true||Number(tests.required_failed??1)!==0)return false;
  if(preview.policy_regression && (preview.policy_regression.ok!==true || Number(preview.policy_regression.required_failed??1)!==0))return false;
  if(preview.blast_radius?.limits?.truncated)return false;
  if((preview.blast_radius?.unknowns||[]).length && !acknowledgedUnknowns)return false;
  return true;
}

export function AccessEvidenceExplorer({api,plane,source,destination,selector,onSelect,onNavigate}:{
  api:LinkApi,plane:AccessPlane,source:string,destination:string,selector:string,
  onSelect:(flow:SelectedFlow)=>void,onNavigate?:Navigate
}){
  const [graph,setGraph]=useState<any>(null),[trace,setTrace]=useState<any>(null);
  const [graphBusy,setGraphBusy]=useState(false),[traceBusy,setTraceBusy]=useState(false);
  const [error,setError]=useState(""),[path,setPath]=useState("");
  const graphRequest=useRef(0),traceRequest=useRef(0);
  useEffect(()=>{graphRequest.current+=1;setGraph(null);setError("");setGraphBusy(false)},[plane]);
  useEffect(()=>{traceRequest.current+=1;setTrace(null);setTraceBusy(false)},[plane,source,destination,selector,path]);
  const ready=!!(source.trim()&&destination.trim()&&selector.trim());
  async function loadGraph(){
    const token=++graphRequest.current;
    setGraph(null);setGraphBusy(true);setError("");
    try{
      const next=await api("/api/v1/policy/graph?plane="+encodeURIComponent(plane));
      if(graphRequest.current===token)setGraph(next);
    }catch(e:any){if(graphRequest.current===token)setError("Core graph unavailable: "+String(e.message||e))}
    finally{if(graphRequest.current===token)setGraphBusy(false)}
  }
  async function explain(){
    if(!ready)return;
    const token=++traceRequest.current;
    setTrace(null);setTraceBusy(true);setError("");
    const body:any={plane,source:source.trim(),destination:destination.trim()};
    if(plane==="ai"){body.permission=selector.trim();if(path.trim())body.path=path.trim()}
    else body.service=selector.trim();
    try{
      const next=await api("/api/v1/policy/trace",{method:"POST",body:JSON.stringify(body)});
      if(traceRequest.current===token)setTrace(next);
    }catch(e:any){if(traceRequest.current===token)setError("Core decision unavailable: "+String(e.message||e))}
    finally{if(traceRequest.current===token)setTraceBusy(false)}
  }
  const observed=explainTrace(trace),paths=Array.isArray(graph?.paths)?graph.paths.slice(0,16):[];
  const limits=graph?.limits||{};
  return <section className="card dr-p0-section" aria-label="Effective access explanation" data-testid="p0-access-explain">
    <div className="dr-section-head"><div><p className="dr-eyebrow">Effective Access · Core evidence</p>
      <h3>Who can reach what — and why?</h3>
      <p className="muted">Select a Core-modeled flow or enter source, destination and service above. Policy result does not prove network reachability.</p>
    </div><button className="secondary" onClick={loadGraph} disabled={graphBusy}>{graphBusy?"Loading…":"Load modeled paths"}</button></div>
    {error&&<div className="error" role="alert">{error}</div>}
    {graph&&<>
      <div className="dr-p0-facts"><span>Modeled flows: {limits.path_count??graph.paths?.length??"UNKNOWN"}</span>
        <span>Core graph: {limits.truncated?"TRUNCATED":"bounded snapshot"}</span>
        <span>Topology discovery: {graph.network_topology?"present":"not performed"}</span></div>
      {limits.truncated&&<p className="warning-box">Only bounded graph paths are shown. Absent paths are not proof of DENY.</p>}
      {paths.length? <div className="dr-p0-paths" aria-label="Core modeled paths">
        {paths.map((row:any,i:number)=>{
          const input=row.input||{},select=plane==="ai"?input.permission:input.service;
          const decision=reliableDecision(row.decision);
          return <button type="button" className="dr-p0-path" key={i} onClick={()=>{
            onSelect({source:String(input.source||""),destination:String(input.destination||""),selector:String(select||""),path:String(input.path||"")});
            setPath(String(input.path||""));
          }}>
            <strong>{input.source||"Unknown source"} <span aria-hidden="true">→</span> {input.destination||"Unknown destination"}</strong>
            <small>{select||"unspecified selector"} · {(row.rules||[]).length?row.rules.join(", "):"no matched rule listed"}</small>
            <span className={"dr-p0-result "+decision.toLowerCase()}>{decision}</span>
          </button>;
        })}</div>:<p className="muted">No modeled paths returned. This does not prove an access decision.</p>}
    </>}
    {plane==="ai"&&<label className="dr-field"><span>Optional AI request path</span><input value={path} onChange={e=>setPath(e.target.value)} placeholder="/resource/path"/></label>}
    <div className="dr-p0-actions"><button className="primary" onClick={explain} disabled={!ready||traceBusy}>{traceBusy?"Checking…":"Explain selected access"}</button>
      <button className="secondary" onClick={()=>onNavigate?.("policies","access")}>View policies</button>
      <button className="secondary" onClick={()=>onNavigate?.("audit","observability")}>Review audit evidence</button></div>
    {trace&&<div className="dr-p0-evidence">
      <div className="dr-p0-decision"><span>Effective policy decision</span><strong className={"dr-p0-result "+observed.decision.toLowerCase()}>{observed.decision}</strong></div>
      <div className="dr-p0-route" aria-label="Core decision route">
        <div><small>Source</small><strong>{trace.normalized_input?.source||source}</strong></div>
        <span aria-hidden="true">→</span>
        <div><small>Policy decision</small><strong>{observed.decision}</strong></div>
        <span aria-hidden="true">→</span>
        <div><small>Destination</small><strong>{trace.normalized_input?.destination||destination}</strong></div>
      </div>
      <p>{observed.reason}</p>
      <p className="muted">Matched rules: {observed.rules.length?observed.rules.join(", "):"none reported"} · Mode: {trace.policy?.mode||"UNKNOWN"} · Enforcement: {trace.policy?.enforcement||"UNKNOWN"}</p>
      {trace.mixed&&<p className="warning-box">Mixed group membership outcomes; inspect individual member results before acting.</p>}
      <details><summary>Advanced · exact Core trace</summary><pre className="plan">{JSON.stringify(trace,null,2)}</pre></details>
    </div>}
    {!trace&&!traceBusy&&<p className="muted">Decision: UNKNOWN until a fresh Core decision trace succeeds.</p>}
  </section>;
}

export function GuidedPolicyJourney({api,onNavigate,initialPlane="remote",lockedPlane=false,initialFlow,onFlowChange,resourceCatalog,onBusyChange}: {
  api:LinkApi,onNavigate?:Navigate,initialPlane?:AccessPlane,lockedPlane?:boolean,
  resourceCatalog?:CoreCatalog|null,
  onBusyChange?:(busy:boolean)=>void,
  initialFlow?:{source?:string,destination?:string,selector?:string},
  onFlowChange?:(flow:{source:string,destination:string,selector:string})=>void,
}) {
  const [plane,setPlane]=useState<AccessPlane>(initialPlane),[operation,setOperation]=useState("set");
  const [name,setName]=useState(""),[mode,setMode]=useState("whitelist");
  const [source,setSource]=useState(initialFlow?.source||""),[destination,setDestination]=useState(initialFlow?.destination||""),[selector,setSelector]=useState(initialFlow?.selector||"");
  const [paths,setPaths]=useState(""),[expiresAt,setExpiresAt]=useState(""),[purpose,setPurpose]=useState("");
  const [enabled,setEnabled]=useState(true),[phase,setPhase]=useState(1);
  const [preview,setPreview]=useState<any>(null),[tests,setTests]=useState<any>(null);
  const [confirmation,setConfirmation]=useState(""),[acknowledge,setAcknowledge]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState("");
  const seq=useRef(0);
  const catalog=useCoreCatalog(api,resourceCatalog);
  useEffect(()=>{onBusyChange?.(busy)},[busy]);
  useEffect(()=>()=>{onBusyChange?.(false)},[]);
  function invalidate(){
    seq.current+=1;setPreview(null);setTests(null);setConfirmation("");setAcknowledge(false);
    setPhase(1);setMessage("");setError("");
  }
  function change<T>(setter:(value:T)=>void,value:T){setter(value);invalidate()}
  function changeFlow(key:"source"|"destination"|"selector",value:string){
    if(key==="source")setSource(value);
    else if(key==="destination")setDestination(value);
    else setSelector(value);
    onFlowChange?.({source:key==="source"?value:source,destination:key==="destination"?value:destination,selector:key==="selector"?value:selector});
    invalidate();
  }
  const ready=!!name.trim()&&(operation==="delete"||!!(source.trim()&&destination.trim()&&selector.trim()));
  async function review(){
    if(!ready||busy)return;
    const token=++seq.current;
    setBusy(true);setError("");setMessage("");setPreview(null);setTests(null);setConfirmation("");setAcknowledge(false);
    const payload:any={operation,name:name.trim()};
    if(operation==="set"){
      Object.assign(payload,{mode,source:source.trim(),destination:destination.trim(),enabled});
      if(expiresAt.trim())payload.expires_at=expiresAt.trim();
      if(plane==="ai"){
        payload.permission=selector.trim();
        if(paths.trim())payload.paths=paths.split(",").map(item=>item.trim()).filter(Boolean);
      }else payload.service=selector.trim();
    }
    try{
      const result=await api("/api/v1/guided/preview",{method:"POST",
        body:JSON.stringify({change_type:plane+"-access-rule",payload})});
      if(seq.current!==token)return;
      setPreview(result);setPhase(2);
    }catch(e:any){if(seq.current===token)setError("Preview failed: "+String(e.message||e))}
    finally{if(seq.current===token)setBusy(false)}
  }
  async function verifyRequired(){
    if(!preview?.change_plan_id||busy)return;
    const token=seq.current;
    setBusy(true);setError("");setTests(null);setConfirmation("");
    try{
      const result=await api("/api/v1/policy-tests/run",{method:"POST",body:JSON.stringify({required_only:true})});
      if(seq.current!==token)return;
      setTests(result);setPhase(3);
    }catch(e:any){if(seq.current===token)setError("Required policy tests unavailable: "+String(e.message||e))}
    finally{if(seq.current===token)setBusy(false)}
  }
  const unknowns=Array.isArray(preview?.blast_radius?.unknowns)?preview.blast_radius.unknowns:[];
  const safe=canApplyGuidedRule(preview,tests,acknowledge);
  const requiredWord=String(preview?.confirmation_class||"APPLY");
  async function apply(){
    if(!safe||confirmation!==requiredWord||busy)return;
    const token=seq.current;
    setBusy(true);setError("");
    try{
      const result=await api("/api/v1/guided/apply",{method:"POST",body:JSON.stringify({
        change_plan_id:preview.change_plan_id,confirmation,
      })});
      if(seq.current!==token)return;
      setMessage("Core applied rule change at revision "+String(result.revision??"UNKNOWN"));
      setPreview(null);setTests(null);setConfirmation("");setAcknowledge(false);setPhase(1);
    }catch(e:any){if(seq.current===token)setError("Apply was not confirmed: "+String(e.message||e))}
    finally{if(seq.current===token)setBusy(false)}
  }
  return <section className="card dr-p0-section" data-testid="p0-guided-policy">
    <div className="dr-section-head"><div><p className="dr-eyebrow">P0 · Guided policy workflow</p>
      <h3>Define → Preview → Test → Apply</h3>
      <p className="muted">Uses existing Core Change Plans. No changes happen until the last confirmed step; expired plans are rejected by Core.</p></div>
      <button className="secondary" disabled={busy} onClick={()=>onNavigate?.("access","access")}>Explain access first →</button></div>
    <ol className="dr-p0-steps" aria-label="Policy change stages">
      {["Define rule","Review impact","Verify required tests","Confirm apply"].map((label,i)=>
        <li key={label} className={phase===i+1?"active":phase>i+1?"done":""}><span>{i+1}</span>{label}</li>)}
    </ol>
    {error&&<div className="error" role="alert">{error}</div>}
    {message&&<div className="notice" role="status">{message}</div>}
    {operation==="set"&&<section className="dr-uxb-catalog-guide" aria-label="Choose observed Core resources">
      <h4>Choose who, where and what (from Core)</h4>
      <p>Start by selecting names that already exist. You may also type another exact name below. A selection is not approval; Core validates the change.</p>
      <div className="dr-uxb-catalog-grid">
        <CoreChoiceField api={api} catalog={catalog} plane={plane} field="source" value={source} disabled={busy} onChoose={v=>changeFlow("source",v)}/>
        <CoreChoiceField api={api} catalog={catalog} plane={plane} field="destination" value={destination} disabled={busy} onChoose={v=>changeFlow("destination",v)}/>
        <CoreChoiceField api={api} catalog={catalog} plane={plane} field="selector" value={selector} disabled={busy} onChoose={v=>changeFlow("selector",v)}/>
      </div>
      <button type="button" className="secondary" disabled={busy} onClick={()=>onNavigate?.("objects","access")}>Manage missing Objects & Groups →</button>
    </section>}
    <fieldset className="dr-p0-form" disabled={busy}>
      <label className="dr-field"><span>Access plane</span><select value={plane} disabled={lockedPlane} onChange={e=>{change(setPlane,e.target.value as AccessPlane);setSelector("");setPaths("")}}>
        <option value="remote">Remote Access</option><option value="internet">Internet Access</option><option value="ai">AI Access</option></select></label>
      <label className="dr-field"><span>Change</span><select value={operation} onChange={e=>change(setOperation,e.target.value)}>
        <option value="set">Create / edit rule</option><option value="delete">Delete existing rule</option></select></label>
      <label className="dr-field"><span>Rule name</span><input value={name} onChange={e=>change(setName,e.target.value)} placeholder="Required canonical rule name"/></label>
      {operation==="set"&&<>
        <label className="dr-field"><span>Policy mode</span><select value={mode} onChange={e=>change(setMode,e.target.value)}>
          <option value="whitelist">Whitelist · grant matching access</option><option value="blacklist">Blacklist · deny matching access</option></select></label>
        <div className="dr-uxb-rule-summary" role="status">
          <strong>Rule you are preparing · {mode==="whitelist"?"Allow matching access":"Deny matching access"}</strong>
          <p>{source||"Choose a source"} <span aria-hidden="true">→</span> {destination||"Choose a destination"} · {selector||("Choose a "+(plane==="ai"?"permission":"service"))}</p>
          <small>This is an unverified draft. No access is granted or denied until Core preview, tests and confirmed Apply.</small>
        </div>
        <details className="dr-uxb-manual-fields">
          <summary>Advanced · review or enter exact Core names manually</summary>
          <div className="dr-uxb-form">
            <label className="dr-field"><span>Who · source</span><input value={source} onChange={e=>changeFlow("source",e.target.value)} placeholder={plane==="ai"?"AI identity":"Source object or group"}/></label>
            <label className="dr-field"><span>What · destination</span><input value={destination} onChange={e=>changeFlow("destination",e.target.value)} placeholder="Destination object or group"/></label>
            <label className="dr-field"><span>{plane==="ai"?"Permission":"Service"} selector</span><input value={selector} onChange={e=>changeFlow("selector",e.target.value)} placeholder={plane==="ai"?"Permission object/group":"Service object/group"}/></label>
          </div>
        </details>
        {plane==="ai"&&<label className="dr-field"><span>Optional AI paths (comma-separated)</span><input value={paths} onChange={e=>change(setPaths,e.target.value)} placeholder="/path/a, /path/b"/></label>}
        <label className="dr-field"><span>Optional expiry · ISO 8601</span><input value={expiresAt} onChange={e=>change(setExpiresAt,e.target.value)} placeholder="2030-01-01T00:00:00Z"/></label>
        <label className="dr-field dr-p0-check"><input type="checkbox" checked={enabled} onChange={e=>change(setEnabled,e.target.checked)}/><span>Rule enabled</span></label>
      </>}
      <label className="dr-field dr-p0-purpose"><span>Review purpose (screen only)</span><input value={purpose} onChange={e=>change(setPurpose,e.target.value)} placeholder="Optional rationale for this review"/><small>Not submitted to Core or stored as a policy audit reason.</small></label>
    </fieldset>
    <div className="dr-p0-actions"><button className="primary" disabled={!ready||busy} onClick={review}>{busy&&phase<3?"Preparing…":"1. Preview Core impact"}</button>
      {preview&&<button className="secondary" disabled={busy} onClick={()=>{setPhase(2);setConfirmation("")}}>Review current plan</button>}</div>
    {preview&&<div className="dr-p0-review">
      <h4>2. Authoritative preview · no mutation</h4>
      <div className="dr-p0-facts"><span>Rule: {name}</span><span>Plane: {plane}</span><span>Valid until: {preview.valid_until||"UNKNOWN"}</span></div>
      {purpose.trim()&&<p>Review note (not persisted): {purpose.trim()}</p>}
      {preview.no_change&&<p className="notice">Core reports no change. No Apply is offered.</p>}
      {preview.impact?.warning&&<p className="warning-box">{preview.impact.warning}</p>}
      <div className="dr-p0-counters"><span>Access broadened: {preview.blast_radius?.access_broadened?"YES":"NO/UNKNOWN"}</span>
        <span>Access narrowed: {preview.blast_radius?.access_narrowed?"YES":"NO/UNKNOWN"}</span>
        <span>Affected rules: {(preview.blast_radius?.affected_rules||[]).join(", ")||"none reported"}</span>
        <span>Hosts: {(preview.blast_radius?.affected_managed_hosts||[]).length}</span>
        <span>Services: {(preview.blast_radius?.affected_remote_services||[]).length}</span></div>
      {preview.blast_radius?.limits?.truncated&&<p className="warning-box">Core impact model is truncated. Apply is blocked until an untruncated preview is available.</p>}
      {unknowns.length>0&&<div className="warning-box">Unknown impact evidence: {unknowns.slice(0,8).join(" · ")}</div>}
      {preview.policy_regression&&<p className={preview.policy_regression.ok?"notice":"warning-box"}>Core preview required tests: {preview.policy_regression.passed??"?"}/{preview.policy_regression.count??"?"}; failures {preview.policy_regression.required_failed??"UNKNOWN"}</p>}
      <details><summary>Advanced · Core preview and graph overlay</summary><pre className="plan">{JSON.stringify({preview:preview.preview,impact:preview.impact,blast_radius:preview.blast_radius,graph_overlay:preview.graph_overlay},null,2)}</pre></details>
      <h4>3. Independently verify saved required tests</h4>
      <p className="muted">Read-only Core test run is a second check. Failing or unavailable results block Apply.</p>
      <button className="secondary" disabled={!preview.change_plan_id||busy} onClick={verifyRequired}>{busy?"Checking…":"Run required policy regression tests"}</button>
      {tests&&<p className={tests.ok&&Number(tests.required_failed??1)===0?"notice":"warning-box"} role="status">Required tests: {tests.passed??"?"}/{tests.count??"?"} passed · failures {tests.required_failed??"UNKNOWN"} · {tests.ok?"PASS":"BLOCKED"}</p>}
      {unknowns.length>0&&<label className="dr-p0-check"><input type="checkbox" checked={acknowledge} onChange={e=>setAcknowledge(e.target.checked)}/><span>I reviewed the unknown Core evidence; it does not prove ALLOW.</span></label>}
      <h4>4. Explicit confirmation</h4>
      <label className="dr-field"><span>Type {requiredWord} to apply the reviewed Core Change Plan</span><input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder={requiredWord} disabled={!safe||busy}/></label>
      <button className="danger" onClick={apply} disabled={!safe||confirmation!==requiredWord||busy}>{busy?"Applying…":"Apply through Core"}</button>
      {!safe&&<p className="muted">Apply locked until plan, untruncated impact and all required tests are verified. Core revalidates at Apply.</p>}
    </div>}
  </section>;
}
