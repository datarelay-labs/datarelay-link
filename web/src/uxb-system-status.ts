/** M2/R4: Product-owned read-only Core System status projection.
 * Do not pass arbitrary nested Core values into Foundation/Admin JSX, input
 * defaults, release/backup tools or a privileged Web control's availability.
 * The authoritative Core session/CSRF/role and confirmation checks are NOT
 * affected by this display-only projection.
 */
const BAD=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const record=(value:unknown):value is Record<string,any>=>
  value!==null&&typeof value==="object"&&!Array.isArray(value);
const label=(value:unknown,max=160):string=>
  typeof value==="string"&&value.length>0&&value.length<=max&&!BAD.test(value)
    ?value:"UNKNOWN";
const field=(value:unknown,max=160):string=>
  typeof value==="string"&&value.length<=max&&!BAD.test(value)?value:"";
const flag=(value:unknown):boolean|undefined=>
  typeof value==="boolean"?value:undefined;
const CERT_MODES=new Set(["AUTO_ACME","USER_CERTIFICATE","PRIVATE_CA"]);
const KNOWN_ENV=new Set(["PRODUCTION","STAGING"]);
const hostname=(value:unknown):string=>
  typeof value==="string"&&value.length<=253
    &&/^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(value)?value:"";

export function observedCoreSystemStatus(input:unknown):Record<string,any>|null{
  if(!record(input)||input.read_only!==true||input.side_effect_free!==true
    ||!record(input.identity)||!record(input.certificate)||!record(input.backup)
    ||!record(input.support_bundle)||!record(input.update))return null;
  const id=input.identity,c=input.certificate,b=input.backup,
    support=input.support_bundle,u=input.update;
  const mode=typeof c.mode==="string"&&CERT_MODES.has(c.mode)?c.mode:"UNKNOWN";
  const environment=typeof c.acme_environment==="string"&&KNOWN_ENV.has(c.acme_environment)
    ?c.acme_environment:"UNKNOWN";
  const sourceHead=typeof id.source_head==="string"&&/^[0-9a-f]{40}$/.test(id.source_head)
    ?id.source_head:"UNKNOWN";
  const digest=typeof id.bundle_sha256==="string"
    &&(/^[0-9a-f]{64}$/.test(id.bundle_sha256)||id.bundle_sha256==="")
    ?id.bundle_sha256:"";
  const toolAvailable=(v:unknown):boolean|undefined=>flag(v);
  const productMode=u.product_apply_mode==="QUEUED_EXACT_BUILD"?"QUEUED_EXACT_BUILD":"UNKNOWN";
  const productApply=productMode==="QUEUED_EXACT_BUILD"?toolAvailable(u.product_apply_via_web):undefined;
  const days=typeof c.days_remaining==="number"&&Number.isSafeInteger(c.days_remaining)
    &&c.days_remaining>=-36500&&c.days_remaining<=36500?c.days_remaining:"UNKNOWN";
  return {
    read_only:true,side_effect_free:true,
    identity:{
      display_identity:label(id.display_identity),project_version:label(id.project_version),
      relay_engine_version:label(id.relay_engine_version),channel:label(id.channel),
      source_ref:label(id.source_ref),source_head:sourceHead,bundle_sha256:digest,
    },
    certificate:{
      mode,hostname:hostname(c.hostname),certificate:label(c.certificate),
      issuer:label(c.issuer),expires:label(c.expires),days_remaining:days,
      auto_renewal:flag(c.auto_renewal)??"UNKNOWN",
      contact_email:field(c.contact_email,160),acme_environment:environment,
    },
    backup:{
      directory:"/var/lib/drlink/backups",
      directory_present:flag(b.directory_present),
      create_available:toolAvailable(b.create_available),
      validate_available:toolAvailable(b.validate_available),
      restore_available:toolAvailable(b.restore_available),
    },
    support_bundle:{
      directory:support.directory==="/var/lib/drlink/support-bundles"
        ?support.directory:"UNKNOWN",
      sanitized:flag(support.sanitized),
      create_available:support.sanitized===true?toolAvailable(support.create_available):undefined,
      directory_present:flag(support.directory_present),
    },
    update:{
      product_check_available:toolAvailable(u.product_check_available),
      product_apply_via_web:productApply,product_apply_mode:productMode,
      engine_check_available:toolAvailable(u.engine_check_available),
      engine_apply_via_web:toolAvailable(u.engine_apply_via_web),
    }
  };
}
