import React,{useEffect,useRef,useState} from "react";
import type {LinkApi} from "./p0-access-policy";
import {CoreChoiceField,useCoreCatalog,type CoreCatalog} from "./uxb-core-choices";
import {isObservedAbsoluteTime} from "./uxb-integrations-state";

/** Queue results use job_id; canonical Core job details use id. Never lose the
 * queued identity or present a different job as evidence for this service. */
export function mergeRemoteServiceJob(queued:any,detail:any){
  const requested=String(queued?.job_id||queued?.id||"");
  const observed=String(detail?.job_id||detail?.id||"");
  if(!/^mjob_[0-9a-f]{24}$/.test(requested)
    ||observed!==requested)throw new Error("Core returned a different Agent job identity.");
  return {...detail,job_id:requested};
}

/** UX-8: a Core Job may include privileged payload, claim and target result
 * fields. Only narrowly approved read-only metadata belongs in Service UX.
 * Unsupported status and untrusted values never become false job SUCCESS.
 */
const JOB_BAD_TEXT=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const JOB_STATUSES=new Set(["QUEUED","RUNNING","SUCCEEDED","FAILED","CANCELLED"]);
export function remoteServiceJobEvidence(input:unknown){
 const data=input!==null&&typeof input==="object"&&!Array.isArray(input)
   ?input as Record<string,unknown>:{};
 const rawId=data.job_id??data.id;
 const jobId=typeof rawId==="string"&&/^mjob_[0-9a-f]{24}$/.test(rawId)
   &&(data.id===undefined||data.job_id===undefined||data.id===data.job_id)
   ?rawId:"UNKNOWN";
 const rawStatus=data.job_status??data.status;
 const count=data.target_count;
 const validCount=typeof count==="number"&&Number.isSafeInteger(count)
   &&count>=1&&count<=100;
 const status=jobId!=="UNKNOWN"&&typeof rawStatus==="string"
   &&JOB_STATUSES.has(rawStatus)
   &&!(data.job_status!==undefined&&data.status!==undefined
     &&data.job_status!==data.status)
   &&!(rawStatus==="SUCCEEDED"&&count===0)
   ?rawStatus:"UNKNOWN";
 const lastError=data.last_error;
 // Core Agent errors are diagnostic codes only in this public view.
 // Arbitrary backend/worker strings can include bearer URLs or credentials.
 const safeError=lastError===""||lastError===null?""
   :typeof lastError==="string"&&/^[A-Z][A-Z0-9_]{0,63}$/.test(lastError)
     ?lastError:"UNKNOWN";
 return {
   job_id:jobId,
   status,
   target_count:validCount?count:"UNKNOWN",
   updated_at:isObservedAbsoluteTime(data.updated_at)?data.updated_at:"UNKNOWN",
   last_error:safeError,
 };
}

/** M2/R6: product-owned, public-only Core Remote Service Change Plan.
 * Core resolves a possibly friendly Host selector into a unique immutable
 * Host ID; do not equate typed display aliases to that ID. Instead require
 * strict internal plan/owner/impact coherence for the exact service name and
 * operation before displaying a one-shot confirmation.
 */
export type ObservedRemoteServicePreview={
 change_plan_id:string,operation_class:"CHANGE",operation:string,
 resource_type:"remote-service",resource_ref:string,
 expected_revision:number,confirmation_class:"APPLY",valid_until:string,
 remote_service:string,
 owner:{id:string,name:string,connectivity:string},
 impact:{requires_confirmation:true,destructive:boolean,
   owner_managed_host_id:string,owner_connectivity:string,
   runtime_authority:"agent-rpc"}
};
const BANNED=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const HOST_ID=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;
const PLAN_ID=/^cp_[A-Za-z0-9_-]{16,128}$/;
const JOB_ID=/^mjob_[0-9a-f]{24}$/;
const coreObject=(v:unknown):v is Record<string,any>=>
  v!==null&&typeof v==="object"&&!Array.isArray(v);
const displayName=(v:unknown,max=160):string=>
  typeof v==="string"&&v.trim().length>0&&v.length<=max&&!BANNED.test(v)
    ?v.trim():"UNKNOWN";
export function observedRemoteServicePreview(
 input:unknown,requested:unknown,now:number=Date.now()
):ObservedRemoteServicePreview|null{
 if(!coreObject(input)||!coreObject(requested)||!Number.isFinite(now))return null;
 const value=input,req=requested;
 const requestedName=typeof req.name==="string"?req.name.trim():"";
 const action=req.operation;
 if(!["set","delete"].includes(String(action))
   ||typeof req.owner!=="string"||!req.owner.trim()
   ||req.owner.length>160||BANNED.test(req.owner)
   ||!requestedName||requestedName.length>128||BANNED.test(requestedName)
   ||action==="set"&&(
      typeof req.destination!=="string"||!req.destination.trim()
      ||typeof req.service!=="string"||!req.service.trim()
      ||typeof req.enabled!=="boolean"))return null;
 if(!PLAN_ID.test(String(value.change_plan_id))
   ||value.operation_class!=="CHANGE"
   ||value.operation!=="remote-service."+action
   ||value.resource_type!=="remote-service"
   ||!Number.isSafeInteger(value.expected_revision)||value.expected_revision<0
   ||value.confirmation_class!=="APPLY"
   ||!isObservedAbsoluteTime(value.valid_until)
   ||Date.parse(value.valid_until)<=now
   ||value.remote_service!==requestedName
   ||!coreObject(value.owner)||!HOST_ID.test(String(value.owner.id))
   ||value.resource_ref!==value.owner.id+":"+requestedName
   ||!coreObject(value.impact)
   ||value.impact.requires_confirmation!==true
   ||value.impact.destructive!==(action==="delete")
   ||value.impact.owner_managed_host_id!==value.owner.id
   ||value.impact.owner_connectivity!==value.owner.connectivity
   ||value.impact.runtime_authority!=="agent-rpc")return null;
 const state=displayName(value.owner.connectivity,40);
 if(state==="UNKNOWN"||state.toLowerCase()!==state)return null;
 return {
  change_plan_id:value.change_plan_id,operation_class:"CHANGE",
  operation:value.operation,resource_type:"remote-service",
  resource_ref:value.resource_ref,expected_revision:value.expected_revision,
  confirmation_class:"APPLY",valid_until:value.valid_until,
  remote_service:requestedName,
  owner:{id:value.owner.id,name:displayName(value.owner.name),connectivity:state},
  impact:{requires_confirmation:true,destructive:action==="delete",
   owner_managed_host_id:value.owner.id,owner_connectivity:state,
   runtime_authority:"agent-rpc"}
 };
}

/** A queued Agent Job is neither an applied Remote Service nor a verified
 * connection. Check Core's immutable Job identity, owner, operation and
 * revision against the exact reviewed Change Plan before showing acceptance.
 */
export function observedRemoteServiceApplyReceipt(
 input:unknown,plan:unknown
):{status:"QUEUED",job_id:string,job_status:"QUEUED",
  target_managed_host_id:string,remote_service:string,operation:string,
  authoritative_revision_at_enqueue:number}|null{
 if(!coreObject(input)||!coreObject(plan)||!coreObject(plan.owner))return null;
 const receipt=input;
 const action=plan.operation==="remote-service.set"?"set":
   plan.operation==="remote-service.delete"?"delete":null;
 if(!action||receipt.status!=="QUEUED"||receipt.job_status!=="QUEUED"
   ||typeof receipt.job_id!=="string"||!JOB_ID.test(receipt.job_id)
   ||receipt.target_managed_host_id!==plan.owner.id
   ||receipt.remote_service!==plan.remote_service
   ||receipt.operation!==action
   ||!Number.isSafeInteger(plan.expected_revision)
   ||receipt.authoritative_revision_at_enqueue!==plan.expected_revision)
   return null;
 return {status:"QUEUED",job_id:receipt.job_id,job_status:"QUEUED",
   target_managed_host_id:receipt.target_managed_host_id,
   remote_service:receipt.remote_service,operation:action,
   authoritative_revision_at_enqueue:receipt.authoritative_revision_at_enqueue};
}

/** UXB-03: one canonical Remote Service editor used from both Services and Setup. */
/** Bind the guided setup to its observed Host, not a retained/manual editor value.
 * The standalone advanced Services editor intentionally remains unbound. */
export function remoteServiceOwner(owner:string,ownerHint:string,lockOwner:boolean):string{
  return String(lockOwner?ownerHint:owner||"").trim();
}

export function RemoteServiceEditor({api,ownerHint="",onSelection,initialSelection,resourceCatalog,onBusyChange,lockOwner=false}:{
  api:LinkApi,ownerHint?:string,resourceCatalog?:CoreCatalog|null,lockOwner?:boolean,
  onBusyChange?:(busy:boolean)=>void,
  onSelection?:(selection:{owner:string,name:string,service:string,destination:string})=>void,
  initialSelection?:{owner?:string,name?:string,service?:string,destination?:string},
}){
  const [owner,setOwner]=useState(lockOwner?ownerHint:initialSelection?.owner||ownerHint||""),[name,setName]=useState(initialSelection?.name||"");
  const [operation,setOperation]=useState("set"),[destination,setDestination]=useState(initialSelection?.destination||"this-host");
  const [service,setService]=useState(initialSelection?.service||""),[enabled,setEnabled]=useState(true);
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState("");
  const [job,setJob]=useState<any>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const lastOwnerHint=useRef(ownerHint);
  const requestGeneration=useRef(0);
  const applyInFlight=useRef(false);
  const catalog=useCoreCatalog(api,resourceCatalog);
  const visibleJob=remoteServiceJobEvidence(job);
  useEffect(()=>{onBusyChange?.(busy)},[busy]);
  useEffect(()=>()=>{onBusyChange?.(false)},[]);
  useEffect(()=>{
    // Do not overwrite a resumed, intentionally selected owner on mount.
    // A genuinely different host selected in Setup resets the owner and plan.
    if(lastOwnerHint.current===ownerHint)return;
    lastOwnerHint.current=ownerHint;
    requestGeneration.current+=1;
    setOwner(ownerHint);setPreview(null);setConfirmation("");setJob(null);setError("");setBusy(false);
  },[ownerHint]);
  const actualOwner=remoteServiceOwner(owner,ownerHint,lockOwner);
  useEffect(()=>{onSelection?.({owner:actualOwner,name,service,destination})},[actualOwner,name,service,destination]);
  function edit<T>(setter:(value:T)=>void,value:T){
    requestGeneration.current+=1;
    setter(value);setPreview(null);setConfirmation("");setJob(null);setError("");
  }
  const ready=!!(actualOwner&&name.trim()&&(operation==="delete"||destination.trim()&&service.trim()));
  const required=String(preview?.confirmation_class||"APPLY");
  async function doPreview(){
    if(!ready||busy)return;
    const generation=++requestGeneration.current;
    setError("");setPreview(null);setConfirmation("");setJob(null);setBusy(true);
    try{
      const body:any={owner:actualOwner,name:name.trim(),operation};
      if(operation==="set")Object.assign(body,{destination:destination.trim(),service:service.trim(),enabled});
      const result=await api("/api/v1/remote-services/preview",{method:"POST",body:JSON.stringify(body)});
      if(generation!==requestGeneration.current)return;
      const observed=observedRemoteServicePreview(result,body);
      if(!observed)throw new Error("Core Remote Service Preview is UNKNOWN; its owner, impact, expiry or requested service was not confirmed.");
      setPreview(observed);setConfirmation("");
    }catch(e:any){if(generation===requestGeneration.current){setPreview(null);setError(String(e?.message||e))}}
    finally{if(generation===requestGeneration.current)setBusy(false)}
  }
  function cancelReview(){
    requestGeneration.current+=1;
    setPreview(null);setConfirmation("");setError("");
  }
  async function doApply(){
    // The Core apply can enqueue a distinct Agent Job before React renders
    // the busy flag. Ref lock closes the duplicate non-idempotent POST gap.
    if(applyInFlight.current)return;
    if(!preview?.change_plan_id||confirmation!==required||busy)return;
    if(!isObservedAbsoluteTime(preview.valid_until)
      ||Date.parse(preview.valid_until)<=Date.now()){
      setPreview(null);setConfirmation("");
      setError("Core Remote Service Change Plan expired. Preview again before queueing an Agent Job.");
      return;
    }
    applyInFlight.current=true;
    const generation=++requestGeneration.current;
    const reviewed=preview;
    setError("");setBusy(true);
    try{
      const result=await api("/api/v1/remote-services/apply",{method:"POST",
        body:JSON.stringify({change_plan_id:reviewed.change_plan_id,confirmation})});
      // A queued Agent job is NOT a published service or a successful connection.
      if(generation!==requestGeneration.current){
        setError("Owner changed during a previous Agent job request. Review Jobs before proceeding.");
        return;
      }
      const receipt=observedRemoteServiceApplyReceipt(result,reviewed);
      if(!receipt)throw new Error("Core Remote Service enqueue receipt does not match reviewed owner, operation or Job.");
      setJob(receipt);setPreview(null);setConfirmation("");
    }catch(e:any){
      if(generation===requestGeneration.current){
        // A timeout/ambiguous 200 may follow a committed Core enqueue.
        // Never offer the same confirmation for a blind second Agent Job.
        setPreview(null);setConfirmation("");setJob(null);
        setError("UNKNOWN · Core Agent Job may already be queued. Inspect Jobs and Service inventory before a fresh Preview. "+String(e?.message||e));
      }
    }finally{applyInFlight.current=false;if(generation===requestGeneration.current)setBusy(false)}
  }
  async function refreshJob(){
    if(!job?.job_id||busy)return;
    const generation=++requestGeneration.current;
    setBusy(true);
    try{
      const detail=await api("/api/v1/jobs/"+encodeURIComponent(String(job.job_id)));
      if(generation!==requestGeneration.current)return;
      setJob(mergeRemoteServiceJob(job,detail));
    }
    catch(e:any){if(generation===requestGeneration.current)setError(String(e?.message||e))}
    finally{if(generation===requestGeneration.current)setBusy(false)}
  }
  return <section className="card dr-uxb-service" data-testid="uxb-remote-service">
    <p className="dr-eyebrow">Publish one internal service</p>
    <h3>Choose what an approved Agent makes available</h3>
    <p className="muted">A Managed Host is not automatically accessible. Each Remote Service needs a real host, a configured Service Object and an explicit Core access rule.</p>
    {operation==="set"&&<div className="dr-uxb-catalog-guide"><strong>Which protocol / port should be published?</strong>
      <CoreChoiceField api={api} catalog={catalog} plane="remote" field="selector" value={service} disabled={busy} onChoose={value=>edit(setService,value)}/>
      <p className="muted">Example: choose your existing TCP/22 Service Object. The Remote Service name is a separate label you choose below.</p>
    </div>}
    {error&&<p className="error" role="alert">{error}</p>}
    {lockOwner?<div className="dr-uxb-selected-owner" role="status">
      <strong>Selected Managed Host</strong><span>{actualOwner||"UNKNOWN"}</span>
      <small>Bound to the observed Agent selected in setup. Change the owner from the previous step; do not retype a Host ID here.</small>
    </div>:<label className="dr-field"><span>Owning Agent / Managed Host</span>
      <input value={actualOwner} onChange={e=>edit(setOwner,e.target.value)} placeholder="Host name or ID"/>
    </label>}
    <fieldset className="dr-uxb-form" disabled={busy}>
      <label className="dr-field"><span>Remote Service name</span><input value={name} onChange={e=>edit(setName,e.target.value)} placeholder="e.g. ssh-admin"/></label>
      {operation==="set"&&<>
        <label className="dr-field"><span>Service Object</span><input value={service} onChange={e=>edit(setService,e.target.value)} placeholder="e.g. ssh-tcp22"/><small>Protocol/port object; not the same as the Remote Service name.</small></label>
        <label className="dr-field"><span>Internal target</span><input value={destination} onChange={e=>edit(setDestination,e.target.value)} placeholder="this-host or approved destination"/><small>The public endpoint remains proposed until Core/Agent inventory confirms it.</small></label>
      </>}
    </fieldset>
    <details className="dr-wf-disclosure dr-uxb-service-advanced">
      <summary>Advanced service options</summary>
      <div className="dr-uxb-form">
        <label className="dr-field"><span>Change</span><select value={operation} disabled={busy} onChange={e=>edit(setOperation,e.target.value)}><option value="set">Create / edit</option><option value="delete">Delete</option></select></label>
        {operation==="set"&&<label className="dr-uxb-check"><input type="checkbox" checked={enabled} disabled={busy} onChange={e=>edit(setEnabled,e.target.checked)}/> Enable service after the Agent job succeeds</label>}
      </div>
      {operation==="delete"&&<p className="warning-box">Delete is destructive for this Remote Service. Core Preview remains mandatory; disabling a service is not the same as releasing its reservation.</p>}
    </details>
    <div className="dr-uxb-service-proposed" role="status"><strong>Proposed configuration</strong>
      <span>{operation==="delete"?"Delete the selected Remote Service after Core impact review.":actualOwner&&name.trim()&&service.trim()?actualOwner+" → "+name.trim()+" → "+service.trim()+" @ "+destination.trim():"Choose the service name and protocol/port object. No public endpoint is confirmed yet."}</span>
    </div>
    <button className="primary" disabled={!ready||busy} onClick={doPreview}>{busy?"Checking…":"Review service change →"}</button>
    {preview&&<div className="dr-p0-review">
      <h4>Core change preview</h4>
      <p>Valid until: {preview.valid_until||"UNKNOWN"} · approval never means Agent job completed.</p>
      <details className="dr-technical-details"><summary>Technical details · owning Host and expected work</summary>
        <pre className="plan">{JSON.stringify({owner:preview.owner,impact:preview.impact,preview:preview.preview},null,2)}</pre>
      </details>
      <label className="dr-field"><span>Type {required} to queue</span><input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder={required}/></label>
      <div className="dr-form-actions"><button className="secondary" type="button" disabled={busy} onClick={cancelReview}>Cancel review</button>
        <button className="danger" disabled={busy||!preview.change_plan_id||confirmation!==required} onClick={doApply}>Queue authenticated Agent job</button></div>
      <p className="muted">Cancel discards only this browser review. No Core or Agent mutation is sent until Apply.</p>
    </div>}
    {job&&<div className="notice" role="status">
      <strong>Agent job: {visibleJob.job_id}</strong>
      <p>Status: {visibleJob.status}. The public endpoint is confirmed only by fresh Remote Service inventory after the job succeeds; target reachability remains separate.</p>
      <button className="secondary" disabled={busy||!job.job_id||visibleJob.job_id==="UNKNOWN"} onClick={refreshJob}>Refresh actual job status</button>
      <details className="dr-technical-details"><summary>Technical details · bounded Core job evidence</summary><pre className="plan">{JSON.stringify(visibleJob,null,2)}</pre>
        <p className="muted">Unrestricted Agent payloads, credentials and job results are not displayed in this workspace. Check authenticated Jobs for permitted diagnostic details.</p>
      </details>
    </div>}
  </section>;
}
