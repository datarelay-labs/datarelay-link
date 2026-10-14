/** Read-only remote Service facets over an exact authorized Core-loaded page.
 * UI-only config state != online Agent, live tunnel or actual access grant.
 */
import {serviceStateLabel} from "./uxb-service-detail";

export type ServiceTypeFacet="all"|"ssh"|"http"|"https"|"tcp"|"unknown";
export type ServiceConfigFacet="all"|"enabled"|"disabled"|"released"|"unknown";
export type LoadedServiceFacetResult={
  items:Record<string,unknown>[],scope:"loaded-only",loadedCount:number,
  invalidCount:number,unknownTypeCount:number,unknownStateCount:number,
  error:string|null
};
const TYPES=new Set(["ssh","http","https","tcp"]);
const TYPE_FILTERS=new Set(["all",...TYPES,"unknown"]);
const STATE_FILTERS=new Set(["all","enabled","disabled","released","unknown"]);

function observedType(row:Record<string,unknown>):string{
  const type=row.service_type;
  // Anything that does not exactly match a supported Core field remains UNKNOWN,
  // not proof that the underlying transport is disabled or unreachable.
  return typeof type==="string"&&TYPES.has(type)?type:"unknown";
}
function observedState(row:Record<string,unknown>):string{
  return serviceStateLabel(row).toLowerCase();
}
export function filterLoadedServiceFacets(
  source:unknown,typeChoice:unknown,configurationChoice:unknown
):LoadedServiceFacetResult{
  const absent:LoadedServiceFacetResult={
    items:[],scope:"loaded-only",loadedCount:0,invalidCount:0,
    unknownTypeCount:0,unknownStateCount:0,error:null
  };
  if(!Array.isArray(source))return {...absent,error:"Core Service inventory unavailable; facets not applied."};
  const valid=source.filter((row):row is Record<string,unknown>=>
    row!==null&&typeof row==="object"&&!Array.isArray(row)&&
    typeof row.id==="string"&&!!row.id.trim()&&
    typeof row.name==="string"&&!!row.name.trim());
  const invalidCount=source.length-valid.length;
  const unknownTypeCount=invalidCount+valid.filter(row=>observedType(row)==="unknown").length;
  const unknownStateCount=invalidCount+valid.filter(row=>observedState(row)==="unknown").length;
  const counts={loadedCount:valid.length,invalidCount,unknownTypeCount,unknownStateCount};
  if(typeof typeChoice!=="string"||!TYPE_FILTERS.has(typeChoice)||
     typeof configurationChoice!=="string"||!STATE_FILTERS.has(configurationChoice))
    return {...absent,...counts,error:"Invalid Service type or configuration filter."};
  const items=valid.filter(row=>
    (typeChoice==="all"||observedType(row)===typeChoice)&&
    (configurationChoice==="all"||observedState(row)===configurationChoice));
  return {...absent,...counts,items};
}
