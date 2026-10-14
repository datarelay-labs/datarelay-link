export type TemporaryAccessRequestStatus="PENDING"|"APPROVED"|"REJECTED"|"EXPIRED"|"REVOKED";
export type ObservedTemporaryAccessRequest={
 id:string,server_id:string,requester_actor_id:string,requester_role:"Admin"|"Operator",
 plane:"remote"|"internet"|"ai",resource_type:string,resource_ref:string,purpose:string,
 requested_duration_seconds:number,approved_duration_seconds:number|null,
 requested_revision:number,status:TemporaryAccessRequestStatus,created_at:string,
 reviewed_at:string|null,reviewer_actor_id:string|null,decision_reason:string,
 approved_expires_at:string|null,applied_revision:number|null,revoked_at:string|null,
 revoked_by_actor_id:string|null,revoked_revision:number|null,row_version:number
};

const idPattern=/^tar_[A-Za-z0-9_-]{16,96}$/;
const forbidden=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const statuses=new Set(["PENDING","APPROVED","REJECTED","EXPIRED","REVOKED"]);
const planes=new Set(["remote","internet","ai"]);

function text(value:unknown,max:number,empty=false):string|null{
 if(typeof value!=="string"||value.length>max||forbidden.test(value))return null;
 const out=value.trim();if(!empty&&!out)return null;return out;
}
function integer(value:unknown,min=0,max=Number.MAX_SAFE_INTEGER):number|null{
 return Number.isSafeInteger(value)&&Number(value)>=min&&Number(value)<=max?Number(value):null;
}
function absoluteTime(value:unknown,nullable=true):string|null|undefined{
 if(value===null&&nullable)return null;
 const out=text(value,64);if(!out)return undefined;
 const parsed=Date.parse(out);
 if(!Number.isFinite(parsed)||!/(?:Z|[+-]\d\d:\d\d)$/.test(out))return undefined;
 return out;
}
function nullableId(value:unknown,max=256):string|null|undefined{
 if(value===null)return null;const out=text(value,max);return out===null?undefined:out;
}

export function observedTemporaryAccessRequest(input:unknown):ObservedTemporaryAccessRequest|null{
 if(!input||typeof input!=="object"||Array.isArray(input))return null;
 const row=input as Record<string,unknown>;
 const id=text(row.id,100),server=text(row.server_id,256),requester=text(row.requester_actor_id,256);
 const role=row.requester_role,plane=row.plane,status=row.status;
 const resourceType=text(row.resource_type,64),resourceRef=text(row.resource_ref,160),purpose=text(row.purpose,500);
 const requested=integer(row.requested_duration_seconds,300,86400),approved=row.approved_duration_seconds===null?null:integer(row.approved_duration_seconds,300,86400);
 const requestedRevision=integer(row.requested_revision),rowVersion=integer(row.row_version,1);
 const created=absoluteTime(row.created_at,false),reviewed=absoluteTime(row.reviewed_at);
 const reviewer=nullableId(row.reviewer_actor_id),reason=text(row.decision_reason,500,true);
 const expiry=absoluteTime(row.approved_expires_at),applied=row.applied_revision===null?null:integer(row.applied_revision);
 const revokedAt=absoluteTime(row.revoked_at),revoker=nullableId(row.revoked_by_actor_id);
 const revokedRevision=row.revoked_revision===null?null:integer(row.revoked_revision);
 if(!id||!idPattern.test(id)||!server||!requester||!["Admin","Operator"].includes(String(role))
   ||!planes.has(String(plane))||resourceType!==String(plane)+"-access-rule"||!resourceRef||!purpose
   ||requested===null||requestedRevision===null||rowVersion===null||!statuses.has(String(status))
   ||created===undefined||reviewed===undefined||reviewer===undefined||reason===null||expiry===undefined
   ||applied===null&&row.applied_revision!==null||revokedAt===undefined||revoker===undefined
   ||revokedRevision===null&&row.revoked_revision!==null)return null;
 if(approved!==null&&approved>requested)return null;
 if(["APPROVED","EXPIRED","REVOKED"].includes(String(status))
   &&(approved===null||expiry===null||applied===null||reviewed===null||reviewer===null))return null;
 if(status==="REJECTED"&&(reviewed===null||reviewer===null))return null;
 if(status==="REVOKED"&&(revokedAt===null||revoker===null||revokedRevision===null))return null;
 return {
  id,server_id:server,requester_actor_id:requester,requester_role:role as "Admin"|"Operator",
  plane:plane as "remote"|"internet"|"ai",resource_type:resourceType,resource_ref:resourceRef,purpose,
  requested_duration_seconds:requested,approved_duration_seconds:approved,
  requested_revision:requestedRevision,status:status as TemporaryAccessRequestStatus,created_at:created,
  reviewed_at:reviewed,reviewer_actor_id:reviewer,decision_reason:reason,
  approved_expires_at:expiry,applied_revision:applied,revoked_at:revokedAt,
  revoked_by_actor_id:revoker,revoked_revision:revokedRevision,row_version:rowVersion
 };
}

export function observedTemporaryAccessRequestPage(input:unknown):{items:ObservedTemporaryAccessRequest[],next_cursor:string|null,limit:number}|null{
 if(!input||typeof input!=="object"||Array.isArray(input))return null;
 const page=input as Record<string,unknown>,limit=integer(page.limit,1,100);
 if(limit===null||!Array.isArray(page.items)||page.items.length>limit)return null;
 const items=page.items.map(observedTemporaryAccessRequest);
 if(items.some(x=>x===null))return null;
 const cursor=page.next_cursor===null?null:text(page.next_cursor,512);
 if(cursor===null&&page.next_cursor!==null)return null;
 return {items:items as ObservedTemporaryAccessRequest[],next_cursor:cursor,limit};
}

export function temporaryAccessRequesterIsActor(row:ObservedTemporaryAccessRequest,operatorId:unknown):boolean{
 return typeof operatorId==="string"&&!!operatorId&&row.requester_actor_id==="web:"+operatorId;
}
export function temporaryAccessCanReview(row:ObservedTemporaryAccessRequest,operator:{id?:unknown,role?:unknown}):boolean{
 return operator?.role==="Admin"&&row.status==="PENDING"&&!temporaryAccessRequesterIsActor(row,operator?.id);
}
export function temporaryAccessCanRevoke(row:ObservedTemporaryAccessRequest,operator:{id?:unknown,role?:unknown}):boolean{
 return row.status==="APPROVED"&&(operator?.role==="Admin"||temporaryAccessRequesterIsActor(row,operator?.id));
}
export function temporaryAccessDurationLabel(seconds:number|null):string{
 if(seconds===null)return "—";if(seconds%3600===0)return String(seconds/3600)+"h";return String(seconds/60)+"m";
}
