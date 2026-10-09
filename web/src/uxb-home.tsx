import React,{useEffect,useState} from "react";

/** UXB-02: Core-observed evidence only. A saved policy is not a verified connection. */
export type TaskState="Not started"|"Needs approval"|"Configured · verify"|"Needs verification"|"Unknown"|"Attention";
export function firstConnectionStates(data:any,inventory:any[]|null):TaskState[]{
  const hosts=data?.overview?.managed_hosts||{};
  const services=data?.overview?.remote_services||{};
  const remote=data?.overview?.policies?.remote||{};
  const hostCount=typeof hosts.total==="number"?hosts.total:null;
  const serviceCount=typeof services.total==="number"?services.total:null;
  const serviceEnabled=typeof services.enabled==="number"?services.enabled:null;
  const ruleEnabled=typeof remote.enabled==="number"?remote.enabled:null;
  const pending=inventory?.filter(host=>host.admission_state==="PENDING_APPROVAL").length||0;
  const verifiedHost=inventory?.some(host=>host.admission_state==="APPROVED"
    &&String(host.trust_status||"").toLowerCase()==="trusted"
    &&(host.connected===true||host.connected===1));
  const agent:TaskState = inventory===null?"Unknown":pending>0?"Needs approval"
    :hostCount===0?"Not started":verifiedHost?"Configured · verify"
    :hostCount===null?"Unknown":"Needs verification";
  const service:TaskState=serviceCount===null||serviceEnabled===null?"Unknown"
    :serviceCount===0?"Not started":serviceEnabled>0?"Configured · verify":"Needs verification";
  const rule:TaskState=ruleEnabled===null?"Unknown":ruleEnabled>0?"Configured · verify":"Not started";
  return [data?.overview?"Configured · verify":"Unknown",agent,service,rule,"Needs verification"];
}
const steps=[
  {title:"Check system readiness",description:"Core is responding, but that alone does not prove a remote connection.",route:"health",group:"activity",action:"View system health"},
  {title:"Add and approve a server",description:"Install one Agent; admission, trust and connection are separate checks.",route:"enrollments",group:"connections",action:"Add a server / Agent"},
  {title:"Publish a specific service",description:"Expose only the intended internal service, such as SSH, not the whole network.",route:"services",group:"connections",action:"Publish a service"},
  {title:"Create narrow access rules",description:"Decide who may access what, then preview and run required policy tests.",route:"policies",group:"access",action:"Set access rules"},
  {title:"Test and explain the connection",description:"A saved ALLOW is not proof of target reachability. Ask Core for the decision.",route:"access",group:"access",action:"Test a connection"},
] as const;

export function FirstUseHome({data,operator,api,onNavigate}:{
  data:any,operator:any,api:(path:string)=>Promise<any>,
  onNavigate?:(id:string,groupId?:string)=>void
}){
  const [inventory,setInventory]=useState<any[]|null>(null);
  const [loadState,setLoadState]=useState<"loading"|"ready"|"error">("loading");
  const [error,setError]=useState("");
  useEffect(()=>{
    let active=true;
    api("/api/v1/inventory?resource_type=managed-host&limit=100")
      .then(payload=>{if(!active)return;
        if(!Array.isArray(payload?.items))throw new Error("Core inventory response missing items");
        setInventory(payload.items);setLoadState("ready");
      })
      .catch(err=>{if(active){setInventory(null);setLoadState("error");setError(String(err?.message||err))}});
    return()=>{active=false};
  },[api]);
  const stage=firstConnectionStates(data,inventory);
  const total=data?.overview?.managed_hosts?.total;
  const newInstall=loadState==="ready"&&total===0;
  const pending=inventory?.filter(host=>host.admission_state==="PENDING_APPROVAL").length||0;
  const cards=steps.map((item,i)=>({...item,status:stage[i]}));
  const next=operator?.role==="Admin"?
    cards.find((x,i)=>i>0 && (x.status==="Not started"||x.status==="Needs approval"||x.status==="Needs verification"))||cards[4]:
    cards.find((x,i)=>i>0&&x.status==="Needs verification")||cards[4];
  return <section className="card dr-uxb-home" data-testid="uxb-first-connection">
    <div className="dr-section-head"><div><p className="dr-eyebrow">Get started · Core-observed progress</p>
      <h2>{newInstall?"Your first protected connection starts here":"What would you like to do next?"}</h2>
      <p className="muted">Five steps from adding one server to explaining an access decision. No setup status is stored in your browser.</p>
    </div><button className="primary" onClick={()=>onNavigate?.("setup","connections")}>Open guided setup →</button></div>
    {loadState==="error"&&<p className="warning-box" role="alert">Managed Host inventory unavailable ({error}). Agent readiness is UNKNOWN, not healthy.</p>}
    <ol className="dr-uxb-task-list">
      {cards.map((item,i)=>{
        const limited=operator?.role!=="Admin"&&item.route==="enrollments";
        return <li key={item.title} className={i===4?"dr-uxb-last-step":""}>
          <span className="dr-uxb-step-count">{i+1}</span>
          <div><strong>{item.title}</strong><p>{item.description}</p>
            <small className={item.status==="Unknown"?"dr-uxb-status unknown":"dr-uxb-status"}>{i===0?"Core overview received · check Health for details":loadState==="loading"&&i===1?"Checking Core inventory…":item.status}</small></div>
          {limited?<span className="dr-uxb-role-hint">Admin required to issue an Agent ticket</span>:
          <button className="secondary" onClick={()=>onNavigate?.(item.route,item.group)}>{item.action} →</button>}
        </li>;
      })}
    </ol>
    {pending>0&&<p className="notice">{pending} Host(s) await Admin approval. Connected does not mean approved.</p>}
    <div className="dr-uxb-home-next"><div><strong>Suggested next action</strong><small>{next.title}</small></div>
      <button className="primary" disabled={operator?.role!=="Admin"&&next.route==="enrollments"} onClick={()=>onNavigate?.(next.route,next.group)}>{next.action} →</button></div>
    <div className="dr-uxb-access-choices" aria-label="Choose access direction">
      <div><strong>Remote Access</strong><small>External user → one approved internal service</small></div>
      <div><strong>Internet Access</strong><small>Managed internal source → permitted outside destination</small></div>
      <div><strong>AI Access</strong><small>Authenticated AI Identity → named permission</small></div>
    </div>
    <p className="muted">A “Configured” item is not a successful connection. Always perform the last verification step with the actual Core evidence.</p>
  </section>;
}
