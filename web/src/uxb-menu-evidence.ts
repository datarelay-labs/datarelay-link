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
    ||page.items.length>limit||page.next_cursor===requestedCursor
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
