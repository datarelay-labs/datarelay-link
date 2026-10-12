/** Read-only UI projection of Core-backed Web operator flags.
 * This module does not change MFA/session/permission behavior.
 */
import {isObservedAbsoluteTime} from "./uxb-integrations-state";
type User=Record<string,unknown>;
const BANNED=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/g;
function row(value:unknown):User{
 return value!==null&&typeof value==="object"&&!Array.isArray(value)
   ?value as User:{};
}
function observedBool(value:unknown):boolean|null{
 if(value===true||value===1)return true;
 if(value===false||value===0)return false;
 return null;
}
export function operatorAccountState(value:unknown):"Enabled"|"Disabled"|"UNKNOWN"{
 const enabled=observedBool(row(value).enabled);
 return enabled===true?"Enabled":enabled===false?"Disabled":"UNKNOWN";
}
export function operatorMfaState(value:unknown):"Enabled"|"Setup pending"|"Disabled"|"UNKNOWN"{
 const user=row(value);
 const required=observedBool(user.mfa_required),
   enrolled=observedBool(user.mfa_enrolled);
 if(required===null||enrolled===null)return "UNKNOWN";
 if(!required)return enrolled?"UNKNOWN":"Disabled";
 return enrolled?"Enabled":"Setup pending";
}
/** A missing/ambiguous MFA state may not become an implicit toggle target.
 * Only a known identified Core operator yields an actionable intent.
 */
export function operatorMfaAction(value:unknown):{
  required:boolean|null,label:string
}{
 const user=row(value);
 const id=user.id, role=user.role, status=operatorMfaState(user);
 if(typeof id!=="string"||!id.trim()||id.length>160||
  /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/.test(id)||
  !["Admin","Operator","Read Only"].includes(String(role))||status==="UNKNOWN")
   return {required:null,label:"MFA status UNKNOWN"};
 const required=observedBool(user.mfa_required);
 if(required===null)return {required:null,label:"MFA status UNKNOWN"};
 return required?{required:false,label:"Disable MFA"}:
   {required:true,label:"Enable MFA"};
}
/** Display-only label; the authoritative MFA target stays the exact Core ID. */
export function operatorUserLabel(value:unknown):string{
 const name=row(value).username;
 if(typeof name!=="string")return "UNKNOWN";
 const visible=name.replace(BANNED," ").trim().slice(0,100);
 return visible||"UNKNOWN";
}
export function operatorLastLogin(value:unknown):string{
 const user=row(value);
 if(Object.prototype.hasOwnProperty.call(user,"last_login_at")&&user.last_login_at===null)
   return "Never";
 return isObservedAbsoluteTime(user.last_login_at)?user.last_login_at:"UNKNOWN";
}


/** M2 authenticated Web operator inventory: use only Core's fixed public
 * projected fields, not arbitrary session/MFA secret material in HTTP JSON.
 * Core still owns Admin RBAC and all MFA/session writes.
 */
const CORE_OPERATOR_ID=/^wop_[0-9a-f]{24}$/;
const CORE_OPERATOR_NAME=/^[A-Za-z][A-Za-z0-9._-]{0,63}$/;
const CORE_OPERATOR_ROLES=new Set(["Admin","Operator","Read Only"]);
function validOperatorName(name:unknown):name is string{
 return typeof name==="string"&&CORE_OPERATOR_NAME.test(name);
}
export function observedOperatorInventory(input:unknown):Record<string,unknown>[]|null{
 // Core currently exposes all user rows, not a cursor or a known global count.
 // Refuse an oversized/unverified response rather than render thousands of
 // possible attacker-supplied rows or claim a false empty list.
 if(!Array.isArray(input)||input.length>500)return null;
 const ids=new Set<string>(),names=new Set<string>(),rows:Record<string,unknown>[]=[];
 for(const raw of input){
   if(!raw||typeof raw!=="object"||Array.isArray(raw))return null;
   const entry=raw as User,id=entry.id,username=entry.username,role=entry.role;
   if(typeof id!=="string"||!CORE_OPERATOR_ID.test(id)
     ||!validOperatorName(username)
     ||typeof role!=="string"||!CORE_OPERATOR_ROLES.has(role)
     ||ids.has(id)||names.has(username.toLowerCase()))return null;
   ids.add(id);names.add(username.toLowerCase());
   const enabled=observedBool(entry.enabled),
     required=observedBool(entry.mfa_required),
     enrolled=observedBool(entry.mfa_enrolled),
     recovery=observedBool(entry.recovery_admin);
   const lastLogin=entry.last_login_at===null?null:
     isObservedAbsoluteTime(entry.last_login_at)?entry.last_login_at:undefined;
   rows.push({id,username,role,enabled:enabled===null?undefined:enabled,
     recovery_admin:recovery===null?undefined:recovery,
     mfa_required:required===null?undefined:required,
     mfa_enrolled:enrolled===null?undefined:enrolled,
     last_login_at:lastLogin});
 }
 return rows;
}

export type ObservedOperatorMfaReceipt={
 operator_id:string,mfa_required:boolean,changed:boolean,sessions_revoked:number
};
export function observedOperatorMfaReceipt(
 input:unknown,requestedId:unknown,requestedRequired:unknown
):ObservedOperatorMfaReceipt|null{
 if(!input||typeof input!=="object"||Array.isArray(input)
   ||typeof requestedId!=="string"||!CORE_OPERATOR_ID.test(requestedId)
   ||typeof requestedRequired!=="boolean")return null;
 const value=input as User;
 if(value.operator_id!==requestedId
   ||!validOperatorName(value.username)
   ||value.mfa_required!==requestedRequired
   ||typeof value.mfa_enrolled!=="boolean"
   ||typeof value.changed!=="boolean"
   ||(value.changed===true&&value.mfa_enrolled!==false)
   ||!Number.isSafeInteger(value.sessions_revoked)
   ||Number(value.sessions_revoked)<0
   ||(value.changed===false&&value.sessions_revoked!==0))return null;
 return {operator_id:requestedId,mfa_required:requestedRequired,
   changed:value.changed,sessions_revoked:value.sessions_revoked as number};
}


/** Local Web User creation is default-MFA-OFF; only the canonical Core
 * operator ID/name/role response may unlock a product UI "created" state.
 * This does not prove authentication or authorize a newly minted role.
 */
export function observedOperatorCreateReceipt(
 input:unknown,request:unknown
):{operator_id:string,username:string,role:string}|null{
 if(!input||typeof input!=="object"||Array.isArray(input)
   ||!request||typeof request!=="object"||Array.isArray(request))return null;
 const response=input as User,desired=request as User,
   name=typeof desired.username==="string"?desired.username.trim():"";
 if(!validOperatorName(name)||typeof desired.role!=="string"
   ||!CORE_OPERATOR_ROLES.has(desired.role)
   ||typeof response.operator_id!=="string"||!CORE_OPERATOR_ID.test(response.operator_id)
   ||response.username!==name||response.role!==desired.role
   ||response.mfa_required!==false||response.mfa_enrolled!==false)return null;
 return {operator_id:response.operator_id,username:name,role:desired.role};
}
