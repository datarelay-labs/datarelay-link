/** Derived Web integration inventory UI facts, not token/secret authority. */
type Row=Record<string,unknown>;
const PERMISSIONS=new Set([
 "management-read","management-diagnose","management-policy-test","management-job-observe"
]);
const DELIVERY_STATUSES=["PENDING","SENDING","DELIVERED","FAILED"] as const;
const BANNED=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
function row(value:unknown):Row{
 return value!==null&&typeof value==="object"&&!Array.isArray(value)
   ?value as Row:{};
}
function knownBool(value:unknown):boolean|null{
 if(value===true||value===1)return true;
 if(value===false||value===0)return false;
 return null;
}
export function serviceAccountStatus(value:unknown):"Active"|"Revoked"|"UNKNOWN"{
 const v=knownBool(row(value).enabled);
 return v===true?"Active":v===false?"Revoked":"UNKNOWN";
}
export function webhookStatus(value:unknown):"Enabled"|"Disabled"|"UNKNOWN"{
 const v=knownBool(row(value).enabled);
 return v===true?"Enabled":v===false?"Disabled":"UNKNOWN";
}
export function serviceAccountExpiry(value:unknown):string{
 const data=row(value);
 if(!Object.prototype.hasOwnProperty.call(data,"expires_at"))return "UNKNOWN";
 const v=data.expires_at;
 if(v===null||v==="")return "No expiry";
 if(typeof v!=="string"||v.length>80||BANNED.test(v)
  ||! /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(v) || !Number.isFinite(Date.parse(v)))
   return "UNKNOWN";
 return v;
}
export function serviceAccountPermissions(value:unknown):string{
 const perms=row(value).permissions;
 if(!Array.isArray(perms))return "UNKNOWN";
 if(perms.length===0)return "none reported";
 if(perms.length>8||perms.some(p=>typeof p!=="string"||!PERMISSIONS.has(p)))return "UNKNOWN";
 return [...new Set(perms)].join(", ");
}
export function webhookDeliverySummary(value:unknown):string{
 const data=row(value).delivery_counts;
 if(data===null||typeof data!=="object"||Array.isArray(data))return "UNKNOWN";
 const counts=data as Row;
 const keys=Object.keys(counts);
 if(keys.some(k=>!DELIVERY_STATUSES.includes(k as any)
    ||typeof counts[k]!=="number"||!Number.isSafeInteger(counts[k])||Number(counts[k])<0))
   return "UNKNOWN";
 const presented=DELIVERY_STATUSES.filter(k=>k in counts);
 return presented.length?presented.map(k=>k+":"+counts[k]).join(" · "):"none reported";
}
