import React,{useEffect,useState} from "react";
import {isObservedAbsoluteTime} from "./uxb-integrations-state";

/** UXE-09: a resolved HTTP call with malformed Core entries is not an
 * acknowledged activity feed; keep presentation bounded and non-secret. */
export type RecentFeed={status:"loading"|"ready"|"unknown",items:any[]};
const CORE_TEXT_BAD=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const FEED_FIELDS=["event_id","id","event_type","action","operation","actor_id",
  "actor","resource_type","resource_id","occurred_at","timestamp","result","category",
  "summary","message","created_at"] as const;
const FEED_TIME_FIELDS=new Set(["occurred_at","timestamp","created_at"]);
const safeCount=(value:unknown):value is number=>
  typeof value==="number"&&Number.isSafeInteger(value)&&value>=0;
const safeFeedText=(value:unknown):value is string=>
  typeof value==="string"&&value.length>0&&value.length<=160&&!CORE_TEXT_BAD.test(value);
export function observedRecentFeed(result:PromiseSettledResult<any>):RecentFeed{
  const unknown:RecentFeed={status:"unknown",items:[]};
  if(result.status!=="fulfilled"||!Array.isArray(result.value?.items)
    ||result.value.items.length>6)return unknown;
  const observed=[];
  for(const item of result.value.items){
    if(!item||typeof item!=="object"||Array.isArray(item)
      ||![item.event_id,item.id].some(safeFeedText)
        &&![item.row_id,item.revision].some(safeCount))return unknown;
    const view:Record<string,string|number>={};
    for(const key of FEED_FIELDS){
      const value=item[key];
      if(value===null||value===undefined)continue;
      // Never display arbitrary relative or impossible dates as observed
      // Core event times. The read-only preview retains the row itself.
      view[key]=FEED_TIME_FIELDS.has(key)
        ?isObservedAbsoluteTime(value)?value:"UNKNOWN"
        :safeFeedText(value)?value:"UNKNOWN";
    }
    if(safeCount(item.revision))view.revision=item.revision;
    if(safeCount(item.row_id))view.id=view.id||String(item.row_id);
    observed.push(view);
  }
  return {status:"ready",items:observed};
}
export function observedNumber(value:unknown):number|"UNKNOWN"{
  return safeCount(value)?value:"UNKNOWN";
}
/** UX-4: a valid count for one Core projection never authorizes a
 * contradictory active/connected subset. Keep an independently observed
 * total when the subset is missing, but show no reassuring false count.
 */
export function observedBoundedCountPair(
 data:unknown,key:"connected"|"enabled"
):{total:number|"UNKNOWN",subset:number|"UNKNOWN"}{
 if(!data||typeof data!=="object"||Array.isArray(data))
   return {total:"UNKNOWN",subset:"UNKNOWN"};
 const row=data as Record<string,unknown>;
 const total=observedNumber(row.total);
 const part=observedNumber(row[key]);
 return {total,subset:typeof total==="number"&&typeof part==="number"
   &&part<=total?part:"UNKNOWN"};
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

/** A partial or malformed Core summary must not masquerade as an observed one.
 * The actual overview always contains a policy map with the AI family. */
export function hasObservedCoreOverview(data:any):boolean{
  const overview=data?.overview;
  const hosts=overview?.managed_hosts,services=overview?.remote_services,policies=overview?.policies;
  const validPart=(part:any):boolean=>safeCount(part?.total)
    &&(part?.enabled===undefined||(safeCount(part.enabled)&&part.enabled<=part.total));
  return validPart(hosts)&&validPart(services)
    &&(hosts?.pending_approval===undefined||(safeCount(hosts.pending_approval)
      &&hosts.pending_approval<=hosts.total))
    &&!!policies&&typeof policies==="object"&&!Array.isArray(policies)
    &&Object.keys(policies).length>0
    &&Object.values(policies).every(row=>validPart(row));
}

/** UX-4 · Twingate/NetBird-inspired evidence scope and observation time.
 * Derived Core counts span the fleet, unlike the role-scoped first Host page.
 * A valid timestamp establishes only when Core generated the projection: it
 * never proves runtime liveness or actual successful network access.
 */
export type CoreOverviewEvidence={
 status:"observed"|"UNKNOWN",scope:string,observedAt:string
};
export function observedCoreOverviewEvidence(data:unknown):CoreOverviewEvidence{
 const unknown:CoreOverviewEvidence={status:"UNKNOWN",scope:"UNKNOWN",observedAt:"UNKNOWN"};
 if(!hasObservedCoreOverview(data))return unknown;
 const projection=(data as any).overview;
 if(projection.state_class!=="DERIVED"||projection.authoritative!==false
   ||projection.rebuildable!==true)return unknown;
 const at=isObservedAbsoluteTime(projection.generated_at)?projection.generated_at:"UNKNOWN";
 return {status:at==="UNKNOWN"?"UNKNOWN":"observed",
   scope:"Fleet-wide derived Core counts",observedAt:at};
}

/** Task-first Home is shown only when actual Core counts establish an empty
 * installation. Missing/partial evidence must never be guessed as zero. */
export function isFreshInstallation(data:any):boolean{
  if(!hasObservedCoreOverview(data))return false;
  const overview=data.overview;
  return overview.managed_hosts.total===0&&overview.remote_services.total===0
    &&Object.values(overview.policies).every((row:any)=>row.total===0);
}

/** UXE-09: a missing or partial Core observation must never announce a new install.
 * Checking only Managed Host count is wrong when policies or services remain. */
export function showFreshHomeWelcome(data:any,inventoryState:"loading"|"ready"|"error"):boolean{
  return inventoryState==="ready"&&isFreshInstallation(data);
}

/** A bounded inventory page is not an exhaustive approval queue.
 * Only an explicit terminal cursor proves full inventory pagination.
 */
export function hostInventoryPageComplete(payload:any):boolean|null{
  if(!Array.isArray(payload?.items)||payload.items.length>100
    ||payload.items.some((row:any)=>!row||typeof row!=="object"
      ||Array.isArray(row)
      ||!["PENDING_APPROVAL","APPROVED","QUARANTINED"].includes(row.admission_state)))
    return null;
  if(payload.next_cursor===null)return true;
  if(typeof payload.next_cursor==="string"&&payload.next_cursor.length>0)return false;
  return null;
}

/** Only role-scoped, identified and bounded Core Host rows may drive Home
 * Agent readiness. A malformed collection is UNKNOWN, not an empty inventory.
 */
export function observedHomeHostPage(payload:unknown):{
  items:any[],complete:boolean|null
}|null{
  if(!payload||typeof payload!=="object"||Array.isArray(payload))return null;
  const page=payload as Record<string,any>;
  if(!Array.isArray(page.items)||page.items.length>100
    ||page.items.some((row:any)=>!row||typeof row!=="object"||Array.isArray(row)
      ||typeof row.id!=="string"||!row.id.trim()||row.id.length>160
      ||CORE_TEXT_BAD.test(row.id)
      ||!["PENDING_APPROVAL","APPROVED","QUARANTINED"].includes(row.admission_state)))
    return null;
  return {items:page.items,complete:hostInventoryPageComplete(page)};
}

/** The derived Core overview covers all Hosts; a first inventory page does not.
 * If neither a valid summary nor a complete page exists, never announce zero.
 */
export function observedApprovalQueueCount(
  data:any,inventory:any[]|null,inventoryComplete:boolean
):number|"UNKNOWN"{
  const hosts=data?.overview?.managed_hosts;
  const pending=hosts?.pending_approval;
  const total=hosts?.total;
  if(Number.isSafeInteger(pending)&&pending>=0&&
    (!Number.isSafeInteger(total)||(total>=0&&pending<=total)))return pending;
  // Even a cursor-complete role-scoped list is not proof of the full fleet
  // when Core's separately observed overall Host total is larger.
  if(inventoryComplete&&Array.isArray(inventory)
    &&(!safeCount(total)||total===inventory.length)
    &&inventory.every(host=>host&&typeof host==="object"
      &&["PENDING_APPROVAL","APPROVED","QUARANTINED"].includes(host.admission_state)))
    return inventory.filter(host=>host.admission_state==="PENDING_APPROVAL").length;
  return "UNKNOWN";
}

/** UXB-02: Core-observed evidence only. A saved policy is not a verified connection. */
export type TaskState="Not started"|"Needs approval"|"Configured · verify"|"Needs verification"|"Unknown"|"Attention";
export function firstConnectionStates(data:any,inventory:any[]|null,inventoryComplete:boolean|null=true):TaskState[]{
  const hosts=data?.overview?.managed_hosts||{};
  const services=data?.overview?.remote_services||{};
  const remote=data?.overview?.policies?.remote||{};
  const hostCount=safeCount(hosts.total)?hosts.total:null;
  const serviceCount=safeCount(services.total)?services.total:null;
  const serviceEnabled=safeCount(services.enabled)
    &&serviceCount!==null&&services.enabled<=serviceCount?services.enabled:null;
  // The canonical overview omits Remote/Internet families with zero rules.
  // An observed empty policy map means no rules, not an unavailable Core.
  const policies=data?.overview?.policies;
  const policyRows=policies&&typeof policies==="object"&&!Array.isArray(policies)?policies:null;
  const ruleEnabled=policyRows&&!Object.prototype.hasOwnProperty.call(policyRows,"remote")?0
    :safeCount(remote.total)&&safeCount(remote.enabled)&&remote.enabled<=remote.total
      ?remote.enabled:null;
  const pending=observedApprovalQueueCount(data,inventory,inventoryComplete===true);
  const verifiedHost=inventory?.some(host=>host.admission_state==="APPROVED"
    &&String(host.trust_status||"").toLowerCase()==="trusted"
    &&(host.connected===true||host.connected===1));
  const agent:TaskState = inventory===null?"Unknown"
    :typeof pending==="number"&&pending>0?"Needs approval"
    :hostCount===0?"Not started":verifiedHost?"Configured · verify"
    :hostCount===null||pending==="UNKNOWN"?"Unknown":"Needs verification";
  const service:TaskState=serviceCount===null||serviceEnabled===null?"Unknown"
    :serviceCount===0?"Not started":serviceEnabled>0?"Configured · verify":"Needs verification";
  const rule:TaskState=ruleEnabled===null?"Unknown":ruleEnabled>0?"Configured · verify":"Not started";
  return [hasObservedCoreOverview(data)?"Configured · verify":"Unknown",agent,service,rule,"Needs verification"];
}
const steps=[
  {title:"Check system readiness",description:"Core is responding, but that alone does not prove a remote connection.",route:"health",group:"activity",action:"View system health"},
  {title:"Add and approve a server",description:"Install one Agent; admission, trust and connection are separate checks.",route:"enrollments",group:"connections",action:"Add a server / Agent"},
  {title:"Publish a specific service",description:"Expose only the intended internal service, such as SSH, not the whole network.",route:"services",group:"connections",action:"Publish a service"},
  {title:"Create narrow access rules",description:"Decide who may access what, then preview and run required policy tests.",route:"policies",group:"access",action:"Set access rules"},
  {title:"Test and explain the connection",description:"A saved ALLOW is not proof of target reachability. Ask Core for the decision.",route:"access",group:"access",action:"Test a connection"},
] as const;

/** A missing/denied/unverified prerequisite must never be skipped in the
 * suggested task merely because a later count happens to be zero.
 * Read Only users receive inspect actions, never edit/issue prompts.
 */
export function nextFirstConnectionAction(states:TaskState[],role:string){
  const host=states[1]||"Unknown";
  if(host==="Unknown"||host==="Needs approval"||host==="Needs verification")
    return {title:host==="Needs approval"?"Review pending Agent approvals":"Verify Managed Host readiness",
      route:"hosts",group:"connections",action:"Inspect Servers & Agents"};
  if(host==="Not started")return role==="Admin"?steps[1]:{
    title:"Check available Managed Hosts",route:"hosts",group:"connections",action:"Inspect Servers & Agents"};
  const service=states[2]||"Unknown";
  if(service!=="Configured · verify")
    return {title:"Review the published services",route:"services",group:"connections",
      action:role==="Read Only"?"Review published services":"Publish or inspect one service"};
  const rule=states[3]||"Unknown";
  if(rule!=="Configured · verify")
    return {title:"Review the access rules",route:"policies",group:"access",
      action:role==="Read Only"?"Inspect access rules":"Set or inspect access rules"};
  return steps[4];
}

/** UX-4 · Core-driven, read-only task links for bounded Attention items.
 * An unknown/malformed snapshot is not an empty/no-problems observation.
 * Routes navigate into already authorized workspaces, not mutation endpoints.
 */
export type HomeAttentionItem={
 kind:string,label:string,count:number,severity:"info"|"warning"|"critical",
 route:string,group:string,action:string
};
export type HomeAttentionState={items:HomeAttentionItem[],observedAt:string};
const ATTENTION_ROUTES:Record<string,[string,string,string]>={
 "pending-host-approval":["hosts","connections","Inspect Hosts"],
 "quarantined-hosts":["hosts","connections","Inspect Hosts"],
 disconnected:["hosts","connections","Inspect Hosts"],
 stale:["hosts","connections","Inspect Hosts"],
 version_unknown:["versions","activity","Inspect Agent Versions"],
 "degraded-remote-services":["services","connections","Inspect Services"],
 "runtime-mismatch":["health","activity","Inspect System Health"],
 "repeated-policy-denies":["audit","activity","Inspect Audit"],
 "version-drift":["versions","activity","Inspect Agent Versions"],
 "temporary-access-clock":["policies","access","Inspect Access Rules"],
 "temporary-access-expiring":["policies","access","Inspect Access Rules"],
 "audit-spool":["audit","activity","Inspect Audit"],
 "certificate-readiness":["health","activity","Inspect System Health"],
 "backup-readiness":["health","activity","Inspect System Health"],
 "update-readiness":["health","activity","Inspect System Health"],
 "system-readiness":["health","activity","Inspect System Health"],
 "failed-jobs":["jobs","activity","Inspect Jobs"],
 "job-saturation":["jobs","activity","Inspect Jobs"],
 "access-hygiene-review":["doctor","activity","Troubleshoot"],
 "emergency-cutoff":["access","access","Inspect Access"],
};
export function observedHomeAttention(data:unknown,role:unknown):HomeAttentionState|null{
 const source=data as any;
 const attention=source?.attention;
 if(!attention||typeof attention!=="object"||Array.isArray(attention)
   ||attention.authoritative!==false
   ||!isObservedAbsoluteTime(attention.generated_at)
   ||!Array.isArray(attention.items)||attention.items.length>32
   ||!safeCount(attention.count)||attention.count!==attention.items.length)return null;
 const seen=new Set<string>();
 const rows:HomeAttentionItem[]=[];
 for(const item of attention.items){
   if(!item||typeof item!=="object"||Array.isArray(item)
     ||typeof item.kind!=="string"||!/^([a-z][a-z0-9-]{0,63})$/.test(item.kind)
     ||seen.has(item.kind)||typeof item.label!=="string"
     ||!item.label.trim()||item.label.length>160||CORE_TEXT_BAD.test(item.label)
     ||!safeCount(item.count)||!["info","warning","critical"].includes(item.severity))
     return null;
   seen.add(item.kind);
   // Only Admin may navigate to integrations. For every other actor, a
   // visible notification is diagnosis-only, not an admin invitation.
   const route=["webhook-delivery","webhook-backlog"].includes(item.kind)
     ?role==="Admin"
       ?["integrations","administration","Inspect Integrations"]
       :["health","activity","Inspect System Health"]
     :Object.prototype.hasOwnProperty.call(ATTENTION_ROUTES,item.kind)
       ?ATTENTION_ROUTES[item.kind]
       :["doctor","activity","Troubleshoot"];
   rows.push({kind:item.kind,label:item.label,count:item.count,
     severity:item.severity,route:route[0],group:route[1],action:route[2]});
 }
 return {items:rows,observedAt:attention.generated_at};
}

/** Previously fetched Host evidence cannot be reused across Web sessions,
 * including two different operators holding the same nominal role.
 * This is UI display isolation; the authenticated Core owns authorization.
 */
export function homeInventoryMatchesActor(loadedFor:unknown,current:unknown):boolean{
  const obj=(v:unknown):v is Record<string,unknown>=>
    !!v&&typeof v==="object"&&!Array.isArray(v);
  if(!obj(loadedFor)||!obj(current))return false;
  const id=current.id,role=current.role;
  return typeof id==="string"&&!!id.trim()&&id.length<=160
    &&!CORE_TEXT_BAD.test(id)
    &&["Admin","Operator","Read Only"].includes(String(role))
    &&loadedFor.id===id&&loadedFor.role===role;
}

export function FirstUseHome({data,operator,api,onNavigate}:{
  data:any,operator:any,api:(path:string)=>Promise<any>,
  onNavigate?:(id:string,groupId?:string,context?:any)=>void
}){
  const [inventory,setInventory]=useState<any[]|null>(null);
  const [inventoryComplete,setInventoryComplete]=useState<boolean|null>(null);
  const [loadState,setLoadState]=useState<"loading"|"ready"|"error">("loading");
  const [error,setError]=useState("");
  const [loadedFor,setLoadedFor]=useState<{id:string,role:string}|null>(null);
  useEffect(()=>{
    let active=true;
    // A different actor or Web role must never reuse the previous Host page.
    setLoadedFor(null);
    setInventory(null);setInventoryComplete(null);setLoadState("loading");setError("");
    api("/api/v1/inventory?resource_type=managed-host&limit=100")
      .then(payload=>{if(!active)return;
        const observed=observedHomeHostPage(payload);
        if(!observed)throw new Error("Core inventory response missing or malformed items");
        setInventory(observed.items);setInventoryComplete(observed.complete);
        setLoadedFor({id:operator?.id,role:operator?.role});
        setLoadState("ready");
      })
      .catch(err=>{if(active){setLoadedFor({id:operator?.id,role:operator?.role});setInventory(null);setInventoryComplete(null);setLoadState("error");setError(String(err?.message||err))}});
    return()=>{active=false};
  },[api,operator?.id,operator?.role]);
  // Gate render synchronously, before passive useEffect cleanup on actor swap.
  const matchingActor=homeInventoryMatchesActor(loadedFor,operator);
  const scopedInventory=matchingActor?inventory:null;
  const scopedComplete=matchingActor?inventoryComplete:null;
  const scopedLoadState=matchingActor?loadState:"loading";
  const stage=firstConnectionStates(data,scopedInventory,scopedComplete);
  const newInstall=showFreshHomeWelcome(data,scopedLoadState);
  const pending=observedApprovalQueueCount(data,scopedInventory,scopedComplete===true);
  const cards=steps.map((item,i)=>({...item,status:stage[i]}));
  const next=nextFirstConnectionAction(stage,String(operator?.role||"Read Only"));
  const evidence=observedCoreOverviewEvidence(data);
  const attention=observedHomeAttention(data,operator?.role);
  return <section className="card dr-uxb-home" data-testid="uxb-first-connection">
    <div className="dr-section-head"><div><p className="dr-eyebrow">Get started · Core-observed progress</p>
      <h2>{newInstall?"Your first protected connection starts here":"What would you like to do next?"}</h2>
      <p className="muted">Five steps from adding one server to explaining an access decision. No setup status is stored in your browser.</p>
    </div><button className="primary" onClick={()=>onNavigate?.("setup","connections")}>Open guided setup →</button></div>
    <div className="toolbar dr-uxb-evidence-strip" role="status" aria-label="Core overview observation">
      <strong>Core overview {evidence.status==="observed"?"evidence":"UNKNOWN"}</strong>
      <span className="muted">{evidence.scope}</span>
      <span className="muted">{evidence.observedAt!=="UNKNOWN"
        ?"Observed at "+evidence.observedAt:"Observation timestamp unavailable"}</span>
      <small className="muted">Not proof of live connectivity or policy reachability.</small>
      <button type="button" className="secondary"
        onClick={()=>onNavigate?.("health","activity")}>Inspect System Health →</button>
    </div>
    {attention===null?<p className="muted" role="status">
      Core attention UNKNOWN · Core did not provide a validated Attention snapshot.
      Open System Health before interpreting an empty Attention list.
    </p>:attention.items.length>0&&<section className="dr-uxb-attention-summary" aria-label="Core attention investigation">
      <div className="dr-section-head">
        <div><h3>Investigate Core attention</h3><p className="muted">
          Core attention observed at {attention.observedAt} · Derived observations, not a live connection test.</p></div>
        <button type="button" className="secondary" onClick={()=>onNavigate?.("doctor","activity")}>
          Troubleshoot all →
        </button>
      </div>
      <ul className="dr-uxb-attention-list">{attention.items.slice(0,4).map(item=>
        <li key={item.kind}>
          <div><strong>{item.label}</strong><small>{item.count} affected · {item.severity}</small></div>
          <button type="button" className="secondary" onClick={()=>onNavigate?.(item.route,item.group)}>
            {item.action} →
          </button>
        </li>
      )}</ul>
      {attention.items.length>4&&<p className="muted">
        Showing first 4 of {attention.items.length} Core attention categories. Troubleshoot for the rest.
      </p>}
    </section>}
    {scopedLoadState==="error"&&<p className="warning-box" role="alert">Managed Host inventory unavailable ({error}). Agent readiness is UNKNOWN, not healthy.</p>}
    {scopedLoadState==="ready"&&scopedComplete!==true&&<p className="warning-box" role="status">
      Managed Host inventory {scopedComplete===false?"is paginated":"completeness is UNKNOWN"}:
      only {scopedInventory?.length??"UNKNOWN"} loaded Host records are available on this page.
      Approval counts come from the full Core overview when valid; unloaded Hosts may still require attention.
      Open Servers &amp; Agents to load additional pages.
    </p>}
    <ol className="dr-uxb-task-list">
      {cards.map((item,i)=>{
        const limited=operator?.role!=="Admin"&&item.route==="enrollments";
        return <li key={item.title} className={i===4?"dr-uxb-last-step":""}>
          <span className="dr-uxb-step-count">{i+1}</span>
          <div><strong>{item.title}</strong><p>{item.description}</p>
            <small className={item.status==="Unknown"?"dr-uxb-status unknown":"dr-uxb-status"}>{i===0&&item.status!=="Unknown"?"Core overview received · check Health for details":scopedLoadState==="loading"&&i===1?"Checking Core inventory…":item.status}</small></div>
          {limited?<span className="dr-uxb-role-hint">Admin required to issue an Agent ticket</span>:
          <button className="secondary" onClick={()=>onNavigate?.(item.route,item.group)}>{item.action} →</button>}
        </li>;
      })}
    </ol>
    {typeof pending==="number"&&pending>0&&<div className="notice" role="status">
      <strong>{pending} Host(s) await Admin approval.</strong>
      <p>Core overview or complete inventory evidence · Connected does not mean approved.</p>
      <button type="button" className="secondary"
        onClick={()=>onNavigate?.("hosts","connections",{savedAdmission:"PENDING_APPROVAL"})}>
        Review pending Hosts →
      </button>
      <small>Opens only the already authorized Host inventory; more pages may be needed.</small>
    </div>}
    {pending==="UNKNOWN"&&scopedLoadState==="ready"&&<p className="muted" role="status">
      Pending Host approvals: UNKNOWN · Review Servers &amp; Agents to inspect missing Core evidence.</p>}
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
