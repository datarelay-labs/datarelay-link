import React,{useState} from "react";

/** A version mismatch is not proof of stale binaries, an active Agent or a
 * successful update. Unknown Server version makes *all* comparisons unknown. */
export type VersionState="SAME"|"DIFFERENT"|"UNKNOWN";
const UNSAFE_TEXT=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const validCoreText=(value:unknown):value is string=>
  typeof value==="string"&&value.length<=160&&!UNSAFE_TEXT.test(value);
/** Core inventory metadata is untrusted UI input: only known, bounded strings
 * may become React children or searchable display fields. */
function observedDisplay(value:unknown,missing="UNKNOWN"):string{
  if(value===null||value===undefined||value==="")return missing;
  if(!validCoreText(value)||!value.trim())return "UNKNOWN";
  return value.trim();
}
export function observedVersionState(server:unknown,agent:unknown):VersionState{
  const good=(x:unknown)=>validCoreText(x)&&!!x.trim()&&x.trim().toLowerCase()!=="unknown";
  if(!good(server)||!good(agent))return "UNKNOWN";
  return (server as string).trim()===(agent as string).trim()?"SAME":"DIFFERENT";
}
export function validatedVersionInventory(payload:unknown){
  if(!payload||typeof payload!=="object"||Array.isArray(payload))
    throw new Error("Core Agent version inventory is unavailable. State is UNKNOWN.");
  const data=payload as Record<string,unknown>;
  if(!validCoreText(data.server_version)||!Array.isArray(data.hosts)
    ||!Number.isSafeInteger(data.limit)||Number(data.limit)<1
    ||data.hosts.length>Number(data.limit)
    ||!Number.isSafeInteger(data.drift_count)||Number(data.drift_count)<0
    ||!Number.isSafeInteger(data.unknown_count)||Number(data.unknown_count)<0
    ||data.hosts.some((x:any)=>!x||typeof x!=="object"||Array.isArray(x)
      ||!validCoreText(x.id)||!x.id.trim()||!validCoreText(x.version)))
    throw new Error("Core Agent version inventory has missing or malformed evidence. State is UNKNOWN.");
  // The Core read model derives both counts from these same bounded rows.
  // Contradictory counts, duplicated identities or a drift count without a
  // known Server cannot support a healthy/empty version comparison.
  const ids=(data.hosts as any[]).map(host=>host.id as string);
  if(new Set(ids).size!==ids.length
    ||Number(data.drift_count)+Number(data.unknown_count)>ids.length
    ||(observedVersionState(data.server_version,data.server_version)==="UNKNOWN" &&
      Number(data.drift_count)!==0))
    throw new Error("Core Agent version summary contradicts observed rows. State is UNKNOWN.");
  const hosts=(data.hosts as any[]).map(host=>({
    id:host.id,version:host.version,
    name:observedDisplay(host.name,host.id),
    platform:observedDisplay(host.platform),
    lifecycle:observedDisplay(host.lifecycle),
    heartbeat:observedDisplay(host.heartbeat,"Not observed"),
    comparison:observedVersionState(data.server_version,host.version),
  }));
  const hasKnownServer=observedVersionState(data.server_version,data.server_version)!=="UNKNOWN";
  // Core derives both aggregates from this same limited Host snapshot.
  // With an observed Server version, a missing/underreported drift or unknown
  // count is as misleading as one exceeding the page bound.
  if(hasKnownServer&&(hosts.filter(host=>host.comparison==="DIFFERENT").length!==data.drift_count
    ||hosts.filter(host=>host.comparison==="UNKNOWN").length!==data.unknown_count))
    throw new Error("Core Agent version summary contradicts observed rows. State is UNKNOWN.");
  return {
    serverVersion:data.server_version as string,hosts,limit:data.limit as number,
    hasKnownServer,
    maybeTruncated:hosts.length>=Number(data.limit),
  };
}

export function AgentVersionDrift({data,onNavigate}:{
  data:unknown,onNavigate?:(id:string,group?:string)=>void
}){
  const [filter,setFilter]=useState("all");
  const [query,setQuery]=useState("");
  // A syntactically successful Core HTTP response can still contradict its
  // bounded Host inventory. Render UNKNOWN rather than crash the Web shell.
  // Hooks stay unconditional when a later refresh changes validity.
  let inventory:ReturnType<typeof validatedVersionInventory>|null=null;
  try{inventory=validatedVersionInventory(data)}catch{ /* no untrusted Core error to UI */ }
  if(!inventory)return <section className="dr-resource-workspace"
      aria-label="Agent version drift">
    <header className="dr-page-intro"><div>
      <p className="dr-eyebrow">Activity &amp; Health · Advanced</p>
      <h2>Agent version drift</h2></div></header>
    <p className="warning-box" role="alert">UNKNOWN · Core Agent version inventory could not be validated. No Agent count, version comparison, fleet health or successful upgrade was observed.</p>
    <button className="secondary" type="button"
      onClick={()=>onNavigate?.("hosts","connections")}>View Servers &amp; Agents →</button>
  </section>;
  const same=inventory.hosts.filter(row=>row.comparison==="SAME").length;
  const different=inventory.hosts.filter(row=>row.comparison==="DIFFERENT").length;
  const unknown=inventory.hosts.filter(row=>row.comparison==="UNKNOWN").length;
  const visible=inventory.hosts.filter(row=>
    (filter==="all"||row.comparison===filter)
    &&(!query.trim()||[row.name,row.id,row.version,row.platform,row.lifecycle].some(
      value=>String(value??"").toLowerCase().includes(query.trim().toLowerCase()))));
  return <div className="dr-resource-workspace">
    <header className="dr-page-intro"><div><p className="dr-eyebrow">Activity &amp; Health · Advanced</p>
      <h2>Agent version drift</h2><p className="muted">Compare last observed Agent versions with the installed Server version. An unknown or different version does not prove network access or an update failure.</p>
      </div><div className="dr-page-actions"><button type="button" className="secondary"
        onClick={()=>onNavigate?.("hosts","connections")}>View Servers &amp; Agents →</button></div></header>
    <section className="grid" aria-label="Version comparison summary">
      <div className="card"><strong>Server version</strong><p>{inventory.hasKnownServer?inventory.serverVersion:"UNKNOWN"}</p></div>
      <div className="card"><strong>Different versions</strong><p>{inventory.hasKnownServer?different:"UNKNOWN"}</p></div>
      <div className="card"><strong>Unknown comparisons</strong><p>{unknown}</p></div>
      <div className="card"><strong>Matching versions</strong><p>{inventory.hasKnownServer?same:"UNKNOWN"}</p></div>
    </section>
    {!inventory.hasKnownServer&&<p role="alert" className="warning-box">UNKNOWN · Installed Server version was not observed. No Agent can be classified as matching or different; do not interpret the Core drift count as zero problems.</p>}
    {inventory.maybeTruncated&&<p role="status" className="dr-uxb-catalog-page-notice">Partial Core version snapshot possible · {inventory.hosts.length} rows reached the API bound. Filters only inspect observed rows; this is not the total managed fleet.</p>}
    <section className="card dr-list-card"><div className="dr-list-toolbar">
      <span>{visible.length} displayed · {inventory.hosts.length} observed Agent records</span>
      <select aria-label="Filter observed Agent version status" value={filter} onChange={e=>setFilter(e.target.value)}>
        <option value="all">All comparison states</option>
        <option value="DIFFERENT" disabled={!inventory.hasKnownServer}>Different</option>
        <option value="SAME" disabled={!inventory.hasKnownServer}>Matching</option>
        <option value="UNKNOWN">Unknown</option>
      </select>
      <input aria-label="Find observed Agent" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Filter observed Agents…"/>
    </div>
    {!visible.length?<p className="dr-empty-state">{inventory.hosts.length?
      "No matches in the currently observed Core version snapshot.":
      "No managed Agents in this observed Core version snapshot."}</p>:
    <div className="dr-table-scroll"><table className="dr-resource-table">
      <thead><tr><th>Agent</th><th>Platform</th><th>Observed version</th><th>Comparison</th><th>Lifecycle</th><th>Last heartbeat</th></tr></thead>
      <tbody>{visible.map(row=><tr key={row.id}><td><strong>{row.name||row.id}</strong><small>{row.id}</small></td>
        <td>{row.platform||"UNKNOWN"}</td><td>{row.version||"UNKNOWN"}</td>
        <td><span className={row.comparison==="SAME"?"dr-state active":"dr-state"}><i/>{row.comparison==="SAME"?"Matching":row.comparison==="DIFFERENT"?"Different":"UNKNOWN"}</span></td>
        <td>{row.lifecycle||"UNKNOWN"}</td><td>{row.heartbeat||"Not observed"}</td>
      </tr>)}</tbody>
    </table></div>}
    <p className="muted">Version comparison is a previously recorded inventory snapshot; use System Health and Jobs for separate operational evidence. No update or connectivity change is performed here.</p>
    </section>
  </div>;
}
