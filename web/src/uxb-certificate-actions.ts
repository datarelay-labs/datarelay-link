/** M2/R4 — Core certificate mutation receipts projected for public Web
 * display only. This does not authorize issuance, import, ACME traffic,
 * private-key access, recovery, deployment or a privileged Host action.
 * Raw Core nested certificate state and arbitrary errors are never exposed.
 */
type Mode="AUTO_ACME"|"USER_CERTIFICATE"|"PRIVATE_CA";
type Configured={hostname:string,mode:Mode};
type CoreCertificateAction={
 status:"CONFIGURED"|"ISSUED"|"IMPORTED",hostname:string,mode:Mode,
 authoritative_mutation:true,certificate_state:"CORE_REPORTS_VALID"|"UNKNOWN"
};
type CoreCertificateRenewal={
 outcome:"RENEWED"|"NOT_DUE"|"BACKOFF"|"NOT_APPLICABLE"|"DISABLED"|"FRONTEND_REQUIRED"|"FAILED",
 hostname:string,mode:Mode,authoritative_mutation:boolean,
 certificate_state:"CORE_REPORTS_VALID"|"UNKNOWN",failure_class:string
};
const MODES=new Set(["AUTO_ACME","USER_CERTIFICATE","PRIVATE_CA"]);
const HOST=/^[a-z0-9][a-z0-9.-]{0,252}$/;
const CODE=/^[A-Z][A-Z0-9_]{0,63}$/;
const obj=(v:unknown):v is Record<string,any>=>
  v!==null&&typeof v==="object"&&!Array.isArray(v);
function expectCertificate(input:unknown,expected:unknown):{
 hostname:string,mode:Mode,certificate_state:"CORE_REPORTS_VALID"|"UNKNOWN"
}|null{
 if(!obj(input)||!obj(expected)
   ||typeof expected.hostname!=="string"||!HOST.test(expected.hostname)
   ||!MODES.has(expected.mode)
   ||input.hostname!==expected.hostname||input.mode!==expected.mode
   ||!(typeof input.certificate==="string"
     &&input.certificate.length<=64
     &&(CODE.test(input.certificate)||input.certificate===""))
 )return null;
 return {hostname:expected.hostname,mode:expected.mode,
   certificate_state:input.certificate==="VALID"?"CORE_REPORTS_VALID":"UNKNOWN"};
}
/** Exact Core status == requested mutation family plus post-operation
 * hostname/mode identity. Unknown HTTP200 is NOT confirmation. */
export function observedCoreCertificateActionReceipt(
 input:unknown,operation:unknown,expected:unknown
):CoreCertificateAction|null{
 const statuses:{[name:string]:"CONFIGURED"|"ISSUED"|"IMPORTED"}={
  configure:"CONFIGURED",issue:"ISSUED",import:"IMPORTED"
 };
 if(!obj(input)||typeof operation!=="string"
   ||!Object.prototype.hasOwnProperty.call(statuses,operation)
   ||input.status!==statuses[operation]
   ||input.authoritative_mutation!==true)return null;
 const identity=expectCertificate(input.certificate,expected);
 if(!identity)return null;
 if(operation==="issue"&&identity.mode==="USER_CERTIFICATE"
    ||operation==="import"&&identity.mode!=="USER_CERTIFICATE")return null;
 return {status:statuses[operation],...identity,authoritative_mutation:true};
}
/** Core renewal is not always a mutation. Most non-error returns mean
 * not due/backoff/not applicable: they must not be misreported as renewed. */
export function observedCoreCertificateRenewalReceipt(
 input:unknown,expected:unknown
):CoreCertificateRenewal|null{
 if(!obj(input)||typeof input.renewed!=="boolean"
   ||typeof input.reason!=="string"
   ||typeof input.authoritative_mutation!=="boolean")return null;
 const identity=expectCertificate(input.certificate,expected);
 if(!identity)return null;
 const cases:{[name:string]:CoreCertificateRenewal["outcome"]}={
  renewed:"RENEWED",not_due:"NOT_DUE",backoff:"BACKOFF",
  renewal_not_applicable:"NOT_APPLICABLE",
  renewal_disabled:"DISABLED",frontend_required:"FRONTEND_REQUIRED",
  failed:"FAILED"
 };
 const outcome=cases[input.reason];
 if(!outcome)return null;
 if((input.renewed&&outcome!=="RENEWED")
   ||(!input.renewed&&outcome==="RENEWED")
   ||input.authoritative_mutation!==(input.renewed||outcome==="FAILED"))return null;
 const failure=typeof input.failure_class==="string"&&CODE.test(input.failure_class)
   ?input.failure_class:input.failure_class===""||input.failure_class===undefined
   ?"": "UNKNOWN";
 if(outcome==="FAILED"&&failure==="")return null;
 return {...identity,outcome,authoritative_mutation:input.authoritative_mutation,
   failure_class:failure};
}
