import React,{useState} from "react";

/** A successful Core HTTP read does not make nested UI values renderable.
 * Keep only bounded scalar evidence. An invalid reason cannot establish PASS.
 */
const DOCTOR_ID=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;
const DOCTOR_BAD=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
function doctorText(value:unknown,fallback="UNKNOWN"):string{
  if(typeof value!=="string"||value.length>240||DOCTOR_BAD.test(value))
    return fallback;
  return value.trim()||fallback;
}
function doctorCount(value:unknown):number|string{
  return typeof value==="number"&&Number.isSafeInteger(value)&&value>=0?value:"UNKNOWN";
}
/** The Core Doctor is a read-only snapshot. Missing checks do not prove health. */
export function validatedDoctorEvidence(payload:unknown){
  if(!payload||typeof payload!=="object"||Array.isArray(payload))
    throw new Error("Core Doctor response unavailable. State is UNKNOWN.");
  const report=payload as Record<string,unknown>;
  if(report.read_only!==true||report.side_effect_free!==true
    ||!Array.isArray(report.checks)
    ||!report.health||typeof report.health!=="object"||Array.isArray(report.health)
    ||!report.attention||typeof report.attention!=="object"||Array.isArray(report.attention)
    ||report.checks.length>32
    ||report.checks.some((row:any)=>!row||typeof row!=="object"||Array.isArray(row)
      ||typeof row.id!=="string"||!DOCTOR_ID.test(row.id))
    ||new Set((report.checks as any[]).map(row=>row.id)).size!==report.checks.length)
    throw new Error("Core Doctor evidence is incomplete or not certified read-only. State is UNKNOWN.");
  const checks=(report.checks as any[]).map(row=>{
    const message=doctorText(row.message,"UNKNOWN · Core reason unavailable");
    const status=(message!=="UNKNOWN · Core reason unavailable")?row.status:null;
    return {
      id:row.id,
      plane:doctorText(row.plane,row.id),
      message,
      error:row.error===null||row.error===undefined||row.error===""
        ?"":doctorText(row.error,"UNKNOWN · Core error unavailable"),
      db_revision:doctorCount(row.db_revision),
      generation:doctorCount(row.generation),
      activated_at:row.activated_at===null||row.activated_at===undefined||row.activated_at===""
        ?"Not observed":doctorText(row.activated_at),
      observedState:status==="PASS"?"PASS":status==="ATTENTION"?"ATTENTION":"UNKNOWN",
    };
  });
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
