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
 if(offset!=="Z"){
  const hours=Number(offset.slice(1,3)),minutes=Number(offset.slice(4,6));
  // Date.parse accepts impossible UTC offsets; Core observation time must not.
  if(hours>14||minutes>59||(hours===14&&minutes!==0))return false;
 }
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
/** An enabled flag is not an active credential when Core's expiry has
 * already passed. This projection never rotates/revokes credentials itself.
 * Missing or malformed expiry is UNKNOWN, not silently "Active".
 */
export function serviceAccountOperationalStatus(
 value:unknown,at:number=Date.now()
):"Active"|"Expired"|"Revoked"|"UNKNOWN"{
 const base=serviceAccountStatus(value);
 if(base!=="Active")return base;
 const account=row(value);
 if(!Object.prototype.hasOwnProperty.call(account,"expires_at"))return "UNKNOWN";
 const expiry=account.expires_at;
 if(expiry===null||expiry==="")return "Active";
 if(!isObservedAbsoluteTime(expiry)||!Number.isFinite(at))return "UNKNOWN";
 return Date.parse(expiry)<=at?"Expired":"Active";
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


/** R4 native Webhook outbox snapshot: Core DELIVERED means only remote
 * HTTP 2xx accepted by the transport; receiver processing is never proven.
 * Counts are retained outbox records, not fresh live health or totals over
 * all historical events (Core may prune terminal rows). Invalid/absent
 * evidence is UNKNOWN and never an all-healthy zero.
 */
export type ObservedWebhookDeliveryPulse={
 state:"UNKNOWN"|"NO_EVENTS_OBSERVED"|"QUEUED_OR_SENDING"|
       "FAILURE_RECORDED"|"HTTP_ACKNOWLEDGED_ONLY",
 pending:number|null,sending:number|null,delivered:number|null,failed:number|null
};
export function observedWebhookDeliveryPulse(value:unknown):ObservedWebhookDeliveryPulse{
 const counts=observedCounts(row(value).delivery_counts);
 if(!counts||Object.values(counts).some(n=>n>1000000)
   ||Object.values(counts).reduce((a,b)=>a+b,0)>1000000)
   return {state:"UNKNOWN",pending:null,sending:null,delivered:null,failed:null};
 const pending=counts.PENDING||0,sending=counts.SENDING||0,
   delivered=counts.DELIVERED||0,failed=counts.FAILED||0;
 const state=failed>0?"FAILURE_RECORDED":
   pending+sending>0?"QUEUED_OR_SENDING":
   delivered>0?"HTTP_ACKNOWLEDGED_ONLY":"NO_EVENTS_OBSERVED";
 return {state,pending,sending,delivered,failed};
}

/** M2 read-only Admin Integration inventory: Core currently returns up to
 * 200 accounts/hooks without a pagination cursor. Only fixed validated public
 * fields may reach JSX; a malformed list is UNKNOWN, never a confirmed zero.
 * This is not an Admin privilege check; Core Web API enforces that boundary.
 */
const INTEGRATION_EVENTS=new Set([
 "attention","security.lifecycle","policy.change","managed_host.lifecycle"
]);
const ACCOUNT_ID=/^msa_[0-9a-f]{24}$/,WEBHOOK_ID=/^wh_[0-9a-f]{24}$/;
function validPublicName(value:unknown):value is string{
 return typeof value==="string"&&!!value.trim()&&value.length<=128
   &&!BANNED.test(value);
}
function validPublicEndpoint(value:unknown):value is string{
 if(typeof value!=="string"||value.length>2048||BANNED.test(value))return false;
 try{
   const endpoint=new URL(value);
   const host=endpoint.hostname.toLowerCase(),parts=host.split(".");
   const dnsLabel=/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
   return endpoint.protocol==="https:"&&!!host&&host.length<=253
     &&parts.length>=2&&parts.every(x=>dnsLabel.test(x))
     &&!/^\d+(?:\.\d+){3}$/.test(host)
     &&(endpoint.port===""||endpoint.port==="443")
     &&!endpoint.username&&!endpoint.password
     &&!endpoint.search&&!endpoint.hash;
 }catch{return false}
}
function observedCounts(input:unknown):Record<string,number>|undefined{
 if(!input||typeof input!=="object"||Array.isArray(input))return undefined;
 const data=input as Record<string,unknown>,result:Record<string,number>={};
 for(const [key,value] of Object.entries(data)){
   if(!DELIVERY_STATUSES.includes(key as typeof DELIVERY_STATUSES[number])
     ||typeof value!=="number"||!Number.isSafeInteger(value)||value<0)return undefined;
   result[key]=value;
 }
 return result;
}
export function observedIntegrationInventory(
 kind:unknown,input:unknown
):Record<string,unknown>[]|null{
 if((kind!=="service-accounts"&&kind!=="webhooks")
    ||!Array.isArray(input)||input.length>200)return null;
 const seen=new Set<string>(),result:Record<string,unknown>[]=[];
 for(const raw of input){
   if(!raw||typeof raw!=="object"||Array.isArray(raw))return null;
   const entry=raw as Row;
   const id=entry.id;
   if(typeof id!=="string"
     ||!(kind==="service-accounts"?ACCOUNT_ID:WEBHOOK_ID).test(id)
     ||seen.has(id)||!validPublicName(entry.name))return null;
   seen.add(id);
   const enabled=knownBool(entry.enabled);
   if(kind==="service-accounts"){
     if(!Array.isArray(entry.permissions)||entry.permissions.length<1
       ||entry.permissions.length>PERMISSIONS.size
       ||entry.permissions.some(p=>typeof p!=="string"||!PERMISSIONS.has(p))
       ||new Set(entry.permissions).size!==entry.permissions.length)return null;
     // Invalid/non-observed flags and expiry never enable a management action.
     const expires=entry.expires_at===null||entry.expires_at===""
       ?entry.expires_at:isObservedAbsoluteTime(entry.expires_at)
         ?entry.expires_at:undefined;
     result.push({id,name:entry.name,permissions:[...entry.permissions],
       enabled:enabled===null?undefined:enabled,expires_at:expires});
   }else{
     if(!validPublicEndpoint(entry.url)||!Array.isArray(entry.event_classes)
       ||entry.event_classes.length<1||entry.event_classes.length>INTEGRATION_EVENTS.size
       ||entry.event_classes.some(c=>typeof c!=="string"||!INTEGRATION_EVENTS.has(c))
       ||new Set(entry.event_classes).size!==entry.event_classes.length)return null;
     result.push({id,name:entry.name,url:entry.url,
       event_classes:[...entry.event_classes],
       enabled:enabled===null?undefined:enabled,
       delivery_counts:observedCounts(entry.delivery_counts)});
   }
 }
 return result;
}
