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
function connectivity(data:HostFields):"Connected"|"Disconnected"|"UNKNOWN"{
  // The authoritative SQLite inventory projection may serialize BOOL as 1/0.
  if(data.connected===true||data.connected===1)return "Connected";
  if(data.connected===false||data.connected===0)return "Disconnected";
  return "UNKNOWN";
}
// Shared status semantics for both the Host inventory table and detail drawer.
// A lifecycle string or arbitrary truthy value is NOT a live connection fact.
/** A Host list row distinguishes observed Core facts from missing evidence.
 * agent_heartbeat_at is connectivity telemetry, never an alias for last_seen.
 */
/** Safe presentation identity shared by Host table and detail headings. */
export function hostVisibleIdentity(value:unknown):{primary:string,secondary:string}{
  const data:HostFields=value!==null&&typeof value==="object"&&!Array.isArray(value)
    ?value as HostFields:{};
  const ident=safeText(data,"id")||"UNKNOWN";
  return {
    primary:safeText(data,"name")||ident,
    secondary:safeText(data,"hostname")||ident,
  };
}
export function hostInventoryFacts(value:unknown):{
  trust:"Trusted"|"Revoked"|"Untrusted"|"UNKNOWN";
  platform:string;version:string;lastActivity:string;
}{
  const data:HostFields=value!==null&&typeof value==="object"&&!Array.isArray(value)
    ?value as HostFields:{};
  const trust=data.trust_status==="trusted"?"Trusted"
    :data.trust_status==="revoked"?"Revoked"
    :data.trust_status==="untrusted"?"Untrusted":"UNKNOWN";
  const observedString=(key:string):string=>
    typeof data[key]==="string" ? (safeText(data,key)||"UNKNOWN") : "UNKNOWN";
  return {
    trust,platform:observedString("agent_platform"),
    version:observedString("agent_version"),
    lastActivity:observedString("last_seen"),
  };
}
export function hostConnectionState(value:unknown):"Connected"|"Disconnected"|"UNKNOWN"{
  const data:HostFields=value!==null&&typeof value==="object"&&!Array.isArray(value)
    ?value as HostFields:{};
  return connectivity(data);
}
export function hostDetailSections(value:unknown):HostDetailSection[]{
  const data:HostFields=value!==null&&typeof value==="object"&&!Array.isArray(value)
    ?value as HostFields:{};
  const identity=TEXT_FIELDS.Identity
    .map(([label,key])=>({label,value:safeText(data,key)}))
    .filter((row):row is HostDetailField=>row.value!==null);
  const trust:HostDetailField[]=[
    {label:"Admission",value:admission(data)},
    {label:"Management trust",value:hostInventoryFacts(data).trust},
  ];
  const connection:HostDetailField[]=[
    {label:"Connection",value:hostConnectionState(data)},
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
