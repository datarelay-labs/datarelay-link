/** M1-B G-21: independently authored, read-only policy card projection.
 * Only already Core-loaded, allowlisted actual policy fields are shown.
 * Configured policy state or expiration never proves live effective access.
 */
import {policyExpiryLabel,policyStateLabel} from "./uxb-menu-evidence";
import {observedPolicyDetailFields,observedPolicyExpiryState} from "./uxb-policy-expiry";
export type ObservedPolicyCard={
  id:string,title:string,plane:string,status:string,
  expiryStatus:string,expiryAt:string,
  facts:Array<{label:string,value:string}>
};
const PLANES:Record<string,string>={remote:"Remote",internet:"Internet",ai:"AI"};
export function observedPolicyCardSummary(row:unknown,asOf:unknown):ObservedPolicyCard|null{
  if(!row||typeof row!=="object"||Array.isArray(row))return null;
  const item=row as Record<string,unknown>;
  if(typeof item.plane!=="string"||
     !Object.prototype.hasOwnProperty.call(PLANES,item.plane))return null;
  const fields=observedPolicyDetailFields(row);
  if(!fields.length)return null;
  const get=(label:string):string=>
    fields.find(field=>field.label===label)?.value||"UNKNOWN";
  const id=get("Policy ID"),name=get("Name");
  const status=policyStateLabel(item.enabled);
  const kind=observedPolicyExpiryState(item,asOf);
  const expiryStatus=kind==="due24h"?"Due within 24h":
    kind==="expired"?"Expired":kind==="later"?"Later":
    kind==="never"?"Never":"UNKNOWN";
  const expiryAt=policyExpiryLabel(item);
  // G-25: explicit AI Core references, not effective authorization assertions.
  // Both kind and ID must already be safe fixed-whitelist scalars; otherwise
  // the entire pair is UNKNOWN. No imported NetBird implementation.
  const reference=(kind:string,value:string):string=>
    kind==="UNKNOWN"||value==="UNKNOWN"?"UNKNOWN":kind+" · "+value;
  const aiReferences=item.plane==="ai"?[
    {label:"Destination reference",
     value:reference(get("Destination kind"),get("Destination ID"))},
    {label:"Permission reference",
     value:reference(get("Permission kind"),get("Permission ID"))}
  ]:[];
  return {
    id,title:name==="UNKNOWN"?id:name,plane:PLANES[item.plane],
    status,expiryStatus,expiryAt,
    facts:[
      {label:item.plane==="ai"?"Source identity":"Action",
       value:get(item.plane==="ai"?"Source identity":"Action")},
      ...aiReferences,
      {label:"Expires",value:expiryAt}
    ]
  };
}
