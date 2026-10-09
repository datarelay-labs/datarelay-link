import React, {useEffect,useRef,useState} from "react";
import {isPartialCorePage,requireObservedMenuPayload,selectMenuPage,type MenuPagePosition} from "./uxb-menu-evidence";

/** Activity & Health → Change History. A Core keyset page is never a total. */
export function RevisionHistory({initial,api}:{
  initial:any,api:(path:string)=>Promise<any>
}){
  const first=requireObservedMenuPayload("revisions",initial);
  const [page,setPage]=useState<any>(first);
  const [position,setPosition]=useState<MenuPagePosition>({cursor:"",history:[]});
  const [requested,setRequested]=useState<MenuPagePosition>({cursor:"",history:[]});
  const [loading,setLoading]=useState(false),[error,setError]=useState("");
  const requestEpoch=useRef(0);
  useEffect(()=>{
    requestEpoch.current+=1;
    setPage(requireObservedMenuPayload("revisions",initial));
    setPosition({cursor:"",history:[]});
    setRequested({cursor:"",history:[]});
    setLoading(false);setError("");
    return()=>{requestEpoch.current+=1};
  },[initial]);

  async function load(target:MenuPagePosition){
    const epoch=++requestEpoch.current;
    setRequested(target);setPage(null);setLoading(true);setError("");
    try{
      const url="/api/v1/revisions?limit=100"+
        (target.cursor?"&cursor="+encodeURIComponent(target.cursor):"");
      const observed=requireObservedMenuPayload("revisions",await api(url));
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
