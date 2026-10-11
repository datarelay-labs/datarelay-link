/** Contextual, read-only audit investigation. The Core audit resource filter is
 * an exact entity ID: it does NOT prove entity type, policy authority, reachability
 * or full retention coverage. Never pass arbitrary search/URL/secrets into context.
 */
import {isObservedAbsoluteTime} from "./uxb-integrations-state";

export type AuditOriginType="managed-host"|"remote-service"|"access-rule";
export type AuditReturnTarget={
 id:"hosts"|"services"|"policies",group:"connections"|"access",
 context:{savedFilter:string,inspectResourceId:string}|{plane:"remote"|"internet"|"ai",inspectPolicyId:string}|undefined
};
export type AuditInvestigation={
 originType:AuditOriginType|null,resource:string,actor:string,category:string,result:string,
 start:string,end:string,returnTarget:AuditReturnTarget|null
};
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;
const CATEGORY=new Set(["CONTROL","ACCESS_DECISION","SECURITY_LIFECYCLE"]);
const RESULTS=new Set(["success","deny","denied","failure","error"]);
const PLANE=new Set(["remote","internet","ai"]);
function safeIdentifier(value:unknown):string{
 return typeof value==="string"&&ID.test(value)?value:"";
}
function record(input:unknown):Record<string,unknown>{
 return input!==null&&typeof input==="object"&&!Array.isArray(input)
  ?input as Record<string,unknown>:{};
}
export function auditInvestigation(input:unknown):AuditInvestigation{
 const ctx=record(input);
 const originType=typeof ctx.originType==="string"&&
   ["managed-host","remote-service","access-rule"].includes(ctx.originType)
   ?ctx.originType as AuditOriginType:null;
 const resource=originType?safeIdentifier(ctx.originId):"";
 if(!resource)return {originType:null,resource:"",actor:"",category:"",result:"",
   start:"",end:"",returnTarget:null};
 const actor=safeIdentifier(ctx.auditActor);
 // A corrupted or reversed prefilled Core Audit window is not a search.
 // Preserve only explicit, timezone-qualified, ordered user context; an
 // otherwise valid entity/actor return remains available without that window.
 const parseBound=(value:unknown):string|null=>
   value===null||value===undefined||value===""?""
   :isObservedAbsoluteTime(value)?value:null;
 const first=parseBound(ctx.auditStart),last=parseBound(ctx.auditEnd);
 const validWindow=first!==null&&last!==null&&
   (!first||!last||Date.parse(first)<=Date.parse(last));
 const start=validWindow?first!:"";
 const end=validWindow?last!:"";
 const category=typeof ctx.auditCategory==="string"&&CATEGORY.has(ctx.auditCategory)
   ?ctx.auditCategory:"";
 const result=typeof ctx.auditResult==="string"&&RESULTS.has(ctx.auditResult)
   ?ctx.auditResult:"";
 const plane=typeof ctx.plane==="string"&&PLANE.has(ctx.plane)
  ?ctx.plane as "remote"|"internet"|"ai":null;
 const returnTarget:AuditReturnTarget=originType==="managed-host"
  ?{id:"hosts",group:"connections",context:{savedFilter:"id:"+resource,inspectResourceId:resource}}
  :originType==="remote-service"
    ?{id:"services",group:"connections",context:{savedFilter:"id:"+resource,inspectResourceId:resource}}
    :{id:"policies",group:"access",context:plane?{plane,inspectPolicyId:resource}:undefined};
 return {originType,resource,actor,category,result,start,end,returnTarget};
}


/** UX-5: the Home recent-activity list may open a narrowly scoped
 * read-only Core Audit investigation only when the Core event itself carries
 * an exact supported resource type, validated ID and absolute observation
 * instant. Missing/untrusted data falls back to the unfiltered Audit page.
 * This NEVER infers policy reachability, a new permission or a host edge.
 */
export function recentAuditInvestigation(input:unknown):Record<string,string>|null{
 const entry=record(input);
 const type=entry.resource_type;
 const id=safeIdentifier(entry.resource_id);
 const occurredAt=entry.occurred_at;
 if(typeof type!=="string"||
   !["managed-host","remote-service","access-rule"].includes(type)||
   !id||!isObservedAbsoluteTime(occurredAt))return null;
 return {originType:type,originId:id,
   auditActor:safeIdentifier(entry.actor_id),
   auditCategory:typeof entry.category==="string"&&CATEGORY.has(entry.category)
     ?entry.category:"",
   auditResult:typeof entry.result==="string"&&RESULTS.has(entry.result)
     ?entry.result:"",
   auditStart:occurredAt,auditEnd:occurredAt};
}

/** A resource detail may reopen only from the currently authorized/loaded Core
 * inventory page(s). Never fetch the resource by ID or search an unbounded fleet.
 */
export function matchObservedAuditReturn(loaded:unknown,id:unknown):Record<string,unknown>|null{
 if(!Array.isArray(loaded)||!safeIdentifier(id))return null;
 const matches=loaded.filter((row:unknown)=>{
   const data=record(row);
   return typeof data.id==="string"&&data.id===id;
 });
 return matches.length===1?record(matches[0]):null;
}


/** Exact policy ID and plane must resolve to ONE already authorized Core rule.
 * No cross-plane guessing or privileged rule-by-ID fetch.
 */
export function matchObservedPolicyReturn(
 loaded:unknown,id:unknown,plane:unknown
):Record<string,unknown>|null{
 if(!Array.isArray(loaded)||!safeIdentifier(id)||
   typeof plane!=="string"||!PLANE.has(plane))return null;
 const matches=loaded.filter((entry:unknown)=>{
   const item=record(entry);
   return item.id===id&&item.plane===plane;
 });
 return matches.length===1?record(matches[0]):null;
}


/** CUI-007 — original, bounded Event Details for one authorized loaded Core
 * Audit row. NEVER send back nested actor/session/source/destination payloads,
 * matched-policy blobs, before/after summaries or event secret metadata.
 */
export type ObservedAuditEventDetail={
 eventId:string,occurredAt:string,category:string,eventType:string,actor:string,
 resourceType:string,resourceId:string,result:string,reason:string,
 correlation:string,revisionBefore:string,revisionAfter:string
};
export function observedAuditEventDetails(input:unknown):ObservedAuditEventDetail|null{
 if(!input||typeof input!=="object"||Array.isArray(input))return null;
 const entry=input as Record<string,unknown>;
 const clean=(value:unknown,max=160):value is string=>
   typeof value==="string"&&value.length>0&&value.length<=max
   &&!(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(value));
 const scalar=(value:unknown,max=160):string|null=>
   value===null||value===undefined||value===""?"UNKNOWN":
   clean(value,max)?value.trim():null;
 const id=entry.event_id===null||entry.event_id===undefined
   ?Number.isSafeInteger(entry.row_id)&&Number(entry.row_id)>=0
      ?"legacy:"+entry.row_id:null
   :safeIdentifier(entry.event_id);
 if(!id||!isObservedAbsoluteTime(entry.occurred_at)
   ||typeof entry.category!=="string"||!CATEGORY.has(entry.category)
   ||!clean(entry.event_type,160)||!clean(entry.result,64))return null;
 const actor=scalar(entry.actor_id),resourceType=scalar(entry.resource_type),
   resourceId=entry.resource_id===null||entry.resource_id===undefined
     ?"UNKNOWN":safeIdentifier(entry.resource_id),
   reason=scalar(entry.reason_code),correlation=scalar(entry.correlation_id);
 if(!actor||!resourceType||!resourceId||!reason||!correlation
   ||!clean(resourceType,160))return null;
 const rev=(value:unknown):string|null=>
   value===null||value===undefined?"UNKNOWN":
   Number.isSafeInteger(value)&&Number(value)>=0?String(value):null;
 const before=rev(entry.revision_before),after=rev(entry.revision_after);
 if(before===null||after===null)return null;
 return {eventId:id,occurredAt:entry.occurred_at,category:entry.category,
   eventType:entry.event_type.trim(),actor,resourceType,resourceId,
   result:entry.result.trim(),reason,correlation,
   revisionBefore:before,revisionAfter:after};
}

/** Show the filters of the successfully loaded Core query — never present
 * edited-but-unsent input as the provenance for already rendered audit rows.
 * The input is the exact prior safe URLSearchParams query, no secret URL.
 */
export function observedAuditAppliedFilters(input:unknown):{
 label:string,value:string
}[]|null{
 if(typeof input!=="string"||!input||input.length>2048)return null;
 const query=new URLSearchParams(input);
 const names=["start","end","category","event_type","actor","resource","result","correlation_id"];
 const keys=new Set([...names,"limit"]);
 for(const [key] of query){
   if(!keys.has(key)||query.getAll(key).length!==1)return null;
 }
 if(query.get("limit")!=="50")return null;
 const clean=(v:string):boolean=>v.length>0&&v.length<=160
   &&!(/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(v));
 const labels=["Start UTC","End UTC","Category","Event type","Actor","Resource","Result","Correlation ID"];
 const rows:{label:string,value:string}[]=[];
 for(let i=0;i<names.length;i++){
   const raw=query.get(names[i]);if(raw===null)continue;
   if(!clean(raw)||((names[i]==="start"||names[i]==="end")
      &&!isObservedAbsoluteTime(raw)))return null;
   if(names[i]==="category"&&!CATEGORY.has(raw))return null;
   rows.push({label:labels[i],value:raw});
 }
 const first=query.get("start"),last=query.get("end");
 if(first&&last&&Date.parse(first)>Date.parse(last))return null;
 return rows;
}
