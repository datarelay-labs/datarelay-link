import React,{useState} from "react";

export type StoredViewTarget="managed-host"|"remote-service";
// A saved view is a personal display preference, never an access rule.
export function saveDraftForResource(kind:unknown,filter:unknown):{resource_type:StoredViewTarget,filter:string}|null{
  if((kind!=="host"&&kind!=="service")||typeof filter!=="string")return null;
  const text=filter.trim();
  if(!text||text.length>120)return null;
  return {resource_type:kind==="host"?"managed-host":"remote-service",filter:text};
}
export function readSavedView(value:unknown):{route:"hosts"|"services",filter:string}|null{
  if(!value||typeof value!=="object"||Array.isArray(value))return null;
  const payload=(value as any).payload;
  if(!payload||typeof payload!=="object"||Array.isArray(payload))return null;
  if(typeof payload.filter!=="string"||payload.filter.length>120)return null;
  if(payload.resource_type==="managed-host")return {route:"hosts",filter:payload.filter};
  if(payload.resource_type==="remote-service")return {route:"services",filter:payload.filter};
  return null;
}

export function SavedViewsWorkspace({data,api,onNavigate,refresh,initialDraft}:{
  data:any,api:(path:string,init?:RequestInit)=>Promise<any>,initialDraft?:unknown,
  onNavigate?:(id:string,group?:string,context?:any)=>void,refresh:()=>void
}){
  const prepared=readSavedView({payload:initialDraft});
  const safeDraft=prepared?saveDraftForResource(prepared.route==="hosts"?"host":"service",prepared.filter):null;
  const [name,setName]=useState(""),[filter,setFilter]=useState(safeDraft?.filter||"");
  const [target,setTarget]=useState<StoredViewTarget>(safeDraft?.resource_type||"managed-host");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  async function save(e:React.FormEvent){
    e.preventDefault();
    if(busy||!name.trim()||!filter.trim())return;
    setError("");setNotice("");setBusy(true);
    try{
      await api("/api/v1/saved-views",{method:"POST",
        body:JSON.stringify({name:name.trim(),payload:{resource_type:target,filter:filter.trim()}})});
      setName("");setNotice("Private filter saved. Check My saved filters for the latest list.");refresh();
    }catch(e:any){setError(e.message||String(e))}
    finally{setBusy(false)}
  }
  const rows=Array.isArray(data?.items)?data.items:[];
  return <div className="dr-resource-workspace">
    <header className="dr-page-intro"><div><p className="dr-eyebrow">Activity &amp; Health · Preferences</p>
      <h2>Saved Views</h2><p className="muted">Reuse a named filter for observed Hosts or Remote Services. These are private display preferences, never access policies.</p></div></header>
    {error&&<p role="alert" className="warning-box">{error}</p>}
    {notice&&<p role="status" className="muted">{notice}</p>}
    <section className="card dr-list-card"><h3>Save a resource filter</h3>
      {safeDraft&&<p role="status" className="muted">Pre-filled from {safeDraft.resource_type==="managed-host"?"Servers & Agents":"Published Services"}. Give this text filter a name, then explicitly save it. Other list controls and unpublished Core pages are not included.</p>}
      <form onSubmit={save}>
        <div className="toolbar">
          <label>View name <input value={name} maxLength={80} onChange={e=>setName(e.target.value)} placeholder="Offline hosts" required/></label>
          <label>Resource type <select value={target} onChange={e=>setTarget(e.target.value as StoredViewTarget)}>
            <option value="managed-host">Servers &amp; Agents</option>
            <option value="remote-service">Published Services</option>
          </select></label>
          <label>Filter text <input value={filter} maxLength={120} onChange={e=>setFilter(e.target.value)} placeholder="offline" required/></label>
          <button type="submit" className="primary" disabled={busy||!name.trim()||!filter.trim()}>
            {busy?"Saving…":"Save filter"}</button>
        </div>
      </form>
    </section>
    <section className="card dr-list-card"><h3>My saved filters</h3>
      {rows.length?<div className="dr-table-scroll"><table className="dr-resource-table">
        <thead><tr><th>View</th><th>Resources</th><th>Filter</th><th>Updated</th><th>Action</th></tr></thead>
        <tbody>{rows.map((item:any,i:number)=>{
          const parsed=readSavedView(item);
          return <tr key={item.id||i}><td><strong>{item.name||item.id||"Unnamed view"}</strong></td>
            <td>{parsed?(parsed.route==="hosts"?"Servers & Agents":"Published Services"):"Target unspecified"}</td>
            <td>{parsed?.filter||"Not specified"}</td><td>{item.updated_at||"UNKNOWN"}</td>
            <td>{parsed?<button type="button" className="secondary"
              onClick={()=>onNavigate?.(parsed.route,"connections",{savedFilter:parsed.filter})}>
              Open saved filter →</button>:<span className="muted">
              Legacy/unsupported view; save a new named target</span>}</td>
          </tr>;
        })}</tbody>
      </table></div>:<p className="dr-empty-state">No saved views yet. Save a named filter for an observed resource list.</p>}
      <p className="muted">A saved view only changes the visible filter. It does not fetch missing inventory pages, permit a connection or create a Core configuration revision.</p>
    </section>
  </div>;
}
