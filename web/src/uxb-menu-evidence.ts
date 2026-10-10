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
