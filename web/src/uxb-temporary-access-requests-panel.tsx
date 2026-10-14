import React,{useEffect,useRef,useState} from "react";
import {
 observedTemporaryAccessRequest,observedTemporaryAccessRequestPage,
 temporaryAccessCanReview,temporaryAccessCanRevoke,temporaryAccessDurationLabel,
 type ObservedTemporaryAccessRequest
} from "./uxb-temporary-access-requests";

type Api=(path:string,init?:RequestInit)=>Promise<any>;
type Props={api:Api,operator:{id?:unknown,role?:unknown,username?:unknown}};
const durationOptions=[
 [300,"5 minutes"],[900,"15 minutes"],[1800,"30 minutes"],[3600,"1 hour"],
 [7200,"2 hours"],[14400,"4 hours"],[28800,"8 hours"],[86400,"24 hours"]
] as const;

function statusClass(status:string){
 return status==="APPROVED"?"success":status==="PENDING"?"warning":
  status==="REJECTED"||status==="REVOKED"?"critical":"neutral";
}

export function TemporaryAccessRequestsPanel({api,operator}:Props){
 const [page,setPage]=useState<{items:ObservedTemporaryAccessRequest[],next_cursor:string|null,limit:number}|null>(null);
 const [listState,setListState]=useState<"loading"|"ready"|"unknown">("loading");
 const [filter,setFilter]=useState("");
 const [plane,setPlane]=useState<"remote"|"internet"|"ai">("remote"),[rule,setRule]=useState("");
 const [purpose,setPurpose]=useState(""),[duration,setDuration]=useState(1800);
 const [selected,setSelected]=useState<ObservedTemporaryAccessRequest|null>(null);
 const [reviewDuration,setReviewDuration]=useState(900),[reviewReason,setReviewReason]=useState("");
 const [message,setMessage]=useState(""),[error,setError]=useState("");
 const [createBusy,setCreateBusy]=useState(false),[reviewBusy,setReviewBusy]=useState(false),[revokeBusy,setRevokeBusy]=useState(false);
 const createLock=useRef(false),reviewLock=useRef(false),revokeLock=useRef(false),readEpoch=useRef(0);
 const requestEligible=operator?.role==="Admin"||operator?.role==="Operator";

 async function load(){
  const epoch=++readEpoch.current;
  if(!requestEligible){setPage(null);setListState("ready");setError("");return}
  setListState("loading");setError("");
  try{
   const query=new URLSearchParams({limit:"50"});if(filter)query.set("status",filter);
   const result=observedTemporaryAccessRequestPage(await api("/api/v1/temporary-access-requests?"+query.toString()));
   if(epoch!==readEpoch.current)return;
   if(!result)throw new Error("Core Temporary Access request inventory is incomplete or unsafe.");
   setPage(result);setListState("ready");
   setSelected(current=>current?result.items.find(item=>item.id===current.id)||null:null);
  }catch(e:any){
   if(epoch!==readEpoch.current)return;
   setPage(null);setListState("unknown");setError("Temporary Access requests UNKNOWN: "+String(e?.message||e));
  }
 }
 useEffect(()=>{load();return()=>{readEpoch.current+=1}},[filter,requestEligible]);

 async function createRequest(){
  if(createLock.current||!rule.trim()||!purpose.trim())return;
  createLock.current=true;setCreateBusy(true);setError("");setMessage("");
  const intent={plane,rule:rule.trim(),purpose:purpose.trim(),duration_seconds:duration};
  try{
   const result=observedTemporaryAccessRequest(await api("/api/v1/temporary-access-requests",{
    method:"POST",body:JSON.stringify(intent)
   }));
   if(!result||result.status!=="PENDING"||result.plane!==plane||result.resource_ref!==intent.rule
      ||result.purpose!==intent.purpose||result.requested_duration_seconds!==duration)
    throw new Error("Core request receipt does not match submitted intent.");
   setMessage("Request created. No access was granted; a different authorized Admin must review it.");
   setRule("");setPurpose("");setSelected(result);
   await load();
  }catch(e:any){
   setError("Request outcome UNKNOWN. Re-reading authoritative requests before any retry. "+String(e?.message||e));
   await load();
  }finally{createLock.current=false;setCreateBusy(false)}
 }
 function chooseReview(row:ObservedTemporaryAccessRequest){
  setSelected(row);setReviewReason("");
  setReviewDuration(Math.min(row.requested_duration_seconds,3600));
  setMessage("");setError("");
 }
 async function review(decision:"approve"|"reject"){
  if(reviewLock.current||!selected||!temporaryAccessCanReview(selected,operator))return;
  reviewLock.current=true;setReviewBusy(true);setError("");setMessage("");
  const reviewed=selected;
  try{
   const body:any={decision,row_version:reviewed.row_version,reason:reviewReason.trim()};
   if(decision==="approve")body.approved_duration_seconds=reviewDuration;
   const result=observedTemporaryAccessRequest(await api(
    "/api/v1/temporary-access-requests/"+encodeURIComponent(reviewed.id)+"/review",
    {method:"POST",body:JSON.stringify(body)}
   ));
   if(!result||result.id!==reviewed.id
      ||result.row_version<=reviewed.row_version
      ||(decision==="approve"&&result.status!=="APPROVED")
      ||(decision==="reject"&&result.status!=="REJECTED"))
    throw new Error("Core review receipt is incomplete or does not match the selected request.");
   setMessage(decision==="approve"
    ?"Approved through Core. Access expires at "+String(result.approved_expires_at)+"."
    :"Request denied. No policy access was granted.");
   setSelected(result);setReviewReason("");
   await load();
  }catch(e:any){
   setSelected(null);
   setError("Review outcome UNKNOWN. Re-reading request and policy state before any retry. "+String(e?.message||e));
   await load();
  }finally{reviewLock.current=false;setReviewBusy(false)}
 }
 async function revoke(row:ObservedTemporaryAccessRequest){
  if(revokeLock.current||!temporaryAccessCanRevoke(row,operator))return;
  revokeLock.current=true;setRevokeBusy(true);setError("");setMessage("");
  try{
   const result=observedTemporaryAccessRequest(await api(
    "/api/v1/temporary-access-requests/"+encodeURIComponent(row.id)+"/revoke",
    {method:"POST",body:JSON.stringify({row_version:row.row_version})}
   ));
   if(!result||result.id!==row.id||result.status!=="REVOKED"||result.row_version<=row.row_version)
    throw new Error("Core revoke receipt is incomplete or does not match the selected request.");
   setMessage("Temporary Access revoked through Core. Existing sessions are not claimed terminated.");
   setSelected(result);await load();
  }catch(e:any){
   setSelected(null);
   setError("Revoke outcome UNKNOWN. Re-reading request and policy state before any retry. "+String(e?.message||e));
   await load();
  }finally{revokeLock.current=false;setRevokeBusy(false)}
 }
 const rows=page?.items||[];
 if(!requestEligible)return <section className="card dr-ui06" aria-labelledby="ui06-title-readonly">
  <div className="dr-section-head"><div><p className="dr-eyebrow">Two-person Temporary Access</p>
   <h3 id="ui06-title-readonly">Temporary Access requests</h3>
   <p className="muted">Read Only can inspect policy state but cannot request, review, or revoke Temporary Access.</p>
  </div></div>
 </section>;
 return <section className="card dr-ui06" aria-labelledby="ui06-title">
  <div className="dr-section-head"><div><p className="dr-eyebrow">Two-person Temporary Access</p>
   <h3 id="ui06-title">Request short-lived access</h3>
   <p className="muted">A request grants nothing by itself. A different authorized Admin reviews it, and Core owns the expiry.</p>
  </div><button type="button" className="secondary" onClick={load} disabled={listState==="loading"}>Refresh requests</button></div>
  {error&&<div className="error" role="alert">{error}</div>}
  {message&&<div className="notice" role="status" aria-live="polite">{message}</div>}
  <div className="dr-ui06-request-grid">
   <label className="dr-field"><span>Access plane</span><select value={plane} disabled={createBusy} onChange={e=>setPlane(e.target.value as any)}>
    <option value="remote">Remote</option><option value="internet">Internet</option><option value="ai">AI</option>
   </select></label>
   <label className="dr-field"><span>Existing WHITELIST rule</span><input value={rule} maxLength={160} disabled={createBusy}
    onChange={e=>setRule(e.target.value)} placeholder="Rule name"/></label>
   <label className="dr-field"><span>Requested duration</span><select value={duration} disabled={createBusy}
    onChange={e=>setDuration(Number(e.target.value))}>{durationOptions.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   <label className="dr-field dr-ui06-purpose"><span>Purpose</span><textarea value={purpose} maxLength={500} disabled={createBusy}
    onChange={e=>setPurpose(e.target.value)} placeholder="Why is this temporary access needed?"/></label>
  </div>
  <div className="dr-form-actions"><button type="button" className="primary" disabled={createBusy||!rule.trim()||!purpose.trim()}
   onClick={createRequest}>{createBusy?"Submitting request…":"Request temporary access"}</button></div>
  <div className="dr-ui06-list-head"><label className="dr-field"><span>Request status</span>
   <select value={filter} onChange={e=>setFilter(e.target.value)}>
    <option value="">All</option><option value="PENDING">Pending</option><option value="APPROVED">Approved</option>
    <option value="EXPIRED">Expired</option><option value="REJECTED">Rejected</option><option value="REVOKED">Revoked</option>
   </select></label><span className="muted">{listState==="ready"?rows.length+" loaded":"Core request state "+listState}</span></div>
  {listState==="loading"&&<p role="status" className="muted">Loading Core Temporary Access requests…</p>}
  {listState==="unknown"&&<p role="status" className="warning-box">No request list is treated as empty while Core state is UNKNOWN.</p>}
  {listState==="ready"&&!rows.length&&<div className="empty">No matching Temporary Access requests in this loaded Core page.</div>}
  {rows.length>0&&<div className="dr-ui06-requests" role="list">{rows.map(row=><article className="dr-ui06-request" role="listitem" key={row.id}>
   <header><div><strong>{row.resource_ref}</strong><small>{row.plane} · {row.resource_type}</small></div>
    <span className={"dr-wf-state "+statusClass(row.status)}>{row.status}</span></header>
   <p>{row.purpose}</p>
   <dl><div><dt>Requester</dt><dd>{row.requester_actor_id}</dd></div>
    <div><dt>Requested</dt><dd>{temporaryAccessDurationLabel(row.requested_duration_seconds)}</dd></div>
    <div><dt>Approved</dt><dd>{temporaryAccessDurationLabel(row.approved_duration_seconds)}</dd></div>
    <div><dt>Expires</dt><dd>{row.approved_expires_at||"Not approved"}</dd></div>
    <div><dt>Reviewer</dt><dd>{row.reviewer_actor_id||"Not reviewed"}</dd></div>
    <div><dt>Revision</dt><dd>{row.applied_revision??"No policy mutation"}</dd></div></dl>
   <details className="dr-technical-details dr-ui06-history"><summary>Request history</summary>
    <dl><div><dt>Created</dt><dd>{row.created_at}</dd></div>
     <div><dt>Reviewed at</dt><dd>{row.reviewed_at||"Not reviewed"}</dd></div>
     <div><dt>Review note</dt><dd>{row.decision_reason||"No review note"}</dd></div>
     <div><dt>Revoked at</dt><dd>{row.revoked_at||"Not revoked"}</dd></div>
     <div><dt>Revoked by</dt><dd>{row.revoked_by_actor_id||"Not revoked"}</dd></div>
     <div><dt>Revoke revision</dt><dd>{row.revoked_revision??"No revoke mutation"}</dd></div></dl>
   </details>
   <div className="dr-form-actions">
    {temporaryAccessCanReview(row,operator)&&<button type="button" className="secondary" onClick={()=>chooseReview(row)}>Review request →</button>}
    {temporaryAccessCanRevoke(row,operator)&&<button type="button" className="danger" disabled={revokeBusy} onClick={()=>revoke(row)}>Revoke early</button>}
   </div>
  </article>)}</div>}
  {selected&&temporaryAccessCanReview(selected,operator)&&<section className="warning-box dr-ui06-review" aria-label="Review Temporary Access request">
   <h4>Review request · {selected.resource_ref}</h4>
   <p><strong>Requester:</strong> {selected.requester_actor_id} · <strong>Purpose:</strong> {selected.purpose}</p>
   <p className="muted">You are a distinct Admin reviewer. Approval may shorten, never extend, the requested {temporaryAccessDurationLabel(selected.requested_duration_seconds)}.</p>
   <div className="dr-form-grid two">
    <label className="dr-field"><span>Approved duration</span><select value={reviewDuration} disabled={reviewBusy}
      onChange={e=>setReviewDuration(Number(e.target.value))}>
      {durationOptions.filter(([value])=>value<=selected.requested_duration_seconds).map(([value,label])=><option key={value} value={value}>{label}</option>)}
    </select></label>
    <label className="dr-field"><span>Review reason</span><input value={reviewReason} maxLength={500} disabled={reviewBusy}
      onChange={e=>setReviewReason(e.target.value)} placeholder="Optional bounded review note"/></label>
   </div>
   <div className="dr-form-actions"><button type="button" className="primary" disabled={reviewBusy} onClick={()=>review("approve")}>Approve request</button>
    <button type="button" className="danger" disabled={reviewBusy} onClick={()=>review("reject")}>Deny request</button>
    <button type="button" className="secondary" disabled={reviewBusy} onClick={()=>setSelected(null)}>Cancel review</button></div>
  </section>}
  <details className="dr-technical-details"><summary>Technical details · two-person authority</summary>
   <p>Core binds each request to one existing WHITELIST rule, requester, revision and Server. Review uses a different Admin principal. Browser timers never grant or revoke access.</p>
   <p>Approved access is still the canonical Temporary Access expiry. Early revoke narrows expiry; it never clears expiry or claims existing sessions were terminated.</p>
  </details>
 </section>;
}
