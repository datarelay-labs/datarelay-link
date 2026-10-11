import React,{useEffect,useRef,useState} from "react";
import type {LinkApi} from "./p0-access-policy";
import {isObservedAbsoluteTime} from "./uxb-integrations-state";

type Navigate=(id:string,groupId?:string)=>void;
export const enrollmentSteps=["Issue enrollment","Install / join","Review & approve","Verify connectivity"] as const;

/** UX-3: Core's list_enrollments returns at most 50 recently observed rows
 * and a fleet total. A malformed snapshot must not look like zero tickets or
 * expose arbitrary nested allocator credentials in this read-only history.
 */
export type ObservedEnrollmentRow={
 id:string,label:string,type:string,state:string,admission:string,remaining:string
};
export type ObservedEnrollmentHistory={
 status:"ready"|"UNKNOWN",items:ObservedEnrollmentRow[],total:number|null,partial:boolean
};
const BAD_ENROLLMENT_TEXT=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
function historyText(value:unknown):string{
 return typeof value==="string"&&value.trim().length>0
   &&value.length<=160&&!BAD_ENROLLMENT_TEXT.test(value)?value.trim():"UNKNOWN";
}
export function observedEnrollmentHistory(data:unknown):ObservedEnrollmentHistory{
 const unknown:ObservedEnrollmentHistory={status:"UNKNOWN",items:[],total:null,partial:false};
 if(!data||typeof data!=="object"||Array.isArray(data))return unknown;
 const page=data as Record<string,unknown>;
 if(!Array.isArray(page.items)||page.items.length>50)return unknown;
 const total=page.total===undefined?null:page.total;
 if(total!==null&&(!Number.isSafeInteger(total)||Number(total)<page.items.length))
   return unknown;
 if(page.items.length===0&&total!==null&&Number(total)>0)return unknown;
 const seen=new Set<string>();
 const items:ObservedEnrollmentRow[]=[];
 for(const raw of page.items){
   if(!raw||typeof raw!=="object"||Array.isArray(raw))return unknown;
   const row=raw as Record<string,unknown>;
   const id=historyText(row.id);
   if(id==="UNKNOWN"||seen.has(id))return unknown;
   seen.add(id);
   const label=row.label===undefined||row.label===""?id:historyText(row.label);
   const admission=["PENDING_APPROVAL","APPROVED","INVALID_PAIR"].includes(
     typeof row.first_host_admission==="string"?row.first_host_admission:""
   )?row.first_host_admission as string:"UNKNOWN";
   const remaining=typeof row.remaining_seconds==="number"
     &&Number.isSafeInteger(row.remaining_seconds)&&row.remaining_seconds>=0
     ?row.remaining_seconds+" seconds":"UNKNOWN";
   items.push({id,label,type:historyText(row.type),state:historyText(row.state),
     admission,remaining});
 }
 return {status:"ready",items,total:total as number|null,
   partial:total!==null?Number(total)>items.length:items.length>=50};
}

/** UX-3: the first Core managed-host page is role-scoped and bounded.
 * Never select a spoofed/duplicate identity, interpret a foreign-resource
 * response as a Host, or show a nested arbitrary label or credential.
 */
export type ObservedEnrollmentHost={
 id:string,name:string,admission_state:string,trust_status:string,
 connected:boolean|number|null,agent_heartbeat_at?:string,last_seen?:string
};
export function observedEnrollmentHostPage(input:unknown):{
 items:ObservedEnrollmentHost[],complete:boolean|null
}|null{
 if(!input||typeof input!=="object"||Array.isArray(input))return null;
 const page=input as Record<string,unknown>;
 if(page.resource_type!==undefined&&page.resource_type!=="managed-host"
   ||!Array.isArray(page.items)||page.items.length>100
   ||page.limit!==undefined&&(!Number.isSafeInteger(page.limit)
     ||Number(page.limit)<1||Number(page.limit)>100)
   ||page.next_cursor!==undefined&&page.next_cursor!==null
     &&(typeof page.next_cursor!=="string"||!page.next_cursor
       ||page.next_cursor.length>1024||BAD_ENROLLMENT_TEXT.test(page.next_cursor)))
   return null;
 const observed:ObservedEnrollmentHost[]=[];
 const seen=new Set<string>();
 for(const raw of page.items){
   if(!raw||typeof raw!=="object"||Array.isArray(raw))return null;
   const row=raw as Record<string,unknown>;
   if(typeof row.id!=="string"
     ||!/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/.test(row.id)
     ||seen.has(row.id)
     ||!["PENDING_APPROVAL","APPROVED","QUARANTINED"].includes(
       typeof row.admission_state==="string"?row.admission_state:""))
     return null;
   seen.add(row.id);
   const name=historyText(row.name)!=="UNKNOWN"?historyText(row.name)
     :historyText(row.label)!=="UNKNOWN"?historyText(row.label):row.id;
   const connected=[true,false,1,0].includes(row.connected as any)
     ?row.connected as boolean|number:null;
   const trust_status=historyText(row.trust_status);
   const host:ObservedEnrollmentHost={
     id:row.id,name,admission_state:row.admission_state as string,
     trust_status,connected
   };
   if(isObservedAbsoluteTime(row.agent_heartbeat_at))
     host.agent_heartbeat_at=row.agent_heartbeat_at;
   if(isObservedAbsoluteTime(row.last_seen))
     host.last_seen=row.last_seen;
   observed.push(host);
 }
 const complete=page.next_cursor===null?true
   :typeof page.next_cursor==="string"?false:null;
 return {items:observed,complete};
}

/** Core returns an explicit, display-once issuance response. Never advance
 * onboarding or display/copy a malformed, nested or wrong-mode credential.
 * A failed response could have created a ticket; users must inspect history
 * rather than automatically repeating a potentially one-time operation.
 */
export type ObservedIssuedEnrollment={
 mode:"zero-touch"|"manual",platform:string,expires_at:string,command:string,
 enrollment_code:string,pre_approved:boolean,next_step:string
};
const BAD_COMMAND_TEXT=/[\u0000-\u0008\u000b-\u000c\u000e-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
export function observedIssuedEnrollment(
 input:unknown,mode:unknown,platform:unknown
):ObservedIssuedEnrollment|null{
 if(!input||typeof input!=="object"||Array.isArray(input)
   ||typeof mode!=="string"||!["zero-touch","manual"].includes(mode)
   ||typeof platform!=="string"||!["linux","macos","windows"].includes(platform))return null;
 const row=input as Record<string,unknown>;
 if(row.mode!==mode||row.platform!==platform||row.state!=="pending"
   ||row.display_once!==true||row.management_only!==true
   ||!isObservedAbsoluteTime(row.expires_at)
   ||typeof row.ttl_seconds!=="number"||!Number.isSafeInteger(row.ttl_seconds)
   ||row.ttl_seconds<=0
   ||row.ttl_seconds>(mode==="manual"?30*86400:24*3600)
   ||typeof row.command!=="string"||!row.command.trim()
   ||row.command.length>65536||BAD_COMMAND_TEXT.test(row.command))
   return null;
 if(mode==="zero-touch"&&typeof row.pre_approved!=="boolean"
   ||mode==="manual"&&row.pre_approved!==undefined&&row.pre_approved!==false)
   return null;
 const enrollment_code=mode==="manual"?row.enrollment_code:"";
 if(mode==="manual"&&(typeof enrollment_code!=="string"
   ||!/^[a-f0-9]{16}\.[a-f0-9]{64}$/.test(enrollment_code)))return null;
 const next_step=historyText(row.next_step);
 return {
  mode:mode as "zero-touch"|"manual",
  platform:platform as string,
  expires_at:row.expires_at as string,
  command:row.command as string,
  enrollment_code:enrollment_code as string,
  pre_approved:mode==="zero-touch"?row.pre_approved as boolean:false,
  next_step:next_step==="UNKNOWN"?"Inspect Managed Hosts after installing the Agent.":next_step,
 };
}

/** A display-once response can be structurally valid yet contradict what
 * the Admin explicitly selected. Never treat a changed TTL or pre-approval
 * flag as evidence of the requested enrollment. Core remains authoritative.
 */
export function issuedEnrollmentMatchesRequestedOptions(
 input:unknown,request:unknown
):boolean{
 if(!input||typeof input!=="object"||Array.isArray(input)
   ||!request||typeof request!=="object"||Array.isArray(request))return false;
 const row=input as Record<string,unknown>,expected=request as Record<string,unknown>;
 const mode=expected.mode,ttl=expected.ttl;
 if(!["zero-touch","manual"].includes(String(mode))
   ||!["linux","macos","windows"].includes(String(expected.platform))
   ||mode==="manual"&&expected.platform==="windows"
   ||typeof ttl!=="string"||!/^[0-9]+$/.test(ttl.trim())
   ||!Number.isSafeInteger(Number(ttl))
   ||typeof expected.preApproved!=="boolean")return false;
 return row.mode===mode&&row.platform===expected.platform
   &&typeof row.ttl_seconds==="number"&&Number.isSafeInteger(row.ttl_seconds)
   &&row.ttl_seconds===Number(ttl)
   &&(mode==="zero-touch"?row.pre_approved===expected.preApproved
      :expected.preApproved===false
        &&(row.pre_approved===undefined||row.pre_approved===false));
}

/** UX-3: a Core Host inventory and its approval preview are private to the
 * exact current operator, including two different users with the same role.
 * Web remains a read-only projection until Core approves the actual Change Plan.
 */
export function onboardingHostSnapshotMatchesActor(scope:unknown,current:unknown):boolean{
 const obj=(v:unknown):v is Record<string,unknown>=>
   !!v&&typeof v==="object"&&!Array.isArray(v);
 if(!obj(scope)||!obj(current))return false;
 const id=current.id,role=current.role;
 return typeof id==="string"&&!!id.trim()&&id.length<=160
   &&!BAD_ENROLLMENT_TEXT.test(id)
   &&["Admin","Operator","Read Only"].includes(String(role))
   &&scope.id===id&&scope.role===role;
}

/** Mirror the existing Core enrollment input limits for an immediate, safe
 * user-facing explanation. The Core still owns validation and issuance.
 */
export function enrollmentIssuePreflight(
 mode:unknown,platform:unknown,ttl:unknown,label:unknown,note:unknown
):string|null{
 if(mode!=="zero-touch"&&mode!=="manual")return "Choose a supported enrollment mode.";
 if(!["linux","macos","windows"].includes(String(platform))
   ||mode==="manual"&&platform==="windows")
   return "Unsupported Agent platform for the selected enrollment mode.";
 const max=mode==="manual"?2592000:86400;
 if(typeof ttl!=="string"||!/^[0-9]+$/.test(ttl.trim())
   ||!Number.isSafeInteger(Number(ttl.trim()))||Number(ttl.trim())<60
   ||Number(ttl.trim())>max)
   return "Invitation TTL must be a whole number from 60 to "+max+" seconds.";
 const invalid=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
 if(typeof label!=="string"||label.trim().length>128||invalid.test(label))
   return "Host label must be at most 128 characters without control text.";
 if(typeof note!=="string"||note.trim().length>1024||invalid.test(note))
   return "Optional note must be at most 1024 characters without control text.";
 return null;
}

/** A display-once ticket belongs to one exact requested UI intent and Web
 * operator, never merely to a role or a previously selected Agent platform.
 * These inputs are reference text only, not authorization/secret storage.
 */
export type EnrollmentIssuanceIntent={
 operatorId:unknown,role:unknown,mode:unknown,platform:unknown,
 ttl:unknown,label:unknown,note:unknown,preApproved:unknown
};
export function enrollmentIssuanceIntent(data:EnrollmentIssuanceIntent):string{
 if(typeof data.operatorId!=="string"||!data.operatorId.trim()
   ||typeof data.role!=="string"||data.role!=="Admin"
   ||typeof data.mode!=="string"||!["manual","zero-touch"].includes(data.mode)
   ||typeof data.platform!=="string"||!["linux","macos","windows"].includes(data.platform)
   ||typeof data.ttl!=="string"||typeof data.label!=="string"
   ||typeof data.note!=="string"||typeof data.preApproved!=="boolean")return "";
 return JSON.stringify([data.operatorId,data.role,data.mode,data.platform,
   data.ttl,data.label,data.note,data.preApproved]);
}
export function issuedEnrollmentForCurrentIntent(
 input:unknown,intent:unknown
):ObservedIssuedEnrollment|null{
 if(!intent||typeof intent!=="string"
   ||!input||typeof input!=="object"||Array.isArray(input))return null;
 const state=input as Record<string,unknown>;
 const evidence=state.evidence;
 if(state.intent!==intent||!evidence||typeof evidence!=="object"
   ||Array.isArray(evidence))return null;
 const item=evidence as Record<string,unknown>;
 if(typeof item.mode!=="string"||!["zero-touch","manual"].includes(item.mode)
   ||typeof item.platform!=="string"||!["linux","macos","windows"].includes(item.platform)
   ||typeof item.command!=="string"||!item.command.trim()||item.command.length>65536
   ||BAD_COMMAND_TEXT.test(item.command)
   ||!isObservedAbsoluteTime(item.expires_at)
   ||typeof item.pre_approved!=="boolean"
   ||typeof item.enrollment_code!=="string"
   ||typeof item.next_step!=="string"
   ||BAD_ENROLLMENT_TEXT.test(item.next_step))
   return null;
 return item as ObservedIssuedEnrollment;
}

/** UX-3: an HTTP 200 alone does not make a Host admission request safe to
 * approve. Validate the exact current Host, approved target, confirmation,
 * revision and non-destructive Core Change Plan, projecting only safe fields.
 * The Core remains the final authorization/CSRF/revision authority.
 */
export function observedHostAdmissionApprovalPlan(input:unknown,hostId:unknown){
 if(!input||typeof input!=="object"||Array.isArray(input)
   ||typeof hostId!=="string"
   ||!/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/.test(hostId))return null;
 const plan=input as Record<string,any>;
 const summary=plan.preview,impact=plan.impact;
 if(typeof plan.change_plan_id!=="string"
   ||!/^cp_[A-Za-z0-9_-]{16,128}$/.test(plan.change_plan_id)
   ||plan.operation_class!=="CHANGE"
   ||plan.operation!=="managed-host-admission.approve"
   ||plan.admission_operation!=="approve"
   ||plan.resource_type!=="managed-host"||plan.resource_ref!==hostId
   ||!Number.isSafeInteger(plan.expected_revision)||plan.expected_revision<0
   ||plan.confirmation_class!=="APPROVE"
   ||!isObservedAbsoluteTime(plan.valid_until)
   ||Date.parse(plan.valid_until)<=Date.now()
   ||plan.no_change!==false
   ||!summary||typeof summary!=="object"||Array.isArray(summary)
   ||!impact||typeof impact!=="object"||Array.isArray(impact)
   ||summary.id!==hostId||summary.after!=="APPROVED"
   ||!["PENDING_APPROVAL","QUARANTINED"].includes(summary.before)
   ||impact.kind!=="managed-host-admission"
   ||impact.before!==summary.before||impact.after!=="APPROVED"
   ||impact.requires_confirmation!==true||impact.destructive!==false
   ||impact.access_broadened!==true||impact.access_narrowed!==false
   ||typeof impact.warning!=="string"||!impact.warning.trim()
   ||impact.warning.length>160||BAD_ENROLLMENT_TEXT.test(impact.warning)
   ||!Array.isArray(impact.kept)||impact.kept.length>10
   ||impact.kept.some((x:any)=>typeof x!=="string"||!x.trim()
     ||x.length>80||BAD_ENROLLMENT_TEXT.test(x)))
   return null;
 return {
   change_plan_id:plan.change_plan_id as string,
   expected_revision:plan.expected_revision as number,
   confirmation_class:"APPROVE" as const,
   valid_until:plan.valid_until as string,
   preview:{id:hostId,before:summary.before as string,after:"APPROVED" as const},
   impact:{
     kind:"managed-host-admission" as const,
     before:summary.before as string,after:"APPROVED" as const,
     access_broadened:true as const,destructive:false as const,
     warning:impact.warning as string,kept:impact.kept as string[]
   }
 };
}
/** A revision-confirmed Core acknowledgement is distinct from an HTTP 200
 * carrying malformed or no-change data. Do not silently advance enrollment.
 */
export function observedHostAdmissionApplyResult(
 input:unknown,expectedRevision:unknown
):{revision:number}|null{
 if(!input||typeof input!=="object"||Array.isArray(input)
   ||!Number.isSafeInteger(expectedRevision)||Number(expectedRevision)<0)
   return null;
 const data=input as Record<string,unknown>;
 if(data.status!=="APPLIED"||data.admission_operation!=="approve"
   ||!Number.isSafeInteger(data.revision)
   ||Number(data.revision)<=Number(expectedRevision))return null;
 return {revision:data.revision as number};
}

/** A previously valid Core Change Plan may expire while the operator's tab
 * is idle. Neither a stale Host nor a stale revision can authorize Apply.
 * The Core remains authoritative and will revalidate the plan on request.
 */
export function currentHostAdmissionApprovalIsActionable(
 plan:unknown,hostId:unknown,at:number=Date.now()
):boolean{
 if(!plan||typeof plan!=="object"||Array.isArray(plan)
   ||typeof hostId!=="string"||!Number.isFinite(at))return false;
 const row=plan as Record<string,unknown>;
 const preview=row.preview;
 return typeof row.change_plan_id==="string"
   &&/^cp_[A-Za-z0-9_-]{16,128}$/.test(row.change_plan_id)
   &&Number.isSafeInteger(row.expected_revision)&&Number(row.expected_revision)>=0
   &&!!preview&&typeof preview==="object"&&!Array.isArray(preview)
   &&(preview as Record<string,unknown>).id===hostId
   &&isObservedAbsoluteTime(row.valid_until)
   &&Date.parse(row.valid_until)>at;
}

/** Admission, trust, connection and policy are independent Core concepts.
 * Do not stringify arbitrary nested Core state or trust an unverified time.
 */
export function hostReadiness(host:unknown){
  const unknown={admission:"UNKNOWN",trust:"UNKNOWN",connection:"UNKNOWN",
    observedAt:"No observation",policy:"NOT VERIFIED"};
  if(!host||typeof host!=="object"||Array.isArray(host))return unknown;
  const row=host as Record<string,unknown>;
  const admission=typeof row.admission_state==="string"&&
    ["PENDING_APPROVAL","APPROVED","QUARANTINED"].includes(row.admission_state)
    ?row.admission_state:"UNKNOWN";
  const rawTrust=typeof row.trust_status==="string"
    &&row.trust_status.length<=40&&!BAD_ENROLLMENT_TEXT.test(row.trust_status)
    ?row.trust_status.toUpperCase():"UNKNOWN";
  const trust=["TRUSTED","UNTRUSTED","REVOKED","PENDING"].includes(rawTrust)
    ?rawTrust:"UNKNOWN";
  const connection=row.connected===true||row.connected===1?"CONNECTED"
    :row.connected===false||row.connected===0?"NOT CONNECTED":"UNKNOWN";
  const observedAt=isObservedAbsoluteTime(row.agent_heartbeat_at)?row.agent_heartbeat_at
    :isObservedAbsoluteTime(row.last_seen)?row.last_seen:"UNKNOWN";
  return {admission,trust,connection,observedAt,policy:"NOT VERIFIED"};
}
export function hostReadinessLabel(host:any):string {
  const s=hostReadiness(host);
  if(s.admission==="PENDING_APPROVAL")return "WAITING FOR APPROVAL";
  if(s.admission==="QUARANTINED")return "QUARANTINED";
  if(s.connection==="UNKNOWN")return "NO CONNECTION EVIDENCE";
  if(s.admission==="APPROVED"&&s.connection==="CONNECTED"&&s.trust!=="TRUSTED")return "CONNECTED · TRUST NOT VERIFIED";
  if(s.admission==="APPROVED"&&s.connection==="CONNECTED"&&s.trust==="TRUSTED")return "CONNECTED · APPROVED · TRUSTED";
  if(s.connection==="NOT CONNECTED")return "NOT CONNECTED";
  return "UNKNOWN · REVIEW CORE STATE";
}

export function EnrollmentOnboarding({api,data,refresh,operator,onNavigate,onBusyChange}:{
  api:LinkApi,data:any,refresh:()=>void,operator:any,onNavigate?:Navigate,
  onBusyChange?:(busy:boolean)=>void
}){
  const [step,setStep]=useState(1),[mode,setMode]=useState("zero-touch"),[platform,setPlatform]=useState("linux");
  const [ttl,setTtl]=useState("3600"),[label,setLabel]=useState(""),[note,setNote]=useState("");
  const [preApproved,setPreApproved]=useState(false),[issued,setIssued]=useState<any>(null);
  const [hosts,setHosts]=useState<ObservedEnrollmentHost[]|null>(null),[selectedHost,setSelectedHost]=useState("");
  const [hostsScope,setHostsScope]=useState<{id:unknown,role:unknown}|null>(null);
  const [hostsComplete,setHostsComplete]=useState<boolean|null>(null);
  const [fetchBusy,setFetchBusy]=useState(false),[busy,setBusy]=useState(false);
  useEffect(()=>{onBusyChange?.(busy)},[busy]);
  useEffect(()=>()=>{onBusyChange?.(false)},[]);
  const [error,setError]=useState(""),[inventoryError,setInventoryError]=useState("");
  const [copyStatus,setCopyStatus]=useState("");
  const [preview,setPreview]=useState<any>(null),[confirm,setConfirm]=useState(""),[message,setMessage]=useState("");
  const approvalGeneration=useRef(0);
  const inventoryGeneration=useRef(0);
  const admin=operator?.role==="Admin";
  const issueProblem=enrollmentIssuePreflight(mode,platform,ttl,label,note);
  const matchingHostScope=onboardingHostSnapshotMatchesActor(hostsScope,operator);
  const visibleHosts=matchingHostScope?hosts:null;
  const visibleHostComplete=matchingHostScope?hostsComplete:null;
  const visibleSelectedHost=matchingHostScope?selectedHost:"";
  const selected=visibleHosts?.find(h=>String(h.id)===visibleSelectedHost)||null;
  const scopedPreview=matchingHostScope?preview:null;
  const approvalActionable=currentHostAdmissionApprovalIsActionable(scopedPreview,visibleSelectedHost);
  const readiness=hostReadiness(selected);
  const required=String(scopedPreview?.confirmation_class||"APPROVE");
  const history=observedEnrollmentHistory(data);
  const issuedIntent=enrollmentIssuanceIntent({
    operatorId:operator?.id,role:operator?.role,mode,platform,ttl,label,note,preApproved
  });
  const currentIssueIntent=useRef(issuedIntent);
  currentIssueIntent.current=issuedIntent;
  const visibleIssued=issuedEnrollmentForCurrentIntent(issued,issuedIntent);
  useEffect(()=>{
    if(step>=3)void refreshHosts();
    return()=>{inventoryGeneration.current+=1;approvalGeneration.current+=1;};
  },[step,operator?.id,operator?.role]);
  useEffect(()=>{
    // Expire idle approval UI as well as validating again at click time.
    if(!scopedPreview||!matchingHostScope)return;
    const deadline=Date.parse(scopedPreview.valid_until);
    const delay=deadline-Date.now();
    if(!Number.isFinite(delay)||delay>2147483647)return;
    const timer=setTimeout(()=>{
      if(Date.now()>=deadline){
        setPreview(null);setConfirm("");
        setError("Core approval Preview expired. Refresh Host inventory before requesting a new approval plan.");
      }
    },Math.max(0,delay));
    return()=>clearTimeout(timer);
  },[scopedPreview?.change_plan_id,scopedPreview?.valid_until,matchingHostScope,visibleSelectedHost]);
  async function refreshHosts(){
    approvalGeneration.current+=1;
    const generation=++inventoryGeneration.current;
    setFetchBusy(true);setInventoryError("");setPreview(null);setConfirm("");
    setHostsScope(null);setHosts(null);setHostsComplete(null);
    try{
      const result=await api("/api/v1/inventory?resource_type=managed-host&limit=100");
      if(generation!==inventoryGeneration.current)return;
      const observed=observedEnrollmentHostPage(result);
      if(!observed)throw new Error("Managed Host inventory response incomplete or malformed");
      setHosts(observed.items);setHostsComplete(observed.complete);
      setHostsScope({id:operator?.id,role:operator?.role});
      // Explicit selection is required; never approve another observed Host.
      setSelectedHost(value=>value&&observed.items.some(h=>h.id===value)?value:"");
    }catch(e:any){
      if(generation===inventoryGeneration.current){
        setHostsScope(null);setHosts(null);setHostsComplete(null);setSelectedHost("");
        setInventoryError(String(e?.message||e));
      }
    }finally{if(generation===inventoryGeneration.current)setFetchBusy(false)}
  }
  async function copyIssued(label:string,value:string){
    setCopyStatus("");
    if(!value)return;
    try{
      if(typeof navigator==="undefined"||!navigator.clipboard?.writeText)
        throw new Error("Secure clipboard unavailable");
      await navigator.clipboard.writeText(value);
      setCopyStatus(label+" copied. Clipboard may be visible to other apps. Clear it after use.");
    }catch{
      setCopyStatus("Copy unavailable. Select the displayed text manually.");
    }
  }
  async function issue(){
    if(!admin||busy)return;
    if(issueProblem){setError(issueProblem);return;}
    const requestedIntent=issuedIntent;
    if(!requestedIntent){setError("Authenticated Admin identity is unavailable. Re-login before issuing an enrollment.");return;}
    setCopyStatus("");setError("");setMessage("");setIssued(null);setBusy(true);
    try{
      const result=await api(mode==="manual"?"/api/v1/enrollments/manual":"/api/v1/enrollments/zero-touch",{
        method:"POST",body:JSON.stringify({platform,ttl_seconds:ttl,label,note,
          ...(mode==="zero-touch"?{pre_approved:preApproved}:{})}),
      });
      const observed=observedIssuedEnrollment(result,mode,platform);
      if(!observed)throw new Error("Core returned invalid enrollment evidence. The ticket may exist; inspect enrollment history before retrying.");
      if(!issuedEnrollmentMatchesRequestedOptions(result,{mode,platform,ttl,preApproved}))
        throw new Error("Core enrollment TTL or first-Host pre-approval contradicts the requested intent. The ticket may exist; inspect Core enrollment history before retrying.");
      if(currentIssueIntent.current!==requestedIntent){
        setError("Enrollment form or account changed while issuing. Inspect Core enrollment history before retrying.");
        return;
      }
      setIssued({intent:requestedIntent,evidence:observed});refresh();setStep(2);
    }catch(e:any){
      const stale=currentIssueIntent.current!==requestedIntent;
      // Transport failure may occur AFTER Core created the one-use ticket.
      // Show no previous actor's error details and never auto-issue again.
      setError((stale?"Enrollment form or account changed. ":"Enrollment request outcome UNKNOWN. ")
        +"The ticket may exist; inspect Core enrollment history before retrying."
        +(stale?"":" "+String(e?.message||e)));
    }
    finally{setBusy(false)}
  }
  async function previewApproval(){
    if(!admin||!matchingHostScope||!selectedHost||!selected||busy||fetchBusy)return;
    const generation=++approvalGeneration.current;
    setBusy(true);setError("");setPreview(null);setConfirm("");
    try{
      const result=await api("/api/v1/managed-hosts/admission/preview",{
        method:"POST",body:JSON.stringify({host:selectedHost,operation:"approve"}),
      });
      if(generation!==approvalGeneration.current)return;
      const observed=observedHostAdmissionApprovalPlan(result,selectedHost);
      if(!observed)throw new Error("Core admission Preview is unverified; no approval is available. Refresh Host state before retrying.");
      setPreview(observed);
    }catch(e:any){if(generation===approvalGeneration.current)setError(String(e.message||e))}
    finally{if(generation===approvalGeneration.current)setBusy(false)}
  }
  async function applyApproval(){
    if(!admin||!matchingHostScope||!selectedHost||!scopedPreview?.change_plan_id
      ||!approvalActionable||confirm!==required||busy)return;
    // Recheck at the instant of the click: render-time state can be stale.
    if(!currentHostAdmissionApprovalIsActionable(scopedPreview,selectedHost)){
      setPreview(null);setConfirm("");
      setError("Core approval Preview expired. Refresh Host inventory and request a new plan.");
      return;
    }
    setBusy(true);setError("");
    try{
      const result=await api("/api/v1/managed-hosts/admission/apply",{
        method:"POST",body:JSON.stringify({change_plan_id:scopedPreview.change_plan_id,confirmation:confirm}),
      });
      const applied=observedHostAdmissionApplyResult(result,scopedPreview.expected_revision);
      if(!applied)throw new Error("Core admission apply result is unverified; refresh Host inventory before deciding whether to retry.");
      setMessage("Core admission review applied at revision "+applied.revision);
      setPreview(null);setConfirm("");refresh();setStep(4);
    }catch(e:any){
      // A timeout or malformed acknowledgement can follow a committed Core
      // change. Retire the one-shot plan: never offer a blind second Apply.
      setPreview(null);setConfirm("");
      setError("Approval not confirmed; refresh Host inventory before deciding whether to retry. "+String(e.message||e));
    }
    finally{setBusy(false)}
  }
  return <section className="dr-p0-onboarding" data-testid="p0-enrollment-journey">
    <div className="card dr-p0-section">
      <p className="dr-eyebrow">P0 · Agent onboarding</p>
      <h2>Connect an Agent in four steps</h2>
      <p className="muted">Issue → install → approve → verify. Admission approval never guarantees network reachability; pre-approval is off by default.</p>
      <ol className="dr-p0-steps" aria-label="Agent enrollment stages">{enrollmentSteps.map((name,i)=>
        <li className={step===i+1?"active":step>i+1?"done":""} key={name}>
          <button type="button" disabled={busy||fetchBusy} onClick={()=>{approvalGeneration.current+=1;setStep(i+1);setError("");setPreview(null);setConfirm("")}} aria-current={step===i+1?"step":undefined}>
            <span>{i+1}</span>{name}</button></li>
      )}</ol>
      {error&&<p className="error" role="alert">{error}</p>}
      {message&&<p className="notice" role="status">{message}</p>}
      {step===1&&<div className="dr-p0-stage">
        <h3>1. Issue an enrollment invitation</h3>
        <div className="dr-p0-form">
          <label className="dr-field"><span>Enrollment mode</span><select value={mode} disabled={busy} onChange={e=>{setIssued(null);setCopyStatus("");setMode(e.target.value);setPreApproved(false);setTtl(e.target.value==="manual"?"600":"3600");if(e.target.value==="manual"&&platform==="windows")setPlatform("linux")}}><option value="zero-touch">Zero-Touch (recommended)</option><option value="manual">Manual (interactive credential)</option></select></label>
          <label className="dr-field"><span>Agent platform</span><select value={platform} disabled={busy} onChange={e=>{setIssued(null);setCopyStatus("");setPlatform(e.target.value)}}><option value="linux">Linux</option><option value="macos">macOS</option>{mode!=="manual"&&<option value="windows">Windows</option>}</select></label>
          <label className="dr-field"><span>Invitation TTL (seconds)</span><input value={ttl} disabled={busy} onChange={e=>{setIssued(null);setCopyStatus("");setTtl(e.target.value)}} placeholder={mode==="manual"?"60–2592000":"60–86400"}/></label>
          <label className="dr-field"><span>Host label</span><input value={label} disabled={busy} onChange={e=>{setIssued(null);setCopyStatus("");setLabel(e.target.value)}} placeholder="e.g. branch-gateway"/></label>
          <label className="dr-field"><span>Optional note</span><input value={note} disabled={busy} onChange={e=>{setIssued(null);setCopyStatus("");setNote(e.target.value)}} placeholder="Operator context"/></label>
        </div>
        {admin&&mode==="zero-touch"&&<label className="dr-p0-check"><input type="checkbox" checked={preApproved} disabled={busy} onChange={e=>{setIssued(null);setCopyStatus("");setPreApproved(e.target.checked)}}/><span>Pre-approve first Host from this ticket (explicit Admin action)</span></label>}
        <p className="muted">Pending Approval is the default, regardless of agent connection status. Credentials are display-once and must not be saved to browser storage.</p>
        {issueProblem&&<p className="warning-box" role="alert">{issueProblem}</p>}
        <button className="primary" disabled={!admin||busy||!!issueProblem} onClick={issue}>{busy?"Issuing…":"Issue enrollment →"}</button>
      </div>}
      {step===2&&<div className="dr-p0-stage">
        <h3>2. Install the Agent and join</h3>
        {visibleIssued?<div className="warning-box">
          <p><strong>Display-once credential · expires {visibleIssued.expires_at||"UNKNOWN"}</strong></p>
          <p>First Host admission: {visibleIssued.pre_approved?"Pre-approved by explicit Admin choice":"Pending Approval"}</p>
          {visibleIssued.enrollment_code&&<><p>Enrollment code</p><pre className="plan">{visibleIssued.enrollment_code}</pre>
            <button type="button" className="secondary" onClick={()=>copyIssued("Enrollment code",visibleIssued.enrollment_code)}>Copy enrollment code</button>
          </>}
          <p>Canonical install command</p><pre className="plan">{visibleIssued.command||"No install command issued"}</pre>
          {visibleIssued.command&&<button type="button" className="secondary" onClick={()=>copyIssued("Install command",visibleIssued.command)}>Copy install command</button>}
          {copyStatus&&<p className="notice" role="status">{copyStatus}</p>}
          <p className="muted">Copy only when you intend to install this Agent. Paste secrets only into the intended trusted machine and clear sensitive clipboard content afterward.</p>
          <p>{visibleIssued.next_step}</p>
        </div>:<p className="muted">No invitation issued during this session. Return to Step 1 to create one, or continue to inspect a previously enrolled Host.</p>}
        <button className="primary" onClick={()=>setStep(3)}>Next: inspect Host admission →</button>
      </div>}
      {step>=3&&<div className="dr-p0-stage">
        <div className="dr-section-head"><div><h3>{step===3?"3. Review and approve the Host":"4. Verify admission, trust and connectivity"}</h3>
          <p className="muted">Current data comes from the canonical Managed Host inventory, not from the enrollment ticket.</p>
        </div><button className="secondary" onClick={refreshHosts} disabled={busy||fetchBusy}>{fetchBusy?"Refreshing…":"Refresh inventory"}</button></div>
        {inventoryError&&<p className="error" role="alert">Inventory unavailable: {inventoryError}</p>}
        {visibleHosts!==null&&visibleHostComplete!==true&&<p className="muted" role="status">
          Other Hosts may exist beyond this Core page. Loaded entries are not proof
          of a full fleet inventory; use Servers &amp; Agents for additional pages.
        </p>}
        <label className="dr-field"><span>Managed Host</span><select value={visibleSelectedHost} disabled={busy||fetchBusy||!matchingHostScope} onChange={e=>{approvalGeneration.current+=1;setSelectedHost(e.target.value);setPreview(null);setConfirm("")}}>
          {!visibleSelectedHost&&<option value="">{visibleHosts===null?"Host inventory: UNKNOWN":visibleHosts.length?"Select an observed Managed Host"
          :visibleHostComplete===true?"No observed Hosts":"No Hosts observed on this Core page"}</option>}
          {(visibleHosts||[]).map(h=><option value={String(h.id)} key={h.id}>{h.name||h.label||h.id} · {h.id}</option>)}
        </select></label>
        <p className="dr-p0-status">{selected?hostReadinessLabel(selected):visibleHosts===null?"HOST INVENTORY UNKNOWN"
          :visibleHosts.length?"NO HOST SELECTED · select the intended Host"
          :visibleHostComplete===true?"NO HOST OBSERVED · enrollment may still be pending"
          :"NO HOST IN LOADED PAGE · CHECK OTHER CORE PAGES"}</p>
        <div className="dr-p0-counters">
          <span>Admission: {readiness.admission}</span><span>Trust: {readiness.trust}</span>
          <span>Connection: {readiness.connection}</span><span>Last observation: {readiness.observedAt}</span>
          <span>Effective policy reachability: {readiness.policy}</span>
        </div>
        {step===3&&<>
          <p className="muted">Approval restores normal Core policy evaluation; it does not establish trust or a reachable session. Quarantine remains available under Managed Hosts.</p>
          <button className="secondary" disabled={!admin||!matchingHostScope||!selected||busy||fetchBusy} onClick={previewApproval}>Preview approval impact</button>
          {scopedPreview&&<div className="dr-p0-review">
            <p>Authoritative Core plan · valid until {scopedPreview.valid_until||"UNKNOWN"}</p>
            <details><summary>Review exact approval impact</summary><pre className="plan">{JSON.stringify({preview:scopedPreview.preview,impact:scopedPreview.impact},null,2)}</pre></details>
            <label className="dr-field"><span>Type {required} to approve</span><input value={confirm} onChange={e=>setConfirm(e.target.value)} placeholder={required}/></label>
            <button className="danger" disabled={!admin||!matchingHostScope||!approvalActionable||confirm!==required||busy} onClick={applyApproval}>Approve through Core</button>
          </div>}
        </>}
        {step===4&&<>
          <p className="muted">Even CONNECTED · APPROVED · TRUSTED does not prove a policy ALLOW or target TCP reachability. Run a Core access decision trace separately.</p>
          <button className="primary" onClick={()=>onNavigate?.("access","access")}>Verify effective access →</button>
        </>}
        <button className="secondary" disabled={busy||fetchBusy} onClick={()=>onNavigate?.("hosts","infrastructure")}>Open Managed Hosts →</button>
      </div>}
    </div>
    <div className="card"><h3>Enrollment history · Core</h3>
      <div className="dr-p0-table"><table><thead><tr><th>Ticket</th><th>Type</th><th>State</th><th>First-Host admission</th><th>Time remaining</th></tr></thead>
        <tbody>{history.items.map(item=><tr key={item.id}><td>{item.label} · {item.id}</td>
          <td>{item.type}</td><td>{item.state}</td>
          <td>{item.admission}</td><td>{item.remaining}</td></tr>)}</tbody>
      </table></div>
      {history.status==="UNKNOWN"
        ?<p className="warning-box" role="status">Enrollment history: UNKNOWN — Core list is missing, malformed, or incomplete. Refresh the authorized enrollment inventory; an empty list was not confirmed.</p>
        :history.items.length===0
          ?<p className="muted">No enrollment history reported.</p>
          :history.partial&&<p className="muted" role="status">Showing first {history.items.length} of {history.total??"at least 50"} observed enrollments. More records may exist outside this bounded Core page.</p>}
    </div>
  </section>;
}
