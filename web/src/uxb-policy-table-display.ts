/** M1-B G-29: safe, independent display projection for the default Policy
 * Table. Reuse the exact Core field whitelist G-20 already enforces. No new
 * API, entitlement, policy evaluation, third-party implementation or mutation.
 */
import {observedPolicyDetailFields} from "./uxb-policy-expiry";

export type PolicyTableDisplayCells={
 id:string,name:string,action:string,description:string
};
export function observedPolicyTableDisplayCells(row:unknown):PolicyTableDisplayCells{
 const fields=observedPolicyDetailFields(row);
 const get=(label:string):string=>fields.find(field=>field.label===label)?.value||"UNKNOWN";
 const id=get("Policy ID");
 if(id==="UNKNOWN")return {id:"UNKNOWN",name:"UNKNOWN",action:"UNKNOWN",
   description:"UNKNOWN"};
 const name=get("Name");
 return {
  id,name:name==="UNKNOWN"?id:name,
  action:get("Action"),description:get("Description")
 };
}
