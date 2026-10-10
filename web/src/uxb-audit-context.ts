/** Contextual, read-only audit investigation. The Core audit resource filter is
 * an exact entity ID: it does NOT prove entity type, policy authority, reachability
 * or full retention coverage. Never pass arbitrary search/URL/secrets into context.
 */
export type AuditOriginType="managed-host"|"remote-service"|"access-rule";
export type AuditReturnTarget={
 id:"hosts"|"services"|"policies",group:"connections"|"access",
 context:{savedFilter:string,inspectResourceId:string}|{plane:"remote"|"internet"|"ai",inspectPolicyId:string}|undefined
};
export type AuditInvestigation={
 originType:AuditOriginType|null,resource:string,actor:string,category:string,result:string,
 returnTarget:AuditReturnTarget|null
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
 const originType=["managed-host","remote-service","access-rule"].includes(String(ctx.originType))
   ?ctx.originType as AuditOriginType:null;
 const resource=originType?safeIdentifier(ctx.originId):"";
 if(!resource)return {originType:null,resource:"",actor:"",category:"",result:"",returnTarget:null};
 const actor=safeIdentifier(ctx.auditActor);
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
 return {originType,resource,actor,category,result,returnTarget};
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
