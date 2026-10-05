import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";

type Json = Record<string, any>;
const nav=[
  ["overview","Overview"],["hosts","Managed Hosts"],["services","Remote Services"],
  ["objects","Objects & Groups"],["policies","Policies"],["versions","Version Drift"],
  ["audit","Audit"],["revisions","Revisions"],["doctor","Doctor"],["health","Health"],
  ["search","Search"],["views","Saved Views"],["drafts","Draft Workspace"],
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
  async function doPreview(){
    setError("");setMessage("");
    try{
      const id=await ensureDraft();
      const result=await api("/api/v1/drafts/"+id+"/preview",{method:"POST",body:"{}"});
      setPreview(result);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doApply(){
    setError("");setMessage("");
    try{
      const id=await ensureDraft();
      const result=await api("/api/v1/drafts/"+id+"/apply",{method:"POST",body:JSON.stringify({change_plan_id:preview?.change_plan_id||"",confirmation})});
      setMessage("Applied at revision "+result.revision);setPreview(null);setDraftId("");setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doCancel(){
    if(!draftId)return;
    setError("");
    try{
      await api("/api/v1/drafts/"+draftId+"/cancel",{method:"POST",body:"{}"});
      setMessage("Draft cancelled with zero authoritative mutation");setDraftId("");setPreview(null);setConfirmation("");
    }catch(e:any){setError(e.message||String(e))}
  }
  async function doExport(){
    if(!draftId)return;
    setError("");
    try{
      const result=await api("/api/v1/drafts/"+draftId+"/export");
      setBundle(result.bundle_text);setMessage("Draft exported to the editor");
    }catch(e:any){setError(e.message||String(e))}
  }
  return <div className="draft-layout">
    <div className="card">
      <h3>Configuration Draft</h3>
      <div className="muted">Non-authoritative until Apply. Preview uses the canonical ConfigurationBundle engine and revision guard.</div>
      {error&&<div className="error">{error}</div>}{message&&<div className="notice">{message}</div>}
      <textarea className="draft-editor" value={bundle} onChange={e=>setBundle(e.target.value)} spellCheck={false}/>
      <div className="toolbar">
        <button className="primary" onClick={doPreview}>Preview</button>
        <button className="secondary" onClick={doExport} disabled={!draftId}>Export</button>
        <button className="secondary" onClick={doCancel} disabled={!draftId}>Cancel Draft</button>
      </div>
    </div>
    <div className="card">
      <h3>Change Plan</h3>
      {!preview&&<div className="muted">Preview the Draft to validate references, dependency ordering, revision, and security impact.</div>}
      {preview&&<>
        <pre className="plan">{preview.formatted_plan}</pre>
        {(preview.security_impact||[]).length>0&&<div className="warning-box">{preview.security_impact.map((x:string)=><div key={x}>{x}</div>)}</div>}
        <label className="apply-label">Type APPLY to commit<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="APPLY"/></label>
        <button className="danger" onClick={doApply} disabled={confirmation!=="APPLY"}>Apply Draft</button>
      </>}
    </div>
  </div>;
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

function View({active,operator}:{active:string,operator:any}){
  const [data,setData]=useState<any>(null),[error,setError]=useState(""),[query,setQuery]=useState("");
  useEffect(()=>{
    setData(null);setError("");
    const paths:Record<string,string>={
      overview:"/api/v1/overview",hosts:"/api/v1/inventory?resource_type=managed-host&limit=100",
      services:"/api/v1/inventory?resource_type=remote-service&limit=100",
      objects:"/api/v1/objects-groups?limit=50",policies:"/api/v1/policies?limit=100",
      versions:"/api/v1/versions",audit:"/api/v1/audit?limit=100",revisions:"/api/v1/revisions?limit=100",
      doctor:"/api/v1/doctor",health:"/api/v1/health",views:"/api/v1/saved-views",
    };
    if(paths[active])api(paths[active]).then(setData).catch((e:any)=>setError(e.message||String(e)));
  },[active]);
  if(error)return <div className="error">{error}</div>;
  if(active==="drafts")return <DraftWorkspace/>;
  if(active==="search")return <div><div className="toolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search resources and policy"/><button className="primary" onClick={()=>api("/api/v1/search?q="+encodeURIComponent(query)+"&limit=50").then(setData).catch((e:any)=>setError(e.message))}>Search</button></div>{data&&<Table items={(data.items||[]).map((x:any)=>({type:x.resource_type,id:x.id,name:x.name}))}/>}</div>;
  if(active==="overview"&&data){const h=data.overview?.managed_hosts||{},s=data.overview?.remote_services||{},j=data.overview?.management_jobs||{};return <><div className="grid"><Metric label="Managed Hosts" value={h.total}/><Metric label="Connected" value={h.connected}/><Metric label="Remote Services" value={s.total}/><Metric label="Active Jobs" value={j.active_jobs}/></div><div className="card"><h3>Attention Center</h3>{(data.attention?.items||[]).map((x:any)=><span key={x.kind} className={"badge "+x.severity}>{x.label}: {x.count}</span>)}{!(data.attention?.items||[]).length&&<div className="muted">No current attention items</div>}</div></>};
  if(active==="versions"&&data)return <><div className="grid"><Metric label="Server version" value={data.server_version}/><Metric label="Drift" value={data.drift_count}/><Metric label="Unknown" value={data.unknown_count}/></div><Table items={data.hosts||[]}/></>;
  if(active==="objects"&&data){const rows=Object.entries(data.resources||{}).flatMap(([type,page]:any)=>(page.items||[]).map((item:any)=>({type,id:item.id,name:item.name||item.id,description:item.description||"",status:item.status||""})));return <Table items={rows}/>;}
  if(active==="policies"&&data)return <><Table items={data.items||[]}/>{operator.role!=="Read Only"&&<><GuidedPolicyRulePanel/><TemporaryAccessPanel/></>}</>;
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
  const visibleNav=nav.filter(([id])=>id!=="drafts"||operator.role!=="Read Only");
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
