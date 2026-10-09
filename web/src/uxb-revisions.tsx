import React, {useEffect,useRef,useState} from "react";
import {isPartialCorePage,requireObservedMenuPayload,selectMenuPage,type MenuPagePosition} from "./uxb-menu-evidence";

/** A successful Core HTTP read still must be a genuine bounded revision page.
 * A structurally valid but wrong-family page is UNKNOWN, never an empty history. */
export function validateObservedRevisionPage(value:unknown):any{
  const fail=()=>{throw new Error("UNKNOWN · Core Change History returned an invalid or out-of-order revision page.");};
  if(!value||typeof value!=="object"||Array.isArray(value))return fail();
  const page=value as Record<string,any>;
  if(page.resource_type!=="revision"||page.limit!==100
    ||!Array.isArray(page.items)||page.items.length>100
    ||(page.next_cursor!==null&&(typeof page.next_cursor!=="string"||!page.next_cursor))
    ||(!page.items.length&&page.next_cursor!==null))return fail();
  let previous=Infinity;
  for(const row of page.items){
    if(!row||typeof row!=="object"||Array.isArray(row)
      ||!Number.isSafeInteger(row.revision)||row.revision<0
      ||row.revision>=previous
      ||["actor","command","created_at","summary"].some(key=>
        row[key]!==null&&row[key]!==undefined&&typeof row[key]!=="string"))return fail();
    previous=row.revision;
  }
  return value;
}

/** Activity & Health → Change History. A Core keyset page is never a total. */
export function RevisionHistory({initial,api}:{
  initial:any,api:(path:string)=>Promise<any>
}){
  // An inconsistent initial Core response must render UNKNOWN in this workspace,
  // rather than throw during React render and tear down the entire Web shell.
  let first:any=null,initialIssue="";
  try{first=validateObservedRevisionPage(requireObservedMenuPayload("revisions",initial))}
  catch(e:any){initialIssue=e.message||String(e)}
  const [page,setPage]=useState<any>(first);
  const [position,setPosition]=useState<MenuPagePosition>({cursor:"",history:[]});
  const [requested,setRequested]=useState<MenuPagePosition>({cursor:"",history:[]});
  const [loading,setLoading]=useState(false),[error,setError]=useState(initialIssue);
  const requestEpoch=useRef(0);
  useEffect(()=>{
    requestEpoch.current+=1;
    try{
      setPage(validateObservedRevisionPage(requireObservedMenuPayload("revisions",initial)));
      setError("");
    }catch(e:any){
      setPage(null);setError(e.message||String(e));
    }
    setPosition({cursor:"",history:[]});
    setRequested({cursor:"",history:[]});
    setLoading(false);
    return()=>{requestEpoch.current+=1};
  },[initial]);

  async function load(target:MenuPagePosition){
    const epoch=++requestEpoch.current;
    setRequested(target);setPage(null);setLoading(true);setError("");
    try{
      const url="/api/v1/revisions?limit=100"+
        (target.cursor?"&cursor="+encodeURIComponent(target.cursor):"");
      const observed=validateObservedRevisionPage(requireObservedMenuPayload("revisions",await api(url)));
      if(epoch!==requestEpoch.current)return;
      if(observed.resource_type&&observed.resource_type!=="revision")
        throw new Error("Core Change History returned another resource type. State is UNKNOWN.");
      setPage(observed);setPosition(target);
    }catch(e:any){
      if(epoch===requestEpoch.current)setError(e.message||String(e));
    }finally{
      if(epoch===requestEpoch.current)setLoading(false);
    }
  }

  const older=page&&selectMenuPage(position,page.next_cursor,"older");
  const newer=page&&selectMenuPage(position,page.next_cursor,"newer");
  const rows=Array.isArray(page?.items)?page.items:[];
  return <section className="dr-resource-workspace" aria-label="Change History">
    <header className="dr-page-intro">
      <div><p className="dr-eyebrow">Activity &amp; Health</p><h2>Change History</h2>
        <p className="muted">Core configuration revisions, newest first. These records are not live connection status.</p></div>
      <div className="dr-page-actions"><button type="button" className="secondary"
        disabled={loading} onClick={()=>load({cursor:"",history:[]})}>Refresh history</button></div>
    </header>
    {loading?<p className="warning-box" role="status">Loading Change History from Core…</p>:
      error?<div className="warning-box" role="alert"><strong>UNKNOWN · Core Change History unavailable</strong>
        <p>{error} No empty history was confirmed.</p><button type="button" className="secondary"
          onClick={()=>load(requested)}>Retry Core page →</button></div>:
      <section className="card dr-list-card">
        <p className="muted">Page {position.history.length+1} · {rows.length} observed revisions
          {isPartialCorePage(page)?" · older revisions available":""}</p>
        {rows.length?<div className="dr-table-scroll"><table className="dr-resource-table">
          <thead><tr><th>Revision</th><th>Time</th><th>Actor</th><th>Command</th><th>Summary</th></tr></thead>
          <tbody>{rows.map((item:any,i:number)=><tr key={item.revision??i}>
            <td>{item.revision??"—"}</td><td>{item.created_at||"UNKNOWN"}</td>
            <td>{item.actor||"UNKNOWN"}</td><td>{item.command||"—"}</td>
            <td>{item.summary||"—"}</td>
          </tr>)}</tbody></table></div>:
          <p className="dr-empty-state">No configuration revisions on this observed Core page.</p>}
        {(older||newer)&&<div className="toolbar" role="group" aria-label="Change History pagination">
          <button type="button" className="secondary" disabled={!newer} onClick={()=>{if(newer)load(newer)}}>
            ← Newer revisions</button>
          <button type="button" className="secondary" disabled={!older} onClick={()=>{if(older)load(older)}}>
            Older revisions →</button>
        </div>}
      </section>}
  </section>;
}
