import React,{useEffect,useState} from "react";

/** UXE-09: only an acknowledged Core list is empty; loading/failure is unknown. */
export type RecentFeed={status:"loading"|"ready"|"unknown",items:any[]};
export function observedRecentFeed(result:PromiseSettledResult<any>):RecentFeed{
  if(result.status==="fulfilled"&&Array.isArray(result.value?.items))
    return {status:"ready",items:result.value.items};
  return {status:"unknown",items:[]};
}
export function observedNumber(value:unknown):number|"UNKNOWN"{
  return typeof value==="number"&&Number.isFinite(value)?value:"UNKNOWN";
}
export function coreHealthState(data:any):"Healthy"|"Attention"|"UNKNOWN"{
  if(typeof data?.db_healthy!=="boolean"||typeof data?.mismatch!=="boolean")return "UNKNOWN";
  return data.db_healthy&&!data.mismatch?"Healthy":"Attention";
}
export function accessPlaneCount(data:any):number|null{
  const generations=data?.generations;
  if(!generations||typeof generations!=="object"||!["remote","internet","ai"].every(
    plane=>generations[plane]&&typeof generations[plane].status==="string"&&generations[plane].status
  ))return null;
  return ["remote","internet","ai"].filter(plane=>generations[plane].status==="active").length;
}

/** Task-first Home is shown only when actual Core counts establish an empty
 * installation. Missing/partial evidence must never be guessed as zero. */
export function isFreshInstallation(data:any):boolean{
  const overview=data?.overview;
  const hosts=overview?.managed_hosts,services=overview?.remote_services,policies=overview?.policies;
  if(typeof hosts?.total!=="number"||typeof services?.total!=="number"
    ||!policies||typeof policies!=="object"||!Object.keys(policies).length)return false;
  if(hosts.total!==0||services.total!==0)return false;
  return Object.values(policies).every((row:any)=>typeof row?.total==="number"&&row.total===0);
}

/** UXB-02: Core-observed evidence only. A saved policy is not a verified connection. */
export type TaskState="Not started"|"Needs approval"|"Configured · verify"|"Needs verification"|"Unknown"|"Attention";
export function firstConnectionStates(data:any,inventory:any[]|null):TaskState[]{
  const hosts=data?.overview?.managed_hosts||{};
  const services=data?.overview?.remote_services||{};
  const remote=data?.overview?.policies?.remote||{};
  const hostCount=typeof hosts.total==="number"?hosts.total:null;
  const serviceCount=typeof services.total==="number"?services.total:null;
  const serviceEnabled=typeof services.enabled==="number"?services.enabled:null;
  // The canonical overview omits Remote/Internet families with zero rules.
  // An observed empty policy map means no rules, not an unavailable Core.
  const ruleEnabled=typeof remote.enabled==="number"?remote.enabled
    :data?.overview?.policies&&typeof data.overview.policies==="object"?0:null;
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
  onNavigate?:(id:string,groupId?:string,context?:any)=>void
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
    <div className="dr-uxb-access-choices" role="group" aria-label="Start by choosing an access direction">
      {[
        {plane:"remote",title:"Connect to a server",detail:"Remote Access · outside user → protected SSH or other internal service",action:"Set up Remote Access"},
        {plane:"internet",title:"Allow approved outbound access",detail:"Internet Access · managed server → approved external destination",action:"Set up Internet Access"},
        {plane:"ai",title:"Grant an AI integration permission",detail:"AI Access · verified identity → named permission",action:"Set up AI Access"},
      ].map(item=><button key={item.plane} type="button" onClick={()=>onNavigate?.("setup","connections",{plane:item.plane})}>
        <strong>{item.title}</strong><small>{item.detail}</small><span>{item.action} →</span>
      </button>)}
    </div>
    <p className="muted">A “Configured” item is not a successful connection. Always perform the last verification step with the actual Core evidence.</p>
  </section>;
}
