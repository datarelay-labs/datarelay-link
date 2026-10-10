/** Host-only view projection. Never render arbitrary Core object keys, auth tokens or credentials. */
export type HostDetailField={label:string,value:string};
export type HostDetailSection={title:string,fields:HostDetailField[]};
type HostFields=Record<string,unknown>;
const BANNED_TEXT=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g;
const TEXT_FIELDS={
  Identity:[["Host name","name"],["Hostname","hostname"],["Host ID","id"],
    ["Label","label"],["Description","description"]],
  "Trust & Admission":[["Management trust","trust_status"]],
  "Connectivity & Version":[["Agent lifecycle","agent_lifecycle_state"],
    ["Platform","agent_platform"],["Agent version","agent_version"],
    ["Last heartbeat","agent_heartbeat_at"],["Last activity","last_seen"]],
} as const;
function safeText(data:HostFields,key:string):string|null{
  const raw=data[key];
  if(typeof raw!=="string"&&typeof raw!=="number")return null;
  if(typeof raw==="number"&&!Number.isFinite(raw))return null;
  const text=String(raw).replace(BANNED_TEXT," ").trim();
  return text?text.slice(0,key==="description"?240:140):null;
}
function admission(data:HostFields):string{
  if(data.admission_state==="APPROVED")return "Approved";
  if(data.admission_state==="PENDING_APPROVAL")return "Pending approval";
  if(data.admission_state==="QUARANTINED")return "Quarantined";
  return "UNKNOWN";
}
function connectivity(data:HostFields):string{
  // The authoritative SQLite inventory projection may serialize BOOL as 1/0.
  if(data.connected===true||data.connected===1)return "Connected";
  if(data.connected===false||data.connected===0)return "Disconnected";
  return "UNKNOWN";
}
export function hostDetailSections(value:unknown):HostDetailSection[]{
  const data:HostFields=value!==null&&typeof value==="object"&&!Array.isArray(value)
    ?value as HostFields:{};
  const identity=TEXT_FIELDS.Identity
    .map(([label,key])=>({label,value:safeText(data,key)}))
    .filter((row):row is HostDetailField=>row.value!==null);
  const trust:HostDetailField[]=[
    {label:"Admission",value:admission(data)},
    {label:"Management trust",value:safeText(data,"trust_status")||"UNKNOWN"},
  ];
  const connection:HostDetailField[]=[
    {label:"Connection",value:connectivity(data)},
    ...TEXT_FIELDS["Connectivity & Version"].map(([label,key])=>({
      label,value:safeText(data,key)
    })).filter((row):row is HostDetailField=>row.value!==null),
  ];
  return [
    {title:"Identity",fields:identity.length?identity:[{label:"Host identity",value:"UNKNOWN"}]},
    {title:"Trust & Admission",fields:trust},
    {title:"Connectivity & Version",fields:connection},
  ];
}
