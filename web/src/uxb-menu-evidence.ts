import {isObservedAbsoluteTime} from "./uxb-integrations-state";

/** UXB-06F: a successful HTTP response is not automatically a valid, empty Core page.
 * Each listed menu must receive its canonical collection before showing "No results".
 * This changes Web presentation only; the Server/Core remains the authority. */
const collectionPages:Record<string,string>={
  hosts:"Servers & Agents",
  services:"Published services",
  policies:"Access rules",
  enrollments:"Agent enrollments",
  hygiene:"Access hygiene",
  jobs:"Management Jobs",
  audit:"Activity log",
  users:"Web Users",
  "service-accounts":"Service Accounts",
  webhooks:"Signed Event Webhooks",
  revisions:"Change history",
  views:"Saved views",
};

/** A page with a Core cursor is not a complete inventory; local filters only
 * check loaded rows and may not find the rest. */
export function isPartialCorePage(payload:any):boolean{
  return typeof payload?.next_cursor==="string"&&payload.next_cursor.length>0;
}

/** SQLite policy rows carry enabled=0/1, but a missing or malformed field
 * is not evidence of Disabled. This is presentation only; Core is authority.
 */
export function policyStateLabel(value:unknown):"Enabled"|"Disabled"|"UNKNOWN"{
  if(value===true||value===1)return "Enabled";
  if(value===false||value===0)return "Disabled";
  return "UNKNOWN";
}
/** An explicit Core NULL expiry means no expiry; an absent/invalid field
 * means the Web has no reliable expiry evidence.
 */
export function policyExpiryLabel(item:unknown):string{
  if(!item||typeof item!=="object"||Array.isArray(item))return "UNKNOWN";
  const row=item as Record<string,unknown>;
  if(!Object.prototype.hasOwnProperty.call(row,"expires_at"))return "UNKNOWN";
  if(row.expires_at===null)return "Never";
  return typeof row.expires_at==="string"&&!!row.expires_at.trim()
    &&row.expires_at.length<=160?row.expires_at:"UNKNOWN";
}

/** UI-06 distinction: existing Temporary Access is a *same-actor* Core
 * policy-expiry Change Plan, NOT a requester/reviewer access request.
 * Return only a revision proven against that exact approved plan.
 */
export function requireObservedTemporaryAccessApplyForPlan(
 input:unknown,plan:unknown
):{revision:number}{
 const error=()=>{throw new Error("UNKNOWN · Core Temporary Access Apply receipt is unverified. Inspect the policy and Change History before any retry.");};
 const record=(x:unknown):x is Record<string,unknown>=>
   !!x&&typeof x==="object"&&!Array.isArray(x);
 if(!record(input)||!record(plan))return error();
 const row=input,preview=plan;
 const operation=preview.operation,resourceType=preview.resource_type;
 if(typeof preview.change_plan_id!=="string"||!/^cp_[A-Za-z0-9_-]{16,128}$/.test(preview.change_plan_id)
   ||!["temporary-access.set","temporary-access.clear"].includes(String(operation))
   ||!["remote-access-rule","internet-access-rule","ai-access-rule"].includes(String(resourceType))
   ||typeof preview.resource_ref!=="string"||!preview.resource_ref.trim()
   ||preview.resource_ref.length>160
   ||!Number.isSafeInteger(preview.expected_revision)||Number(preview.expected_revision)<0
   ||preview.no_change!==false||preview.confirmation_class!=="APPLY"
   ||!isObservedAbsoluteTime(preview.valid_until)
   ||Date.parse(preview.valid_until)<=Date.now()
   ||operation==="temporary-access.set"&&
      !isObservedAbsoluteTime(preview.desired_expires_at)
   ||operation==="temporary-access.clear"&&preview.desired_expires_at!==null)return error();
 if(row.status!=="APPLIED"||row.operation!==operation||row.resource_type!==resourceType
   ||row.resource_ref!==preview.resource_ref
   ||row.expires_at!==preview.desired_expires_at
   ||!Number.isSafeInteger(row.revision)
   ||Number(row.revision)<=Number(preview.expected_revision))return error();
 return {revision:row.revision as number};
}

/** Read-only, bounded projection of the exact Core incident preview.
 * Core may resolve a typed Service/Host alias to its canonical ID; require
 * either that immutable ID or the canonical display name to match the
 * request, never an arbitrary unrelated resource.
 */
export type ObservedEmergencyCutoffPreview={
 change_plan_id:string,valid_until:string,operation_class:"INCIDENT_CHANGE",
 resource_type:"emergency-cutoff",resource_ref:string,
 operation:"emergency-cutoff.apply"|"emergency-cutoff.clear",
 confirmation_class:"CONFIRM CUTOFF",expected_revision:number,
 scope_kind:string,scope_ref:string,scope_display:string,
 currently_active:boolean,desired_active:boolean,
 active_sessions_terminated:false,no_change:false,
 impact:{requires_confirmation:true,access_broadened:boolean,
   access_narrowed:boolean,warning:string}
};
export function observedEmergencyCutoffPreviewForIntent(
 input:unknown,plane:unknown,kind:unknown,selector:unknown,action:unknown,
 now:number=Date.now()
):ObservedEmergencyCutoffPreview|null{
 const record=(v:unknown):v is Record<string,unknown>=>
   !!v&&typeof v==="object"&&!Array.isArray(v);
 const safe=(v:unknown,max=160):v is string=>
   typeof v==="string"&&!!v.trim()&&v.length<=max
     &&!/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(v);
 if(!record(input)||typeof plane!=="string"
   ||!["remote","internet","ai"].includes(plane)
   ||typeof kind!=="string"||typeof selector!=="string"
   ||!["apply","clear"].includes(String(action))||!Number.isFinite(now))return null;
 const allowed=plane==="remote"?["plane","remote-service"]:
   plane==="internet"?["plane","managed-host"]:["plane","ai-identity"];
 if(!allowed.includes(kind))return null;
 const data=input,ref=data.scope_ref,display=data.scope_display,
   impact=data.impact,operation="emergency-cutoff."+action;
 if(typeof data.change_plan_id!=="string"
   ||!/^cp_[A-Za-z0-9_-]{16,128}$/.test(data.change_plan_id)
   ||data.operation_class!=="INCIDENT_CHANGE"
   ||data.resource_type!=="emergency-cutoff"
   ||data.operation!==operation||data.scope_kind!==kind
   ||typeof ref!=="string"||ref.length>160
   ||/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(ref)
   ||(kind==="plane"?ref!==""||selector.trim()!=="":!safe(ref))
   ||!safe(display)
   ||(kind!=="plane"&&![ref.toLowerCase(),display.toLowerCase()]
     .includes(selector.trim().toLowerCase()))
   ||data.resource_ref!==(kind==="plane"?plane:kind+":"+ref)
   ||data.desired_active!==(action==="apply")
   ||typeof data.currently_active!=="boolean"
   ||data.active_sessions_terminated!==false||data.no_change!==false
   ||data.confirmation_class!=="CONFIRM CUTOFF"
   ||!Number.isSafeInteger(data.expected_revision)||Number(data.expected_revision)<0
   ||!isObservedAbsoluteTime(data.valid_until)
   ||Date.parse(data.valid_until)<=now
   ||!record(impact)||impact.requires_confirmation!==true
   ||impact.access_broadened!==(action==="clear")
   ||impact.access_narrowed!==(action==="apply")
   ||!safe(impact.warning,512))return null;
 return {
   change_plan_id:data.change_plan_id,valid_until:data.valid_until as string,
   operation_class:"INCIDENT_CHANGE",resource_type:"emergency-cutoff",
   resource_ref:data.resource_ref as string,operation:operation as ObservedEmergencyCutoffPreview["operation"],
   confirmation_class:"CONFIRM CUTOFF",expected_revision:data.expected_revision as number,
   scope_kind:kind,scope_ref:ref,scope_display:display,
   currently_active:data.currently_active as boolean,
   desired_active:data.desired_active as boolean,
   active_sessions_terminated:false,no_change:false,
   impact:{requires_confirmation:true,
     access_broadened:impact.access_broadened as boolean,
     access_narrowed:impact.access_narrowed as boolean,
     warning:(impact.warning as string).trim()}
 };
}

/** Emergency cutoff is a Core-only, one-shot incident Change Plan. A
 * syntactically successful HTTP response cannot confirm the desired access
 * state unless the exact plan, scope, operation and revision are acknowledged.
 */
export function requireObservedEmergencyCutoffApplyForPlan(
 input:unknown,plan:unknown,plane:unknown,action:unknown
):{revision:number,active_sessions_terminated:false}{
 const unknown=():never=>{throw new Error(
   "UNKNOWN · Core Emergency Cutoff Apply receipt is unverified. Inspect Core cutoff inventory and Change History before any retry."
 )};
 const obj=(v:unknown):v is Record<string,unknown>=>
   !!v&&typeof v==="object"&&!Array.isArray(v);
 if(!obj(input)||!obj(plan)||!["remote","internet","ai"].includes(String(plane))
   ||!["apply","clear"].includes(String(action)))return unknown();
 const receipt=input,review=plan,operation="emergency-cutoff."+action;
 const validScope=plane==="remote"?["plane","remote-service"]
   :plane==="internet"?["plane","managed-host"]:["plane","ai-identity"];
 const ident=review.scope_ref;
 if(typeof review.change_plan_id!=="string"
   ||!/^cp_[A-Za-z0-9_-]{16,128}$/.test(review.change_plan_id)
   ||review.operation_class!=="INCIDENT_CHANGE"
   ||review.resource_type!=="emergency-cutoff"||review.operation!==operation
   ||typeof review.scope_kind!=="string"||!validScope.includes(review.scope_kind)
   ||typeof ident!=="string"||ident.length>160
   ||/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(ident)
   ||(review.scope_kind==="plane"?ident!=="":!ident)
   ||review.resource_ref!==(review.scope_kind==="plane"?plane:review.scope_kind+":"+ident)
   ||review.desired_active!==(action==="apply")
   ||review.no_change!==false
   ||review.confirmation_class!=="CONFIRM CUTOFF"
   ||!Number.isSafeInteger(review.expected_revision)||Number(review.expected_revision)<0
   ||!isObservedAbsoluteTime(review.valid_until)
   ||Date.parse(review.valid_until)<=Date.now())return unknown();
 if(receipt.status!=="APPLIED"||receipt.operation!==operation
   ||receipt.plane!==plane||receipt.scope_kind!==review.scope_kind
   ||receipt.scope_ref!==ident||receipt.active!==(action==="apply")
   ||receipt.active_sessions_terminated!==false
   ||!Number.isSafeInteger(receipt.revision)
   ||Number(receipt.revision)<=Number(review.expected_revision))return unknown();
 return {revision:receipt.revision as number,active_sessions_terminated:false};
}

/** Project the official Core live-access read model only from same-plane,
 * bounded observation pages. Never use arbitrary producer metadata as a Web
 * table column; unknown fidelity never becomes a confirmed zero count.
 */
export function requireObservedLiveAccessView(
 payload:unknown,plane:unknown,requestedResource:unknown
):{
 plane:string,fidelity:"UNKNOWN"|"EXACT_PER_CONNECTION",
 active_count:number|null,observations:Record<string,string>[],reason:string,partial:boolean
}{
 const fail=():never=>{throw new Error(
   "UNKNOWN · Core Live Access evidence is incomplete or does not match the requested plane. Refresh Core observations before interpreting connectivity."
 )};
 const record=(v:unknown):v is Record<string,unknown>=>
   !!v&&typeof v==="object"&&!Array.isArray(v);
 const safe=(v:unknown,max=160):v is string=>
   typeof v==="string"&&v.length<=max
   &&!/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(v);
 if(!record(payload)||!["remote","internet","ai"].includes(String(plane))
   ||!safe(requestedResource,160))return fail();
 const row=payload,fidelity=row.fidelity;
 const actualResource=row.resource;
 if(row.plane!==plane
   ||!(actualResource===requestedResource||
     requestedResource===""&&(actualResource===null||actualResource===""))
   ||row.resource_type!==null
   ||!Number.isSafeInteger(row.limit)||row.limit!==50
   ||!Array.isArray(row.observations)||row.observations.length>50
   ||!(row.next_cursor===null||(safe(row.next_cursor,1024)&&!!row.next_cursor))
   ||!safe(row.reason,512)
   ||!["UNKNOWN","EXACT_PER_CONNECTION"].includes(String(fidelity)))return fail();
 if(fidelity==="UNKNOWN"){
   if(row.active_count!==null||row.observations.length!==0||!!row.next_cursor
     ||!row.reason)return fail();
   return {plane:plane as string,fidelity:"UNKNOWN",active_count:null,
     observations:[],reason:row.reason as string,partial:false};
 }
 if(plane==="remote"
   ||!Number.isSafeInteger(row.active_count)
   ||Number(row.active_count)<row.observations.length
   ||Number(row.active_count)<0)return fail();
 const allowed=plane==="ai"
   ?["observation_kind","observation_id","job_id","status","capability",
       "ai_identity","managed_host_id","endpoint","started_at","updated_at"]
   :["observation_kind","observation_id","session_id","connection_id",
       "hostname","relay_name","profile_id","source_ip","started_at"];
 const kind=plane==="ai"?"AI_JOB":"NETWORK_SESSION";
 const observations:Record<string,string>[]=[];
 for(const raw of row.observations){
   if(!record(raw)||raw.observation_kind!==kind
     ||!safe(raw.observation_id)||!raw.observation_id)return fail();
   const item:Record<string,string>={};
   for(const field of allowed){
     const value=raw[field];
     if(value===undefined||value===null)continue;
     if(!safe(value,160))return fail();
     item[field]=value;
   }
   observations.push(item);
 }
 return {plane:plane as string,fidelity:"EXACT_PER_CONNECTION",
   active_count:row.active_count as number,observations,
   reason:row.reason as string,partial:row.next_cursor!==null};
}

/** A Core diagnosis response is descriptive evidence, never a probe or
 * authorization decision. Strip nested policy traces and enforce the actual
 * requested selectors and coherent layer severity before rendering.
 */
export function requireObservedDiagnosisView(
 payload:unknown,plane:unknown,source:unknown,destination:unknown,selector:unknown
):{
 overall:"HEALTHY"|"FAILED"|"UNKNOWN",network_probe_performed:false,
 next_action:string,layers:{layer:string,status:string,summary:string}[]
}{
 const fail=():never=>{throw new Error(
   "UNKNOWN · Core Connection Diagnosis response has unverified fields, mismatched flow or inconsistent health evidence."
 )};
 const obj=(v:unknown):v is Record<string,unknown>=>
   !!v&&typeof v==="object"&&!Array.isArray(v);
 const safe=(v:unknown,max=240):v is string=>
   typeof v==="string"&&!!v.trim()&&v.length<=max
     &&!/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(v);
 if(!obj(payload)||!obj(payload.input)||!Array.isArray(payload.layers)
   ||!["remote","internet","ai"].includes(String(plane))
   ||![source,destination,selector].every(v=>safe(v,160)))return fail();
 const input=payload.input;
 if(payload.plane!==plane||payload.side_effect_free!==true
   ||payload.network_probe_performed!==false
   ||input.source!==source||input.destination!==destination
   ||(plane==="ai"?input.permission:input.service)!==selector
   ||!["HEALTHY","FAILED","UNKNOWN"].includes(String(payload.overall))
   ||!safe(payload.next_action,240)
   ||payload.layers.length===0||payload.layers.length>16)return fail();
 const known=new Set(["input","policy","managed_host","remote_service","runtime",
   "dns","target_reachability","emergency_cutoff","recent_activity"]);
 const statuses=new Set(["HEALTHY","FAILED","UNKNOWN","N_A"]);
 const layers:{layer:string,status:string,summary:string}[]=[];
 const observed=new Set<string>();
 for(const raw of payload.layers){
   if(!obj(raw)||!safe(raw.layer,64)||!known.has(raw.layer)
     ||observed.has(raw.layer)||!statuses.has(String(raw.status))
     ||!safe(raw.summary,512))return fail();
   observed.add(raw.layer as string);
   layers.push({layer:raw.layer as string,status:raw.status as string,
     summary:(raw.summary as string).trim()});
 }
 const derived=layers.some(x=>x.status==="FAILED")?"FAILED":
   layers.some(x=>x.status==="UNKNOWN")?"UNKNOWN":"HEALTHY";
 if(derived!==payload.overall)return fail();
 return {overall:derived,network_probe_performed:false,
   next_action:(payload.next_action as string).trim(),layers};
}

/** Keyset page navigation only uses observed opaque Core cursors. The UI may
 * navigate backwards using previous request cursors; it never guesses a total. */
export type MenuPagePosition={cursor:string,history:string[]};
export function selectMenuPage(
  current:MenuPagePosition, nextCursor:unknown, direction:"older"|"newer"|"reset"
):MenuPagePosition|null{
  if(direction==="reset")return {cursor:"",history:[]};
  if(direction==="older"){
    if(typeof nextCursor!=="string"||!nextCursor||nextCursor===current.cursor)return null;
    return {cursor:nextCursor,history:[...current.history,current.cursor]};
  }
  if(!current.history.length)return null;
  return {cursor:current.history[current.history.length-1],
    history:current.history.slice(0,-1)};
}

/** Fetch each policy plane separately: a single all-plane 100-row limit can
 * hide an entire later plane behind earlier Remote rules. Keep the limit honest. */
export function combineObservedPolicyPlanes(
  pages:unknown[],limit:number
):{items:any[],possibly_truncated_planes:string[],next_cursor_by_plane:Record<string,string|null>}{
  const planes=["remote","internet","ai"] as const;
  if(!Array.isArray(pages)||pages.length!==planes.length
    ||!Number.isSafeInteger(limit)||limit<1)
    throw new Error("Core policy plane inventory is incomplete. State is UNKNOWN.");
  const items:any[]=[],possibly_truncated_planes:string[]=[];
  const next_cursor_by_plane:Record<string,string|null>={};
  for(let i=0;i<planes.length;i++){
    const page=requireObservedMenuPayload("policies",pages[i]);
    if(page.plane!==planes[i]||page.limit!==limit
      ||page.items.length>limit
      ||page.items.some((item:any)=>item.plane!==planes[i]))
      throw new Error("Core "+planes[i]+" policy response is inconsistent. State is UNKNOWN.");
    items.push(...page.items);
    // New Core supports real per-plane next_cursor. A legacy response that
    // exactly reaches the limit must still be marked potentially incomplete.
    const hasCursor=Object.prototype.hasOwnProperty.call(page,"next_cursor");
    next_cursor_by_plane[planes[i]]=isPartialCorePage(page)?page.next_cursor:null;
    if(page.items.length===limit&&(!hasCursor||!!page.next_cursor))
      possibly_truncated_planes.push(planes[i]);
  }
  return {items,possibly_truncated_planes,next_cursor_by_plane};
}

/** Only observed Core pages of the requested resource family may extend a
 * loaded inventory. Never guess a next cursor or silently swap Host/Service. */
export function requireObservedInventoryContinuation(
  route:"hosts"|"services",payload:unknown,requestedCursor:string,limit:number
):any{
  const page=requireObservedMenuPayload(route,payload);
  const expected=route==="hosts"?"managed-host":"remote-service";
  if(page.resource_type!==expected||page.limit!==limit
    ||!Number.isSafeInteger(limit)||limit<1
    // Keyset Core cannot produce an empty page with another next cursor.
    // Treat a broken continuation as UNKNOWN rather than looping "Load more".
    ||page.items.length>limit||(page.items.length===0&&isPartialCorePage(page))
    ||page.next_cursor===requestedCursor
    ||page.items.some((item:any)=>typeof item.id!=="string"||!item.id))
    throw new Error("Core inventory page does not match the requested "+expected+
      " resource type, size or cursor. State is UNKNOWN.");
  return page;
}

/** Objects & Groups uses the same Core inventory keyset API for seven public
 * resource types. A continuation is valid only for the requested family. */
export function requireObservedObjectContinuation(
  type:string,payload:unknown,requestedCursor:string,limit:number
):any{
  const allowed=new Set(["network-object","network-group","service-object",
    "service-group","permission-object","permission-group","ai-identity"]);
  const page=requireObservedMenuPayload("objects",payload);
  if(!allowed.has(type)||page.resource_type!==type
    ||!Array.isArray(page.items)||page.limit!==limit
    ||!Number.isSafeInteger(limit)||limit<1||page.items.length>limit
    ||page.next_cursor===requestedCursor
    ||page.items.some((item:any)=>!item||typeof item.id!=="string"||!item.id))
    throw new Error("Core Objects & Groups page is not the requested type, size or cursor. State is UNKNOWN.");
  return page;
}

/** Access Hygiene is read-only, bounded, and never a clearance/zero inferred
 * from omitted Core summary values or an incomplete item list. */
export function requireObservedAccessHygiene(payload:unknown):any{
  const page=requireObservedMenuPayload("hygiene",payload);
  const whole=(n:unknown)=>typeof n==="number"&&Number.isSafeInteger(n)&&n>=0;
  const summary=page.summary;
  if(!whole(page.count)||page.count<page.items.length||page.items.length>200
    ||!summary||typeof summary!=="object"||Array.isArray(summary)
    ||!whole(summary.action_required)||summary.action_required>page.count
    ||!whole(summary.unknown_evidence)||summary.unknown_evidence>page.count
    ||page.authoritative!==false||page.read_only!==true||page.auto_mutation!==false
    ||typeof page.generated_at!=="string"||!page.generated_at.trim())
    throw new Error("Core Access Hygiene report is incomplete. State is UNKNOWN; no clean result can be inferred.");
  return page;
}

/** Only true, role-appropriate workspaces offer an Inspect action.
 * Unrecognized resource kinds must not show a clickable no-op. */
export function hygieneInspectTarget(type:unknown,role:unknown):{route:string,group:string}|null{
  if(!["Admin","Operator","Read Only"].includes(String(role)))return null;
  if(type==="service-account"&&role!=="Admin")return null;
  const destinations:Record<string,{route:string,group:string}>={
    "managed-host":{route:"hosts",group:"connections"},
    "object":{route:"objects",group:"access"},
    "access-rule":{route:"policies",group:"access"},
    "service-account":{route:"integrations",group:"administration"},
  };
  return typeof type==="string"?destinations[type]||null:null;
}

/** A retention read must prove every metric before the UI can say "Normal".
 * Zero is valid only when Core explicitly returned the numeric value. */
export type ObservedAuditRetention={
  config:{control_days:number,access_days:number,max_events:number},
  total_events:number,db_size_bytes:number,capacity_exceeded:boolean,
  capacity_policy:string,
};
export function requireObservedAuditRetention(payload:unknown):ObservedAuditRetention{
  const fail=()=>{throw new Error("Core Audit Retention status is incomplete or malformed. State is UNKNOWN.");};
  if(!payload||typeof payload!=="object"||Array.isArray(payload))return fail();
  const record=payload as Record<string,unknown>;
  const config=record.config;
  if(!config||typeof config!=="object"||Array.isArray(config))return fail();
  const values=config as Record<string,unknown>;
  const nonnegative=(n:unknown)=>typeof n==="number"&&Number.isSafeInteger(n)&&n>=0;
  const positive=(n:unknown)=>nonnegative(n)&&Number(n)>0;
  if(!nonnegative(record.total_events)||!nonnegative(record.db_size_bytes)
    ||typeof record.capacity_exceeded!=="boolean"
    ||typeof record.capacity_policy!=="string"||!record.capacity_policy.trim()
    ||!positive(values.control_days)||!positive(values.access_days)
    ||!positive(values.max_events))return fail();
  return payload as ObservedAuditRetention;
}

/** Retention deletes old audit rows. Require explicit typed approval against
 * the exact observed Core policy, not a merely edited local form. */
export function auditRetentionRunPermitted(
  snapshot:unknown,draft:unknown,state:unknown,busy:unknown,confirmation:unknown
):boolean{
  if(state!=="ready"||busy!==false||confirmation!=="RUN RETENTION"
    ||!draft||typeof draft!=="object"||Array.isArray(draft))return false;
  let value:ObservedAuditRetention;
  try{value=requireObservedAuditRetention(snapshot)}catch{return false}
  const form=draft as Record<string,unknown>;
  return form.control_days===String(value.config.control_days)
    &&form.access_days===String(value.config.access_days)
    &&form.max_events===String(value.config.max_events);
}

/** Audit Export is a bounded, server-side operation, NOT a Web download.
 * A successful HTTP code alone cannot prove an artifact was actually created.
 * Match the acknowledged artifact and filter facts from authoritative Core. */
export function requireObservedAuditExport(payload:unknown,requestedFilters:unknown):any{
  const fail=()=>{throw new Error("UNKNOWN · Core Audit Export response did not confirm the submitted filters and server-side artifact. Inspect Activity log before retrying.");};
  if(!payload||typeof payload!=="object"||Array.isArray(payload)
    ||!requestedFilters||typeof requestedFilters!=="object"||Array.isArray(requestedFilters))return fail();
  const data=payload as Record<string,any>;
  const clean=requestedFilters as Record<string,unknown>;
  const received=data.filters;
  const allowed=new Set(["start","end","category","event_type","actor","resource","result","correlation"]);
  if(data.status!=="CREATED"||data.schema_version!==1
    ||typeof data.path!=="string"
    ||!/^\/var\/lib\/drlink\/audit-exports\/drlink-audit-\d{8}T\d{6}Z-[a-f0-9]{8}\.ndjson$/.test(data.path)
    ||typeof data.sha256!=="string"||!/^[a-f0-9]{64}$/.test(data.sha256)
    ||typeof data.event_count!=="number"||!Number.isSafeInteger(data.event_count)
    ||data.event_count<0||data.event_count>50000
    ||typeof data.size_bytes!=="number"||!Number.isSafeInteger(data.size_bytes)
    ||data.size_bytes<1||data.size_bytes>64*1024*1024
    ||data.sanitized!==true||data.download_exposed!==false
    ||data.authoritative_mutation!==false
    ||!received||typeof received!=="object"||Array.isArray(received))return fail();
  const got=received as Record<string,unknown>;
  const expectedKeys=Object.keys(clean),receivedKeys=Object.keys(got);
  if(expectedKeys.length!==receivedKeys.length
    ||expectedKeys.some(key=>!allowed.has(key)||typeof clean[key]!=="string"
      ||!(clean[key] as string).trim()||(clean[key] as string)!==(clean[key] as string).trim()
      ||got[key]!==clean[key])
    ||receivedKeys.some(key=>!allowed.has(key)||!Object.prototype.hasOwnProperty.call(clean,key)))return fail();
  return payload;
}

/** Read-only rollout Preview must describe exactly the requested target/immutable
 * artifact without granting Agent update authority. Stale or invalid receipts are UNKNOWN. */
export function requireObservedRolloutPreview(payload:unknown,request:unknown):any{
  const fail=()=>{throw new Error("UNKNOWN · Core Agent Update Preview did not match the current request. Inspect real Agent state and retry preview.");};
  const object=(v:unknown):v is Record<string,any>=>!!v&&typeof v==="object"&&!Array.isArray(v);
  const list=(v:unknown,allowEmpty=false):string[]|null=>{
    if(!Array.isArray(v)||v.length>100)return null;
    const out:string[]=[],seen=new Set<string>();
    for(const element of v){
      if(typeof element!=="string"||!element.trim())return null;
      const value=element.trim();
      if(!seen.has(value)){out.push(value);seen.add(value)}
    }
    return (allowEmpty||out.length>0)?out:null;
  };
  if(!object(payload)||!object(request)||!object(request.artifact))return fail();
  const data=payload as Record<string,any>,req=request as Record<string,any>;
  const expected=list(req.targets);
  const canaries=list(req.canary_targets,true);
  const wave=req.wave_size,threshold=req.failure_threshold_percent;
  const art=req.artifact;
  const version=typeof art.version==="string"?art.version.trim():"";
  const ref=typeof art.source_ref==="string"?art.source_ref.trim().toLowerCase():"";
  const digest=typeof art.sha256==="string"?art.sha256.trim().toLowerCase():"";
  if(!expected||!canaries||!version||!/^[0-9a-f]{40}$/.test(ref)
    ||!/^[0-9a-f]{64}$/.test(digest)
    ||!Number.isSafeInteger(wave)||wave<1||wave>25
    ||!Number.isSafeInteger(threshold)||threshold<0||threshold>100)return fail();
  const expectedCanaries=canaries.length?canaries:expected.slice(0,wave);
  if(expectedCanaries.some(id=>!expected.includes(id)))return fail();
  if(data.read_only!==true||data.ready_to_apply!==false||data.creates_job!==false
    ||data.requires_fresh_validation_on_apply!==true
    ||data.artifact_qualification!=="NOT_VERIFIED"
    ||typeof data.qualification_note!=="string"||!data.qualification_note.trim()
    ||data.wave_size!==wave||data.failure_threshold_percent!==threshold
    ||data.target_count!==expected.length
    ||!Array.isArray(data.targets)||data.targets.length!==expected.length
    ||data.targets.some((id:any,i:number)=>id!==expected[i])
    ||!Array.isArray(data.canary_targets)||data.canary_targets.length!==expectedCanaries.length
    ||data.canary_targets.some((id:any,i:number)=>id!==expectedCanaries[i])
    ||!object(data.artifact)||data.artifact.version!==version
    ||data.artifact.source_ref!==ref
    ||typeof data.artifact.sha256!=="string"||data.artifact.sha256.toLowerCase()!==digest
    ||!Array.isArray(data.blocked_targets)
    ||data.blocked_targets.some((id:any)=>typeof id!=="string"||!expected.includes(id))
    ||new Set(data.blocked_targets).size!==data.blocked_targets.length
    ||typeof data.eligible!=="boolean"||data.eligible!==(data.blocked_targets.length===0)
    ||!Array.isArray(data.target_observations)||data.target_observations.length!==expected.length)return fail();
  for(let i=0;i<expected.length;i++){
    const row=data.target_observations[i];
    if(!object(row)||row.target_id!==expected[i]
      ||row.target_version!==version||typeof row.current_version!=="string"
      ||!row.current_version||typeof row.platform!=="string"||!row.platform
      ||row.provenance!=="NOT_VERIFIED"||row.update_available!=="UNKNOWN"
      ||row.version_relation!==(
        row.current_version==="unknown"?"UNKNOWN"
          :row.current_version===version?"SAME_VERSION":"DIFFERENT"
      ))return fail();
  }
  return payload;
}

/** Core Inventory Export is a bounded server-side file, not a Web download.
 * Never infer CREATED from HTTP status, fabricated counts or a missing digest. */
export function requireObservedInventoryExport(payload:unknown):any{
  const fail=()=>{throw new Error("UNKNOWN · Core Inventory Export receipt did not confirm a bounded server-side file. Inspect Core export records before retrying.");};
  if(!payload||typeof payload!=="object"||Array.isArray(payload))return fail();
  const value=payload as Record<string,any>;
  const limits:Record<string,number>={managed_hosts:100,remote_services:1000,
    managed_host_groups:200,managed_host_tags:1000};
  const keys=Object.keys(limits);
  if(value.status!=="CREATED"
    ||typeof value.path!=="string"
    ||!/^\/var\/lib\/drlink\/exports\/drlink-inventory-\d{8}T\d{6}Z-[a-f0-9]{8}\.ndjson$/.test(value.path)
    ||typeof value.sha256!=="string"||!/^[a-f0-9]{64}$/.test(value.sha256)
    ||typeof value.size_bytes!=="number"||!Number.isSafeInteger(value.size_bytes)||value.size_bytes<1
    ||typeof value.record_count!=="number"||!Number.isSafeInteger(value.record_count)||value.record_count<0
    ||value.sanitized!==true||value.download_exposed!==false||value.authoritative_mutation!==false
    ||!value.counts||typeof value.counts!=="object"||Array.isArray(value.counts)
    ||!value.limits||typeof value.limits!=="object"||Array.isArray(value.limits)
    ||Object.keys(value.counts).length!==keys.length||Object.keys(value.limits).length!==keys.length)return fail();
  let sum=0;
  for(const key of keys){
    if(value.limits[key]!==limits[key]
      ||typeof value.counts[key]!=="number"||!Number.isSafeInteger(value.counts[key])
      ||value.counts[key]<0||value.counts[key]>limits[key])return fail();
    sum+=value.counts[key];
  }
  if(value.record_count!==sum)return fail();
  return payload;
}

/** A Job detail belongs to one explicitly requested ID. Incomplete or
 * superseded reads must not imply a matching current Job or cancellable state. */
export function requireObservedJobDetail(payload:unknown,requestedId:unknown):any{
  const fail=()=>{throw new Error("UNKNOWN · Core Job Detail is missing, mismatched or incomplete. Retry the exact Job ID.");};
  if(!payload||typeof payload!=="object"||Array.isArray(payload)
    ||typeof requestedId!=="string"||!requestedId.trim())return fail();
  const job=payload as Record<string,any>;
  const validStates=new Set(["QUEUED","RUNNING","SUCCEEDED","FAILED","CANCELLED"]);
  if(job.id!==requestedId||typeof job.id!=="string"||!job.id.trim()
    ||typeof job.job_type!=="string"||!job.job_type.trim()
    ||!validStates.has(job.status)
    ||typeof job.target_count!=="number"||!Number.isSafeInteger(job.target_count)
    ||job.target_count<1||job.target_count>100
    ||![true,false,0,1].includes(job.cancel_requested)
    ||!Array.isArray(job.targets)||job.targets.length!==job.target_count)return fail();
  const seen=new Set<string>();
  for(const t of job.targets){
    if(!t||typeof t!=="object"||Array.isArray(t)
      ||typeof t.target_id!=="string"||!t.target_id.trim()
      ||seen.has(t.target_id)||!validStates.has(t.status))return fail();
    seen.add(t.target_id);
  }
  return payload;
}

/** Job cancellation may finish with running targets still active, or an already
 * terminal Job. Neither condition is proof all target operations stopped. */
export function requireObservedJobCancellation(payload:unknown,requestedId:string):
  {job:any,outcome:"REQUESTED"|"ALREADY_TERMINAL"}{
  const job=requireObservedJobDetail(payload,requestedId);
  const recorded=job.cancel_requested===1||job.cancel_requested===true;
  if(["SUCCEEDED","FAILED"].includes(job.status)
    ||job.status==="CANCELLED"&&!recorded)
    return {job,outcome:"ALREADY_TERMINAL"};
  if(recorded&&["RUNNING","CANCELLED"].includes(job.status))
    return {job,outcome:"REQUESTED"};
  throw new Error("UNKNOWN · Core Job cancellation response did not confirm the current Job or cancellation state.");
}

/** A 200 response does not prove a Job was enqueued. Check the actual
 * Core queue identity, status and bounded target counts before reporting it. */
export function requireObservedJobStart(payload:unknown,expectedJobType:string):any{
  const failure=()=>{throw new Error("UNKNOWN · Core Job start response did not confirm the requested queue entry. Inspect Jobs before retrying.");};
  if(!payload||typeof payload!=="object"||Array.isArray(payload))return failure();
  const record=payload as Record<string,any>;
  const job=record.job,selection=record.selection;
  const validCount=(value:unknown)=>typeof value==="number"&&Number.isSafeInteger(value)
    &&value>=1&&value<=100;
  if(!job||typeof job!=="object"||Array.isArray(job)
    ||!selection||typeof selection!=="object"||Array.isArray(selection)
    ||typeof job.id!=="string"||!job.id.trim()
    ||job.job_type!==expectedJobType||job.status!=="QUEUED"
    ||!validCount(job.target_count)||!validCount(selection.target_count)
    ||job.target_count!==selection.target_count
    ||!["managed-host","managed-host-group"].includes(selection.resource_type))
    return failure();
  return payload;
}

/** A Fleet Preview is only meaningful when the Core plan belongs to this
 * form's resource family and the exact intended normalized metadata change. */
export function requireObservedFleetPreview(payload:unknown,request:unknown):any{
  const fail=()=>{throw new Error("UNKNOWN · Core Fleet Preview has mismatched targets, changes, or impact. Recheck the selection before creating a fresh Change Plan.");};
  const object=(v:unknown):v is Record<string,any>=>!!v&&typeof v==="object"&&!Array.isArray(v);
  if(!object(payload)||!object(request)||!object(request.changes)
    ||!["managed-host","managed-host-group"].includes(request.resource_type)
    ||typeof request.resource!=="string")return fail();
  const plan=payload as Record<string,any>,sel=plan.selection,preview=plan.preview,
    impact=plan.impact;
  if(!object(sel)||!object(preview)||!object(impact)||!object(plan.changes))return fail();
  const validCount=(n:unknown)=>typeof n==="number"&&Number.isSafeInteger(n)&&n>=1&&n<=100;
  if(typeof plan.change_plan_id!=="string"||!/^cp_[A-Za-z0-9_-]{20,}$/.test(plan.change_plan_id)
    ||plan.operation_class!=="CHANGE"||plan.operation!=="fleet-metadata.apply"
    ||plan.resource_type!=="managed-host-fleet"||plan.confirmation_class!=="APPLY"
    ||typeof plan.expected_revision!=="number"||!Number.isSafeInteger(plan.expected_revision)||plan.expected_revision<0
    ||sel.resource_type!==request.resource_type
    ||typeof sel.resource_ref!=="string"||!sel.resource_ref.trim()
    ||typeof sel.resource_display!=="string"||!sel.resource_display.trim()
    ||(request.resource_type==="managed-host"&&!request.resource.trim()&&sel.resource_ref!=="all")
    ||plan.resource_ref!==sel.resource_ref
    ||!validCount(sel.target_count)||preview.target_count!==sel.target_count
    ||impact.target_count!==sel.target_count
    ||!Array.isArray(preview.targets)||preview.targets.length!==sel.target_count
    ||typeof preview.operation_count!=="number"||!Number.isSafeInteger(preview.operation_count)||preview.operation_count<0
    ||impact.operation_count!==preview.operation_count
    ||impact.requires_confirmation!==true||impact.destructive!==false
    ||impact.access_broadened!==false||impact.access_narrowed!==false)return fail();
  let totalOperations=0;
  const ids=new Set<string>();
  for(const item of preview.targets){
    if(!object(item)||typeof item.managed_host_id!=="string"||!item.managed_host_id.trim()
      ||ids.has(item.managed_host_id)||typeof item.operation_count!=="number"
      ||!Number.isSafeInteger(item.operation_count)||item.operation_count<0)return fail();
    ids.add(item.managed_host_id);totalOperations+=item.operation_count;
  }
  if(totalOperations!==preview.operation_count)return fail();

  const keys=["description","tags","remove_tags","add_groups","remove_groups"];
  if(Object.keys(request.changes).some(k=>!keys.includes(k))
    ||Object.keys(plan.changes).some(k=>!keys.includes(k)))return fail();
  const expected:Record<string,any>={};
  for(const key of keys){
    if(!Object.prototype.hasOwnProperty.call(request.changes,key))continue;
    const value=request.changes[key];
    if(key==="description"){
      if(typeof value!=="string")return fail();
      expected[key]=value.trim();
    }else if(key==="tags"){
      if(!object(value)||Object.keys(value).length>64)return fail();
      const clean:Record<string,string>={};
      for(const [k,v] of Object.entries(value)){
        if(typeof v!=="string"||!k.trim()||Object.prototype.hasOwnProperty.call(clean,k.trim()))return fail();
        clean[k.trim()]=v.trim();
      }
      expected[key]=clean;
    }else{
      if(!Array.isArray(value)||value.length>(key==="remove_tags"?64:32))return fail();
      const out:string[]=[];
      for(const v of value){
        if(typeof v!=="string"||!v.trim())return fail();
        if(!out.includes(v.trim()))out.push(v.trim());
      }
      expected[key]=out;
    }
  }
  if(Object.keys(expected).length!==Object.keys(plan.changes).length)return fail();
  for(const key of Object.keys(expected)){
    const a=expected[key],b=plan.changes[key];
    if(Array.isArray(a)){
      if(!Array.isArray(b)||a.length!==b.length||a.some((v,i)=>v!==b[i]))return fail();
    }else if(object(a)){
      if(!object(b)||Object.keys(a).length!==Object.keys(b).length
        ||Object.keys(a).some(k=>b[k]!==a[k]))return fail();
    }else if(a!==b)return fail();
  }
  return payload;
}

/** A fleet Apply is acknowledged only with Core status/revision/target facts.
 * A missing field is UNKNOWN even if HTTP returned 200 and the change applied. */
export function requireObservedFleetApply(payload:unknown):any{
  if(!payload||typeof payload!=="object"||Array.isArray(payload))
    throw new Error("UNKNOWN · Fleet metadata apply response is incomplete. Inspect Change History before retrying.");
  const value=payload as Record<string,any>;
  const result=value.result;
  if(value.status!=="APPLIED"
    ||typeof value.revision!=="number"||!Number.isSafeInteger(value.revision)||value.revision<0
    ||!result||typeof result!=="object"||Array.isArray(result)
    ||typeof result.target_count!=="number"||!Number.isSafeInteger(result.target_count)
    ||result.target_count<1||result.target_count>100)
    throw new Error("UNKNOWN · Fleet metadata apply response lacks confirmed status, revision or target count. Inspect Change History before retrying.");
  return payload;
}

/** Confirm an Apply receipt against the exact Core Preview that the user
 * reviewed. HTTP success alone does not establish which fleet was updated. */
export function requireObservedFleetApplyForPreview(payload:unknown,preview:unknown):any{
  const fail=()=>{throw new Error("UNKNOWN · Fleet metadata Apply receipt differs from the reviewed Core Change Plan. Inspect Change History before any retry.");};
  const obj=(v:unknown):v is Record<string,any>=>!!v&&typeof v==="object"&&!Array.isArray(v);
  if(!obj(preview))return fail();
  const applied=requireObservedFleetApply(payload) as Record<string,any>;
  if(!obj(applied.selection)||!obj(applied.changes)||!obj(applied.result)
    ||!obj(preview.selection)||!obj(preview.changes)||!obj(preview.preview))return fail();
  const same=(a:unknown,b:unknown):boolean=>{
    if(Array.isArray(a)||Array.isArray(b))
      return Array.isArray(a)&&Array.isArray(b)&&a.length===b.length
        &&a.every((value,i)=>same(value,b[i]));
    if(obj(a)||obj(b))
      return obj(a)&&obj(b)&&Object.keys(a).length===Object.keys(b).length
        &&Object.keys(a).every(key=>Object.prototype.hasOwnProperty.call(b,key)&&same(a[key],b[key]));
    return a===b;
  };
  if(applied.revision!==preview.expected_revision+1
    ||!same(applied.selection,preview.selection)
    ||!same(applied.changes,preview.changes)
    ||applied.result.target_count!==preview.preview.target_count
    ||applied.result.operation_count!==preview.preview.operation_count
    ||!Array.isArray(applied.result.targets)
    ||!same(applied.result.targets,preview.preview.targets))return fail();
  return payload;
}

export function requireObservedMenuPayload(route:string,payload:unknown):any{
  if(payload===null||typeof payload!=="object"||Array.isArray(payload))
    throw new Error("Core response unavailable or malformed. Page state is UNKNOWN; retry the read.");
  const value=payload as Record<string,unknown>;
  if(Object.prototype.hasOwnProperty.call(value,"next_cursor")
    &&value.next_cursor!==null&&typeof value.next_cursor!=="string")
    throw new Error("Core pagination cursor is malformed. Loaded entries may be incomplete; state is UNKNOWN.");
  const collection=collectionPages[route];
  if(collection&&!Array.isArray(value.items))
    throw new Error(collection+" Core API response is missing an items list. State is UNKNOWN, not an empty list; retry or check System health.");
  if(collection&&(value.items as unknown[]).some(row=>
    !row||typeof row!=="object"||Array.isArray(row)))
    throw new Error(collection+" Core API returned invalid resource entries. State is UNKNOWN; retry or check System health.");
  if(route==="doctor"&&!Array.isArray(value.checks))
    throw new Error("Troubleshooting Core API response is missing checks. State is UNKNOWN; retry or check System health.");
  if(route==="versions"&&!Array.isArray(value.hosts))
    throw new Error("Agent versions Core API response is missing hosts. State is UNKNOWN; retry or check System health.");
  if(route==="overview"&&(!value.overview||typeof value.overview!=="object"||Array.isArray(value.overview)))
    throw new Error("Home Core overview is unavailable. State is UNKNOWN; retry or check System health.");
  return payload;
}
