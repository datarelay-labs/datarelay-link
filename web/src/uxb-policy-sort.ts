/** G-23: original, read-only display ordering for already loaded Core policy rows.
 * No Core policy priority, effective-access evaluation, server cursor, persistence
 * or authorization changes. Vendor AGPL implementation is NOT imported.
 */
import {observedPolicyDetailFields} from "./uxb-policy-expiry";

export type PolicySortMode="core"|"name_asc"|"name_desc";
export function isPolicySortMode(value:unknown):value is PolicySortMode{
 return value==="core"||value==="name_asc"||value==="name_desc";
}
function observedPolicyNameKey(value:unknown):string|null{
 // One existing Core/public-field projector is the only source of sortable
 // identity facts. It rejects malformed IDs and controls/bidi in names.
 const fields=observedPolicyDetailFields(value);
 const id=fields.find(field=>field.label==="Policy ID")?.value;
 if(!id)return null;
 const name=fields.find(field=>field.label==="Name")?.value;
 return (name&&name!=="UNKNOWN"?name:id).toLowerCase();
}
export function sortLoadedPolicies<T extends Record<string,unknown>>(
 rows:unknown,mode:unknown
):T[]{
 if(!Array.isArray(rows)||!isPolicySortMode(mode))return [];
 // Never sort the Core inventory array in place. Preserve exact default order,
 // and retain each original Core row reference after optional presentation sort.
 const loaded=[...rows] as T[];
 if(mode==="core")return loaded;
 return loaded.map((row,index)=>({row,index,key:observedPolicyNameKey(row)}))
  .sort((a,b)=>{
   if(a.key===null)return b.key===null?a.index-b.index:1;
   if(b.key===null)return -1;
   const comparison=a.key<b.key?-1:a.key>b.key?1:0;
   return comparison===0?a.index-b.index:mode==="name_asc"?comparison:-comparison;
  }).map(({row})=>row);
}
