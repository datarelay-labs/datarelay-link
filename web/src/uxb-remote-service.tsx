import React,{useEffect,useRef,useState} from "react";
import type {LinkApi} from "./p0-access-policy";
import {CoreChoiceField,useCoreCatalog,type CoreCatalog} from "./uxb-core-choices";

/** Queue results use job_id; canonical Core job details use id. Never lose the
 * queued identity or present a different job as evidence for this service. */
export function mergeRemoteServiceJob(queued:any,detail:any){
  const requested=String(queued?.job_id||queued?.id||"");
  const observed=String(detail?.job_id||detail?.id||"");
  if(!requested||observed!==requested)throw new Error("Core returned a different Agent job identity.");
  return {...detail,job_id:requested};
}

/** UXB-03: one canonical Remote Service editor used from both Services and Setup. */
export function RemoteServiceEditor({api,ownerHint="",onSelection,initialSelection,resourceCatalog,onBusyChange}:{
  api:LinkApi,ownerHint?:string,resourceCatalog?:CoreCatalog|null,
  onBusyChange?:(busy:boolean)=>void,
  onSelection?:(selection:{owner:string,name:string,service:string,destination:string})=>void,
  initialSelection?:{owner?:string,name?:string,service?:string,destination?:string},
}){
  const [owner,setOwner]=useState(initialSelection?.owner||ownerHint||""),[name,setName]=useState(initialSelection?.name||"");
  const [operation,setOperation]=useState("set"),[destination,setDestination]=useState(initialSelection?.destination||"this-host");
  const [service,setService]=useState(initialSelection?.service||""),[enabled,setEnabled]=useState(true);
  const [preview,setPreview]=useState<any>(null),[confirmation,setConfirmation]=useState("");
  const [job,setJob]=useState<any>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  const lastOwnerHint=useRef(ownerHint);
  const requestGeneration=useRef(0);
  const catalog=useCoreCatalog(api,resourceCatalog);
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
  useEffect(()=>{onSelection?.({owner,name,service,destination})},[owner,name,service,destination]);
  function edit<T>(setter:(value:T)=>void,value:T){
    requestGeneration.current+=1;
    setter(value);setPreview(null);setConfirmation("");setJob(null);setError("");
  }
  const ready=!!(owner.trim()&&name.trim()&&(operation==="delete"||destination.trim()&&service.trim()));
  const required=String(preview?.confirmation_class||"APPLY");
  async function doPreview(){
    if(!ready||busy)return;
    const generation=++requestGeneration.current;
    setError("");setPreview(null);setConfirmation("");setJob(null);setBusy(true);
    try{
      const body:any={owner:owner.trim(),name:name.trim(),operation};
      if(operation==="set")Object.assign(body,{destination:destination.trim(),service:service.trim(),enabled});
      const result=await api("/api/v1/remote-services/preview",{method:"POST",body:JSON.stringify(body)});
      if(generation!==requestGeneration.current)return;
      setPreview(result);setConfirmation("");
    }catch(e:any){if(generation===requestGeneration.current){setPreview(null);setError(String(e?.message||e))}}
    finally{if(generation===requestGeneration.current)setBusy(false)}
  }
  async function doApply(){
    if(!preview?.change_plan_id||confirmation!==required||busy)return;
    const generation=++requestGeneration.current;
    setError("");setBusy(true);
    try{
      const result=await api("/api/v1/remote-services/apply",{method:"POST",
        body:JSON.stringify({change_plan_id:preview.change_plan_id,confirmation})});
      // A queued Agent job is NOT a published service or a successful connection.
      if(generation!==requestGeneration.current){
        setError("Owner changed during a previous Agent job request. Review Jobs before proceeding.");
        return;
      }
      setJob(result);setPreview(null);setConfirmation("");
    }catch(e:any){if(generation===requestGeneration.current)setError(String(e?.message||e))}
    finally{if(generation===requestGeneration.current)setBusy(false)}
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
    <fieldset className="dr-uxb-form" disabled={busy}>
      <label className="dr-field"><span>Owning Agent / Managed Host</span><input value={owner} onChange={e=>edit(setOwner,e.target.value)} placeholder="Host name or ID"/></label>
      <label className="dr-field"><span>Remote Service name</span><input value={name} onChange={e=>edit(setName,e.target.value)} placeholder="e.g. ssh-admin"/></label>
      <label className="dr-field"><span>Change</span><select value={operation} onChange={e=>edit(setOperation,e.target.value)}><option value="set">Create / edit</option><option value="delete">Delete</option></select></label>
      {operation==="set"&&<>
        <label className="dr-field"><span>Destination</span><input value={destination} onChange={e=>edit(setDestination,e.target.value)} placeholder="this-host or approved destination"/></label>
        <label className="dr-field"><span>Service Object</span><input value={service} onChange={e=>edit(setService,e.target.value)} placeholder="e.g. ssh-tcp22"/><small>Protocol/port object; not the same as the Remote Service name.</small></label>
        <label className="dr-uxb-check"><input type="checkbox" checked={enabled} onChange={e=>edit(setEnabled,e.target.checked)}/> Enable service</label>
      </>}
    </fieldset>
    <button className="primary" disabled={!ready||busy} onClick={doPreview}>{busy?"Checking…":"Preview service impact"}</button>
    {preview&&<div className="dr-p0-review">
      <h4>Core change preview</h4>
      <p>Valid until: {preview.valid_until||"UNKNOWN"} · approval never means Agent job completed.</p>
      <details><summary>Review owning Host, impact and expected work</summary>
        <pre className="plan">{JSON.stringify({owner:preview.owner,impact:preview.impact,preview:preview.preview},null,2)}</pre>
      </details>
      <label className="dr-field"><span>Type {required} to queue</span><input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder={required}/></label>
      <button className="danger" disabled={busy||!preview.change_plan_id||confirmation!==required} onClick={doApply}>Queue authenticated Agent job</button>
    </div>}
    {job&&<div className="notice" role="status">
      <strong>Agent job: {job.job_id||job.id||"UNKNOWN"}</strong>
      <p>Status: {job.job_status||job.status||"QUEUED / NOT VERIFIED"}. Service publication and target reachability must be verified separately.</p>
      <button className="secondary" disabled={busy||!job.job_id} onClick={refreshJob}>Refresh actual job status</button>
      <details><summary>Advanced job details</summary><pre className="plan">{JSON.stringify(job,null,2)}</pre></details>
    </div>}
  </section>;
}
