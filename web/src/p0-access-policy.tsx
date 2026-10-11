import React, {useEffect, useRef, useState} from "react";
import {CoreChoiceField,useCoreCatalog,type CoreCatalog} from "./uxb-core-choices";
import {isObservedAbsoluteTime} from "./uxb-integrations-state";

export type LinkApi = (path:string, init?:RequestInit)=>Promise<Record<string,any>>;
type Navigate = (id:string,groupId?:string,context?:any)=>void;
export type AccessPlane = "remote"|"internet"|"ai";
type SelectedFlow = {source:string,destination:string,selector:string,path?:string};

const UNSAFE_CORE_TRACE=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
function trustedCoreTraceText(value:unknown,max=160):value is string{
  return typeof value==="string"&&!!value.trim()&&value.length<=max
    &&!UNSAFE_CORE_TRACE.test(value);
}

export function reliableDecision(value:unknown):"ALLOW"|"DENY"|"UNKNOWN" {
  // Array or nested JSON coercion (e.g. ["ALLOW"]) is not a Core verdict.
  if(typeof value!=="string"||!trustedCoreTraceText(value,16))return "UNKNOWN";
  const decision=value.toUpperCase();
  return decision==="ALLOW"||decision==="DENY"?decision:"UNKNOWN";
}

/** Only a scalar, bounded Core route label may be presented as a decision
 * endpoint. A missing optional value may fall back to the explicit user input;
 * malformed Core evidence must instead remain UNKNOWN.
 */
export function observedTraceRouteValue(value:unknown,fallback:unknown):string{
  if(value===undefined)return trustedCoreTraceText(fallback)?fallback.trim():"UNKNOWN";
  return trustedCoreTraceText(value)?value.trim():"UNKNOWN";
}

/** The browser must never authorize based on policy simulation or stale views.
 * Incomplete/tainted matched-rule evidence cannot become "none reported".
 */
export function explainTrace(trace:any):{
 decision:"ALLOW"|"DENY"|"UNKNOWN",reason:string,rules:string[],rulesQualified:boolean
}{
  const decision=reliableDecision(trace?.final?.result);
  const reason=trustedCoreTraceText(trace?.final?.reason,240)
    ?trace.final.reason.trim():"Core did not provide a decision reason.";
  const raw=trace?.policy?.matched_rules;
  const rows=Array.isArray(raw)&&raw.length<=128?raw:[];
  const valid=rows.filter((item:unknown):item is string=>trustedCoreTraceText(item));
  const distinct=[...new Set(valid.map(x=>x.trim()))];
  const rules=distinct.slice(0,20);
  const rulesQualified=Array.isArray(raw)&&raw.length<=20&&valid.length===raw.length
    &&distinct.length<=20;
  return {decision,reason,rules,rulesQualified};
}

/** Label displayed evidence by the exact user-supplied flow, not the currently
 * rendered form alone. Whitespace is normalized like the Core request payload. */
export function coreFlowKey(plane:string,source:string,destination:string,selector:string,path=""):string{
  return JSON.stringify([plane,source.trim(),destination.trim(),selector.trim(),
    plane==="ai"?path.trim():""]);
}
export function visibleCoreEvidence(record:{key:string,value:any}|null,currentKey:string):any|null{
  return record?.key===currentKey?record.value:null;
}

/** Emergency cutoff Change Plans are bound to the complete operator intent.
 * Never display an old plane/scope/operation preview as an active plan. */
export function coreCutoffKey(plane:string,scopeKind:string,scopeRef:string,operation:string,reason:string):string{
  return JSON.stringify([plane,scopeKind,scopeRef.trim(),operation,reason.trim()]);
}

export function canApplyGuidedRule(
 preview:any,tests:any,acknowledgedUnknowns:boolean,now:number=Date.now()
):boolean{
 const object=(value:unknown):value is Record<string,any>=>
   !!value&&typeof value==="object"&&!Array.isArray(value);
 if(!object(preview)||!object(tests)||!Number.isFinite(now)
   ||typeof preview.change_plan_id!=="string"
   ||!/^cp_[A-Za-z0-9_-]{16,128}$/.test(preview.change_plan_id)
   ||preview.operation_class!=="CHANGE"
   ||!["remote-access-rule","internet-access-rule","ai-access-rule"].includes(preview.change_type)
   ||preview.resource_type!==preview.change_type
   ||!["set","delete"].some(op=>preview.operation==="guided."+preview.change_type+"."+op)
   ||!trustedCoreTraceText(preview.resource_ref)
   ||preview.confirmation_class!=="APPLY"||preview.no_change!==false
   ||!Number.isSafeInteger(preview.expected_revision)||preview.expected_revision<0
   ||!isObservedAbsoluteTime(preview.valid_until)
   ||Date.parse(preview.valid_until)<=now
   ||tests.ok!==true||tests.required_failed!==0)return false;
 const regression=preview.policy_regression,blast=preview.blast_radius;
 if(!object(regression)||regression.ok!==true||regression.required_failed!==0
   ||!object(blast)||!object(blast.limits)||blast.limits.truncated!==false
   ||!Array.isArray(blast.unknowns)||blast.unknowns.length>128
   ||blast.unknowns.some((item:unknown)=>!trustedCoreTraceText(item,512)))return false;
 if(blast.unknowns.length>0&&acknowledgedUnknowns!==true)return false;
 return true;
}

/** Guided policy HTTP success is not an Apply acknowledgement. Match the
 * one-shot Core Change Plan's exact access plane/rule/type and require an
 * observed strictly advanced numeric revision before displaying success.
 */
export function observedGuidedPolicyApplyReceipt(result:unknown,plan:unknown,plane:AccessPlane):{revision:number}|null{
 if(!result||typeof result!=="object"||Array.isArray(result)
   ||!plan||typeof plan!=="object"||Array.isArray(plan)
   ||!["remote","internet","ai"].includes(plane))return null;
 const proof=result as Record<string,unknown>,review=plan as Record<string,unknown>;
 const kind=plane+"-access-rule";
 if(typeof review.change_plan_id!=="string"
   ||!/^cp_[A-Za-z0-9_-]{16,128}$/.test(review.change_plan_id)
   ||review.change_type!==kind||review.resource_type!==kind
   ||!trustedCoreTraceText(review.resource_ref)
   ||review.confirmation_class!=="APPLY"||review.no_change!==false
   ||!Number.isSafeInteger(review.expected_revision)||Number(review.expected_revision)<0
   ||proof.status!=="APPLIED"||proof.change_type!==kind||proof.resource_type!==kind
   ||proof.resource_ref!==review.resource_ref
   ||!Number.isSafeInteger(proof.revision)
   ||Number(proof.revision)<=Number(review.expected_revision))return null;
 return {revision:proof.revision as number};
}

/** A modeled Core graph path is evidence, not live connectivity or the final
 * governing rule. Reject incomplete/cross-plane rows rather than guessing.
 */
export function modeledPathEvidence(row:unknown,plane:AccessPlane){
  if(!row||typeof row!=="object"||Array.isArray(row))return null;
  const value=row as Record<string,any>,input=value.input;
  if(!input||typeof input!=="object"||Array.isArray(input))return null;
  if((value.plane!=null&&value.plane!==plane)||(input.plane!=null&&input.plane!==plane))return null;
  const source=input.source,destination=input.destination,selector=plane==="ai"?input.permission:input.service;
  if([source,destination,selector].some(x=>!trustedCoreTraceText(x)))return null;
  const path=plane==="ai"?(typeof input.path==="string"?input.path:""):"";
  if(path.length>512||UNSAFE_CORE_TRACE.test(path))return null;
  const rawRules=Array.isArray(value.rules)?value.rules:[];
  const boundedRules=rawRules.slice(0,128);
  const validRules=boundedRules.filter(
    (x:unknown):x is string=>trustedCoreTraceText(x)
  );
  const distinctRules=[...new Set(validRules)];
  const ruleReferences=distinctRules.slice(0,8);
  return {
    key:coreFlowKey(plane,source,destination,selector,path),
    flow:{source:source.trim(),destination:destination.trim(),selector:selector.trim(),path:path.trim()},
    decision:reliableDecision(value.decision),
    ruleReferences,
    ruleReferencesLimited:distinctRules.length>8||boundedRules.length!==rawRules.length||validRules.length!==boundedRules.length,
  };
}

/** A successful HTTP response is not proof of the requested policy graph.
 * Only the canonical read-only Core graph scope, plane, revision and exact
 * bounded path totals can become a UI snapshot. Never expose nested nodes.
 */
export function observedCoreGraphSnapshot(input:unknown,plane:AccessPlane):{
 revision:number,paths:unknown[],limits:{path_count:number,truncated:boolean},network_topology:false
}|null{
 if(!input||typeof input!=="object"||Array.isArray(input)
   ||!["remote","internet","ai"].includes(plane))return null;
 const row=input as Record<string,unknown>,limits=row.limits;
 if(row.scope!=="policy-and-inventory"
   ||!Array.isArray(row.planes)||row.planes.length!==1||row.planes[0]!==plane
   ||row.network_topology!==false
   ||!Number.isSafeInteger(row.revision)||Number(row.revision)<0
   ||!Array.isArray(row.paths)||row.paths.length>400
   ||!limits||typeof limits!=="object"||Array.isArray(limits))return null;
 const bounds=limits as Record<string,unknown>;
 if(!Number.isSafeInteger(bounds.max_paths)||Number(bounds.max_paths)<1
   ||Number(bounds.max_paths)>400||row.paths.length>Number(bounds.max_paths)
   ||!Number.isSafeInteger(bounds.path_count)||Number(bounds.path_count)!==row.paths.length
   ||typeof bounds.truncated!=="boolean"
   ||row.paths.some(path=>modeledPathEvidence(path,plane)===null))return null;
 return {revision:row.revision as number,paths:row.paths,
   limits:{path_count:bounds.path_count as number,truncated:bounds.truncated as boolean},
   network_topology:false};
}

/** Rule names in a Core trace are not IDs. Resolve only against a complete,
 * same-plane Core policy inventory, with exactly one exact-name match.
 */
export function resolveCompletePolicyMatch(items:unknown,plane:AccessPlane,name:unknown,complete:boolean){
  if(!complete||typeof name!=="string"||!name.trim()||name.length>160||!Array.isArray(items))return null;
  const matches=items.filter((item:any)=>item&&typeof item==="object"&&!Array.isArray(item)
    &&item.plane===plane&&item.name===name&&typeof item.id==="string"&&!!item.id.trim());
  return matches.length===1?matches[0]:null;
}


/** UI-02 is a read-only publication relationship, distinct from policy
 * source/destination modeled paths or a live network topology. Project only
 * exact service.client_id -> managed-host.id Core inventory references.
 */
export type ObservedPublicationEdge={serviceId:string,serviceName:string,hostId:string,hostName:string};
export function observedPublicationOwnership(services:unknown,hosts:unknown):{
 edges:ObservedPublicationEdge[],unresolved:number,partial:boolean,limited:boolean
}|null{
 const isRecord=(x:unknown):x is Record<string,unknown>=>!!x&&typeof x==="object"&&!Array.isArray(x);
 const cleanId=(x:unknown):x is string=>typeof x==="string"&&/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/.test(x);
 const cleanLabel=(x:unknown,fallback:string):string=>typeof x==="string"
   &&!!x.trim()&&x.length<=160&&!/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(x)?x.trim():fallback;
 function typedPage(value:unknown,type:string):{items:Record<string,unknown>[],partial:boolean}|null{
   if(!isRecord(value)||value.resource_type!==type||!Array.isArray(value.items)
     ||!Number.isSafeInteger(value.limit)||Number(value.limit)<1||Number(value.limit)>100
     ||value.items.length>Number(value.limit)
     ||value.next_cursor!==null&&!(typeof value.next_cursor==="string"
       &&!!value.next_cursor&&value.next_cursor.length<=1024
       &&!/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(value.next_cursor)))
       return null;
   if(value.items.some(x=>!isRecord(x)||!cleanId(x.id)))return null;
   const items=value.items as Record<string,unknown>[];
   if(new Set(items.map(x=>x.id)).size!==items.length)return null;
   return {items,partial:value.next_cursor!==null};
 }
 const svc=typedPage(services,"remote-service"),h=typedPage(hosts,"managed-host");
 if(!svc||!h)return null;
 const hostMap=new Map(h.items.map(x=>[x.id as string,x]));
 const edges:ObservedPublicationEdge[]=[];
 let unresolved=0;
 for(const item of svc.items){
   const hostId=item.managed_host_id;
   const host=cleanId(hostId)?hostMap.get(hostId):undefined;
   if(!host){unresolved++;continue;}
   edges.push({serviceId:item.id as string,
     serviceName:cleanLabel(item.name,item.id as string),
     hostId:host.id as string,
     hostName:cleanLabel(host.name,host.id as string)});
 }
 return {edges:edges.slice(0,16),unresolved,
   partial:svc.partial||h.partial,limited:edges.length>16};
}

/** UI-02: preserve the exact observed Host ID when routing to the existing
 * loaded-only Host detail. A colon in a Core ID must not be read as a search
 * facet, and IDs longer than the UI's 120-char search input are not truncated.
 */
export function observedHostInspectContext(hostId:unknown):{
 inspectResourceId:string,savedFilter:string
}|null{
 if(typeof hostId!=="string"||
    !/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/.test(hostId))return null;
 return {inspectResourceId:hostId,savedFilter:hostId.length<=117?"id:"+hostId:""};
}

export function AccessEvidenceExplorer({api,plane,source,destination,selector,onSelect,onNavigate,onInspectHost,actor}:{
  api:LinkApi,plane:AccessPlane,source:string,destination:string,selector:string,
  onSelect:(flow:SelectedFlow)=>void,onNavigate?:Navigate,
  onInspectHost?:(hostId:string)=>void,actor?:{id?:unknown,role?:unknown}
}){
  const [graphEvidence,setGraphEvidence]=useState<{key:string,value:any}|null>(null);
  const [traceEvidence,setTraceEvidence]=useState<{key:string,value:any}|null>(null);
  const [graphBusy,setGraphBusy]=useState(false),[traceBusy,setTraceBusy]=useState(false);
  const [error,setError]=useState(""),[path,setPath]=useState("");
  const [selectedPath,setSelectedPath]=useState<ReturnType<typeof modeledPathEvidence>>(null);
  const graphRequest=useRef(0),traceRequest=useRef(0);
  const publicationRequest=useRef(0);
  const [publication,setPublication]=useState<{scope:string,value:NonNullable<ReturnType<typeof observedPublicationOwnership>>}|null>(null);
  const [publicationBusy,setPublicationBusy]=useState(false),[publicationError,setPublicationError]=useState("");
  const actorScope=JSON.stringify([actor?.id,actor?.role]);
  const currentActorScope=useRef(actorScope);
  currentActorScope.current=actorScope;
  const visiblePublication=plane==="remote"&&publication?.scope===actorScope?publication.value:null;
  const currentTraceKey=coreFlowKey(plane,source,destination,selector,path);
  const visibleTrace=visibleCoreEvidence(traceEvidence,currentTraceKey);
  const visibleGraph=visibleCoreEvidence(graphEvidence,plane);
  useEffect(()=>{graphRequest.current+=1;setGraphEvidence(null);setSelectedPath(null);setError("");setGraphBusy(false)},[plane]);
  useEffect(()=>{traceRequest.current+=1;setTraceEvidence(null);setTraceBusy(false);setError("")},[plane,source,destination,selector,path]);
  useEffect(()=>()=>{graphRequest.current+=1;traceRequest.current+=1;publicationRequest.current+=1},[]);
  useEffect(()=>{
    publicationRequest.current+=1;
    setPublication(null);setPublicationError("");setPublicationBusy(false);
  },[plane,actorScope]);
  const ready=!!(source.trim()&&destination.trim()&&selector.trim());
  async function loadOwnership(){
    if(plane!=="remote"||publicationBusy
      ||typeof actor?.id!=="string"||!actor.id.trim()
      ||!["Admin","Operator","Read Only"].includes(String(actor?.role)))return;
    const generation=++publicationRequest.current,requestScope=actorScope;
    setPublication(null);setPublicationBusy(true);setPublicationError("");
    try{
      const [services,hosts]=await Promise.all([
        api("/api/v1/inventory?resource_type=remote-service&limit=100"),
        api("/api/v1/inventory?resource_type=managed-host&limit=100")
      ]);
      if(generation!==publicationRequest.current||requestScope!==currentActorScope.current)return;
      const proof=observedPublicationOwnership(services,hosts);
      if(!proof)throw new Error("Core publication inventory response is unverified");
      setPublication({scope:requestScope,value:proof});
    }catch(e:any){
      if(generation===publicationRequest.current&&requestScope===currentActorScope.current)
        setPublicationError("Core ownership evidence unavailable: "+String(e?.message||e));
    }finally{if(generation===publicationRequest.current)setPublicationBusy(false)}
  }
  async function loadGraph(){
    const token=++graphRequest.current;
    setGraphEvidence(null);setSelectedPath(null);setGraphBusy(true);setError("");
    try{
      const next=await api("/api/v1/policy/graph?plane="+encodeURIComponent(plane));
      const validated=observedCoreGraphSnapshot(next,plane);
      if(!validated)throw new Error("Core graph plane, scope or bounded totals are unverified.");
      if(graphRequest.current===token)setGraphEvidence({key:plane,value:validated});
    }catch(e:any){if(graphRequest.current===token)setError("Core graph unavailable: "+String(e.message||e))}
    finally{if(graphRequest.current===token)setGraphBusy(false)}
  }
  async function explain(){
    if(!ready)return;
    const token=++traceRequest.current;
    setTraceEvidence(null);setTraceBusy(true);setError("");
    const requestKey=currentTraceKey;
    const body:any={plane,source:source.trim(),destination:destination.trim()};
    if(plane==="ai"){body.permission=selector.trim();if(path.trim())body.path=path.trim()}
    else body.service=selector.trim();
    try{
      const next=await api("/api/v1/policy/trace",{method:"POST",body:JSON.stringify(body)});
      if(traceRequest.current===token)setTraceEvidence({key:requestKey,value:next});
    }catch(e:any){if(traceRequest.current===token)setError("Core decision unavailable: "+String(e.message||e))}
    finally{if(traceRequest.current===token)setTraceBusy(false)}
  }
  const observed=explainTrace(visibleTrace);
  const allPaths=Array.isArray(visibleGraph?.paths)?visibleGraph.paths:[];
  const paths=allPaths.slice(0,16).map((raw:any)=>modeledPathEvidence(raw,plane));
  const focus=selectedPath?.key===currentTraceKey&&visibleGraph?selectedPath:null;
  const limits=visibleGraph?.limits||{};
  return <section className="card dr-p0-section" aria-label="Effective access explanation" data-testid="p0-access-explain">
    <div className="dr-section-head"><div><p className="dr-eyebrow">Effective Access · Core evidence</p>
      <h3>Who can reach what — and why?</h3>
      <p className="muted">Select a Core-modeled flow or enter source, destination and service above. Policy result does not prove network reachability.</p>
    </div><button className="secondary" onClick={loadGraph} disabled={graphBusy}>{graphBusy?"Loading…":"Load modeled paths"}</button></div>
    {error&&<div className="error" role="alert">{error}</div>}
    {visibleGraph&&<>
      <div className="dr-p0-facts"><span>Modeled flows: {limits.path_count}</span>
        <span>Core revision: {visibleGraph.revision}</span>
        <span>Core graph: {limits.truncated===true?"TRUNCATED":limits.truncated===false?"bounded snapshot":"UNKNOWN scope"}</span>
        <span>Topology discovery: {visibleGraph.network_topology?"present":"not performed"}</span></div>
      {(limits.truncated!==false||allPaths.length>16)&&<p className="warning-box">
        {allPaths.length>16?"Only the first 16 modeled paths are displayed. ":""}
        {limits.truncated===true?"Core graph is truncated. ":limits.truncated!==false?"Core graph completeness is UNKNOWN. ":""}
        Absent paths are not proof of DENY.
      </p>}
      {paths.length? <div className="dr-p0-paths" aria-label="Core modeled paths">
        {paths.map((row,i)=>row?
          <button type="button" className="dr-p0-path" key={i}
            aria-pressed={focus?.key===row.key}
            onClick={()=>{
              setSelectedPath(row);
              onSelect(row.flow);
              setPath(row.flow.path);
            }}>
            <strong>{row.flow.source} <span aria-hidden="true">→</span> {row.flow.destination}</strong>
            <small>{row.flow.selector} · {row.ruleReferences.length?row.ruleReferences.join(", "):"policy references UNKNOWN"}</small>
            <span className={"dr-p0-result "+row.decision.toLowerCase()}>{row.decision}</span>
          </button>:
          <div className="dr-p0-path" key={i} role="status">Core modeled path {i+1}: UNKNOWN · incomplete or mismatched input</div>
        )}</div>:<p className="muted">No modeled paths returned. This does not prove an access decision.</p>}
    </>}
    {plane==="remote"&&<section className="dr-p0-evidence" role="region" aria-label="Observed Service to owning Host">
      <h4>Observed Service → owning Host</h4>
      <p className="muted">Read-only Core publication identity; this is separate from modeled policy flow, live connectivity and network topology.</p>
      <button className="secondary" type="button" onClick={loadOwnership}
        disabled={publicationBusy||!actor?.id||!["Admin","Operator","Read Only"].includes(String(actor?.role))}>
        {publicationBusy?"Reading Core ownership…":"Load published ownership"}</button>
      {publicationError&&<p className="warning-box" role="alert">{publicationError}</p>}
      {visiblePublication&&<>
        <p role="status">Observed publication relationship: {visiblePublication.edges.length} verified links in the loaded pages.</p>
        {(visiblePublication.partial||visiblePublication.limited||visiblePublication.unresolved>0)&&
          <p className="warning-box" role="status">Partial / UNKNOWN ownership scope. {visiblePublication.unresolved} loaded services have no verified owner in the observed Host page.
            {visiblePublication.partial?" Additional Core pages exist.":""}
            {visiblePublication.limited?" Only the first 16 links are displayed.":""}
            A missing link never proves that a Service has no owning Host.</p>}
        {visiblePublication.edges.length?<div className="dr-p0-paths" aria-label="Verified Core publication edges">
          {visiblePublication.edges.map(edge=><div className="dr-p0-path" key={edge.serviceId}>
            <strong>{edge.serviceName} <span aria-hidden="true">→</span> {edge.hostName}</strong>
            <small>Exact Core Service {edge.serviceId} → Host {edge.hostId}</small>
            <button type="button" className="secondary" disabled={!onInspectHost}
              onClick={()=>onInspectHost?.(edge.hostId)}>Inspect owning Host →</button>
          </div>)}
        </div>:<p className="muted">No exact publication links confirmed in this bounded Core page; ownership outside the observed rows remains UNKNOWN.</p>}
      </>}
    </section>}
    {focus&&<section className="dr-p0-evidence dr-p0-focused" aria-label="Focused Core-modeled access path" role="region">
      <h4>Focused access path · Core model</h4>
      <div className="dr-p0-route" aria-label="Source, policy references and destination">
        <div><small>Source object / group</small><strong>{focus.flow.source}</strong></div>
        <span aria-hidden="true">→</span>
        <div><small>Policy references · not governing proof</small>
          <strong>{focus.ruleReferences.length?focus.ruleReferences.join(", "):"UNKNOWN"}</strong></div>
        <span aria-hidden="true">→</span>
        <div><small>Destination object / group</small><strong>{focus.flow.destination}</strong></div>
      </div>
      <div className="dr-p0-facts"><span>Selector: {focus.flow.selector}</span>
        <span>Modeled decision: {focus.decision}</span>
        <span>Live reachability: NOT VERIFIED</span></div>
      {focus.ruleReferencesLimited&&<p className="warning-box">Policy references were bounded. This list may be incomplete.</p>}
      <p className="muted">These are modeled policy references, not confirmed governing rules. Run the fresh Core trace below before interpreting why access is allowed or denied.</p>
      <button type="button" className="secondary" disabled={!ready||traceBusy} onClick={explain}>
        {traceBusy?"Checking Core…":"Explain focused path with Core →"}
      </button>
    </section>}
    {plane==="ai"&&<label className="dr-field"><span>Optional AI request path</span><input value={path} onChange={e=>setPath(e.target.value)} placeholder="/resource/path"/></label>}
    <div className="dr-p0-actions"><button className="primary" onClick={explain} disabled={!ready||traceBusy}>{traceBusy?"Checking…":"Explain selected access"}</button>
      <button className="secondary" onClick={()=>onNavigate?.("policies","access")}>View policies</button>
      <button className="secondary" onClick={()=>onNavigate?.("audit","observability")}>Review audit evidence</button></div>
    {visibleTrace&&<div className="dr-p0-evidence">
      <div className="dr-p0-decision"><span>Effective policy decision</span><strong className={"dr-p0-result "+observed.decision.toLowerCase()}>{observed.decision}</strong></div>
      <div className="dr-p0-route" aria-label="Core decision route">
        <div><small>Source</small><strong>{observedTraceRouteValue(visibleTrace.normalized_input?.source,source)}</strong></div>
        <span aria-hidden="true">→</span>
        <div><small>Policy decision</small><strong>{observed.decision}</strong></div>
        <span aria-hidden="true">→</span>
        <div><small>Destination</small><strong>{observedTraceRouteValue(visibleTrace.normalized_input?.destination,destination)}</strong></div>
      </div>
      <p>{observed.reason}</p>
      <p className="muted">Matched rules: {observed.rules.length?observed.rules.join(", "):observed.rulesQualified?"none reported":"UNKNOWN"} · Mode: {observedTraceRouteValue(visibleTrace.policy?.mode,undefined)} · Enforcement: {observedTraceRouteValue(visibleTrace.policy?.enforcement,undefined)}</p>
      {!observed.rulesQualified&&<p className="warning-box" role="status">Core matched-rule references were missing, invalid or truncated. This does not prove no rule matched.</p>}
      {observed.rules.length>0&&<div className="dr-p0-actions" aria-label="Find Core-traced policy rule">
        {observed.rules.filter(rule=>rule.length<=160).map(rule=><button key={rule} type="button" className="secondary"
          onClick={()=>onNavigate?.("policies","access",{focusPolicy:{plane,name:rule},
            source:source.trim(),destination:destination.trim(),selector:selector.trim()})}>
          Find traced rule · {rule} →
        </button>)}
        <p className="muted">The policy list verifies an exact single rule identity before opening details. A trace name alone is not a policy ID.</p>
      </div>}
      {visibleTrace.mixed===true&&<p className="warning-box">Mixed group membership outcomes; inspect individual member results before acting.</p>}
      <details><summary>Advanced · exact Core trace</summary><pre className="plan">{JSON.stringify(visibleTrace,null,2)}</pre></details>
    </div>}
    {!visibleTrace&&!traceBusy&&<p className="muted">Decision: UNKNOWN until a fresh Core decision trace succeeds.</p>}
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
  useEffect(()=>{
    if(!preview||busy)return;
    const expires=Date.parse(preview.valid_until);
    const delay=expires-Date.now();
    if(!Number.isFinite(delay)||delay>2147483647)return;
    const timer=setTimeout(()=>{
      if(Date.now()>=expires){
        setPreview(null);setTests(null);setConfirmation("");setAcknowledge(false);
        setPhase(1);setError("Core Change Plan expired. Request a fresh Preview and policy tests.");
      }
    },Math.max(0,delay));
    return()=>clearTimeout(timer);
  },[preview?.change_plan_id,preview?.valid_until,busy]);
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
      const kind=plane+"-access-rule";
      if(result?.change_type!==kind||result?.resource_type!==kind
        ||result?.operation!=="guided."+kind+"."+operation
        ||!isObservedAbsoluteTime(result?.valid_until)
        ||Date.parse(result.valid_until)<=Date.now())
        throw new Error("Core Preview does not confirm the exact requested policy action and current plan expiry.");
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
  const safe=canApplyGuidedRule(preview,tests,acknowledge)
    &&preview?.change_type===plane+"-access-rule"
    &&preview?.operation==="guided."+plane+"-access-rule."+operation;
  const requiredWord=preview?.confirmation_class==="APPLY"?"APPLY":"UNVERIFIED";
  async function apply(){
    if(busy||confirmation!==requiredWord
      ||preview?.change_type!==plane+"-access-rule"
      ||preview?.operation!=="guided."+plane+"-access-rule."+operation)return;
    // Re-evaluate expiry and Core proof at click time; stale render state is
    // never sufficient to send a side-effecting Apply request.
    if(!canApplyGuidedRule(preview,tests,acknowledge)){
      setPreview(null);setTests(null);setConfirmation("");setAcknowledge(false);setPhase(1);
      setError("Core Change Plan is expired or incomplete. Request a fresh Preview and policy tests.");
      return;
    }
    const token=seq.current;
    setBusy(true);setError("");
    try{
      const result=await api("/api/v1/guided/apply",{method:"POST",body:JSON.stringify({
        change_plan_id:preview.change_plan_id,confirmation,
      })});
      if(seq.current!==token)return;
      const confirmed=observedGuidedPolicyApplyReceipt(result,preview,plane);
      if(!confirmed)throw new Error("Core did not confirm the reviewed Change Plan, rule or advanced revision.");
      setMessage("Core applied rule change at revision "+confirmed.revision);
      setPreview(null);setTests(null);setConfirmation("");setAcknowledge(false);setPhase(1);
    }catch(e:any){if(seq.current===token){
      // A transport error or unverified receipt may follow a committed Core
      // change; never invite a blind second Apply with the old one-shot plan.
      setPreview(null);setTests(null);setConfirmation("");setAcknowledge(false);setPhase(1);
      setError("Apply outcome UNKNOWN. Inspect Core Change History before retrying. "+String(e.message||e));
    }}
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
