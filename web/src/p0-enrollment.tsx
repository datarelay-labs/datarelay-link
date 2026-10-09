import React,{useEffect,useState} from "react";
import type {LinkApi} from "./p0-access-policy";

type Navigate=(id:string,groupId?:string)=>void;
export const enrollmentSteps=["Issue enrollment","Install / join","Review & approve","Verify connectivity"] as const;

/** Admission, trust, connection and policy are independent Core concepts. */
export function hostReadiness(host:any){
  if(!host)return {admission:"UNKNOWN",trust:"UNKNOWN",connection:"UNKNOWN",observedAt:"No observation",policy:"NOT VERIFIED"};
  const admission=String(host.admission_state||"UNKNOWN").toUpperCase();
  const trust=String(host.trust_status||"UNKNOWN").toUpperCase();
  const connection=host.connected===true||host.connected===1?"CONNECTED"
    :host.connected===false||host.connected===0?"NOT CONNECTED":"UNKNOWN";
  return {admission,trust,connection,
    observedAt:String(host.agent_heartbeat_at||host.last_seen||"No observation"),policy:"NOT VERIFIED"};
}
export function hostReadinessLabel(host:any):string {
  const s=hostReadiness(host);
  if(s.admission==="PENDING_APPROVAL")return "WAITING FOR APPROVAL";
  if(s.admission==="QUARANTINED")return "QUARANTINED";
  if(s.connection==="UNKNOWN")return "NO CONNECTION EVIDENCE";
  if(s.admission==="APPROVED"&&s.connection==="CONNECTED"&&s.trust!=="TRUSTED")return "CONNECTED · TRUST NOT VERIFIED";
  if(s.admission==="APPROVED"&&s.connection==="CONNECTED"&&s.trust==="TRUSTED")return "CONNECTED · APPROVED · TRUSTED";
  if(s.connection==="NOT CONNECTED")return "NOT CONNECTED";
  return "UNKNOWN · REVIEW CORE STATE";
}

export function EnrollmentOnboarding({api,data,refresh,operator,onNavigate}:{
  api:LinkApi,data:any,refresh:()=>void,operator:any,onNavigate?:Navigate
}){
  const [step,setStep]=useState(1),[mode,setMode]=useState("zero-touch"),[platform,setPlatform]=useState("linux");
  const [ttl,setTtl]=useState("3600"),[label,setLabel]=useState(""),[note,setNote]=useState("");
  const [preApproved,setPreApproved]=useState(false),[issued,setIssued]=useState<any>(null);
  const [hosts,setHosts]=useState<any[]>([]),[selectedHost,setSelectedHost]=useState("");
  const [fetchBusy,setFetchBusy]=useState(false),[busy,setBusy]=useState(false);
  const [error,setError]=useState(""),[inventoryError,setInventoryError]=useState("");
  const [preview,setPreview]=useState<any>(null),[confirm,setConfirm]=useState(""),[message,setMessage]=useState("");
  const admin=operator?.role==="Admin";
  const selected=hosts.find(h=>String(h.id)===selectedHost)||null;
  const readiness=hostReadiness(selected);
  const required=String(preview?.confirmation_class||"APPROVE");
  useEffect(()=>{if(step>=3)void refreshHosts()},[step]);
  async function refreshHosts(){
    setFetchBusy(true);setInventoryError("");
    try{
      const result=await api("/api/v1/inventory?resource_type=managed-host&limit=100");
      const items=Array.isArray(result.items)?result.items:[];
      setHosts(items);
      setSelectedHost(value=>items.some((h:any)=>String(h.id)===value)?value:String(items[0]?.id||""));
    }catch(e:any){setHosts([]);setInventoryError(String(e.message||e))}
    finally{setFetchBusy(false)}
  }
  async function issue(){
    if(!admin||busy)return;
    setError("");setMessage("");setIssued(null);setBusy(true);
    try{
      const result=await api(mode==="manual"?"/api/v1/enrollments/manual":"/api/v1/enrollments/zero-touch",{
        method:"POST",body:JSON.stringify({platform,ttl_seconds:ttl,label,note,
          ...(mode==="zero-touch"?{pre_approved:preApproved}:{})}),
      });
      setIssued(result);refresh();setStep(2);
    }catch(e:any){setError(String(e.message||e))}
    finally{setBusy(false)}
  }
  async function previewApproval(){
    if(!admin||!selectedHost||busy)return;
    setBusy(true);setError("");setPreview(null);setConfirm("");
    try{
      const result=await api("/api/v1/managed-hosts/admission/preview",{
        method:"POST",body:JSON.stringify({host:selectedHost,operation:"approve"}),
      });
      setPreview(result);
    }catch(e:any){setError(String(e.message||e))}
    finally{setBusy(false)}
  }
  async function applyApproval(){
    if(!admin||!selectedHost||!preview?.change_plan_id||confirm!==required||busy)return;
    setBusy(true);setError("");
    try{
      const result=await api("/api/v1/managed-hosts/admission/apply",{
        method:"POST",body:JSON.stringify({change_plan_id:preview.change_plan_id,confirmation:confirm}),
      });
      setMessage("Core admission review applied at revision "+String(result.revision??"UNKNOWN"));
      setPreview(null);setConfirm("");refresh();setStep(4);
    }catch(e:any){setError("Approval not confirmed: "+String(e.message||e))}
    finally{setBusy(false)}
  }
  return <section className="dr-p0-onboarding" data-testid="p0-enrollment-journey">
    <div className="card dr-p0-section">
      <p className="dr-eyebrow">P0 · Agent onboarding</p>
      <h2>Connect an Agent in four steps</h2>
      <p className="muted">Issue → install → approve → verify. Admission approval never guarantees network reachability; pre-approval is off by default.</p>
      <ol className="dr-p0-steps" aria-label="Agent enrollment stages">{enrollmentSteps.map((name,i)=>
        <li className={step===i+1?"active":step>i+1?"done":""} key={name}>
          <button type="button" onClick={()=>{setStep(i+1);setError("");setPreview(null);setConfirm("")}} aria-current={step===i+1?"step":undefined}>
            <span>{i+1}</span>{name}</button></li>
      )}</ol>
      {error&&<p className="error" role="alert">{error}</p>}
      {message&&<p className="notice" role="status">{message}</p>}
      {step===1&&<div className="dr-p0-stage">
        <h3>1. Issue an enrollment invitation</h3>
        <div className="dr-p0-form">
          <label className="dr-field"><span>Enrollment mode</span><select value={mode} onChange={e=>{setMode(e.target.value);setPreApproved(false);setIssued(null);setTtl(e.target.value==="manual"?"600":"3600");if(e.target.value==="manual"&&platform==="windows")setPlatform("linux")}}><option value="zero-touch">Zero-Touch (recommended)</option><option value="manual">Manual (interactive credential)</option></select></label>
          <label className="dr-field"><span>Agent platform</span><select value={platform} onChange={e=>setPlatform(e.target.value)}><option value="linux">Linux</option><option value="macos">macOS</option>{mode!=="manual"&&<option value="windows">Windows</option>}</select></label>
          <label className="dr-field"><span>Invitation TTL (seconds)</span><input value={ttl} onChange={e=>setTtl(e.target.value)} placeholder={mode==="manual"?"60–2592000":"60–86400"}/></label>
          <label className="dr-field"><span>Host label</span><input value={label} onChange={e=>setLabel(e.target.value)} placeholder="e.g. branch-gateway"/></label>
          <label className="dr-field"><span>Optional note</span><input value={note} onChange={e=>setNote(e.target.value)} placeholder="Operator context"/></label>
        </div>
        {admin&&mode==="zero-touch"&&<label className="dr-p0-check"><input type="checkbox" checked={preApproved} onChange={e=>setPreApproved(e.target.checked)}/><span>Pre-approve first Host from this ticket (explicit Admin action)</span></label>}
        <p className="muted">Pending Approval is the default, regardless of agent connection status. Credentials are display-once and must not be saved to browser storage.</p>
        <button className="primary" disabled={!admin||busy} onClick={issue}>{busy?"Issuing…":"Issue enrollment →"}</button>
      </div>}
      {step===2&&<div className="dr-p0-stage">
        <h3>2. Install the Agent and join</h3>
        {issued?<div className="warning-box">
          <p><strong>Display-once credential · expires {issued.expires_at||"UNKNOWN"}</strong></p>
          <p>First Host admission: {issued.pre_approved?"Pre-approved by explicit Admin choice":"Pending Approval"}</p>
          {issued.enrollment_code&&<><p>Enrollment code</p><pre className="plan">{issued.enrollment_code}</pre></>}
          <p>Canonical install command</p><pre className="plan">{issued.command||"No install command issued"}</pre>
          <p>{issued.next_step}</p>
        </div>:<p className="muted">No invitation issued during this session. Return to Step 1 to create one, or continue to inspect a previously enrolled Host.</p>}
        <button className="primary" onClick={()=>setStep(3)}>Next: inspect Host admission →</button>
      </div>}
      {step>=3&&<div className="dr-p0-stage">
        <div className="dr-section-head"><div><h3>{step===3?"3. Review and approve the Host":"4. Verify admission, trust and connectivity"}</h3>
          <p className="muted">Current data comes from the canonical Managed Host inventory, not from the enrollment ticket.</p>
        </div><button className="secondary" onClick={refreshHosts} disabled={fetchBusy}>{fetchBusy?"Refreshing…":"Refresh inventory"}</button></div>
        {inventoryError&&<p className="error" role="alert">Inventory unavailable: {inventoryError}</p>}
        <label className="dr-field"><span>Managed Host</span><select value={selectedHost} onChange={e=>{setSelectedHost(e.target.value);setPreview(null);setConfirm("")}}>
          {hosts.length===0&&<option value="">No observed Hosts</option>}
          {hosts.map(h=><option value={String(h.id)} key={h.id}>{h.name||h.label||h.id} · {h.id}</option>)}
        </select></label>
        <p className="dr-p0-status">{selected?hostReadinessLabel(selected):"NO HOST OBSERVED · enrollment may still be pending"}</p>
        <div className="dr-p0-counters">
          <span>Admission: {readiness.admission}</span><span>Trust: {readiness.trust}</span>
          <span>Connection: {readiness.connection}</span><span>Last observation: {readiness.observedAt}</span>
          <span>Effective policy reachability: {readiness.policy}</span>
        </div>
        {step===3&&<>
          <p className="muted">Approval restores normal Core policy evaluation; it does not establish trust or a reachable session. Quarantine remains available under Managed Hosts.</p>
          <button className="secondary" disabled={!admin||!selectedHost||busy} onClick={previewApproval}>Preview approval impact</button>
          {preview&&<div className="dr-p0-review">
            <p>Authoritative Core plan · valid until {preview.valid_until||"UNKNOWN"}</p>
            <details><summary>Review exact approval impact</summary><pre className="plan">{JSON.stringify({preview:preview.preview,impact:preview.impact},null,2)}</pre></details>
            <label className="dr-field"><span>Type {required} to approve</span><input value={confirm} onChange={e=>setConfirm(e.target.value)} placeholder={required}/></label>
            <button className="danger" disabled={!admin||!preview.change_plan_id||confirm!==required||busy} onClick={applyApproval}>Approve through Core</button>
          </div>}
        </>}
        {step===4&&<>
          <p className="muted">Even CONNECTED · APPROVED · TRUSTED does not prove a policy ALLOW or target TCP reachability. Run a Core access decision trace separately.</p>
          <button className="primary" onClick={()=>onNavigate?.("access","access")}>Verify effective access →</button>
        </>}
        <button className="secondary" onClick={()=>onNavigate?.("hosts","infrastructure")}>Open Managed Hosts →</button>
      </div>}
    </div>
    <div className="card"><h3>Enrollment history · Core</h3>
      <div className="dr-p0-table"><table><thead><tr><th>Ticket</th><th>Type</th><th>State</th><th>First-Host admission</th><th>Time remaining</th></tr></thead>
        <tbody>{(data?.items||[]).map((item:any)=><tr key={item.id}><td>{item.label||item.id}</td><td>{item.type}</td><td>{item.state||"UNKNOWN"}</td>
          <td>{item.first_host_admission||"UNKNOWN"}</td><td>{item.remaining_seconds??"UNKNOWN"} seconds</td></tr>)}</tbody>
      </table></div>
      {!(data?.items||[]).length&&<p className="muted">No enrollment history reported.</p>}
    </div>
  </section>;
}
