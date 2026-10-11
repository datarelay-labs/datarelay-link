import React,{useState} from "react";
import {isObservedAbsoluteTime} from "./uxb-integrations-state";
import {sortLoadedSavedViews,isSavedViewSortMode,type SavedViewSortMode} from "./uxb-saved-views-sort";

/** Private filter metadata is not Core authorization evidence; reject
 * control/bidi spoofing and avoid rendering arbitrary nested values. */
const UNSAFE_VIEW_TEXT=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
function visibleViewText(value:unknown,max=80):string{
  if(typeof value!=="string"||value.length>max||UNSAFE_VIEW_TEXT.test(value))
    return "";
  return value.trim();
}
/** G-30: search ONLY currently loaded operator-private names. The complete
 * loaded list stays authoritative for duplicate-name and 100-row safety.
 * Never inspect private filter payload, credentials or other users' views.
 */
export type VisibleSavedViewList={
 items:Record<string,unknown>[],loadedCount:number,
 scope:"loaded-only",error:string|null
};
export function filterObservedSavedViewList(input:unknown,query:unknown):VisibleSavedViewList{
 const empty=(error:string|null):VisibleSavedViewList=>({
   items:[],loadedCount:0,scope:"loaded-only",error
 });
 if(!Array.isArray(input))return empty("Private saved view inventory unavailable.");
 const valid=input.filter((row):row is Record<string,unknown>=>
   row!==null&&typeof row==="object"&&!Array.isArray(row));
 if(typeof query!=="string"||query.length>80||UNSAFE_VIEW_TEXT.test(query))
   return {...empty("Invalid saved filter search. Use at most 80 printable characters."),
     loadedCount:valid.length};
 const search=query.trim().toLowerCase();
 return {items:search?valid.filter(row=>{
   const name=visibleViewText(row.name);
   return !!name&&name.toLowerCase().includes(search);
 }):[...valid],loadedCount:valid.length,scope:"loaded-only",error:null};
}
/** Match the Core's max-80-character name bound, but refuse invisible
 * controls and bidi overrides before they can spoof a private replace prompt.
 */
export function validSavedViewName(value:unknown):value is string{
 return typeof value==="string"&&value.length<=80
  &&!!value.trim()&&!UNSAFE_VIEW_TEXT.test(value);
}
export type StoredViewTarget="managed-host"|"remote-service"|"access-rule";
export type PolicyPlane="all"|"remote"|"internet"|"ai";
export function isPolicyPlane(value:unknown):value is PolicyPlane{
 return value==="all"||value==="remote"||value==="internet"||value==="ai";
}
export type HostAdmission="all"|"PENDING_APPROVAL"|"APPROVED"|"QUARANTINED";
export function isSavedAdmission(value:unknown):value is HostAdmission{
 return value==="all"||value==="PENDING_APPROVAL"||value==="APPROVED"||value==="QUARANTINED";
}
export type SavedFilterDraft=
 |{resource_type:"managed-host",filter:string,admission?:Exclude<HostAdmission,"all">}
 |{resource_type:"remote-service",filter:string}
 |{resource_type:"access-rule",filter:string,plane:PolicyPlane};
// Match SQLite's ASCII NOCASE behavior for per-operator saved view names.
export function conflictingSavedViewName(items:unknown,name:unknown):string|null{
  if(!Array.isArray(items)||!validSavedViewName(name))return null;
  const asciiFold=(text:string)=>text.replace(/[A-Z]/g,ch=>ch.toLowerCase());
  const requested=asciiFold(name.trim());
  const existing=items.find((item:any)=>validSavedViewName(item?.name)
    &&asciiFold(item.name)===requested);
  return existing?.name||null;
}
// A saved view is a personal display preference, never an access rule.
export function saveDraftForResource(kind:unknown,filter:unknown,admission:unknown=undefined):SavedFilterDraft|null{
  if(typeof filter!=="string"||filter.length>120||UNSAFE_VIEW_TEXT.test(filter))return null;
  const text=filter.trim();
  if(kind==="policy"){
    // The plane must be supplied explicitly. A forgotten third argument is
    // not silently converted into a potentially broad All-policy preference.
    if(!isPolicyPlane(admission)||(!text&&admission==="all"))return null;
    return {resource_type:"access-rule",filter:text,plane:admission};
  }
  if(kind!=="host"&&kind!=="service")return null;
  const choice=admission===undefined?"all":admission;
  if(!isSavedAdmission(choice)||(kind==="service"&&choice!=="all"))return null;
  if(!text&&choice==="all")return null;
  return kind==="host"
    ?{resource_type:"managed-host",filter:text,
      ...(choice!=="all"?{admission:choice}:{})}
    :{resource_type:"remote-service",filter:text};
}
export function readSavedView(value:unknown):
 |{route:"hosts",filter:string,admission?:Exclude<HostAdmission,"all">}
 |{route:"services",filter:string}
 |{route:"policies",filter:string,plane:PolicyPlane}
 |null{
  if(!value||typeof value!=="object"||Array.isArray(value))return null;
  const payload=(value as any).payload;
  if(!payload||typeof payload!=="object"||Array.isArray(payload))return null;
  if(typeof payload.filter!=="string"||payload.filter.length>120
    ||UNSAFE_VIEW_TEXT.test(payload.filter))return null;
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
  if(payload.resource_type==="access-rule"){
    // Policy Saved Views are an explicit, tiny presentation-only schema.
    // In particular a stored role, grant, expiry, sort or admission cannot
    // become either a display choice or an authorization shortcut.
    if(Object.keys(payload).some(key=>!["resource_type","filter","plane"].includes(key))
      ||!isPolicyPlane(payload.plane)
      ||(!payload.filter.trim()&&payload.plane==="all"))return null;
    return {route:"policies",filter:payload.filter,plane:payload.plane};
  }
  return null;
}

export function SavedViewsWorkspace({data,api,onNavigate,refresh,initialDraft}:{
  data:any,api:(path:string,init?:RequestInit)=>Promise<any>,initialDraft?:unknown,
  onNavigate?:(id:string,group?:string,context?:any)=>void,refresh:()=>void
}){
  const prepared=readSavedView({payload:initialDraft});
  const safeDraft=prepared?saveDraftForResource(
    prepared.route==="hosts"?"host":prepared.route==="services"?"service":"policy",
    prepared.filter,prepared.route==="hosts"?prepared.admission||"all":
      prepared.route==="services"?"all":prepared.plane):null;
  const [name,setName]=useState(""),[filter,setFilter]=useState(safeDraft?.filter||"");
  const [listQuery,setListQuery]=useState("");
  const [listSort,setListSort]=useState<SavedViewSortMode>("core");
  const [target,setTarget]=useState<StoredViewTarget>(safeDraft?.resource_type||"managed-host");
  const [admission,setAdmission]=useState<HostAdmission>(
    safeDraft?.resource_type==="managed-host"?safeDraft.admission||"all":"all");
  const [policyPlane,setPolicyPlane]=useState<PolicyPlane>(
    safeDraft?.resource_type==="access-rule"?safeDraft.plane:"all");
  const currentDraft=saveDraftForResource(
    target==="managed-host"?"host":target==="remote-service"?"service":"policy",
    filter,target==="managed-host"?admission:target==="remote-service"?"all":policyPlane);
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const [confirmReplace,setConfirmReplace]=useState(false);
  // Missing/malformed Core inventory is not a confirmed empty private list.
  // Core currently bounds the first operator-private page to 100 rows.
  const observedList=Array.isArray(data?.items)&&data.items.length<=100
    &&data.items.every((row:any)=>row!==null&&typeof row==="object"&&!Array.isArray(row));
  const rows=observedList?data.items:[];
  const visibleRows=filterObservedSavedViewList(rows,listQuery);
  const sortedVisibleRows=sortLoadedSavedViews(visibleRows.items,listSort);
  // Never let a local display filter hide an existing name collision.
  const duplicate=conflictingSavedViewName(rows,name);
  // Core currently returns at most 100 views, so an unobserved collision is possible.
  const incompleteNames=rows.length>=100;
  // All React hooks above are unconditional across Core success/error refreshes.
  if(!observedList)return <div className="dr-resource-workspace">
    <header className="dr-page-intro"><div>
      <p className="dr-eyebrow">Activity &amp; Health · Preferences</p>
      <h2>Saved Views</h2>
    </div></header>
    <p className="warning-box" role="alert">UNKNOWN · Private saved filters were not verified. Neither an empty list nor the absence of existing names was confirmed. Saving is unavailable until the Core list can be read.</p>
    <button type="button" className="secondary" onClick={refresh}>
      Refresh saved filters
    </button>
  </div>;
  async function save(e:React.FormEvent){
    e.preventDefault();
    if(busy||!validSavedViewName(name)||!currentDraft)return;
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
      <h2>Saved Views</h2><p className="muted">Reuse a named filter for observed Hosts, Remote Services or Policies. These are private display preferences, never access policies.</p></div></header>
    {error&&<p role="alert" className="warning-box">{error}</p>}
    {notice&&<p role="status" className="muted">{notice}</p>}
    {!!name&&!validSavedViewName(name)&&<p className="warning-box" role="alert">
      Enter a printable Saved View name of at most 80 characters, without control or direction-changing characters.
    </p>}
    <section className="card dr-list-card"><h3>Save a resource filter</h3>
      {safeDraft&&<p role="status" className="muted">Pre-filled from {safeDraft.resource_type==="managed-host"?"Servers & Agents":safeDraft.resource_type==="access-rule"?"Policies":"Published Services"}. {safeDraft.resource_type==="access-rule"?
        "Saved Policy plane: "+safeDraft.plane.toUpperCase()+".":
        "Saved admission state: "+(safeDraft.resource_type==="managed-host"&&safeDraft.admission?
          safeDraft.admission.replaceAll("_"," "):"All")+"."} Give this view a name and explicitly save it. Unloaded Core pages are not included.</p>}
      <form onSubmit={save}>
        <div className="toolbar">
          <label>View name <input value={name} maxLength={80} onChange={e=>{setName(e.target.value);setConfirmReplace(false);setNotice("")}} placeholder="Offline hosts" required/></label>
          <label>Resource type <select value={target} onChange={e=>{setTarget(e.target.value as StoredViewTarget);setAdmission("all");setPolicyPlane("all");setConfirmReplace(false)}}>
            <option value="managed-host">Servers &amp; Agents</option>
            <option value="remote-service">Published Services</option>
            <option value="access-rule">Policies</option>
          </select></label>
          <label>Filter text <input value={filter} maxLength={120} onChange={e=>{setFilter(e.target.value);setConfirmReplace(false)}} placeholder="offline" required={target==="remote-service"||(target==="managed-host"&&admission==="all")||(target==="access-rule"&&policyPlane==="all")}/></label>
          {target==="access-rule"&&<label>Policy plane <select value={policyPlane} onChange={e=>{setPolicyPlane(isPolicyPlane(e.target.value)?e.target.value:"all");setConfirmReplace(false)}}>
            <option value="all">All Policies</option>
            <option value="remote">Remote</option>
            <option value="internet">Internet</option>
            <option value="ai">AI</option>
          </select></label>}
          {target==="managed-host"&&<label>Filter Managed Host admission <select value={admission} onChange={e=>{setAdmission(e.target.value as HostAdmission);setConfirmReplace(false)}}>
            <option value="all">All admission states</option>
            <option value="PENDING_APPROVAL">Pending approval</option>
            <option value="APPROVED">Approved</option>
            <option value="QUARANTINED">Quarantined</option>
          </select></label>}
          <button type="submit" className="primary" disabled={busy||!validSavedViewName(name)||!currentDraft||!!(duplicate&&!confirmReplace)||incompleteNames&&!confirmReplace}>
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
      <div className="dr-form-actions" role="search" aria-label="Private saved filter name search">
        <label>Find my saved filters <input aria-label="Find my saved filters"
          value={listQuery} maxLength={80}
          onChange={e=>setListQuery(e.target.value)} placeholder="Search saved view names…"/></label>
        {listQuery&&<button type="button" className="secondary"
          onClick={()=>setListQuery("")}>Clear saved filter search</button>}
        <label>Sort loaded saved filters
          <select aria-label="Sort loaded private saved filters" value={listSort}
            onChange={e=>setListSort(isSavedViewSortMode(e.target.value)?e.target.value:"core")}>
            <option value="core">Core order (default)</option>
            <option value="updated_desc">Recently updated</option>
            <option value="updated_asc">Oldest updated</option>
          </select>
        </label>
        <span className="muted">Only names in the loaded private list are searched.
          This does not query other users or fetch missing Core pages.
          Sorting only rearranges loaded operator-private views.
          Missing/invalid Core updated timestamps remain UNKNOWN and sort last.</span>
      </div>
      {visibleRows.error&&<p role="alert" className="warning-box">{visibleRows.error}</p>}
      {rows.length?visibleRows.items.length?<div className="dr-table-scroll"><table className="dr-resource-table">
        <thead><tr><th>View</th><th>Resources</th><th>Filter</th><th>Updated</th><th>Action</th></tr></thead>
        <tbody>{sortedVisibleRows.map((item:any,i:number)=>{
          const parsed=readSavedView(item);
          const safeId=visibleViewText(item?.id,160);
          const safeName=visibleViewText(item?.name)||safeId||"Unnamed view";
          const updated=isObservedAbsoluteTime(item?.updated_at)?item.updated_at:"UNKNOWN";
          return <tr key={safeId||i}><td><strong>{safeName}</strong></td>
            <td>{parsed?(parsed.route==="hosts"?"Servers & Agents":parsed.route==="policies"?"Policies":"Published Services"):"Target unspecified"}</td>
            <td>{parsed?(parsed.filter||"No text")+(parsed.route==="hosts"&&parsed.admission?" · "+parsed.admission.replaceAll("_"," "):"")+(parsed.route==="policies"?" · "+parsed.plane.toUpperCase():""):"Not specified"}</td><td>{updated}</td>
            <td>{parsed?<button type="button" className="secondary"
              onClick={()=>parsed.route==="policies"
                ?onNavigate?.("policies","access",{savedFilter:parsed.filter,savedPolicyPlane:parsed.plane})
                :parsed.route==="hosts"
                  ?onNavigate?.(parsed.route,"connections",{savedFilter:parsed.filter,savedAdmission:parsed.admission||"all"})
                  :onNavigate?.(parsed.route,"connections",{savedFilter:parsed.filter,savedAdmission:"all"})}>
              Open saved filter →</button>:<span className="muted">
              Legacy/unsupported view; save a new named target</span>}</td>
          </tr>;
        })}</tbody>
      </table></div>:<p className="dr-empty-state">No matching loaded saved filters. Clear search to review the observed private list; other Core pages may not be loaded.</p>:<p className="dr-empty-state">No saved views yet. Save a named filter for an observed resource list.</p>}
      <p className="muted">A saved view only changes the visible text filter, optional Host admission display or selected Policy plane. It does not fetch missing inventory pages, permit a connection or create a Core configuration revision.</p>
    </section>
  </div>;
}
