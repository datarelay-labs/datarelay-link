/** Bounded Core impact evidence for UI presentation only. This module never
 * authorizes or changes a policy; Core Change Plans remain authoritative.
 */
export function observedCoreFlag(value:unknown):"YES"|"NO"|"UNKNOWN"{
  return value===true?"YES":value===false?"NO":"UNKNOWN";
}
export function observedCoreCount(value:unknown):number|"UNKNOWN"{
  return typeof value==="number"&&Number.isSafeInteger(value)&&value>=0?value:"UNKNOWN";
}
export function observedCoreNames(value:unknown):string{
  if(!Array.isArray(value))return "UNKNOWN";
  if(!value.length)return "none reported";
  // Affected-rule/Host names are read-only evidence: reject controls and
  // bidi overrides before presenting them as an apparently trusted list.
  const bad=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
  if(value.some(item=>typeof item!=="string"||!item.trim()||item.length>160||bad.test(item)))
    return "UNKNOWN";
  const first=value.slice(0,8);
  return value.length>8?"first 8 of "+value.length+" reported: "+first.join(", "):first.join(", ");
}
