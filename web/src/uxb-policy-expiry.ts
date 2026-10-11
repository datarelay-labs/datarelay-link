/** M1-B G-20: original read-only policy expiry triage and visible-field search.
 * Uses canonical Core expiry/status projections. Never infers reviewer approval,
 * live access, session reachability or enforcement from configured timestamps.
 */
import {policyExpiryLabel,policyStateLabel} from "./uxb-menu-evidence";

export type PolicyExpiryBucket="expired"|"due24h"|"later"|"never"|"unknown";
export type PolicyExpiryChoice="all"|PolicyExpiryBucket;
export type VisiblePolicySearch={
  items:Record<string,unknown>[],scope:"loaded-only",loadedCount:number,error:string|null
};
export type LoadedExpiryCounts={
  loadedCount:number,expired:number,due24h:number,later:number,
  never:number,unknown:number,asOf:number
};
const EXPIRY=new Set(["all","expired","due24h","later","never","unknown"]);
const DAY=24*60*60*1000;
const BAD=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const TEXT_KEYS=["id","name","description","plane","action"] as const;
const isRow=(row:unknown):row is Record<string,unknown>=>
  row!==null&&typeof row==="object"&&!Array.isArray(row);
const validTime=(at:unknown):at is number=>
  typeof at==="number"&&Number.isSafeInteger(at)&&at>=0&&at<8_000_000_000_000_000;
export function observedPolicyExpiryState(row:unknown,at:unknown):PolicyExpiryBucket{
  if(!validTime(at)||!isRow(row))return "unknown";
  const observed=policyExpiryLabel(row);
  if(observed==="UNKNOWN")return "unknown";
  if(observed==="Never")return "never";
  const time=Date.parse(observed);
  if(!Number.isFinite(time))return "unknown";
  if(time<=at)return "expired";
  if(time-at<=DAY)return "due24h";
  return "later";
}
export function filterObservedPoliciesByExpiry<T extends Record<string,unknown>>(
  rows:unknown,choice:unknown,at:unknown
):T[]{
  if(!Array.isArray(rows)||!validTime(at)||
     typeof choice!=="string"||!EXPIRY.has(choice))return [];
  return rows.filter((row):row is T=>isRow(row)&&
    (choice==="all"||observedPolicyExpiryState(row,at)===choice));
}
export function observedPolicyExpiryCounts(rows:unknown,at:unknown):LoadedExpiryCounts{
  const counts:LoadedExpiryCounts={loadedCount:0,expired:0,due24h:0,later:0,
    never:0,unknown:0,asOf:validTime(at)?at:0};
  if(!Array.isArray(rows)||!validTime(at))return counts;
  for(const row of rows){
    if(!isRow(row))continue;
    counts.loadedCount++;
    const kind=observedPolicyExpiryState(row,at);
    counts[kind]++;
  }
  return counts;
}
function safeText(value:unknown,max:number):string|null{
  if(typeof value!=="string"||value.length>max||BAD.test(value))return null;
  return value.trim().toLowerCase();
}
export function filterObservedPolicySearch(input:unknown,query:unknown):VisiblePolicySearch{
  const empty=(error:string|null):VisiblePolicySearch=>({
    items:[],scope:"loaded-only",loadedCount:0,error
  });
  if(!Array.isArray(input))return empty("Core policy inventory unavailable. Search not applied.");
  const valid=input.filter(isRow);
  if(typeof query!=="string"||query.length>120||BAD.test(query))return {
    ...empty("Invalid policy search. Use at most 120 safe characters."),
    loadedCount:valid.length
  };
  const normalized=query.trim().toLowerCase();
  if(!normalized)return {items:valid,scope:"loaded-only",loadedCount:valid.length,error:null};
  const items=valid.filter(row=>{
    const observed=TEXT_KEYS.map(key=>safeText(row[key],key==="description"?240:160));
    const expiry=policyExpiryLabel(row);
    const state=policyStateLabel(row.enabled);
    return [...observed,
      expiry==="UNKNOWN"?null:expiry.toLowerCase(),
      state==="UNKNOWN"?null:state.toLowerCase()
    ].some(value=>value?.includes(normalized)??false);
  });
  return {items,scope:"loaded-only",loadedCount:valid.length,error:null};
}


/** Fixed, public Core policy selectors for the existing read-only detail drawer.
 * Never iterate unknown policy keys or print nested payloads, tokens or secrets.
 */
export type ObservedPolicyDetailField={label:string,value:string};
const PUBLIC_DETAIL_FIELDS=[
  ["Policy ID","id"],
  ["Name","name"],
  ["Plane","plane"],
  ["Action","action"],
  ["Position","position"],
  ["State","enabled"],
  ["Expires","expires_at"],
  ["Description","description"],
  ["Revision","row_version"],
  ["Source identity","source_identity_id"],
  ["Destination kind","destination_ref_kind"],
  ["Destination ID","destination_ref_id"],
  ["Permission kind","permission_ref_kind"],
  ["Permission ID","permission_ref_id"]
] as const;
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;
export function observedPolicyDetailFields(value:unknown):ObservedPolicyDetailField[]{
  if(!isRow(value)||typeof value.id!=="string"||!ID.test(value.id))return [];
  const fields:ObservedPolicyDetailField[]=[];
  for(const [label,key] of PUBLIC_DETAIL_FIELDS){
    if(key!=="enabled"&&key!=="expires_at"&&
       !Object.prototype.hasOwnProperty.call(value,key))continue;
    let scalar:string;
    if(key==="enabled")scalar=policyStateLabel(value.enabled);
    else if(key==="expires_at")scalar=policyExpiryLabel(value);
    else if(key==="position"||key==="row_version"){
      const n=value[key];
      scalar=typeof n==="number"&&Number.isSafeInteger(n)&&n>=0?String(n):"UNKNOWN";
    }else{
      const v=value[key];
      scalar=typeof v==="string"&&v.length>0&&v.length<=(key==="description"?240:160)&&
        !BAD.test(v)?v.trim()||"UNKNOWN":"UNKNOWN";
    }
    fields.push({label,value:scalar});
  }
  return fields;
}
