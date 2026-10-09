import React,{useState} from "react";

/** The Core Doctor is a read-only snapshot. Missing checks do not prove health. */
export function validatedDoctorEvidence(payload:unknown){
  if(!payload||typeof payload!=="object"||Array.isArray(payload))
    throw new Error("Core Doctor response unavailable. State is UNKNOWN.");
  const report=payload as Record<string,unknown>;
  if(report.read_only!==true||report.side_effect_free!==true
    ||!Array.isArray(report.checks)
    ||!report.health||typeof report.health!=="object"||Array.isArray(report.health)
    ||!report.attention||typeof report.attention!=="object"||Array.isArray(report.attention)
    ||report.checks.some((row:any)=>!row||typeof row!=="object"||Array.isArray(row)
      ||typeof row.id!=="string"||!row.id))
    throw new Error("Core Doctor evidence is incomplete or not certified read-only. State is UNKNOWN.");
  const checks=(report.checks as any[]).map(row=>({
    ...row,
    observedState:row.status==="PASS"?"PASS":
      row.status==="ATTENTION"?"ATTENTION":"UNKNOWN",
  }));
  const attention=report.attention as Record<string,unknown>;
  return {
    checks,
    totalObserved:checks.length,
    passCount:checks.filter(x=>x.observedState==="PASS").length,
    attentionCount:checks.filter(x=>x.observedState==="ATTENTION").length,
    unknownCount:checks.filter(x=>x.observedState==="UNKNOWN").length,
    coreAttention:typeof attention.count==="number"&&Number.isSafeInteger(attention.count)
      &&attention.count>=0?attention.count:null,
  };
}

export function CoreDoctorWorkspace({data,onNavigate}:{
 data:unknown,onNavigate?:(id:string,group?:string)=>void
}){
  const evidence=validatedDoctorEvidence(data);
  const [filter,setFilter]=useState("all"),[query,setQuery]=useState("");
  const visible=evidence.checks.filter(row=>(filter==="all"||row.observedState===filter)
    &&(!query.trim()||[row.id,row.plane,row.message,row.error].some(v=>
      String(v??"").toLowerCase().includes(query.trim().toLowerCase()))));
  return <div className="dr-resource-workspace">
    <header className="dr-page-intro"><div>
      <p className="dr-eyebrow">Activity &amp; Health · Troubleshooting</p>
      <h2>Core Doctor</h2><p className="muted">Read-only runtime generation checks. This snapshot does not confirm live Agent reachability or permitted traffic.</p>
    </div><div className="dr-page-actions">
      <button type="button" className="secondary" onClick={()=>onNavigate?.("health","activity")}>System Health →</button>
      <button type="button" className="secondary" onClick={()=>onNavigate?.("jobs","activity")}>Management Jobs →</button>
    </div></header>
    <section className="grid" aria-label="Observed Doctor checks">
      <div className="card"><strong>PASS checks</strong><p>{evidence.passCount}</p></div>
      <div className="card"><strong>ATTENTION checks</strong><p>{evidence.attentionCount}</p></div>
      <div className="card"><strong>UNKNOWN checks</strong><p>{evidence.unknownCount}</p></div>
      <div className="card"><strong>Other Core attention</strong><p>{evidence.coreAttention??"UNKNOWN"}</p></div>
    </section>
    {!evidence.totalObserved&&<p className="warning-box" role="alert">UNKNOWN · No runtime generation checks were observed. An empty Doctor report is not proof of healthy access or policy deployment. Inspect System Health.</p>}
    {evidence.unknownCount>0&&<p className="warning-box" role="status">UNKNOWN · Some Core check states could not be classified. Inspect details and System Health before acting.</p>}
    <section className="card dr-list-card"><div className="dr-list-toolbar">
      <span>{visible.length} displayed · {evidence.totalObserved} observed checks</span>
      <select value={filter} onChange={e=>setFilter(e.target.value)} aria-label="Filter Core Doctor state">
        <option value="all">All observed checks</option>
        <option value="PASS">PASS</option><option value="ATTENTION">ATTENTION</option>
        <option value="UNKNOWN">UNKNOWN</option>
      </select>
      <input value={query} onChange={e=>setQuery(e.target.value)} aria-label="Filter Doctor checks"
        placeholder="Find plane or check…"/>
    </div>
    {visible.length?<div className="dr-table-scroll"><table className="dr-resource-table">
      <thead><tr><th>Check</th><th>State</th><th>Observed reason</th><th>DB revision</th><th>Generation</th><th>Last activated</th></tr></thead>
      <tbody>{visible.map((row:any)=><tr key={row.id}>
        <td><strong>{row.plane||row.id}</strong><small>{row.id}</small></td>
        <td><span className={row.observedState==="PASS"?"dr-state active":"dr-state"}><i/>{row.observedState}</span></td>
        <td>{row.message||"No detail observed"}{row.error&&<small className="dr-health-error">{row.error}</small>}</td>
        <td>{row.db_revision??"UNKNOWN"}</td><td>{row.generation??"UNKNOWN"}</td>
        <td>{row.activated_at||"Not observed"}</td>
      </tr>)}</tbody></table></div>:
      <p className="dr-empty-state">{evidence.totalObserved?
        "No checks match these filters; change the filter to inspect observed Core evidence.":
        "There are no observed runtime generation check records."}</p>}
    <p className="muted">Core Doctor does not change access policy, enroll Agents or restart services. For live troubleshooting, use System Health and the approved Agent diagnostics workflow.</p>
    </section>
  </div>;
}
