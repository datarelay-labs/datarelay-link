/** M2 first-party Link product Web↔Core integration write acknowledgments.
 * Core (not Web) authorizes/mints/stores secrets. A malformed HTTP 200 is an
 * UNKNOWN outcome, not an invitation to create/rotate/revoke again.
 * Response contents are displayed ONLY after exact fixed-schema verification.
 */
type Raw=Record<string,unknown>;
export type ObservedIntegrationReceipt=
 | {status:"secret",kind:"Service Account token"|"Webhook signing secret",id:string,secret:string}
 | {status:"disabled",id:string};
const UNSAFE=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const REFS={
 account:/^msa_[0-9a-f]{24}$/,
 credential:/^msc_[0-9a-f]{24}$/,
 webhook:/^wh_[0-9a-f]{24}$/
};
const SA=/^drlink_sa_[A-Za-z0-9_-]{43}$/;
const WH=/^drlink_wh_[A-Za-z0-9_-]{43}$/;
const RIGHTS=new Set(["management-read","management-diagnose",
  "management-policy-test","management-job-observe"]);
const EVENTS=new Set(["attention","security.lifecycle","policy.change","managed_host.lifecycle"]);
function record(input:unknown):Raw|null{
 return input!==null&&typeof input==="object"&&!Array.isArray(input)
   ?input as Raw:null;
}
function safeName(name:unknown):name is string{
 return typeof name==="string"&&!!name.trim()&&name.length<=128&&!UNSAFE.test(name);
}
function safeRef(kind:keyof typeof REFS,id:unknown):id is string{
 return typeof id==="string"&&REFS[kind].test(id);
}
export function observedIntegrationWriteReceipt(
 path:unknown,request:unknown,response:unknown
):ObservedIntegrationReceipt|null{
 if(typeof path!=="string")return null;
 const body=record(request),received=record(response);
 if(!body||!received)return null;
 if(path==="/api/v1/service-accounts"){
   if(!safeName(body.name)||!Array.isArray(body.permissions)||!body.permissions.length
     ||body.permissions.some(x=>typeof x!=="string"||!RIGHTS.has(x))
     ||received.name!==body.name.trim()
     ||!safeRef("account",received.id)||!safeRef("credential",received.credential_id)
     ||typeof received.credential!=="string"||!SA.test(received.credential))return null;
   return {status:"secret",kind:"Service Account token",
     id:received.id,secret:received.credential};
 }
 if(path==="/api/v1/service-accounts/rotate"){
   if(!safeRef("account",body.account_id)||!safeRef("credential",received.credential_id)
     ||typeof received.credential!=="string"||!SA.test(received.credential))return null;
   // The rotating Service Account API replies with a new credential_id and
   // credential, NOT account_id; bind the result only to the request ID.
   return {status:"secret",kind:"Service Account token",
     id:body.account_id,secret:received.credential};
 }
 if(path==="/api/v1/service-accounts/revoke"){
   if(!safeRef("account",body.account_id)||received.id!==body.account_id
     ||received.enabled!==false)return null;
   return {status:"disabled",id:body.account_id};
 }
 if(path==="/api/v1/webhooks"){
   if(!safeName(body.name)||typeof body.url!=="string"
     ||!body.url.startsWith("https://")||!Array.isArray(body.event_classes)
     ||body.event_classes.length<1||body.event_classes.length>8
     ||body.event_classes.some(x=>typeof x!=="string"||!EVENTS.has(x))
     ||!safeRef("webhook",received.id)
     ||typeof received.secret!=="string"||!WH.test(received.secret))return null;
   return {status:"secret",kind:"Webhook signing secret",
     id:received.id,secret:received.secret};
 }
 if(path==="/api/v1/webhooks/rotate"){
   if(!safeRef("webhook",body.webhook_id)||received.id!==body.webhook_id
     ||typeof received.secret!=="string"||!WH.test(received.secret))return null;
   return {status:"secret",kind:"Webhook signing secret",
     id:received.id,secret:received.secret};
 }
 if(path==="/api/v1/webhooks/disable"){
   if(!safeRef("webhook",body.webhook_id)||received.id!==body.webhook_id
     ||received.enabled!==false)return null;
   return {status:"disabled",id:body.webhook_id};
 }
 return null;
}

/** Account creation accepts browser-local datetime-local input; reject
 * impossible calendar days and DST-normalized wall times before Core receives
 * a canonical UTC value. Blank expiry is explicitly optional.
 */
export function integrationLocalExpiryToUtc(input:unknown):string|null{
 if(input==="")return "";
 if(typeof input!=="string"||UNSAFE.test(input))return null;
 const m=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(input);
 if(!m)return null;
 const date=new Date(input);
 if(!Number.isFinite(date.getTime())
   ||date.getFullYear()!==Number(m[1])||date.getMonth()+1!==Number(m[2])
   ||date.getDate()!==Number(m[3])||date.getHours()!==Number(m[4])
   ||date.getMinutes()!==Number(m[5]))return null;
 return date.toISOString();
}
