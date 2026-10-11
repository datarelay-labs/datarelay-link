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
/** Service Account expiry is an observed instant, never a browser-local guess.
 * Date.parse alone silently normalizes impossible dates such as February 31.
 * Preserve Core's absolute timestamp only after strict calendar/offset proof.
 */
export function isObservedAbsoluteTime(text:unknown):text is string{
 if(typeof text!=="string"||text.length>80||BANNED.test(text))return false;
 const m=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/.exec(text);
 if(!m)return false;
 const year=Number(m[1]),month=Number(m[2]),day=Number(m[3]);
 const hours=Number(m[4]),minutes=Number(m[5]),seconds=Number(m[6]);
 const leap=year%4===0&&(year%100!==0||year%400===0);
 const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
 if(year<1||month<1||month>12||day<1||day>days[month-1]||
   hours>23||minutes>59||seconds>59)return false;
 const offset=m[8];
 if(offset!=="Z"&&(Number(offset.slice(1,3))>23||Number(offset.slice(4,6))>59))return false;
 return Number.isFinite(Date.parse(text));
}
export function serviceAccountExpiry(value:unknown):string{
 const data=row(value);
 if(!Object.prototype.hasOwnProperty.call(data,"expires_at"))return "UNKNOWN";
 const v=data.expires_at;
 if(v===null||v==="")return "No expiry";
 if(!isObservedAbsoluteTime(v))return "UNKNOWN";
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
