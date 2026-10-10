/** Read-only UI projection of Core-backed Web operator flags.
 * This module does not change MFA/session/permission behavior.
 */
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
  /[\u0000-\u001f\u007f-\u009f]/.test(id)||
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
 if(typeof user.last_login_at!=="string")return "UNKNOWN";
 const cleaned=user.last_login_at.replace(BANNED," ").trim();
 return cleaned?cleaned.slice(0,140):"UNKNOWN";
}
