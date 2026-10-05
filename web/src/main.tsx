import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";

type Json = Record<string, any>;
const nav=[
  ["overview","Overview"],["hosts","Managed Hosts"],["services","Remote Services"],["access","Access Operations"],["jobs","Jobs"],
  ["objects","Objects & Groups"],["policies","Policies"],["versions","Version Drift"],["system","System"],
  ["audit","Audit"],["revisions","Revisions"],["doctor","Doctor"],["health","Health"],
  ["search","Search"],["views","Saved Views"],["enrollments","Connect Agent"],["drafts","Draft Workspace"],
];
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

function Table({items}:{items:any[]}){
  if(!items?.length)return <div className="empty">No results</div>;
  const keys=Object.keys(items[0]).filter(k=>typeof items[0][k]!=="object").slice(0,9);
  return <table><thead><tr>{keys.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>
    {items.map((item,i)=><tr key={item.id||i}>{keys.map(k=><td key={k}>{item[k]===null?"":String(item[k]??"")}</td>)}</tr>)}
  </tbody></table>;
}
function Metric({label,value}:{label:string,value:any}){return <div className="card"><div className="muted">{label}</div><div className="metric">{String(value??0)}</div></div>}

function Login({onLogin}:{onLogin:(op:any)=>void}){
  const [username,setUsername]=useState("admin"),[password,setPassword]=useState(""),[totp,setTotp]=useState(""),[recovery,setRecovery]=useState(""),[error,setError]=useState("");
  async function submit(e:React.FormEvent){
    e.preventDefault();setError("");
    try{
      const d=await api("/api/v1/auth/login",{method:"POST",body:JSON.stringify({username,password,totp,recovery_code:recovery})});
      csrf=d.csrf_token;onLogin(d.operator);
    }catch(err:any){setError(err.message||String(err))}
  }
  return <div className="login-wrap"><form className="login" onSubmit={submit}>
    <h1>Data Relay Link</h1><div className="muted">Optional Web Management · local authentication</div>
    {error&&<div className="error">{error}</div>}
    <label>Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label>
    <label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
    <label>MFA code<input inputMode="numeric" autoComplete="one-time-code" value={totp} onChange={e=>setTotp(e.target.value)} placeholder="6-digit TOTP"/></label>
    <label>Recovery code<input value={recovery} onChange={e=>setRecovery(e.target.value)} placeholder="or recovery code"/></label>
    <button className="primary" type="submit">Sign in</button>
  </form></div>
}

function DraftWorkspace(){
  const [bundle,setBundle]=useState("configurationBundle:\n  context: server\n  networkObjects: []\n");
  const [draftId,setDraftId]=useState("");
  const [testResult,setTestResult]=useState<any>(null);
  const [preview,setPreview]=useState<any>(null);
  const [confirmation,setConfirmation]=useState("");
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");

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
    setError("");setMessage("");
    try{
      const id=await ensureDraft();
      const result=await api("/api/v1/drafts/"+id+"/test",{method:"POST",body:"{}"});
      setTestResult(result);setPreview(null);setConfirmation("");
      setMessage("ConfigurationBundle test PASS");
    }catch(e:any){setTestResult(null);setError(e.message||String(e))}
  }
  async function doDiff(){
    setError("");setMessage("");
    try{
      const id=await ensureDraft();
      const result=await api("/api/v1/drafts/"+id+"/diff",{method:"POST",body:"{}"});
      setPreview(result);setTestResult(null);setConfirmation("");
    }catch(e:any){setPreview(null);setError(e.message||String(e))}
  }
  async function doApply(){
    setError("");setMessage("");
    try{
      const id=await ensureDraft();
      const result=await api("/api/v1/drafts/"+id+"/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});
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
    setError("");
    try{
      const result=await api("/api/v1/drafts/"+draftId+"/export");
      setBundle(result.bundle_text);setMessage("Draft ConfigurationBundle exported to the editor");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doExportCurrent(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/configuration/export");
      setBundle(result.bundle_text);setPreview(null);setTestResult(null);setConfirmation("");
      setMessage("Current redacted configuration exported to the editor");
    }catch(e:any){setError(e.message||String(e))}
  }
  return <div className="draft-layout">
    <div className="card">
      <h3>Configuration Draft</h3>
      <div className="muted">Non-authoritative until Apply. Test and Diff use the canonical ConfigurationBundle engine; Apply is revision-bound.</div>
      {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
      <textarea className="draft-editor" value={bundle} onChange={e=>setBundle(e.target.value)} spellCheck={false}/>
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
  const changes=(blast?.decision_changes||[]).map((x:any)=>({
    plane:x.flow?.plane||"",
    source:x.flow?.source||"",
    destination:x.flow?.destination||"",
    selector:x.flow?.service||x.flow?.permission||"",
    current:x.current,
    proposed:x.proposed,
  }));
  return <div className="card">
    <h4>Blast Radius / Draft Graph Overlay</h4>
    <div className="muted">Core-computed policy/inventory facts only. Unknowns are explicit; this is not network-topology discovery.</div>
    {blast&&<div className="grid">
      <Metric label="Broadens access" value={blast.access_broadened?"YES":"NO"}/>
      <Metric label="Narrows access" value={blast.access_narrowed?"YES":"NO"}/>
      <Metric label="Newly reachable" value={limits.newly_reachable_total??(blast.newly_reachable||[]).length}/>
      <Metric label="Newly blocked" value={limits.newly_blocked_total??(blast.newly_blocked||[]).length}/>
      <Metric label="Truncated" value={limits.truncated?"YES":"NO"}/>
    </div>}
    {limits.truncated&&<div className="warning-box">Blast Radius is bounded/truncated: {(limits.truncated_by||[]).join(", ")||"limit reached"}. Review the limit metadata before Apply.</div>}
    {regression&&<div className={regression.ok?"notice":"warning-box"}>Required Policy Tests: {regression.passed}/{regression.count} pass · failures {regression.required_failed}</div>}
    {blast&&<div className="muted">Affected rules: {(blast.affected_rules||[]).join(", ")||"none"} · Managed Hosts: {(blast.affected_managed_hosts||[]).join(", ")||"none"} · Remote Services: {(blast.affected_remote_services||[]).join(", ")||"none"}</div>}
    {changes.length>0&&<Table items={changes}/>}
    {overlay&&<div className="muted">Graph edges · added {limits.references_added_total??(overlay.added_edge_ids||[]).length} · removed {limits.references_removed_total??(overlay.removed_edge_ids||[]).length} · unchanged {(overlay.unchanged_edge_ids||[]).length}</div>}
    {(blast?.unknowns||[]).length>0&&<div className="warning-box">Unknown / not deterministically modeled: {(blast.unknowns||[]).slice(0,10).join(" · ")}</div>}
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
  return <div><div className="card"><h3>Guided Managed Host Metadata</h3><div className="toolbar"><input value={host} onChange={e=>setHost(e.target.value)} placeholder="Managed Host ID/name"/><input value={label} onChange={e=>setLabel(e.target.value)} placeholder="Optional label"/><input value={description} onChange={e=>setDescription(e.target.value)} placeholder="Description (blank clears)"/><input value={tags} onChange={e=>setTags(e.target.value)} placeholder="tags: env=prod,owner=netops"/></div></div><GuidedApplyPanel title="Managed Host Change Plan" build={request}/></div>;
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
      <input value={host} onChange={e=>setHost(e.target.value)} placeholder="Managed Host ID/name"/>
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
  return <div><div className="card"><h3>Guided Object / Group</h3><div className="toolbar"><select value={kind} onChange={e=>{setKind(e.target.value);setSubtype(e.target.value==="service-object"?"tcp":"ip")}}><option value="network-object">Network Object</option><option value="network-group">Network Group</option><option value="service-object">Service Object</option><option value="service-group">Service Group</option><option value="permission-object">Permission Object</option><option value="permission-group">Permission Group</option></select><select value={operation} onChange={e=>setOperation(e.target.value)}><option value="set">Create / edit</option><option value="delete">Delete</option></select><input value={name} onChange={e=>setName(e.target.value)} placeholder="Name"/>{operation==="set"&&kind==="network-object"&&<><input value={subtype} onChange={e=>setSubtype(e.target.value)} placeholder="ip/fqdn/network/host"/><input value={value} onChange={e=>setValue(e.target.value)} placeholder="Value"/></>}{operation==="set"&&kind==="service-object"&&<><input value={subtype} onChange={e=>setSubtype(e.target.value)} placeholder="tcp/udp/fixed-tcp"/><input value={port} onChange={e=>setPort(e.target.value)} placeholder="Port"/></>}{operation==="set"&&!(["network-object","service-object"] as string[]).includes(kind)&&<input value={items} onChange={e=>setItems(e.target.value)} placeholder={kind==="permission-object"?"Permissions, comma-separated":"Members, comma-separated"}/>}</div></div><GuidedApplyPanel title="Object / Group Change Plan" build={request}/></div>;
}

function RemoteServicePanel(){
  const [owner,setOwner]=useState(""),[name,setName]=useState(""),[operation,setOperation]=useState("set"),[destination,setDestination]=useState("this-host"),[service,setService]=useState(""),[enabled,setEnabled]=useState(true);
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[job,setJob]=useState<any>(null),[error,setError]=useState("");
  async function doPreview(){
    setError("");setJob(null);
    try{
      const body:any={owner,name,operation};
      if(operation==="set"){body.destination=destination;body.service=service;body.enabled=enabled;}
      const result=await api("/api/v1/remote-services/preview",{method:"POST",body:JSON.stringify(body)});
      setPreview(result);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doApply(){
    setError("");
    try{
      const result=await api("/api/v1/remote-services/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});
      setJob(result);setPreview(null);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function refreshJob(){
    if(!job?.job_id)return;
    try{setJob(await api("/api/v1/jobs/"+encodeURIComponent(job.job_id)))}catch(e:any){setError(e.message||String(e))}
  }
  const ready=owner&&name&&(operation==="delete"||(destination&&service));
  return <div className="card"><h3>Guided Remote Service</h3>
    <div className="muted">Agent-owned lifecycle. Apply only queues work to the authenticated owner Agent; runtime success is shown only after the Job completes.</div>
    {error&&<div className="error">{error}</div>}
    <div className="toolbar">
      <input value={owner} onChange={e=>setOwner(e.target.value)} placeholder="Owner Managed Host ID/name"/>
      <input value={name} onChange={e=>setName(e.target.value)} placeholder="Remote Service name"/>
      <select value={operation} onChange={e=>setOperation(e.target.value)}><option value="set">Create / edit</option><option value="delete">Delete</option></select>
      {operation==="set"&&<><input value={destination} onChange={e=>setDestination(e.target.value)} placeholder="Destination"/><input value={service} onChange={e=>setService(e.target.value)} placeholder="Service Object"/><label><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> Enabled</label></>}
      <button className="primary" onClick={doPreview} disabled={!ready}>Preview</button>
    </div>
    {preview&&<div className="card"><pre className="plan">{JSON.stringify({owner:preview.owner,impact:preview.impact,valid_until:preview.valid_until},null,2)}</pre><label className="apply-label">Type APPLY to queue<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label><button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Queue Agent Job</button></div>}
    {job&&<div className="notice"><strong>Job:</strong> {job.job_id||job.id} · {job.job_status||job.status}<button className="secondary" onClick={refreshJob}>Refresh Job</button><pre className="plan">{JSON.stringify(job,null,2)}</pre></div>}
  </div>;
}

function EnrollmentPanel({data,refresh}:{data:any,refresh:()=>void}){
  const [mode,setMode]=useState("zero-touch"),[platform,setPlatform]=useState("linux"),[ttl,setTtl]=useState("3600"),[label,setLabel]=useState(""),[note,setNote]=useState("");
  const [issued,setIssued]=useState<any>(null),[error,setError]=useState("");
  async function issue(){
    setError("");setIssued(null);
    try{
      const path=mode==="manual"?"/api/v1/enrollments/manual":"/api/v1/enrollments/zero-touch";
      const result=await api(path,{method:"POST",body:JSON.stringify({platform,ttl_seconds:ttl,label,note})});
      setIssued(result);refresh();
    }catch(e:any){setError(e.message||String(e))}
  }
  const maxTtl=mode==="manual"?"2592000":"86400";
  return <>
    <div className="card"><h3>Connect Agent</h3>
      <div className="muted">Zero-Touch is recommended. Manual Enrollment keeps the credential out of the install command and prompts for it interactively. Secret-bearing material is display-once.</div>
      {error&&<div className="error">{error}</div>}
      <div className="toolbar">
        <select value={mode} onChange={e=>{setMode(e.target.value);setIssued(null);setTtl(e.target.value==="manual"?"600":"3600")}}><option value="zero-touch">Zero-Touch</option><option value="manual">Manual Enrollment</option></select>
        <select value={platform} onChange={e=>setPlatform(e.target.value)}><option value="linux">Linux</option><option value="macos">macOS</option>{mode!=="manual"&&<option value="windows">Windows</option>}</select>
        <input value={ttl} onChange={e=>setTtl(e.target.value)} placeholder={"TTL seconds (60-"+maxTtl+")"}/>
        <input value={label} onChange={e=>setLabel(e.target.value)} placeholder="Managed Host label"/>
        <input value={note} onChange={e=>setNote(e.target.value)} placeholder="Optional note"/>
        <button className="primary" onClick={issue}>Issue Enrollment</button>
      </div>
      {issued&&<div className="warning-box">
        <strong>Display once · expires {issued.expires_at}</strong>
        {issued.enrollment_code&&<><div>Enrollment Code</div><pre className="plan">{issued.enrollment_code}</pre></>}
        <div>Install command</div><pre className="plan">{issued.command}</pre>
        <div>{issued.next_step}</div>
      </div>}
    </div>
    <div className="card"><h3>Enrollment status</h3><Table items={data?.items||[]}/></div>
  </>;
}

function GuidedPolicySettingsPanel(){
  const [plane,setPlane]=useState("remote"),[operation,setOperation]=useState("set-enforcement"),[enabled,setEnabled]=useState(true);
  function request(){const payload:any={operation};if(operation==="set-enforcement")payload.enabled=enabled;return {change_type:plane+"-access-policy",payload};}
  return <div><div className="card"><h3>Access Policy Settings</h3><div className="muted">Enable/disable enforcement or reset policy mode and all rules through the same Core policy functions as CLI.</div><div className="toolbar"><select value={plane} onChange={e=>setPlane(e.target.value)}><option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option></select><select value={operation} onChange={e=>setOperation(e.target.value)}><option value="set-enforcement">Set enforcement</option><option value="reset">Reset policy + rules</option></select>{operation==="set-enforcement"&&<label><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> Enforcement enabled</label>}</div></div><GuidedApplyPanel title="Access Policy Change Plan" build={request}/></div>;
}

function GuidedPolicyRulePanel(){
  const [plane,setPlane]=useState("remote"),[operation,setOperation]=useState("set"),[name,setName]=useState(""),[mode,setMode]=useState("whitelist");
  const [source,setSource]=useState(""),[destination,setDestination]=useState(""),[selector,setSelector]=useState(""),[enabled,setEnabled]=useState(true),[expiresAt,setExpiresAt]=useState(""),[paths,setPaths]=useState("");
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[message,setMessage]=useState(""),[error,setError]=useState("");
  async function doPreview(){
    setError("");setMessage("");
    try{
      const payload:any={operation,name};
      if(operation==="set"){
        payload.mode=mode;payload.source=source;payload.destination=destination;payload.enabled=enabled;
        if(expiresAt)payload.expires_at=expiresAt;
        if(plane==="ai"){
          payload.permission=selector;
          if(paths.trim())payload.paths=paths.split(",").map(x=>x.trim()).filter(Boolean);
        }else payload.service=selector;
      }
      const result=await api("/api/v1/guided/preview",{method:"POST",body:JSON.stringify({change_type:plane+"-access-rule",payload})});
      setPreview(result);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doApply(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/guided/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});
      setMessage("Access Rule applied at revision "+result.revision);setPreview(null);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  const ready=name&&(
    operation==="delete"||(source&&destination&&selector)
  );
  return <div className="card">
    <h3>Guided Access Rule</h3>
    <div className="muted">Preview and apply Remote, Internet, or AI Access rules through the same Core Change Plan path as CLI.</div>
    {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
    <div className="toolbar">
      <select value={plane} onChange={e=>setPlane(e.target.value)}><option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option></select>
      <select value={operation} onChange={e=>setOperation(e.target.value)}><option value="set">Create / edit</option><option value="delete">Delete</option></select>
      <input value={name} onChange={e=>setName(e.target.value)} placeholder="Rule name"/>
      {operation==="set"&&<>
        <select value={mode} onChange={e=>setMode(e.target.value)}><option value="whitelist">Whitelist</option><option value="blacklist">Blacklist</option></select>
        <input value={source} onChange={e=>setSource(e.target.value)} placeholder={plane==="ai"?"AI Identity":"Source object/group"}/>
        <input value={destination} onChange={e=>setDestination(e.target.value)} placeholder="Destination object/group"/>
        <input value={selector} onChange={e=>setSelector(e.target.value)} placeholder={plane==="ai"?"Permission object/group":"Service object/group"}/>
        {plane==="ai"&&<input value={paths} onChange={e=>setPaths(e.target.value)} placeholder="Optional paths, comma-separated"/>}
        <input value={expiresAt} onChange={e=>setExpiresAt(e.target.value)} placeholder="Optional expiry ISO8601"/>
        <label><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> Enabled</label>
      </>}
      <button className="primary" onClick={doPreview} disabled={!ready}>Preview</button>
    </div>
    {preview&&<div className="card">
      {preview.impact?.warning&&<div className="warning-box">{preview.impact.warning}</div>}
      <pre className="plan">{JSON.stringify({resource:preview.resource_ref,impact:preview.impact,preview:preview.preview},null,2)}</pre>
      <BlastRadiusView preview={preview}/>
      <label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label>
      <button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply Access Rule</button>
    </div>}
  </div>;
}

function TemporaryAccessPanel(){
  const [plane,setPlane]=useState("remote"),[rule,setRule]=useState(""),[operation,setOperation]=useState("set"),[expiresAt,setExpiresAt]=useState("");
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[message,setMessage]=useState(""),[error,setError]=useState("");
  async function doPreview(){
    setError("");setMessage("");
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
      <select value={plane} onChange={e=>setPlane(e.target.value)}><option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option></select>
      <input value={rule} onChange={e=>setRule(e.target.value)} placeholder="Rule name"/>
      <select value={operation} onChange={e=>setOperation(e.target.value)}><option value="set">Set / change expiry</option><option value="clear">Clear expiry</option></select>
      {operation==="set"&&<input value={expiresAt} onChange={e=>setExpiresAt(e.target.value)} placeholder="2030-01-01T00:00:00Z"/>}
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
          <input value={testName} onChange={e=>setTestName(e.target.value)} placeholder="Test name"/>
          <select value={expected} onChange={e=>setExpected(e.target.value)}><option value="ALLOW">Expect ALLOW</option><option value="DENY">Expect DENY</option></select>
          <label><input type="checkbox" checked={required} onChange={e=>setRequired(e.target.checked)}/> Required</label>
          <label><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> Enabled</label>
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

function SystemPanel({data,operator}:{data:any,operator:any}){
  const [backupPath,setBackupPath]=useState("/var/lib/drlink/backups/");
  const [renewConfirmation,setRenewConfirmation]=useState(""),[restoreConfirmation,setRestoreConfirmation]=useState("");
  const [certMode,setCertMode]=useState(String(data.certificate?.mode||"AUTO_ACME").toLowerCase().replaceAll("_","-"));
  const [certHostname,setCertHostname]=useState(data.certificate?.hostname||""),[certEmail,setCertEmail]=useState(data.certificate?.contact_email||""),[acmeEnv,setAcmeEnv]=useState(String(data.certificate?.acme_environment||"PRODUCTION").toLowerCase());
  const [certConfigConfirmation,setCertConfigConfirmation]=useState(""),[issueConfirmation,setIssueConfirmation]=useState(""),[importConfirmation,setImportConfirmation]=useState("");
  const [certPem,setCertPem]=useState(""),[keyPem,setKeyPem]=useState(""),[chainPem,setChainPem]=useState("");
  const [engineUpdateConfirmation,setEngineUpdateConfirmation]=useState("");
  const [preflight,setPreflight]=useState<any>(null),[renewal,setRenewal]=useState<any>(null),[certAction,setCertAction]=useState<any>(null),[updateResult,setUpdateResult]=useState<any>(null),[validation,setValidation]=useState<any>(null),[backupArtifact,setBackupArtifact]=useState<any>(null),[supportArtifact,setSupportArtifact]=useState<any>(null),[error,setError]=useState("");
  async function runPreflight(){setError("");try{setPreflight(await api("/api/v1/system/certificate/preflight",{method:"POST",body:"{}"}))}catch(e:any){setError(e.message||String(e))}}
  async function configureCertificate(){setError("");setCertAction(null);try{setCertAction(await api("/api/v1/system/certificate/configure",{method:"POST",body:JSON.stringify({mode:certMode,hostname:certHostname,contact_email:certEmail,acme_environment:acmeEnv,confirmation:certConfigConfirmation})}));setCertConfigConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function issueCertificate(){setError("");setCertAction(null);try{setCertAction(await api("/api/v1/system/certificate/issue",{method:"POST",body:JSON.stringify({confirmation:issueConfirmation})}));setIssueConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function importCertificate(){setError("");setCertAction(null);try{setCertAction(await api("/api/v1/system/certificate/import",{method:"POST",body:JSON.stringify({cert_pem:certPem,key_pem:keyPem,chain_pem:chainPem,confirmation:importConfirmation})}));setImportConfirmation("");setCertPem("");setKeyPem("");setChainPem("")}catch(e:any){setError(e.message||String(e))}}
  async function renewCertificate(){setError("");setRenewal(null);try{setRenewal(await api("/api/v1/system/certificate/renew",{method:"POST",body:JSON.stringify({confirmation:renewConfirmation})}));setRenewConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function checkUpdate(target:string){setError("");setUpdateResult(null);try{setUpdateResult(await api("/api/v1/system/update/check",{method:"POST",body:JSON.stringify({target})}))}catch(e:any){setError(e.message||String(e))}}
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
      <Metric label="Backup Ready" value={backup.create_available&&backup.validate_available?"YES":"NO"}/>
    </div>
    <div className="card">
      <h3>Release Provenance</h3>
      <Table items={[{source_ref:identity.source_ref,source_head:identity.source_head,bundle_sha256:identity.bundle_sha256||"not recorded"}]}/>
    </div>
    <div className="card">
      <h3>Update</h3>
      <div className="muted">Checks use the canonical read-only updater paths. Core product apply remains CLI-only until DRL3-7 qualifies Web package update/reinstall semantics.</div>
      <div className="toolbar">
        <button className="secondary" onClick={()=>checkUpdate("product")} disabled={!update.product_check_available}>Check Product Update</button>
        <button className="secondary" onClick={()=>checkUpdate("engine")} disabled={!update.engine_check_available}>Check Relay Engine Update</button>
      </div>
      {operator.role==="Admin"&&update.engine_apply_via_web&&<div className="toolbar"><input value={engineUpdateConfirmation} onChange={e=>setEngineUpdateConfirmation(e.target.value)} placeholder="Type UPDATE ENGINE"/><button className="danger" onClick={updateEngine} disabled={engineUpdateConfirmation!=="UPDATE ENGINE"}>Update Relay Engine</button></div>}
      <div className="muted">Product update apply via Web: {update.product_apply_via_web?"enabled":"deferred to "+(update.product_apply_phase||"DRL3-7")}</div>
      {updateResult&&<pre className="plan">{JSON.stringify(updateResult,null,2)}</pre>}
    </div>
    <div className="card">
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
    <div className="card">
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

function AccessOperations({operator}:{operator:any}){
  const [plane,setPlane]=useState("remote"),[source,setSource]=useState(""),[destination,setDestination]=useState(""),[selector,setSelector]=useState("");
  const [diagnosis,setDiagnosis]=useState<any>(null),[live,setLive]=useState<any>(null),[error,setError]=useState("");
  const [liveResource,setLiveResource]=useState(""),[cutoffState,setCutoffState]=useState<any>(null);
  const [scopeKind,setScopeKind]=useState("plane"),[scopeRef,setScopeRef]=useState(""),[cutoffOperation,setCutoffOperation]=useState("apply"),[reason,setReason]=useState("");
  const [cutoffPreview,setCutoffPreview]=useState<any>(null),[cutoffConfirm,setCutoffConfirm]=useState(""),[cutoffMessage,setCutoffMessage]=useState("");
  const scopeOptions:Record<string,string[]>={remote:["plane","remote-service"],internet:["plane","managed-host"],ai:["plane","ai-identity"]};

  async function loadCutoffs(){
    try{setCutoffState(await api("/api/v1/emergency-cutoffs?plane="+encodeURIComponent(plane)))}catch(e:any){setError(e.message||String(e))}
  }
  useEffect(()=>{loadCutoffs()},[plane]);
  function changePlane(value:string){setPlane(value);setSelector("");setDiagnosis(null);setLive(null);setScopeKind("plane");setScopeRef("");setCutoffPreview(null);setCutoffConfirm("")}
  async function runDiagnosis(){
    setError("");setDiagnosis(null);
    try{
      const body:any={plane,source,destination};
      if(plane==="ai")body.permission=selector;else body.service=selector;
      setDiagnosis(await api("/api/v1/diagnose",{method:"POST",body:JSON.stringify(body)}));
    }catch(e:any){setError(e.message||String(e))}
  }
  async function loadLive(){
    setError("");
    try{
      const q=new URLSearchParams({plane,limit:"50"});
      if(liveResource)q.set("resource",liveResource);
      setLive(await api("/api/v1/live-access?"+q.toString()));
    }catch(e:any){setError(e.message||String(e))}
  }
  async function previewCutoff(){
    setError("");setCutoffMessage("");setCutoffConfirm("");
    try{
      const body:any={plane,scope_kind:scopeKind,operation:cutoffOperation,reason};
      if(scopeKind!=="plane")body.scope_ref=scopeRef;
      setCutoffPreview(await api("/api/v1/emergency-cutoff/preview",{method:"POST",body:JSON.stringify(body)}));
    }catch(e:any){setCutoffPreview(null);setError(e.message||String(e))}
  }
  async function applyCutoff(){
    setError("");
    try{
      const result=await api("/api/v1/emergency-cutoff/apply",{method:"POST",body:JSON.stringify({
        operation:cutoffOperation,
        change_plan_id:cutoffPreview?.change_plan_id||"",
        confirmation:cutoffConfirm,
      })});
      setCutoffMessage((cutoffOperation==="clear"?"Cutoff cleared":"Cutoff applied")+" at revision "+result.revision+"; existing sessions terminated: "+String(result.active_sessions_terminated));
      setCutoffPreview(null);setCutoffConfirm("");
      await loadLive();
      await loadCutoffs();
    }catch(e:any){setError(e.message||String(e))}
  }
  const layers=(diagnosis?.layers||[]).map((x:any)=>({layer:x.layer,status:x.status,summary:x.summary}));
  return <>
    {error&&<div className="error">{error}</div>}
    <div className="card">
      <h3>Connection Diagnosis</h3>
      <div className="muted">Side-effect-free Core correlation. No browser-triggered DNS or target probe is launched; missing evidence stays UNKNOWN.</div>
      <div className="toolbar">
        <select value={plane} onChange={e=>changePlane(e.target.value)}><option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option></select>
        <input value={source} onChange={e=>setSource(e.target.value)} placeholder={plane==="ai"?"AI Identity / source":"Source Object / Group"}/>
        <input value={destination} onChange={e=>setDestination(e.target.value)} placeholder="Destination Object / Group"/>
        <input value={selector} onChange={e=>setSelector(e.target.value)} placeholder={plane==="ai"?"Permission Object / Group":"Service Object / Group"}/>
        <button className="primary" onClick={runDiagnosis}>Diagnose</button>
      </div>
      {diagnosis&&<>
        <div className="grid"><Metric label="Overall" value={diagnosis.overall}/><Metric label="Network probe" value={diagnosis.network_probe_performed?"YES":"NO"}/></div>
        <Table items={layers}/>
        <div className="muted">Next action: {diagnosis.next_action}</div>
      </>}
    </div>
    <div className="card">
      <h3>Live Access Visibility</h3>
      <div className="muted">Bounded current-use evidence only. Remote Access remains UNKNOWN unless official FRP can prove exact lifecycle state.</div>
      <div className="toolbar">
        <input value={liveResource} onChange={e=>setLiveResource(e.target.value)} placeholder="Optional resource/session/identity filter"/>
        <button className="secondary" onClick={loadLive}>Refresh {plane} live access</button>
      </div>
      {live&&<>
        <div className="grid"><Metric label="Fidelity" value={live.fidelity}/><Metric label="Active count" value={live.active_count??"UNKNOWN"}/><Metric label="Returned" value={(live.observations||[]).length}/></div>
        {live.reason&&<div className="warning-box">{live.reason}</div>}
        <Table items={live.observations||[]}/>
      </>}
    </div>
    <div className="card">
      <h3>Active Emergency Cutoffs</h3>
      <div className="muted">Authoritative active override state for the selected plane. Clearing a cutoff reveals the unchanged normal policy.</div>
      {cutoffState&&<div className="grid"><Metric label="Active" value={cutoffState.count||0}/><Metric label="Returned" value={cutoffState.returned||0}/><Metric label="Truncated" value={cutoffState.truncated?"YES":"NO"}/></div>}
      <Table items={cutoffState?.items||[]}/>
    </div>
    {operator.role==="Admin"&&<div className="card">
      <h3>Emergency New-Access Cutoff</h3>
      <div className="warning-box">This reversible override affects new authorization only. Existing sessions are not claimed to be terminated.</div>
      {cutoffMessage&&<div className="notice">{cutoffMessage}</div>}
      <div className="toolbar">
        <select value={cutoffOperation} onChange={e=>{setCutoffOperation(e.target.value);setCutoffPreview(null)}}><option value="apply">Apply cutoff</option><option value="clear">Clear cutoff</option></select>
        <select value={scopeKind} onChange={e=>{setScopeKind(e.target.value);setScopeRef("");setCutoffPreview(null)}}>{scopeOptions[plane].map(x=><option key={x} value={x}>{x}</option>)}</select>
        {scopeKind!=="plane"&&<input value={scopeRef} onChange={e=>setScopeRef(e.target.value)} placeholder={scopeKind+" selector"}/>}
        {cutoffOperation==="apply"&&<input value={reason} onChange={e=>setReason(e.target.value)} placeholder="Incident reason (optional)"/>}
        <button className="danger" onClick={previewCutoff}>Preview cutoff</button>
      </div>
      {cutoffPreview&&<>
        <pre className="plan">{JSON.stringify({scope_kind:cutoffPreview.scope_kind,scope_ref:cutoffPreview.scope_ref,scope_display:cutoffPreview.scope_display,currently_active:cutoffPreview.currently_active,desired_active:cutoffPreview.desired_active,impact:cutoffPreview.impact,active_sessions_terminated:cutoffPreview.active_sessions_terminated},null,2)}</pre>
        <label className="apply-label">Type CONFIRM CUTOFF<input value={cutoffConfirm} onChange={e=>setCutoffConfirm(e.target.value)} placeholder="CONFIRM CUTOFF"/></label>
        <button className="danger" onClick={applyCutoff} disabled={cutoffConfirm!=="CONFIRM CUTOFF"}>{cutoffOperation==="clear"?"Clear Cutoff":"Apply Cutoff"}</button>
      </>}
    </div>}
  </>;
}

function AuditExplorer({operator}:{operator:any}){
  const [data,setData]=useState<any>(null),[retention,setRetention]=useState<any>(null),[error,setError]=useState(""),[message,setMessage]=useState(""),[exportResult,setExportResult]=useState<any>(null);
  const [start,setStart]=useState(""),[end,setEnd]=useState(""),[category,setCategory]=useState(""),[eventType,setEventType]=useState(""),[actor,setActor]=useState(""),[resource,setResource]=useState(""),[result,setResult]=useState(""),[correlation,setCorrelation]=useState("");
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
  async function load(cursor?:string){
    setError("");
    try{const q=filterParams();if(cursor)q.set("cursor",cursor);setData(await api("/api/v1/audit?"+q.toString()))}catch(e:any){setError(e.message||String(e))}
  }
  async function loadRetention(){
    try{
      const value=await api("/api/v1/audit/retention");
      setRetention(value);
      if(value?.config){setControlDays(String(value.config.control_days));setAccessDays(String(value.config.access_days));setMaxEvents(String(value.config.max_events))}
    }catch(e:any){setError(e.message||String(e))}
  }
  useEffect(()=>{load();loadRetention()},[]);
  async function exportAudit(){
    setError("");setMessage("");
    try{const value=await api("/api/v1/audit/export",{method:"POST",body:JSON.stringify({filters:exportFilters()})});setExportResult(value);setMessage("Audit export created: "+String(value.path||""))}catch(e:any){setError(e.message||String(e))}
  }
  async function configureRetention(){
    setError("");setMessage("");
    try{
      const value=await api("/api/v1/audit/retention/configure",{method:"POST",body:JSON.stringify({control_days:Number(controlDays),access_days:Number(accessDays),max_events:Number(maxEvents)})});
      setMessage("Audit retention configured.");
      setRetention((prev:any)=>({...prev,config:value.config}));
      await load();
    }catch(e:any){setError(e.message||String(e))}
  }
  async function runRetention(){
    setError("");setMessage("");
    try{const value=await api("/api/v1/audit/retention/run",{method:"POST",body:"{}"});setMessage("Audit retention: "+value.status+" · deleted "+String((value.control_deleted||0)+(value.access_deleted||0)+(value.capacity_deleted||0)));await load();await loadRetention()}catch(e:any){setError(e.message||String(e))}
  }
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
    {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
    <div className="card">
      <h3>Audit Explorer</h3>
      <div className="muted">Unified CONTROL / ACCESS_DECISION / SECURITY_LIFECYCLE history with stable event IDs and bounded keyset pagination.</div>
      <div className="toolbar">
        <input value={start} onChange={e=>setStart(e.target.value)} placeholder="Start UTC"/>
        <input value={end} onChange={e=>setEnd(e.target.value)} placeholder="End UTC"/>
        <select value={category} onChange={e=>setCategory(e.target.value)}><option value="">All categories</option><option value="CONTROL">CONTROL</option><option value="ACCESS_DECISION">ACCESS_DECISION</option><option value="SECURITY_LIFECYCLE">SECURITY_LIFECYCLE</option></select>
        <input value={eventType} onChange={e=>setEventType(e.target.value)} placeholder="Event type"/>
        <input value={actor} onChange={e=>setActor(e.target.value)} placeholder="Actor"/>
        <input value={resource} onChange={e=>setResource(e.target.value)} placeholder="Resource ID"/>
        <input value={result} onChange={e=>setResult(e.target.value)} placeholder="Result"/>
        <input value={correlation} onChange={e=>setCorrelation(e.target.value)} placeholder="Correlation ID"/>
        <button className="primary" onClick={()=>load()}>Search</button>
        <button className="secondary" onClick={exportAudit}>Export NDJSON</button>
      </div>
      <Table items={rows}/>
      {data?.next_cursor&&<button className="secondary" onClick={()=>load(data.next_cursor)}>Next page</button>}
      {exportResult&&<pre className="plan">{JSON.stringify({path:exportResult.path,event_count:exportResult.event_count,schema_version:exportResult.schema_version,sha256:exportResult.sha256,download_exposed:exportResult.download_exposed},null,2)}</pre>}
    </div>
    <div className="card">
      <h3>Audit Retention</h3>
      {retention&&<div className="grid"><Metric label="Events" value={retention.total_events}/><Metric label="DB bytes" value={retention.db_size_bytes}/><Metric label="Capacity exceeded" value={retention.capacity_exceeded?"YES":"NO"}/></div>}
      <div className="muted">{retention?.capacity_policy||"CONTROL/SECURITY and ACCESS_DECISION use split retention."}</div>
      {operator.role==="Admin"&&<div className="toolbar">
        <input value={controlDays} onChange={e=>setControlDays(e.target.value)} placeholder="CONTROL days"/>
        <input value={accessDays} onChange={e=>setAccessDays(e.target.value)} placeholder="ACCESS days"/>
        <input value={maxEvents} onChange={e=>setMaxEvents(e.target.value)} placeholder="Max events"/>
        <button className="secondary" onClick={configureRetention}>Configure</button>
        <button className="danger" onClick={runRetention}>Run Retention</button>
      </div>}
    </div>
  </>;
}

function JobOperations({operator}:{operator:any}){
  const [jobs,setJobs]=useState<any>(null),[detail,setDetail]=useState<any>(null),[error,setError]=useState(""),[message,setMessage]=useState(""),[inventoryExport,setInventoryExport]=useState<any>(null);
  const [jobType,setJobType]=useState("doctor"),[resourceType,setResourceType]=useState("managed-host"),[resource,setResource]=useState(""),[detailId,setDetailId]=useState("");
  const [fleetResourceType,setFleetResourceType]=useState("managed-host"),[fleetResource,setFleetResource]=useState(""),[fleetDescription,setFleetDescription]=useState(""),[fleetTags,setFleetTags]=useState(""),[fleetRemoveTags,setFleetRemoveTags]=useState(""),[fleetAddGroups,setFleetAddGroups]=useState(""),[fleetRemoveGroups,setFleetRemoveGroups]=useState(""),[fleetPreview,setFleetPreview]=useState<any>(null),[fleetConfirm,setFleetConfirm]=useState("");
  async function refresh(){
    setError("");
    try{setJobs(await api("/api/v1/jobs?limit=50"))}catch(e:any){setError(e.message||String(e))}
  }
  useEffect(()=>{refresh()},[]);
  async function start(){
    setError("");setMessage("");
    try{
      const body:any={job_type:jobType,resource_type:resourceType};
      if(resource)body.resource=resource;
      const result=await api("/api/v1/jobs/diagnostic",{method:"POST",body:JSON.stringify(body)});
      setDetail(result.job);
      setDetailId(result.job?.id||"");
      setMessage("Queued "+jobType+" for "+String(result.selection?.target_count||0)+" Managed Host(s)");
      await refresh();
    }catch(e:any){setError(e.message||String(e))}
  }
  async function loadDetail(id?:string){
    const target=(id||detailId).trim();if(!target)return;
    setError("");
    try{const result=await api("/api/v1/jobs/"+encodeURIComponent(target));setDetail(result);setDetailId(target)}catch(e:any){setError(e.message||String(e))}
  }
  function csvList(value:string){return value.split(",").map(x=>x.trim()).filter(Boolean)}
  async function previewFleetMetadata(){
    setError("");setMessage("");setFleetConfirm("");
    try{
      const changes:any={};
      if(fleetDescription!=="")changes.description=fleetDescription;
      if(fleetTags.trim())changes.tags=JSON.parse(fleetTags);
      const removeTags=csvList(fleetRemoveTags);if(removeTags.length)changes.remove_tags=removeTags;
      const addGroups=csvList(fleetAddGroups);if(addGroups.length)changes.add_groups=addGroups;
      const removeGroups=csvList(fleetRemoveGroups);if(removeGroups.length)changes.remove_groups=removeGroups;
      const result=await api("/api/v1/fleet/metadata/preview",{method:"POST",body:JSON.stringify({
        resource_type:fleetResourceType,resource:fleetResource,changes
      })});
      setFleetPreview(result);
    }catch(e:any){setFleetPreview(null);setError(e.message||String(e))}
  }
  async function applyFleetMetadata(){
    if(!fleetPreview)return;
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/fleet/metadata/apply",{method:"POST",body:JSON.stringify({
        change_plan_id:fleetPreview.change_plan_id,confirmation:fleetConfirm
      })});
      setMessage("Fleet metadata applied at revision "+String(result.revision)+" to "+String(result.result?.target_count||0)+" Managed Host(s)");
      setFleetPreview(null);setFleetConfirm("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function exportInventory(){
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/inventory/export",{method:"POST",body:"{}"});
      setInventoryExport(result);
      setMessage("Inventory export created at "+String(result.path||""));
    }catch(e:any){setError(e.message||String(e))}
  }
  async function cancelJob(){
    if(!detail?.id)return;
    setError("");setMessage("");
    try{
      const result=await api("/api/v1/jobs/cancel",{method:"POST",body:JSON.stringify({job_id:detail.id})});
      setDetail(result);
      setMessage("Cancellation requested. Queued targets are cancelled; running targets are not claimed terminated.");
      await refresh();
    }catch(e:any){setError(e.message||String(e))}
  }
  const rows=(jobs?.items||[]).map((x:any)=>({id:x.id,job_type:x.job_type,status:x.status,resource_type:x.resource_type,resource_ref:x.resource_ref,target_count:x.target_count,created_at:x.created_at,finished_at:x.finished_at||""}));
  return <>
    {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
    <div className="card">
      <h3>Bounded Management Jobs</h3>
      <div className="muted">Safe fleet operations only. Jobs are bounded to at most 100 trusted Managed Hosts and use the signed Agent claim/complete transport.</div>
      {operator.role!=="Read Only"&&<div className="toolbar">
        <select value={jobType} onChange={e=>setJobType(e.target.value)}><option value="doctor">Doctor diagnostics</option><option value="refresh">Synchronize / refresh</option><option value="version-check">Version check</option><option value="support-bundle">Support bundle</option></select>
        <select value={resourceType} onChange={e=>{setResourceType(e.target.value);setResource("")}}><option value="managed-host">Managed Host(s)</option><option value="managed-host-group">Managed Host Group</option></select>
        <input value={resource} onChange={e=>setResource(e.target.value)} placeholder={resourceType==="managed-host"?"Host selector; blank = all trusted":"Managed Host Group name / ID"}/>
        <button className="primary" onClick={start} disabled={resourceType==="managed-host-group"&&!resource.trim()}>Start Job</button>
      </div>}
      <div className="toolbar"><button className="secondary" onClick={refresh}>Refresh Jobs</button><input value={detailId} onChange={e=>setDetailId(e.target.value)} placeholder="Job ID"/><button className="secondary" onClick={()=>loadDetail()}>Load Detail</button><button className="secondary" onClick={exportInventory}>Export Inventory</button></div>
      {inventoryExport&&<pre className="plan">{JSON.stringify({path:inventoryExport.path,record_count:inventoryExport.record_count,counts:inventoryExport.counts,sha256:inventoryExport.sha256,download_exposed:inventoryExport.download_exposed},null,2)}</pre>}
      <Table items={rows}/>
    </div>
    {operator.role!=="Read Only"&&<div className="card">
      <h3>Fleet Metadata Change Plan</h3>
      <div className="muted">Bounded to 100 trusted Managed Hosts. Description, tags, and Managed Host Group membership apply atomically as one revision after Preview.</div>
      <div className="toolbar">
        <select value={fleetResourceType} onChange={e=>{setFleetResourceType(e.target.value);setFleetResource("");setFleetPreview(null)}}><option value="managed-host">Managed Host(s)</option><option value="managed-host-group">Managed Host Group</option></select>
        <input value={fleetResource} onChange={e=>{setFleetResource(e.target.value);setFleetPreview(null)}} placeholder={fleetResourceType==="managed-host"?"Host selector; blank = all trusted":"Managed Host Group name / ID"}/>
      </div>
      <label>Description<input value={fleetDescription} onChange={e=>{setFleetDescription(e.target.value);setFleetPreview(null)}} placeholder="Optional description applied to all selected Hosts"/></label>
      <label>Tags JSON<input value={fleetTags} onChange={e=>{setFleetTags(e.target.value);setFleetPreview(null)}} placeholder='{"site":"lab","owner":"secops"}'/></label>
      <label>Remove tags<input value={fleetRemoveTags} onChange={e=>{setFleetRemoveTags(e.target.value);setFleetPreview(null)}} placeholder="comma,separated,tag-keys"/></label>
      <label>Add Managed Host Groups<input value={fleetAddGroups} onChange={e=>{setFleetAddGroups(e.target.value);setFleetPreview(null)}} placeholder="group-a,group-b"/></label>
      <label>Remove Managed Host Groups<input value={fleetRemoveGroups} onChange={e=>{setFleetRemoveGroups(e.target.value);setFleetPreview(null)}} placeholder="group-c"/></label>
      <button className="primary" onClick={previewFleetMetadata} disabled={fleetResourceType==="managed-host-group"&&!fleetResource.trim()}>Preview Fleet Change</button>
      {fleetPreview&&<>
        <pre className="plan">{JSON.stringify({selection:fleetPreview.selection,changes:fleetPreview.changes,preview:fleetPreview.preview,impact:fleetPreview.impact},null,2)}</pre>
        <label className="apply-label">Type APPLY<input value={fleetConfirm} onChange={e=>setFleetConfirm(e.target.value)} placeholder="APPLY"/></label>
        <button className="danger" onClick={applyFleetMetadata} disabled={fleetConfirm!=="APPLY"}>Apply Fleet Metadata</button>
      </>}
    </div>}
    {detail&&<div className="card">
      <h3>Job Detail</h3>
      <div className="grid"><Metric label="Status" value={detail.status}/><Metric label="Targets" value={detail.target_count}/><Metric label="Type" value={detail.job_type}/></div>
      {operator.role!=="Read Only"&&["QUEUED","RUNNING"].includes(String(detail.status||""))&&<button className="danger" onClick={cancelJob}>Cancel Job</button>}
      <Table items={(detail.targets||[]).map((x:any)=>({target_id:x.target_id,status:x.status,attempt:x.attempt,error:x.error||"",updated_at:x.updated_at}))}/>
      <pre className="plan">{JSON.stringify({id:detail.id,resource_type:detail.resource_type,resource_ref:detail.resource_ref,deadline_at:detail.deadline_at,last_error:detail.last_error,targets:(detail.targets||[]).map((x:any)=>({target_id:x.target_id,status:x.status,result:x.result,error:x.error}))},null,2)}</pre>
    </div>}
  </>;
}

function View({active,operator}:{active:string,operator:any}){
  const [data,setData]=useState<any>(null),[error,setError]=useState(""),[query,setQuery]=useState("");
  useEffect(()=>{
    setData(null);setError("");
    const paths:Record<string,string>={
      overview:"/api/v1/overview",hosts:"/api/v1/inventory?resource_type=managed-host&limit=100",
      services:"/api/v1/inventory?resource_type=remote-service&limit=100",
      objects:"/api/v1/objects-groups?limit=50",policies:"/api/v1/policies?limit=100",
      versions:"/api/v1/versions",system:"/api/v1/system",revisions:"/api/v1/revisions?limit=100",
      doctor:"/api/v1/doctor",health:"/api/v1/health",views:"/api/v1/saved-views",enrollments:"/api/v1/enrollments?limit=50",
    };
    if(paths[active])api(paths[active]).then(setData).catch((e:any)=>setError(e.message||String(e)));
  },[active]);
  if(error)return <div className="error">{error}</div>;
  if(active==="drafts")return <DraftWorkspace/>;
  if(active==="access")return <AccessOperations operator={operator}/>;
  if(active==="jobs")return <JobOperations operator={operator}/>;
  if(active==="audit")return <AuditExplorer operator={operator}/>;
  if(active==="enrollments"&&data)return <EnrollmentPanel data={data} refresh={()=>api("/api/v1/enrollments?limit=50").then(setData)}/>;
  if(active==="search")return <div><div className="toolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search resources and policy"/><button className="primary" onClick={()=>api("/api/v1/search?q="+encodeURIComponent(query)+"&limit=50").then(setData).catch((e:any)=>setError(e.message))}>Search</button></div>{data&&<Table items={(data.items||[]).map((x:any)=>({type:x.resource_type,id:x.id,name:x.name}))}/>}</div>;
  if(active==="overview"&&data){const h=data.overview?.managed_hosts||{},s=data.overview?.remote_services||{},j=data.overview?.management_jobs||{};return <><div className="grid"><Metric label="Managed Hosts" value={h.total}/><Metric label="Connected" value={h.connected}/><Metric label="Remote Services" value={s.total}/><Metric label="Active Jobs" value={j.active_jobs}/></div><div className="card"><h3>Attention Center</h3>{(data.attention?.items||[]).map((x:any)=><span key={x.kind} className={"badge "+x.severity}>{x.label}: {x.count}</span>)}{!(data.attention?.items||[]).length&&<div className="muted">No current attention items</div>}</div></>};
  if(active==="versions"&&data)return <><div className="grid"><Metric label="Server version" value={data.server_version}/><Metric label="Drift" value={data.drift_count}/><Metric label="Unknown" value={data.unknown_count}/></div><Table items={data.hosts||[]}/></>;
  if(active==="system"&&data)return <SystemPanel data={data} operator={operator}/>;
  if(active==="objects"&&data){const rows=Object.entries(data.resources||{}).flatMap(([type,page]:any)=>(page.items||[]).map((item:any)=>({type,id:item.id,name:item.name||item.id,description:item.description||"",status:item.status||""})));return <><Table items={rows}/>{operator.role!=="Read Only"&&<GuidedObjectPanel/>}</>;}
  if(active==="hosts"&&data)return <><Table items={data.items||[]}/>{operator.role!=="Read Only"&&<ManagedHostMetadataPanel/>}{operator.role==="Admin"&&<ManagedHostLifecyclePanel/>}</>;
  if(active==="services"&&data)return <><Table items={data.items||[]}/>{operator.role!=="Read Only"&&<RemoteServicePanel/>}</>;
  if(active==="policies"&&data)return <><Table items={data.items||[]}/><PolicySafetyPanel operator={operator}/>{operator.role!=="Read Only"&&<><GuidedPolicySettingsPanel/><GuidedPolicyRulePanel/><TemporaryAccessPanel/></>}</>;
  if(active==="doctor"&&data)return <><div className="grid"><Metric label="Attention" value={data.attention?.count}/><Metric label="Checks" value={(data.checks||[]).length}/></div><Table items={data.checks||[]}/></>;
  if(active==="health"&&data)return <pre className="card">{JSON.stringify(data,null,2)}</pre>;
  if(active==="views"&&data)return <SavedViews data={data} refresh={()=>api("/api/v1/saved-views").then(setData)}/>;
  if(data)return <Table items={data.items||[]}/>;
  return <div className="empty">Loading…</div>;
}

function SavedViews({data,refresh}:{data:any,refresh:()=>void}){
  const [name,setName]=useState(""),[filter,setFilter]=useState(""),[error,setError]=useState("");
  async function save(){try{await api("/api/v1/saved-views",{method:"POST",body:JSON.stringify({name,payload:{filter}})});setName("");setFilter("");refresh()}catch(e:any){setError(e.message||String(e))}}
  return <>{error&&<div className="error">{error}</div>}<div className="toolbar"><input placeholder="View name" value={name} onChange={e=>setName(e.target.value)}/><input placeholder="Filter text" value={filter} onChange={e=>setFilter(e.target.value)}/><button className="primary" onClick={save}>Save current view</button></div><Table items={(data.items||[]).map((x:any)=>({id:x.id,name:x.name,updated_at:x.updated_at}))}/></>;
}

function Shell({operator,onLogout}:{operator:any,onLogout:()=>void}){
  const [active,setActive]=useState("overview");
  async function logout(){try{await api("/api/v1/auth/logout",{method:"POST",body:"{}"})}finally{csrf="";onLogout()}}
  const visibleNav=nav.filter(([id])=>{
    if(id==="drafts")return operator.role!=="Read Only";
    if(id==="enrollments")return operator.role==="Admin";
    return true;
  });
  const title=visibleNav.find(x=>x[0]===active)?.[1]||"Overview";
  return <div className="shell"><aside className="sidebar"><div className="brand">Data Relay Link<small>Web Management 3.0</small></div><div className="nav">{visibleNav.map(([id,label])=><button key={id} className={id===active?"active":""} onClick={()=>setActive(id)}>{label}</button>)}</div></aside><section className="content"><div className="top"><div><div className="title">{title}</div><div className="muted">{operator.username} · {operator.role}</div></div><button className="secondary" onClick={logout}>Sign out</button></div><View active={active} operator={operator}/></section></div>;
}

function App(){
  const [operator,setOperator]=useState<any>(undefined);
  useEffect(()=>{api("/api/v1/session").then(d=>setOperator(d.operator)).catch(()=>setOperator(null))},[]);
  if(operator===undefined)return <div className="login-wrap"><div className="muted">Loading…</div></div>;
  if(!operator)return <Login onLogin={setOperator}/>;
  return <Shell operator={operator} onLogout={()=>setOperator(null)}/>;
}

createRoot(document.getElementById("app")!).render(<App/>);
