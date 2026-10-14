/** M1-A original Global Search Core-hit projection and safe navigation intent.
 * A Core search hit is NOT permission to open a record. Destination pages must
 * retrieve their own currently authorized inventory and uniquely match the ID.
 * Never expose nested returned Core item data to rendered Global Search rows.
 */
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}$/;
const TYPE=/^[a-z][a-z0-9-]{0,63}$/;
const CONTROL=/[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/;
const PLANES=new Set(["remote","internet","ai"]);
const CATALOG_TYPES=new Set([
  "network-object","network-group","service-object","service-group",
  "permission-object","permission-group","ai-identity"
]);
const MAX_RETURNED=20;
type NavigationContext={
  savedFilter?:string,inspectResourceId?:string,searchResultKey:string,
  plane?:string,inspectPolicyId?:string
};
export type ObservedCoreSearchDestination={
  id:"hosts"|"services"|"policies"|"objects",
  group:"connections"|"access",exact:boolean,context:NavigationContext|null
};
export type ObservedCoreSearchHit={
  id:string,name:string,resourceType:string,
  destination:ObservedCoreSearchDestination|null
};
export type ObservedGlobalSearchResult={
  items:ObservedCoreSearchHit[],totalCount:number,invalidCount:number,
  scope:"bounded-core-search"
};
function record(value:unknown):Record<string,unknown>|null{
  return value!==null&&typeof value==="object"&&!Array.isArray(value)
    ?value as Record<string,unknown>:null;
}
function safeId(value:unknown):value is string{
  return typeof value==="string"&&ID.test(value);
}
function safeLabel(value:unknown,id:string):string{
  if(typeof value!=="string"||!value.trim()||value.length>160||CONTROL.test(value))return id;
  return value.trim();
}
function destination(entry:Record<string,unknown>,type:string,id:string):
  ObservedCoreSearchDestination|null|undefined{
  const nested=record(entry.item);
  if(type==="managed-host"||type==="remote-service"||type==="access-policy-rule"){
    // invalid/contradictory nested Core identity: reject the hit altogether.
    if(!nested||nested.id!==id)return undefined;
    if(type==="access-policy-rule"){
      if(typeof nested.plane!=="string"||!PLANES.has(nested.plane))return undefined;
      return {id:"policies",group:"access",exact:true,
        context:{plane:nested.plane,inspectPolicyId:id,
          searchResultKey:"policy:"+nested.plane+":"+id}};
    }
    return {id:type==="managed-host"?"hosts":"services",group:"connections",
      exact:true,context:{
        savedFilter:"id:"+id,inspectResourceId:id,
        searchResultKey:(type==="managed-host"?"host:":"service:")+id}};
  }
  // Other supported Core inventory nouns have a category browser but no
  // currently validated exact-by-ID drawer contract on their target page.
  if(CATALOG_TYPES.has(type)){
    if(nested&&nested.id!==id)return undefined;
    return {id:"objects",group:"access",exact:false,context:null};
  }
  // Unknown noun families are shown as non-actionable evidence, not guessed
  // into an access/administration screen or confused with policy authority.
  return null;
}
export function projectObservedGlobalSearchResults(input:unknown):
  ObservedGlobalSearchResult|null{
  if(!Array.isArray(input)||input.length>MAX_RETURNED)return null;
  const items:ObservedCoreSearchHit[]=[];
  let invalidCount=0;
  for(const raw of input){
    const entry=record(raw);
    if(!entry||!safeId(entry.id)||
      typeof entry.resource_type!=="string"||!TYPE.test(entry.resource_type)){
      invalidCount++;continue;
    }
    const target=destination(entry,entry.resource_type,entry.id);
    if(target===undefined){invalidCount++;continue;}
    items.push({
      id:entry.id,name:safeLabel(entry.name,entry.id),
      resourceType:entry.resource_type,destination:target
    });
  }
  return {items,totalCount:input.length,invalidCount,scope:"bounded-core-search"};
}


/** R2.2/M2: Core global_search returns an echo of the submitted trimmed
 * search and a first-20 row limit. Do not present a successful HTTP response
 * for a different query or bound as today's authorized search evidence. */
export function observedBoundedCoreSearchResponse(
  payload:unknown,submittedQuery:string
):ObservedGlobalSearchResult|null{
  const page=record(payload);
  if(!page||typeof submittedQuery!=="string"
    ||!submittedQuery||submittedQuery.length>128
    ||submittedQuery!==submittedQuery.trim()||CONTROL.test(submittedQuery)
    ||page.query!==submittedQuery||page.limit!==20)return null;
  const projection=projectObservedGlobalSearchResults(page.items);
  if(!projection)return null;
  const seen=new Set<string>();
  for(const raw of page.items as unknown[]){
    const item=record(raw);
    if(!item||!safeId(item.id)
      ||typeof item.resource_type!=="string"||!TYPE.test(item.resource_type))
      continue; // Current projector counts malformed individual hits as invalid.
    const key=item.resource_type+":"+item.id;
    if(seen.has(key))return null;
    seen.add(key);
  }
  return projection;
}
