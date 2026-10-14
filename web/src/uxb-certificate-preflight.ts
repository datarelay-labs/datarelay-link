/** M2/R4: trustworthy public projection of the already-existing Core
 * certificate/preflight diagnostic. Core runs local DNS and TCP/80 probes,
 * but a successful HTTP response does not by itself prove ACME issuance,
 * external reachability or permission to change TLS settings.
 *
 * No network effect is executed here. Suppress raw DNS addresses, arbitrary
 * warnings/errors and extra nested Core values; show only fixed counts and
 * boolean diagnostic results bound to current Core certificate identity.
 */
export type ObservedCoreCertificatePreflight={
 hostname:string,mode:"AUTO_ACME"|"USER_CERTIFICATE"|"PRIVATE_CA",
 read_only:true,conclusion:"CORE_PREFLIGHT_PASS"|"CORE_PREFLIGHT_ATTENTION",
 dns:"RESOLVED"|"NOT_RESOLVED",private_only:boolean,
 local_port_80:"REACHABLE"|"UNREACHABLE"|"NOT_CHECKED",
 address_count:number,warnings_count:number,errors_count:number
};
const MODES=new Set(["AUTO_ACME","USER_CERTIFICATE","PRIVATE_CA"]);
const HOST=/^[a-z0-9][a-z0-9.-]{0,252}$/;
const IP=/^[0-9a-fA-F:.]{2,45}$/;
function record(value:unknown):value is Record<string,unknown>{
 return value!==null&&typeof value==="object"&&!Array.isArray(value);
}
function boundedStringList(value:unknown,max:number,length:number):value is string[]{
 return Array.isArray(value)&&value.length<=max
   &&value.every(v=>typeof v==="string"&&v.length<=length);
}
export function observedCoreCertificatePreflight(
 input:unknown,expected:unknown
):ObservedCoreCertificatePreflight|null{
 if(!record(input)||!record(expected)
   ||typeof expected.hostname!=="string"||!HOST.test(expected.hostname)
   ||!MODES.has(expected.mode as string)
   ||input.hostname!==expected.hostname||input.mode!==expected.mode
   ||input.authoritative_mutation!==false
   ||typeof input.ok!=="boolean"||typeof input.resolves!=="boolean"
   ||typeof input.private_only!=="boolean"
   ||![true,false,null].includes(input.challenge_port_80_open as boolean|null)
   ||!boundedStringList(input.addresses,100,45)
   ||!(input.addresses as string[]).every(v=>IP.test(v))
   ||!boundedStringList(input.warnings,20,1024)
   ||!boundedStringList(input.errors,20,1024))return null;
 const addresses=input.addresses as string[],warnings=input.warnings as string[],
   errors=input.errors as string[];
 // Inconsistencies are UNKNOWN, not healthy or safely ready to issue.
 if(input.resolves!==Boolean(addresses.length)
   ||(input.challenge_port_80_open===true&&!input.resolves)
   ||(input.ok===true&&errors.length>0)
   ||(input.ok===false&&errors.length===0))return null;
 return {
  hostname:expected.hostname as string,
  mode:expected.mode as ObservedCoreCertificatePreflight["mode"],
  read_only:true,
  conclusion:input.ok?"CORE_PREFLIGHT_PASS":"CORE_PREFLIGHT_ATTENTION",
  dns:input.resolves?"RESOLVED":"NOT_RESOLVED",
  private_only:input.private_only as boolean,
  local_port_80:input.challenge_port_80_open===null?"NOT_CHECKED":
    input.challenge_port_80_open===true?"REACHABLE":"UNREACHABLE",
  address_count:addresses.length,warnings_count:warnings.length,errors_count:errors.length
 };
}
