import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";

type Json = Record<string, any>;
const nav=[
  ["overview","Overview"],["hosts","Managed Hosts"],["services","Remote Services"],
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
        <label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label>
        <button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply Draft</button>
      </>}
    </div>
  </div>;
}

function GuidedApplyPanel({title,build}:{title:string,build:()=>any}){
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState(""),[message,setMessage]=useState(""),[error,setError]=useState("");
  async function doPreview(){setError("");setMessage("");try{const req=build();const result=await api("/api/v1/guided/preview",{method:"POST",body:JSON.stringify(req)});setPreview(result);setConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  async function doApply(){setError("");try{const result=await api("/api/v1/guided/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});setMessage("Applied at revision "+result.revision);setPreview(null);setConfirmation("")}catch(e:any){setError(e.message||String(e))}}
  return <div className="card"><h3>{title}</h3>{error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}<button className="primary" onClick={doPreview}>Preview</button>{preview&&<div className="card"><pre className="plan">{JSON.stringify({change_type:preview.change_type,preview:preview.preview,impact:preview.impact,valid_until:preview.valid_until},null,2)}</pre><label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label><button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply</button></div>}</div>;
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
      <label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label>
      <button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply Temporary Access</button>
    </div>}
  </div>;
}

function SystemPanel({data}:{data:any}){
  const [backupPath,setBackupPath]=useState("/var/lib/drlink/backups/");
  const [preflight,setPreflight]=useState<any>(null),[validation,setValidation]=useState<any>(null),[error,setError]=useState("");
  async function runPreflight(){setError("");try{setPreflight(await api("/api/v1/system/certificate/preflight",{method:"POST",body:"{}"}))}catch(e:any){setError(e.message||String(e))}}
  async function validateBackup(){setError("");try{setValidation(await api("/api/v1/system/backup/validate",{method:"POST",body:JSON.stringify({path:backupPath})}))}catch(e:any){setError(e.message||String(e))}}
  const identity=data.identity||{},certificate=data.certificate||{},backup=data.backup||{};
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
      <h3>Certificate Status</h3>
      <Table items={[{mode:certificate.mode,hostname:certificate.hostname,certificate:certificate.certificate,issuer:certificate.issuer,expires:certificate.expires,days_remaining:certificate.days_remaining,auto_renewal:certificate.auto_renewal}]}/>
      <button className="secondary" onClick={runPreflight}>Run Certificate Preflight</button>
      {preflight&&<pre className="plan">{JSON.stringify(preflight,null,2)}</pre>}
    </div>
    <div className="card">
      <h3>Backup Validation</h3>
      <div className="muted">Validation is read-only and uses the same disaster-recovery validator as CLI restore preflight.</div>
      <div className="toolbar"><input value={backupPath} onChange={e=>setBackupPath(e.target.value)} placeholder="/var/lib/drlink/backups/server-backup-....tar.gz"/><button className="secondary" onClick={validateBackup} disabled={!backupPath}>Validate Backup</button></div>
      {validation&&<pre className="plan">{JSON.stringify(validation,null,2)}</pre>}
    </div>
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
      versions:"/api/v1/versions",system:"/api/v1/system",audit:"/api/v1/audit?limit=100",revisions:"/api/v1/revisions?limit=100",
      doctor:"/api/v1/doctor",health:"/api/v1/health",views:"/api/v1/saved-views",enrollments:"/api/v1/enrollments?limit=50",
    };
    if(paths[active])api(paths[active]).then(setData).catch((e:any)=>setError(e.message||String(e)));
  },[active]);
  if(error)return <div className="error">{error}</div>;
  if(active==="drafts")return <DraftWorkspace/>;
  if(active==="enrollments"&&data)return <EnrollmentPanel data={data} refresh={()=>api("/api/v1/enrollments?limit=50").then(setData)}/>;
  if(active==="search")return <div><div className="toolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search resources and policy"/><button className="primary" onClick={()=>api("/api/v1/search?q="+encodeURIComponent(query)+"&limit=50").then(setData).catch((e:any)=>setError(e.message))}>Search</button></div>{data&&<Table items={(data.items||[]).map((x:any)=>({type:x.resource_type,id:x.id,name:x.name}))}/>}</div>;
  if(active==="overview"&&data){const h=data.overview?.managed_hosts||{},s=data.overview?.remote_services||{},j=data.overview?.management_jobs||{};return <><div className="grid"><Metric label="Managed Hosts" value={h.total}/><Metric label="Connected" value={h.connected}/><Metric label="Remote Services" value={s.total}/><Metric label="Active Jobs" value={j.active_jobs}/></div><div className="card"><h3>Attention Center</h3>{(data.attention?.items||[]).map((x:any)=><span key={x.kind} className={"badge "+x.severity}>{x.label}: {x.count}</span>)}{!(data.attention?.items||[]).length&&<div className="muted">No current attention items</div>}</div></>};
  if(active==="versions"&&data)return <><div className="grid"><Metric label="Server version" value={data.server_version}/><Metric label="Drift" value={data.drift_count}/><Metric label="Unknown" value={data.unknown_count}/></div><Table items={data.hosts||[]}/></>;
  if(active==="system"&&data)return <SystemPanel data={data}/>;
  if(active==="objects"&&data){const rows=Object.entries(data.resources||{}).flatMap(([type,page]:any)=>(page.items||[]).map((item:any)=>({type,id:item.id,name:item.name||item.id,description:item.description||"",status:item.status||""})));return <><Table items={rows}/>{operator.role!=="Read Only"&&<GuidedObjectPanel/>}</>;}
  if(active==="hosts"&&data)return <><Table items={data.items||[]}/>{operator.role!=="Read Only"&&<ManagedHostMetadataPanel/>}</>;
  if(active==="services"&&data)return <><Table items={data.items||[]}/>{operator.role!=="Read Only"&&<RemoteServicePanel/>}</>;
  if(active==="policies"&&data)return <><Table items={data.items||[]}/>{operator.role!=="Read Only"&&<><GuidedPolicySettingsPanel/><GuidedPolicyRulePanel/><TemporaryAccessPanel/></>}</>;
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
