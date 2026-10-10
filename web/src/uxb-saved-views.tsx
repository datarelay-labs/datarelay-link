import React,{useState} from "react";

export type StoredViewTarget="managed-host"|"remote-service";
export type HostAdmission="all"|"PENDING_APPROVAL"|"APPROVED"|"QUARANTINED";
export function isSavedAdmission(value:unknown):value is HostAdmission{
 return value==="all"||value==="PENDING_APPROVAL"||value==="APPROVED"||value==="QUARANTINED";
}
export type SavedFilterDraft={
 resource_type:StoredViewTarget,filter:string,admission?:Exclude<HostAdmission,"all">
};
// Match SQLite's ASCII NOCASE behavior for per-operator saved view names.
export function conflictingSavedViewName(items:unknown,name:unknown):string|null{
  if(!Array.isArray(items)||typeof name!=="string"||!name.trim())return null;
  const asciiFold=(text:string)=>text.replace(/[A-Z]/g,ch=>ch.toLowerCase());
  const requested=asciiFold(name.trim());
  const existing=items.find((item:any)=>typeof item?.name==="string"
    &&asciiFold(item.name)===requested);
  return existing?.name||null;
}
// A saved view is a personal display preference, never an access rule.
export function saveDraftForResource(kind:unknown,filter:unknown,admission:unknown="all"):SavedFilterDraft|null{
  if((kind!=="host"&&kind!=="service")||typeof filter!=="string")return null;
  if(!isSavedAdmission(admission)||(kind==="service"&&admission!=="all"))return null;
  const text=filter.trim();
  if(text.length>120||(!text&&admission==="all"))return null;
  return {
    resource_type:kind==="host"?"managed-host":"remote-service",filter:text,
    ...(kind==="host"&&admission!=="all"?{admission}:{}),
  };
}
export function readSavedView(value:unknown):{route:"hosts"|"services",filter:string,admission?:Exclude<HostAdmission,"all">}|null{
  if(!value||typeof value!=="object"||Array.isArray(value))return null;
  const payload=(value as any).payload;
  if(!payload||typeof payload!=="object"||Array.isArray(payload))return null;
  if(typeof payload.filter!=="string"||payload.filter.length>120)return null;
  if(payload.resource_type==="managed-host"){
    if(payload.admission!==undefined&&!isSavedAdmission(payload.admission))return null;
    if(!payload.filter.trim()&&(payload.admission===undefined||payload.admission==="all"))return null;
    return {route:"hosts",filter:payload.filter,
      ...(payload.admission&&payload.admission!=="all"?{admission:payload.admission}:{})};
  }
  if(payload.resource_type==="remote-service"){
    if(payload.admission!==undefined||!payload.filter.trim())return null;
    return {route:"services",filter:payload.filter};
  }
  return null;
}

export function SavedViewsWorkspace({data,api,onNavigate,refresh,initialDraft}:{
  data:any,api:(path:string,init?:RequestInit)=>Promise<any>,initialDraft?:unknown,
  onNavigate?:(id:string,group?:string,context?:any)=>void,refresh:()=>void
}){
  const prepared=readSavedView({payload:initialDraft});
  const safeDraft=prepared?saveDraftForResource(prepared.route==="hosts"?"host":"service",prepared.filter,prepared.admission||"all"):null;
  const [name,setName]=useState(""),[filter,setFilter]=useState(safeDraft?.filter||"");
  const [target,setTarget]=useState<StoredViewTarget>(safeDraft?.resource_type||"managed-host");
  const [admission,setAdmission]=useState<HostAdmission>(safeDraft?.admission||"all");
  const currentDraft=saveDraftForResource(target==="managed-host"?"host":"service",filter,admission);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const [confirmReplace,setConfirmReplace]=useState(false);
  const rows=Array.isArray(data?.items)?data.items:[];
  const duplicate=conflictingSavedViewName(rows,name);
  // Core currently returns at most 100 views, so an unobserved collision is possible.
  const incompleteNames=rows.length>=100;
  async function save(e:React.FormEvent){
    e.preventDefault();
    if(busy||!name.trim()||!currentDraft)return;
    if(duplicate&&!confirmReplace)return;
    if(incompleteNames&&!confirmReplace)return;
    setError("");setNotice("");setBusy(true);
    try{
      await api("/api/v1/saved-views",{method:"POST",
        body:JSON.stringify({name:name.trim(),payload:currentDraft})});
      setName("");setConfirmReplace(false);
      setNotice("Private filter saved. Check My saved filters for the latest list.");refresh();
    }catch(e:any){setError(e.message||String(e))}
    finally{setBusy(false)}
  }
  return <div className="dr-resource-workspace">
    <header className="dr-page-intro"><div><p className="dr-eyebrow">Activity &amp; Health · Preferences</p>
      <h2>Saved Views</h2><p className="muted">Reuse a named filter for observed Hosts or Remote Services. These are private display preferences, never access policies.</p></div></header>
    {error&&<p role="alert" className="warning-box">{error}</p>}
    {notice&&<p role="status" className="muted">{notice}</p>}
    <section className="card dr-list-card"><h3>Save a resource filter</h3>
      {safeDraft&&<p role="status" className="muted">Pre-filled from {safeDraft.resource_type==="managed-host"?"Servers & Agents":"Published Services"}. Saved admission state: {safeDraft.admission?safeDraft.admission.replaceAll("_"," "):"All"}. Give this view a name and explicitly save it. Unloaded Core pages are not included.</p>}
      <form onSubmit={save}>
        <div className="toolbar">
          <label>View name <input value={name} maxLength={80} onChange={e=>{setName(e.target.value);setConfirmReplace(false);setNotice("")}} placeholder="Offline hosts" required/></label>
          <label>Resource type <select value={target} onChange={e=>{setTarget(e.target.value as StoredViewTarget);setAdmission("all");setConfirmReplace(false)}}>
            <option value="managed-host">Servers &amp; Agents</option>
            <option value="remote-service">Published Services</option>
          </select></label>
          <label>Filter text <input value={filter} maxLength={120} onChange={e=>{setFilter(e.target.value);setConfirmReplace(false)}} placeholder="offline" required={target!=="managed-host"||admission==="all"}/></label>
          {target==="managed-host"&&<label>Filter Managed Host admission <select value={admission} onChange={e=>{setAdmission(e.target.value as HostAdmission);setConfirmReplace(false)}}>
            <option value="all">All admission states</option>
            <option value="PENDING_APPROVAL">Pending approval</option>
            <option value="APPROVED">Approved</option>
            <option value="QUARANTINED">Quarantined</option>
          </select></label>}
          <button type="submit" className="primary" disabled={busy||!name.trim()||!currentDraft||!!(duplicate&&!confirmReplace)||incompleteNames&&!confirmReplace}>
            {busy?"Saving…":duplicate?"Replace filter":"Save filter"}</button>
        </div>
        {!!name.trim()&&(duplicate||incompleteNames)&&<label className="warning-box">
          <input type="checkbox" checked={confirmReplace} onChange={e=>setConfirmReplace(e.target.checked)} disabled={busy}/>
          <strong>{duplicate?"Replace existing saved filter":"Possible name collision"}</strong>
          <span>{duplicate
            ? "An existing name in your observed private list matches this name (case-insensitive): "+duplicate+". Confirm to replace its saved resource type and text filter."
            : "The first 100 private views were observed, but older names may be missing. Saving this name could replace an unlisted private filter. Confirm before proceeding."}</span>
        </label>}
      </form>
    </section>
    <section className="card dr-list-card"><h3>My saved filters</h3>
      {rows.length?<div className="dr-table-scroll"><table className="dr-resource-table">
        <thead><tr><th>View</th><th>Resources</th><th>Filter</th><th>Updated</th><th>Action</th></tr></thead>
        <tbody>{rows.map((item:any,i:number)=>{
          const parsed=readSavedView(item);
          return <tr key={item.id||i}><td><strong>{item.name||item.id||"Unnamed view"}</strong></td>
            <td>{parsed?(parsed.route==="hosts"?"Servers & Agents":"Published Services"):"Target unspecified"}</td>
            <td>{parsed?(parsed.filter||"No text")+(parsed.admission?" · "+parsed.admission.replaceAll("_"," "):""):"Not specified"}</td><td>{item.updated_at||"UNKNOWN"}</td>
            <td>{parsed?<button type="button" className="secondary"
              onClick={()=>onNavigate?.(parsed.route,"connections",{savedFilter:parsed.filter,savedAdmission:parsed.admission||"all"})}>
              Open saved filter →</button>:<span className="muted">
              Legacy/unsupported view; save a new named target</span>}</td>
          </tr>;
        })}</tbody>
      </table></div>:<p className="dr-empty-state">No saved views yet. Save a named filter for an observed resource list.</p>}
      <p className="muted">A saved view only changes the visible text filter and optional Host admission display. It does not fetch missing inventory pages, permit a connection or create a Core configuration revision.</p>
    </section>
  </div>;
}
