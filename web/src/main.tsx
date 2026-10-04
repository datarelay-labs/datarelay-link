import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";

type Json = Record<string, any>;
const nav=[["overview","Overview"],["hosts","Managed Hosts"],["services","Remote Services"],["objects","Objects & Groups"],["policies","Policies"],["versions","Version Drift"],["audit","Audit"],["revisions","Revisions"],["doctor","Doctor"],["health","Health"],["search","Search"],["views","Saved Views"]];
let csrf="";

async function api(path:string, init:RequestInit={}):Promise<Json>{
  const headers:Record<string,string>={"Accept":"application/json",...((init.headers||{}) as Record<string,string>)};
  if(init.method && init.method!=="GET"){headers["Content-Type"]="application/json";if(csrf)headers["X-CSRF-Token"]=csrf;}
  const res=await fetch(path,{...init,headers,credentials:"same-origin"});
  let body:Json={};try{body=await res.json()}catch{}
  if(!res.ok)throw new Error(body.error||("HTTP "+res.status));
  return body;
}

function Table({items}:{items:any[]}){
  if(!items?.length)return <div className="empty">No results</div>;
  const keys=Object.keys(items[0]).filter(k=>typeof items[0][k]!=="object").slice(0,9);
  return <table><thead><tr>{keys.map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{items.map((item,i)=><tr key={item.id||i}>{keys.map(k=><td key={k}>{item[k]===null?"":String(item[k]??"")}</td>)}</tr>)}</tbody></table>;
}
function Metric({label,value}:{label:string,value:any}){return <div className="card"><div className="muted">{label}</div><div className="metric">{String(value??0)}</div></div>}

function Login({onLogin}:{onLogin:(op:any)=>void}){
  const [username,setUsername]=useState("admin"),[password,setPassword]=useState(""),[totp,setTotp]=useState(""),[recovery,setRecovery]=useState(""),[error,setError]=useState("");
  async function submit(e:React.FormEvent){e.preventDefault();setError("");try{const d=await api("/api/v1/auth/login",{method:"POST",body:JSON.stringify({username,password,totp,recovery_code:recovery})});csrf=d.csrf_token;onLogin(d.operator)}catch(err:any){setError(err.message||String(err))}}
  return <div className="login-wrap"><form className="login" onSubmit={submit}><h1>Data Relay Link</h1><div className="muted">Optional Web Management · local authentication</div>{error&&<div className="error">{error}</div>}<label>Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/></label><label>MFA code<input inputMode="numeric" autoComplete="one-time-code" value={totp} onChange={e=>setTotp(e.target.value)} placeholder="6-digit TOTP"/></label><label>Recovery code<input value={recovery} onChange={e=>setRecovery(e.target.value)} placeholder="or recovery code"/></label><button className="primary" type="submit">Sign in</button></form></div>
}

function View({active}:{active:string}){
  const [data,setData]=useState<any>(null),[error,setError]=useState(""),[query,setQuery]=useState("");
  useEffect(()=>{setData(null);setError("");const paths:Record<string,string>={overview:"/api/v1/overview",hosts:"/api/v1/inventory?resource_type=managed-host&limit=100",services:"/api/v1/inventory?resource_type=remote-service&limit=100",objects:"/api/v1/objects-groups?limit=50",policies:"/api/v1/policies?limit=100",versions:"/api/v1/versions",audit:"/api/v1/audit?limit=100",revisions:"/api/v1/revisions?limit=100",doctor:"/api/v1/doctor",health:"/api/v1/health",views:"/api/v1/saved-views"};if(paths[active])api(paths[active]).then(setData).catch((e:any)=>setError(e.message||String(e)))},[active]);
  if(error)return <div className="error">{error}</div>;
  if(active==="search")return <div><div className="toolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search resources and policy"/><button className="primary" onClick={()=>api("/api/v1/search?q="+encodeURIComponent(query)+"&limit=50").then(setData).catch((e:any)=>setError(e.message))}>Search</button></div>{data&&<Table items={(data.items||[]).map((x:any)=>({type:x.resource_type,id:x.id,name:x.name}))}/>}</div>;
  if(active==="overview"&&data){const h=data.overview?.managed_hosts||{},s=data.overview?.remote_services||{},j=data.overview?.management_jobs||{};return <><div className="grid"><Metric label="Managed Hosts" value={h.total}/><Metric label="Connected" value={h.connected}/><Metric label="Remote Services" value={s.total}/><Metric label="Active Jobs" value={j.active_jobs}/></div><div className="card"><h3>Attention Center</h3>{(data.attention?.items||[]).map((x:any)=><span key={x.kind} className={"badge "+x.severity}>{x.label}: {x.count}</span>)}{!(data.attention?.items||[]).length&&<div className="muted">No current attention items</div>}</div></>};
  if(active==="versions"&&data)return <><div className="grid"><Metric label="Server version" value={data.server_version}/><Metric label="Drift" value={data.drift_count}/><Metric label="Unknown" value={data.unknown_count}/></div><Table items={data.hosts||[]}/></>;
  if(active==="objects"&&data){const rows=Object.entries(data.resources||{}).flatMap(([type,page]:any)=>(page.items||[]).map((item:any)=>({type,id:item.id,name:item.name||item.id,description:item.description||"",status:item.status||""})));return <Table items={rows}/>;}
  if(active==="doctor"&&data)return <><div className="grid"><Metric label="Attention" value={data.attention?.count}/><Metric label="Checks" value={(data.checks||[]).length}/></div><Table items={data.checks||[]}/></>;
  if(active==="health"&&data)return <pre className="card">{JSON.stringify(data,null,2)}</pre>;
  if(active==="views"&&data)return <SavedViews data={data} refresh={()=>api("/api/v1/saved-views").then(setData)}/>;
  if(data)return <Table items={data.items||[]}/>;
  return <div className="empty">Loading…</div>
}

function SavedViews({data,refresh}:{data:any,refresh:()=>void}){
  const [name,setName]=useState(""),[filter,setFilter]=useState(""),[error,setError]=useState("");
  async function save(){try{await api("/api/v1/saved-views",{method:"POST",body:JSON.stringify({name,payload:{filter}})});setName("");setFilter("");refresh()}catch(e:any){setError(e.message||String(e))}}
  return <>{error&&<div className="error">{error}</div>}<div className="toolbar"><input placeholder="View name" value={name} onChange={e=>setName(e.target.value)}/><input placeholder="Filter text" value={filter} onChange={e=>setFilter(e.target.value)}/><button className="primary" onClick={save}>Save current view</button></div><Table items={(data.items||[]).map((x:any)=>({id:x.id,name:x.name,updated_at:x.updated_at}))}/></>
}

function Shell({operator,onLogout}:{operator:any,onLogout:()=>void}){
  const [active,setActive]=useState("overview");
  async function logout(){try{await api("/api/v1/auth/logout",{method:"POST",body:"{}"})}finally{csrf="";onLogout()}}
  const title=nav.find(x=>x[0]===active)?.[1]||"Overview";
  return <div className="shell"><aside className="sidebar"><div className="brand">Data Relay Link<small>Web Management 3.0</small></div><div className="nav">{nav.map(([id,label])=><button key={id} className={id===active?"active":""} onClick={()=>setActive(id)}>{label}</button>)}</div></aside><section className="content"><div className="top"><div><div className="title">{title}</div><div className="muted">{operator.username} · {operator.role}</div></div><button className="secondary" onClick={logout}>Sign out</button></div><View active={active}/></section></div>
}

function App(){
  const [operator,setOperator]=useState<any>(undefined);
  useEffect(()=>{api("/api/v1/session").then(d=>setOperator(d.operator)).catch(()=>setOperator(null))},[]);
  if(operator===undefined)return <div className="login-wrap"><div className="muted">Loading…</div></div>;
  if(!operator)return <Login onLogin={setOperator}/>;
  return <Shell operator={operator} onLogout={()=>setOperator(null)}/>;
}

createRoot(document.getElementById("app")!).render(<App/>);
